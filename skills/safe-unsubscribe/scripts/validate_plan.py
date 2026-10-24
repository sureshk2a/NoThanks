#!/usr/bin/env python3
"""Validate an action plan against the scan it was built from.

Exit code 0 = valid, 1 = invalid. This is the policy gate: it enforces the hard rules
no matter what the AI layer recommended.

  validate_plan.py --plan plan.json --scan candidates.json [--require-approved]
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

BLOCKED_CATEGORIES = {"transactional", "personal"}
MIN_CONFIDENCE = 0.6  # below this an "unsubscribe" is not allowed (open question in the design)


def validate(plan, scan, scan_sha, require_approved=False):
    errors = common.validate_schema(plan, common.load_schema("action-plan.schema.json"))
    if errors:
        return errors
    if plan["scan_sha256"] != scan_sha:
        return ["plan was built from a different scan (scan_sha256 mismatch); rebuild the plan"]
    if require_approved and not plan.get("approved"):
        errors.append("plan is not approved by the user")
    if plan.get("approved") and not plan.get("approved_at"):
        errors.append("approved plan must include approved_at")

    if common.immutable_digest(scan["candidates"]) != scan.get("immutable_sha256"):
        return ["candidates.json: script-derived fields (risk, method, exclusions, counts...) were modified; "
                "only category, recommended_action, confidence and reason may be edited. Re-run the scan."]
    by_id = {c["candidate_id"]: c for c in scan["candidates"]}
    seen = set()
    for i, act in enumerate(plan["actions"]):
        where = f"actions[{i}] ({act['candidate_id']})"
        cand = by_id.get(act["candidate_id"])
        if cand is None:
            errors.append(f"{where}: unknown candidate_id")
            continue
        if act["candidate_id"] in seen:
            errors.append(f"{where}: duplicate candidate")
        seen.add(act["candidate_id"])
        if act["method"] != cand["method"]:
            errors.append(f"{where}: method '{act['method']}' differs from scanned method '{cand['method']}'")
        # block_or_report is advice only, so it is allowed for high-risk impostors of important mail.
        impostor = act["action"] == "block_or_report" and cand["risk"] == "high"
        if cand["excluded_reasons"] and not impostor:
            errors.append(f"{where}: sensitive/transactional mail ({', '.join(cand['excluded_reasons'])}) is never bulk-actioned")
        if cand["category"] in BLOCKED_CATEGORIES:
            errors.append(f"{where}: category '{cand['category']}' is excluded from bulk actions")
        if act["action"] == "unsubscribe":
            if cand["risk"] == "high" or cand["method"] == "unsafe":
                errors.append(f"{where}: high-risk sender; never use its unsubscribe method")
            if cand["method"] not in common.USABLE_METHODS:
                errors.append(f"{where}: no usable unsubscribe method ('{cand['method']}')")
            if cand["confidence"] < MIN_CONFIDENCE:
                errors.append(f"{where}: confidence {cand['confidence']} below {MIN_CONFIDENCE}")
        elif act["action"] == "block_or_report" and cand["risk"] == "low" and cand["category"] != "suspicious":
            errors.append(f"{where}: block_or_report is reserved for suspicious senders")
    return errors


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--plan", required=True)
    ap.add_argument("--scan", required=True)
    ap.add_argument("--require-approved", action="store_true")
    args = ap.parse_args(argv)
    errors = validate(common.read_json(args.plan), common.read_json(args.scan),
                      common.sha256_file(args.scan), args.require_approved)
    if errors:
        print("INVALID plan:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    print("plan is valid")


if __name__ == "__main__":
    main()
