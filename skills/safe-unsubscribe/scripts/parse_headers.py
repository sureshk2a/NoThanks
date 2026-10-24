#!/usr/bin/env python3
"""Parse message headers into a normalized, privacy-minimal metadata record.

Library use:  analyze(headers, read=None) -> dict
CLI use:      parse_headers.py message.eml [more.eml ...]   (prints JSON)

Only headers are read; message bodies are never parsed or kept.
"""
from __future__ import annotations

import argparse
import email
import email.policy
import json
import os
import re
import sys
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

WANTED = (
    "from", "reply-to", "subject", "date", "list-id", "list-unsubscribe",
    "list-unsubscribe-post", "precedence", "authentication-results", "status",
)

_AUTH_RX = re.compile(r"\b(spf|dkim|dmarc)\s*=\s*(pass|fail|softfail|neutral|none|temperror|permerror|policy)", re.I)
_BAD = {"fail", "softfail", "permerror"}
_DOMAIN_TOKEN = re.compile(r"\b([a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,})\b", re.I)

HIGH_SIGNALS = {"dmarc_fail", "auth_failed", "display_name_spoof", "invalid_unsubscribe_url", "unsupported_scheme"}


# ---------------------------------------------------------------- normalization
def normalize_headers(raw):
    """Accept {name: value|[values]} or [{"name":..,"value":..}] -> {lowercase name: str}."""
    out = {}
    items = raw.items() if isinstance(raw, dict) else ((h.get("name", ""), h.get("value", "")) for h in raw)
    for name, value in items:
        name = str(name).lower()
        if name not in WANTED:
            continue
        values = value if isinstance(value, list) else [value]
        joined = "\n".join(str(v) for v in values)
        out[name] = f"{out[name]}\n{joined}" if name in out else joined
    return out


def normalize_record(obj):
    """Convert an adapter record (generic, Gmail API metadata, or Graph message) to
    (headers dict, read flag or None, fallback datetime string or None)."""
    if "payload" in obj:  # Gmail users.messages.get(format=metadata)
        headers = obj["payload"].get("headers", [])
        labels = obj.get("labelIds")
        read = None if labels is None else "UNREAD" not in labels
        fallback = None
        if obj.get("internalDate"):
            fallback = datetime.fromtimestamp(int(obj["internalDate"]) / 1000, timezone.utc).isoformat()
        return normalize_headers(headers), read, fallback
    if "internetMessageHeaders" in obj:  # Microsoft Graph
        headers = list(obj["internetMessageHeaders"])
        if obj.get("subject"):
            headers.append({"name": "Subject", "value": obj["subject"]})
        return normalize_headers(headers), obj.get("isRead"), obj.get("receivedDateTime")
    return normalize_headers(obj.get("headers", {})), obj.get("read"), obj.get("date")


def parse_date(value):
    """Return an aware UTC datetime or None."""
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# --------------------------------------------------------------- authentication
def parse_auth(value):
    result = {}
    for mech, verdict in _AUTH_RX.findall(value or ""):
        result.setdefault(mech.lower(), verdict.lower())  # first (receiver's own) verdict wins
    return result


def _display_name_spoof(name, from_domain):
    base = common.registrable_domain(from_domain)
    for token in _DOMAIN_TOKEN.findall(name or ""):
        if common.registrable_domain(token.lower()) != base:
            return True
    return False


# ------------------------------------------------------------------ unsubscribe
def analyze_unsubscribe(headers, auth, signals):
    """Classify unsubscribe metadata. Adds to `signals`; returns the unsubscribe dict."""
    raw = headers.get("list-unsubscribe", "")
    post = headers.get("list-unsubscribe-post", "")
    https_urls, mailtos = [], []
    if raw.strip():
        entries = [e.strip() for e in re.findall(r"<([^<>]*)>", raw)]
        if not entries:
            signals.add("malformed_list_unsubscribe")
        for entry in entries:
            scheme = entry.split(":", 1)[0].lower() if ":" in entry else ""
            if scheme == "https":
                ok, _ = common.check_https_url(entry)
                if ok:
                    https_urls.append(entry)
                else:
                    signals.add("invalid_unsubscribe_url")
            elif scheme == "http":
                signals.add("insecure_http_unsubscribe")
            elif scheme == "mailto":
                parsed, _ = common.parse_mailto(entry)
                if parsed:
                    mailtos.append({"uri": entry, **parsed})
                else:
                    signals.add("invalid_mailto")
            else:
                signals.add("unsupported_scheme")
    one_click = "list-unsubscribe=one-click" in re.sub(r"\s", "", post).lower()
    return {
        "present": bool(raw.strip()),
        "https_url": https_urls[0] if https_urls else None,
        "mailto": mailtos[0] if mailtos else None,
        "one_click_header": one_click,
        "authenticated": auth.get("dkim") == "pass" or auth.get("dmarc") == "pass",
    }


def decide_method(unsub, risk):
    if risk == "high":
        return "unsafe"
    if unsub["https_url"] and unsub["one_click_header"] and unsub["authenticated"]:
        return "rfc8058-post"
    if unsub["mailto"]:
        return "mailto"
    if unsub["https_url"]:
        return "preference-page"
    return "none"


def risk_from(signals):
    if signals & HIGH_SIGNALS:
        return "high"
    return "medium" if signals else "low"


# --------------------------------------------------------------------- analysis
def analyze(headers, read=None, fallback_date=None):
    """Analyze a normalized header dict. Contains unsubscribe targets: keep private."""
    name, address = common.split_sender(headers.get("from", ""))
    domain = common.address_domain(address)
    auth = parse_auth(headers.get("authentication-results", ""))
    signals = set()

    if not auth:
        signals.add("auth_unknown")
    if auth.get("dmarc") in _BAD:
        signals.add("dmarc_fail")
    if auth.get("spf") in _BAD and auth.get("dkim") in (_BAD | {"none"}):
        signals.add("auth_failed")
    elif auth.get("spf") in _BAD or auth.get("dkim") in _BAD:
        signals.add("partial_auth_failure")
    if _display_name_spoof(name, domain):
        signals.add("display_name_spoof")
    _, reply_addr = common.split_sender(headers.get("reply-to", ""))
    if reply_addr and common.registrable_domain(common.address_domain(reply_addr)) != common.registrable_domain(domain):
        signals.add("reply_to_mismatch")

    unsub = analyze_unsubscribe(headers, auth, signals)
    risk = risk_from(signals)
    precedence = headers.get("precedence", "").strip().lower()
    sent = parse_date(headers.get("date")) or parse_date(fallback_date)
    if read is None and headers.get("status"):
        read = "R" in headers["status"].upper()
    return {
        "sender_name": name,
        "sender_address": address,
        "sender_domain": domain,
        "subject": " ".join(headers.get("subject", "").split()),
        "sent_at": sent.isoformat() if sent else None,
        "list_id": headers.get("list-id", "").strip() or None,
        "bulk": bool(unsub["present"] or headers.get("list-id") or precedence in ("bulk", "list", "junk")),
        "auth": {k: auth.get(k, "none") for k in ("spf", "dkim", "dmarc")},
        "unsubscribe": unsub,
        "risk": risk,
        "risk_signals": sorted(signals),
        "method": decide_method(unsub, risk),
        "read": read,
    }


def headers_from_eml(path):
    with open(path, "rb") as fh:
        msg = email.message_from_binary_file(fh, policy=email.policy.default)
    return normalize_headers([(k, str(v)) for k, v in msg.items()])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("files", nargs="+", help=".eml files")
    args = ap.parse_args(argv)
    out = []
    for path in args.files:
        record = analyze(headers_from_eml(path))
        if record["unsubscribe"]["https_url"]:
            record["unsubscribe"]["https_url"] = common.redact_url(record["unsubscribe"]["https_url"])
        if record["unsubscribe"]["mailto"]:
            record["unsubscribe"]["mailto"] = {"address": common.redact_email(record["unsubscribe"]["mailto"]["address"])}
        out.append({"file": os.path.basename(path), **record})
    json.dump(out, sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
