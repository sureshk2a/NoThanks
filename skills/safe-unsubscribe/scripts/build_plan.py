#!/usr/bin/env python3
"""Build an UNAPPROVED action plan from a scan.

The plan references candidates by ID only (never URLs). Selection:

  --recommended            every candidate whose recommended_action is not "keep"
  --keep <id|domain|addr>  remove from the selection (repeatable; matches sender
                           address, sender domain, group key, name, or candidate ID)
  --only <id|...>          select exactly these candidates (repeatable)

The plan is written with "approved": false. Only after the user has seen the plan
and explicitly approved it should `--mark-approved` be applied (see SKILL.md).
Run validate_plan.py before executing.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402


def matches(cand, token):
    token = token.strip().lower()
    return token in {
        cand["candidate_id"].lower(),
        cand["sender_address"].lower(),
        cand["sender_domain"].lower(),
        cand["group_key"].lower(),
        cand["sender_name"].lower(),
    }


def build_plan(scan, scan_sha, recommended=True, only=(), keep=()):
    chosen = []
    for cand in scan["candidates"]:
        if only:
            selected = any(matches(cand, t) for t in only)
        else:
            selected = recommended and cand["recommended_action"] != "keep"
        if selected and not any(matches(cand, t) for t in keep):
            action = cand["recommended_action"]
            if action == "keep":
                # Explicitly requested via --only: default to the safest useful action.
                action = "block_or_report" if cand["risk"] == "high" else (
                    "unsubscribe" if cand["method"] in common.USABLE_METHODS else "create_rule")
            chosen.append({
                "candidate_id": cand["candidate_id"],
                "action": action,
                "method": cand["method"],
                "reason": cand["reason"],
            })
    return {
        "schema_version": common.SCHEMA_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "scan_sha256": scan_sha,
        "approved": False,
        "approved_at": None,
        "actions": chosen,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scan", help="candidates.json from scan_mailbox.py")
    ap.add_argument("--out", default=".nothanks/plan.json")
    ap.add_argument("--recommended", action="store_true", help="select all non-keep recommendations")
    ap.add_argument("--only", action="append", default=[])
    ap.add_argument("--keep", action="append", default=[])
    ap.add_argument("--mark-approved", metavar="PLAN", help="set approved=true on an existing plan (after explicit user approval)")
    args = ap.parse_args(argv)

    if args.mark_approved:
        plan = common.read_json(args.mark_approved)
        plan["approved"] = True
        plan["approved_at"] = datetime.now(timezone.utc).isoformat()
        common.write_json(args.mark_approved, plan)
        print(f"marked approved: {args.mark_approved}")
        return

    if not args.scan:
        common.die("--scan is required")
    if not (args.recommended or args.only):
        common.die("choose --recommended and/or --only")
    scan = common.read_json(args.scan)
    plan = build_plan(scan, common.sha256_file(args.scan), args.recommended, args.only, args.keep)
    if not plan["actions"]:
        common.die("selection is empty; nothing to plan", code=1)
    common.write_json(args.out, plan)
    print(f"{len(plan['actions'])} actions -> {args.out} (approved=false)")


if __name__ == "__main__":
    main()
