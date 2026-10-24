#!/usr/bin/env python3
"""Verify whether senders kept mailing after an unsubscribe.

Re-run scan_mailbox.py later (e.g. 14-30 days after execution) and compare:

  verify_results.py --results results.json --rescan new/candidates.json [--grace-days 10]

Statuses:
  stopped          no messages after the grace period
  still_mailing    messages arrived after the grace period -> consider a mailbox rule
  not_applicable   action was not a completed unsubscribe (pending/failed/dry run)
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402


def verify(results_doc, rescan, grace_days=10):
    latest = {c["sender_address"]: c.get("last_seen") for c in rescan["candidates"]}
    out = []
    for r in results_doc["results"]:
        row = {"sender_address": r["sender_address"], "method": r["method"], "action": r["action"]}
        done = r["status"] in ("succeeded", "handoff") and r["action"] == "unsubscribe"
        if results_doc.get("dry_run") or not done:
            row.update(status="not_applicable", detail=f"action status was '{r['status']}'")
        else:
            cutoff = datetime.fromisoformat(r["executed_at"]).date() + timedelta(days=grace_days)
            last = latest.get(r["sender_address"])
            if last and date.fromisoformat(last) > cutoff:
                row.update(status="still_mailing", detail=f"last message {last} is after {cutoff}; suggest a mailbox rule")
            else:
                row.update(status="stopped", detail=f"no messages after {cutoff}")
        out.append(row)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--results", required=True)
    ap.add_argument("--rescan", required=True)
    ap.add_argument("--grace-days", type=int, default=10)
    args = ap.parse_args(argv)
    rows = verify(common.read_json(args.results), common.read_json(args.rescan), args.grace_days)
    for row in rows:
        print(f"[{row['status']:>14}] {row['sender_address']}: {row['detail']}")
    sys.exit(1 if any(r["status"] == "still_mailing" for r in rows) else 0)


if __name__ == "__main__":
    main()
