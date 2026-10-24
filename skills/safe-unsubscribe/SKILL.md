---
name: safe-unsubscribe
description: Review recurring newsletter and promotional email, explain which senders are worth removing, and unsubscribe from approved senders safely in one batch without blindly trusting unsubscribe links. Use when the user asks to clean up their inbox, find newsletters they do not need, unsubscribe from promotions, or check whether an unsubscribe link is safe. Works read-only until the user explicitly approves a plan.
---

# Safe Unsubscribe (NoThanks)

Workflow: **SCAN → RECOMMEND → USER APPROVES → EXECUTE → VERIFY**.
Never merge these stages into one step. Scanning and recommending are read-only.

You (the model) interpret and recommend. The scripts in `scripts/` validate and execute.
Paths below are relative to this skill directory. Working files go in `.nothanks/` in the user's
current directory (add it to `.gitignore` if in a repo).

## Hard rules

1. No external action (HTTP request, sent email, mailbox rule, opened page) without an explicit
   user approval of the exact plan shown to them in this conversation.
2. Never open, fetch, click, or print an unsubscribe URL yourself. Only `execute_plan.py` touches
   them, and only for approved plans. `candidates.json` deliberately contains no URLs.
3. Never put URLs or addresses into the plan. Refer to candidates by `candidate_id` only.
4. Never include security, account, financial, medical, government, billing, purchase or delivery
   senders in a bulk action. See `references/safety-policy.md`.
5. Suspicious senders: never visit their unsubscribe link; recommend block/report only.
   Do not report spam or delete anything automatically.
6. Do not paste raw message bodies. Work from headers, counts, and short subject samples.
7. If a script exits non-zero, stop and tell the user what it printed. Do not work around it.

## 1. SCAN (read-only)

Get message **headers only** for roughly the last 90 days, using whatever mail tool the host
provides (Gmail/Outlook connector, MCP server, or an exported `.eml`/`.mbox`). Needed per message:
`From`, `Subject`, `Date`, `List-Id`, `List-Unsubscribe`, `List-Unsubscribe-Post`, `Precedence`,
`Authentication-Results`, plus read/unread state if available. Write them to
`.nothanks/messages.json` as `[{"headers": {...}, "read": true|false|null}]`; Gmail
`format=metadata` and Microsoft Graph message objects are also accepted as-is
(see `references/provider-capabilities.md`). Never request message bodies.

```bash
python3 scripts/scan_mailbox.py --source .nothanks/messages.json --out-dir .nothanks/scan --table
```

This writes `candidates.json` (safe to read) and `targets.private.json` (mode 0600; **do not read
or display it**).

## 2. RECOMMEND (read-only)

Read `.nothanks/scan/candidates.json` and `references/classification-policy.md`. The script
provides a heuristic default recommendation; refine it where context warrants:

- Group senders with the same `group_key` (same publisher) and present them together.
- Apply the user's stated preferences (e.g. keep travel, remove shopping).
- Judge category from `sample_subjects` and sender name; use `confidence` honestly.
- You may change `recommended_action` to something **safer** (e.g. unsubscribe → keep). You may not
  make anything riskier than the script's hard rules allow; `validate_plan.py` will reject it.
  To change a recommendation, edit that candidate's `category`/`recommended_action`/`reason` in
  `candidates.json` before building the plan (the plan binds to the file's hash).

Show the user a table: Sender | Messages (90 days) | Engagement | Recommendation | Method | Why.
Method labels in plain words: verified one-click, mailto email, preference page, none, unsafe link.
Say clearly that **nothing has been changed yet**, and ask which to approve or exclude.

## 3. USER APPROVES

Build the plan from the user's words ("everything recommended except Airline Deals"):

```bash
python3 scripts/build_plan.py --scan .nothanks/scan/candidates.json --recommended --keep airline.example
python3 scripts/validate_plan.py --plan .nothanks/plan.json --scan .nothanks/scan/candidates.json
```

Restate the exact action list (sender, action, method) and, for `mailto`, the preview from the dry
run (step 4). Ask for explicit confirmation. Only after a clear "yes" to *this* list:

```bash
python3 scripts/build_plan.py --mark-approved .nothanks/plan.json
```

If the user changes anything afterwards, rebuild and ask again. Vague replies are not approval.

## 4. EXECUTE

Always dry-run first and show the output:

```bash
python3 scripts/execute_plan.py --plan .nothanks/plan.json --scan .nothanks/scan/candidates.json \
  --targets .nothanks/scan/targets.private.json
```

Then, if approved:

```bash
python3 scripts/execute_plan.py ... --execute            # add --open-pages to open preference pages
```

Result statuses and what you must do:

| Status | Meaning | Your job |
|---|---|---|
| `succeeded` | one-click POST returned 2xx | report it |
| `failed` | validation, network, redirect or non-2xx | report it; do not retry with another URL |
| `pending_host` (mailto) | email not sent by the script | show to/subject/body, send with the host mail tool only if the user approved that preview |
| `pending_host` (rule) | rule not created by the script | create a **move/archive** rule via the mail tool (never delete) |
| `handoff` | preference page opened | tell the user to finish it themselves; never fill or submit forms |
| `recommendation_only` | block/report | tell the user how to do it manually in their mail client |

## 5. VERIFY

Report a summary: succeeded / failed / pending / handoff counts, using redacted details from
`.nothanks/results.json`. Offer a re-check after 2–4 weeks: re-run the scan into a new directory,
then `python3 scripts/verify_results.py --results .nothanks/results.json --rescan <new>/candidates.json`.
For `still_mailing` senders, offer a mailbox rule.

## Reference files

- `references/safety-policy.md` — exclusions, URL rules, suspicious indicators
- `references/classification-policy.md` — categories, engagement, confidence
- `references/provider-capabilities.md` — Gmail/Outlook/local capabilities and data shapes
- `schemas/` — candidate and action-plan JSON schemas
- `evals/cases.yaml` — behavioural cases for this skill
