#!/usr/bin/env python3
"""Deterministic executor: performs ONLY actions in an approved, validated plan.

Dry-run is the default. Real network activity needs --execute.

  execute_plan.py --plan plan.json --scan candidates.json --targets targets.private.json
                  [--execute] [--open-pages] [--out results.json]

Per method:
  rfc8058-post     HTTPS POST "List-Unsubscribe=One-Click". Re-validates the URL,
                   resolves DNS and refuses non-public addresses, pins the connection
                   to the validated IP, never follows redirects, never reads the body.
  mailto           NOT sent here. Emits an exact preview (to/subject/body). The host agent
                   sends it with its own mail tool after the user has seen the preview.
  preference-page  Hand-off only. With --open-pages, opens it in the user's browser.
                   No form is ever submitted.
  create_rule      Emits instructions for the mailbox adapter; no mailbox access here.
  block_or_report  Recommendation only. Never automated.

Logs and results contain redacted URLs/addresses only.
"""
from __future__ import annotations

import argparse
import http.client
import ipaddress
import os
import socket
import ssl
import sys
import webbrowser
from datetime import datetime, timezone
from urllib.parse import urlsplit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
import validate_plan  # noqa: E402

ONE_CLICK_BODY = b"List-Unsubscribe=One-Click"
TIMEOUT = 15


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    """Connects to a pre-validated IP while keeping SNI/cert checks for the real host."""

    def __init__(self, host, ip, **kwargs):
        super().__init__(host, **kwargs)
        self._pinned_ip = ip

    def connect(self):
        sock = socket.create_connection((self._pinned_ip, self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


def resolve_public_ip(host):
    """Return one public IP for host, or raise ValueError if any address is non-public."""
    infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    ips = []
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise ValueError(f"host resolves to non-public address {ip}")
        ips.append(str(ip))
    if not ips:
        raise ValueError("host did not resolve")
    return ips[0]


def post_one_click(url):
    """Real HTTP POST. Returns (status_code, location_header_present)."""
    ok, why = common.check_https_url(url)
    if not ok:
        raise ValueError(why)
    parts = urlsplit(url)
    ip = resolve_public_ip(parts.hostname)
    conn = PinnedHTTPSConnection(parts.hostname, ip, timeout=TIMEOUT, context=ssl.create_default_context())
    try:
        target = parts.path or "/"
        if parts.query:
            target += "?" + parts.query
        conn.request("POST", target, body=ONE_CLICK_BODY, headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Content-Length": str(len(ONE_CLICK_BODY)),
            "User-Agent": "NoThanks-SafeUnsubscribe/0.1",
        })
        resp = conn.getresponse()
        return resp.status, resp.getheader("Location") is not None
    finally:
        conn.close()


def execute(plan, scan, targets, execute_real=False, open_pages=False, poster=post_one_click, opener=webbrowser.open):
    """Run a plan; returns a list of result dicts. Assumes validate_plan already passed
    but re-checks anyway."""
    errors = validate_plan.validate(plan, scan, scan["_sha"], require_approved=True)
    if errors:
        raise ValueError("plan failed validation: " + "; ".join(errors))
    by_id = {c["candidate_id"]: c for c in scan["candidates"]}
    results = []
    for act in plan["actions"]:
        cand = by_id[act["candidate_id"]]
        res = {
            "candidate_id": cand["candidate_id"],
            "sender_address": cand["sender_address"],
            "action": act["action"],
            "method": act["method"],
            "executed_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            res.update(_run_one(act, cand, targets.get(cand["candidate_id"]), execute_real, open_pages, poster, opener))
        except Exception as exc:  # one failure must not stop the batch
            res.update(status="failed", detail=f"{type(exc).__name__}: {exc}"[:300])
        results.append(res)
    return results


def _run_one(act, cand, target, execute_real, open_pages, poster, opener):
    action, method = act["action"], act["method"]
    if action == "block_or_report":
        return {"status": "recommendation_only", "detail": "Block/report manually; never automated."}
    if action == "create_rule":
        return {"status": "pending_host" if execute_real else "dry_run",
                "detail": f"Create a mailbox rule for sender {cand['sender_address']}: move to a folder/archive (no deletion)."}
    # action == "unsubscribe"
    if target is None or target["method"] != method:
        return {"status": "failed", "detail": "no stored target for this candidate/method"}
    if target["sender_address"] != cand["sender_address"]:
        return {"status": "failed", "detail": "target does not belong to this sender"}

    if method == "rfc8058-post":
        url = target["https_url"]
        shown = common.redact_url(url)
        if not execute_real:
            return {"status": "dry_run", "detail": f"would POST one-click to {shown}"}
        status, redirected = poster(url)
        if 200 <= status < 300:
            return {"status": "succeeded", "detail": f"POST {shown} -> HTTP {status}", "http_status": status}
        if redirected:
            return {"status": "failed", "detail": f"POST {shown} -> HTTP {status} redirect (not followed)", "http_status": status}
        return {"status": "failed", "detail": f"POST {shown} -> HTTP {status}", "http_status": status}

    if method == "mailto":
        m = target["mailto"]
        return {
            "status": "pending_host" if execute_real else "dry_run",
            "detail": "Show this exact email to the user, then send it with the host mail tool.",
            "mailto_preview": {"to": m["address"], "subject": m["subject"], "body": m["body"]},
        }

    if method == "preference-page":
        shown = common.redact_url(target["https_url"])
        if execute_real and open_pages:
            opener(target["https_url"])
            return {"status": "handoff", "detail": f"opened {shown} in the browser; complete it yourself"}
        return {"status": "dry_run" if not execute_real else "handoff",
                "detail": f"preference page {shown}; re-run with --execute --open-pages to open it yourself"}

    return {"status": "failed", "detail": f"unsupported method '{method}'"}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--plan", required=True)
    ap.add_argument("--scan", required=True)
    ap.add_argument("--targets", required=True)
    ap.add_argument("--out", default=".nothanks/results.json")
    ap.add_argument("--execute", action="store_true", help="perform real actions (default: dry run)")
    ap.add_argument("--open-pages", action="store_true")
    args = ap.parse_args(argv)

    scan = common.read_json(args.scan)
    scan["_sha"] = common.sha256_file(args.scan)
    try:
        results = execute(common.read_json(args.plan), scan, common.read_json(args.targets).get("targets", {}),
                          args.execute, args.open_pages)
    except ValueError as exc:
        common.die(str(exc), code=1)
    doc = {
        "schema_version": common.SCHEMA_VERSION,
        "dry_run": not args.execute,
        "plan_sha256": common.sha256_file(args.plan),
        "results": results,
    }
    common.write_json(args.out, doc)
    for r in results:
        print(f"[{r['status']:>19}] {r['sender_address']}: {r['detail']}")
        if "mailto_preview" in r:
            p = r["mailto_preview"]
            print(f"{'':>22}to={p['to']} subject={p['subject']!r} body={p['body']!r}")
    failed = sum(r["status"] == "failed" for r in results)
    print(f"{len(results)} actions, {failed} failed -> {args.out}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
