#!/usr/bin/env python3
"""Read-only scan: turn message headers into sender candidates.

Sources (--source):
  * a directory of .eml files
  * an .mbox file
  * a .json file of adapter records (generic, Gmail metadata, or Graph messages)

Outputs (in --out-dir):
  candidates.json       Safe to show to the AI/user. Contains NO unsubscribe URLs.
  targets.private.json  Unsubscribe targets keyed by candidate_id (mode 0600).
                        Only execute_plan.py reads this file.

Nothing is sent, fetched, or modified. Message bodies are never read.
"""
from __future__ import annotations

import argparse
import mailbox
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
import exclusions  # noqa: E402
import parse_headers  # noqa: E402

SAMPLE_SUBJECTS = 3
MIN_MESSAGES_TO_UNSUBSCRIBE = 4


# ------------------------------------------------------------------- loading
def iter_records(source):
    """Yield (headers, read, fallback_date) for every message in the source."""
    if os.path.isdir(source):
        for name in sorted(os.listdir(source)):
            if name.lower().endswith(".eml"):
                yield parse_headers.headers_from_eml(os.path.join(source, name)), None, None
    elif source.lower().endswith((".mbox", ".mbx")):
        for msg in mailbox.mbox(source):
            headers = parse_headers.normalize_headers([(k, str(v)) for k, v in msg.items()])
            yield headers, None, None
    elif source.lower().endswith(".json"):
        data = common.read_json(source)
        records = data.get("messages", data) if isinstance(data, dict) else data
        for obj in records:
            yield parse_headers.normalize_record(obj)
    else:
        common.die(f"unsupported source '{source}' (use a directory of .eml, an .mbox, or a .json file)")


# ------------------------------------------------------------------ aggregation
def engagement_level(read_flags):
    known = [r for r in read_flags if r is not None]
    if len(known) < 2:
        return "unknown"
    ratio = sum(known) / len(known)
    return "high" if ratio >= 0.5 else "medium" if ratio >= 0.2 else "low"


def recommend(cand, excluded_reasons):
    """Heuristic default; the AI layer may refine category/action/reason, but
    validate_plan.py re-applies every hard rule regardless."""
    method, risk, count, eng = cand["method"], cand["risk"], cand["message_count"], cand["engagement"]
    if risk == "high":
        extra = " (imitates important mail: " + ", ".join(sorted(excluded_reasons)) + ")" if excluded_reasons else ""
        return ("suspicious", "block_or_report", 0.85,
                "Suspicious signals (" + ", ".join(cand["risk_signals"]) + ")" + extra + "; do not visit its unsubscribe link")
    if excluded_reasons:
        return ("transactional", "keep", 0.9,
                "Looks like important or transactional mail (" + ", ".join(sorted(excluded_reasons)) + "); excluded from bulk actions")
    if eng == "high":
        return ("newsletter", "keep", 0.8, "You open most of these messages")
    if count < MIN_MESSAGES_TO_UNSUBSCRIBE and eng != "low":
        return ("promotional", "keep", 0.5, f"Only {count} recent messages; not enough evidence to recommend removal")
    base = 0.9 if eng == "low" else 0.65
    if method == "rfc8058-post":
        return ("promotional", "unsubscribe", base + 0.04, f"{count} bulk messages, engagement {eng}; verified one-click unsubscribe available")
    if method == "mailto":
        return ("promotional", "unsubscribe", base, f"{count} bulk messages, engagement {eng}; unsubscribe by email (preview required)")
    if method == "preference-page":
        return ("promotional", "unsubscribe", base - 0.05, f"{count} bulk messages, engagement {eng}; only a preference page is offered (you open it yourself)")
    return ("promotional", "create_rule", base - 0.1, f"{count} bulk messages, engagement {eng}; no trustworthy unsubscribe method, so a mailbox rule is suggested")


def build_candidates(records, now, days):
    cutoff = now - timedelta(days=days)
    groups = defaultdict(list)
    for headers, read, fallback in records:
        info = parse_headers.analyze(headers, read, fallback)
        if not info["sender_address"]:
            continue
        if info["sent_at"] and datetime.fromisoformat(info["sent_at"]) < cutoff:
            continue
        groups[info["sender_address"]].append(info)

    candidates, targets = [], {}
    for address, msgs in sorted(groups.items()):
        bulk = [m for m in msgs if m["bulk"]]
        if not bulk:
            continue
        dated = sorted((m for m in bulk if m["sent_at"]), key=lambda m: m["sent_at"])
        ordered = dated or bulk
        latest_unsub = next((m for m in reversed(ordered) if m["unsubscribe"]["present"]), ordered[-1])

        signals = sorted({s for m in bulk for s in m["risk_signals"]})
        risk = "high" if any(m["risk"] == "high" for m in bulk) else ("medium" if signals else "low")
        method = "unsafe" if risk == "high" else latest_unsub["method"]

        excluded = set(exclusions.sender_categories(address))
        for m in msgs:
            excluded |= exclusions.subject_categories(m["subject"])

        name_counts = Counter(m["sender_name"] for m in bulk if m["sender_name"])
        cand = {
            "candidate_id": common.candidate_id(address),
            "sender_name": name_counts.most_common(1)[0][0] if name_counts else address,
            "sender_address": address,
            "sender_domain": bulk[0]["sender_domain"],
            "group_key": common.registrable_domain(bulk[0]["sender_domain"]),
            "message_count": len(msgs),
            "bulk_message_count": len(bulk),
            "first_seen": dated[0]["sent_at"][:10] if dated else None,
            "last_seen": dated[-1]["sent_at"][:10] if dated else None,
            "engagement": engagement_level([m["read"] for m in bulk]),
            "risk": risk,
            "risk_signals": signals,
            "method": method,
            "excluded_reasons": sorted(excluded),
            "sample_subjects": [m["subject"][:120] for m in ordered[-SAMPLE_SUBJECTS:]],
        }
        category, action, confidence, reason = recommend(cand, excluded)
        cand.update(category=category, recommended_action=action, confidence=round(min(confidence, 0.99), 2), reason=reason)
        candidates.append(cand)

        u = latest_unsub["unsubscribe"]
        if method in common.USABLE_METHODS:
            targets[cand["candidate_id"]] = {
                "method": method,
                "sender_address": address,
                "https_url": u["https_url"] if method in ("rfc8058-post", "preference-page") else None,
                "mailto": u["mailto"] if method == "mailto" else None,
            }

    order = {"block_or_report": 0, "unsubscribe": 1, "create_rule": 2, "keep": 3}
    candidates.sort(key=lambda c: (order[c["recommended_action"]], -c["message_count"], c["sender_address"]))
    return candidates, targets


def render_table(candidates):
    rows = ["| # | Sender | Messages | Engagement | Recommendation | Method | Why |", "|---|---|---:|---|---|---|---|"]
    for i, c in enumerate(candidates, 1):
        rows.append(
            f"| {i} | {c['sender_name']} ({c['sender_domain']}) | {c['message_count']} | {c['engagement']} "
            f"| {c['recommended_action']} | {c['method']} | {c['reason']} |"
        )
    return "\n".join(rows)


def resolve_now(value):
    if not value:
        return datetime.now(timezone.utc)
    dt = parse_headers.parse_date(value)
    if dt is None:
        common.die(f"invalid --now value '{value}'")
    return dt


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", required=True)
    ap.add_argument("--out-dir", default=".nothanks/scan")
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--now", help="ISO timestamp to use as 'now' (for reproducible runs/tests)")
    ap.add_argument("--table", action="store_true", help="also print a Markdown review table")
    args = ap.parse_args(argv)

    now = resolve_now(args.now)
    candidates, targets = build_candidates(iter_records(args.source), now, args.days)
    doc = {
        "schema_version": common.SCHEMA_VERSION,
        "generated_at": now.isoformat(),
        "window_days": args.days,
        "immutable_sha256": common.immutable_digest(candidates),
        "candidates": candidates,
    }
    errors = common.validate_schema(doc, common.load_schema("candidate.schema.json"))
    if errors:
        common.die("internal: candidates failed schema validation:\n  " + "\n  ".join(errors))
    cpath = os.path.join(args.out_dir, "candidates.json")
    tpath = os.path.join(args.out_dir, "targets.private.json")
    common.write_json(cpath, doc)
    common.write_json(tpath, {"schema_version": common.SCHEMA_VERSION, "targets": targets}, private=True)
    print(f"{len(candidates)} candidates -> {cpath}")
    print(f"{len(targets)} private targets -> {tpath} (0600; never share or paste)")
    if args.table:
        print()
        print(render_table(candidates))


if __name__ == "__main__":
    main()
