# Classification policy

The scanner supplies a heuristic first pass. You refine it using sender name, sample subjects,
and the user's preferences. You may edit only `category`, `recommended_action`, `confidence`,
and `reason` in `candidates.json`; all other fields are hash-locked.

## Categories

| Category | Meaning | Default action |
|---|---|---|
| `promotional` | Sales, offers, marketing from a company the user buys from | unsubscribe if low engagement |
| `newsletter` | Editorial/informational recurring content | keep if opened, else unsubscribe |
| `community` | Mailing lists, clubs, open-source, school/work groups | keep unless the user says otherwise |
| `transactional` | Receipts, orders, bills, alerts, account notices | always keep |
| `personal` | A real person writing to the user | always keep |
| `suspicious` | Failed authentication, spoofing, unsafe unsubscribe link | block_or_report |
| `unknown` | Not enough information | keep, and say why |

## Engagement (from read flags, when the provider exposes them)

- `high` ≥ 50% read, `medium` 20–49%, `low` < 20%, `unknown` with fewer than 2 known flags.
- Never treat `unknown` as `low`. Say "engagement not available".

## Recommending

Unsubscribe only when all hold: not excluded, not high risk, category is promotional or
newsletter, a usable method exists (otherwise suggest a rule), and either engagement is low
or the user asked for it. Fewer than 4 messages in the window with non-low engagement → keep.

Minimum confidence for an `unsubscribe` action is **0.6** (enforced by `validate_plan.py`).
Calibrate: 0.9+ = clear pattern across many messages; 0.6–0.8 = reasonable but contextual;
below 0.6 = keep and ask.

## Grouping

Candidates sharing `group_key` belong to one publisher/organization (approximate registrable
domain). Present them together; apply the user's keep/remove decision to the whole group, and
mention when addresses in a group get different recommendations.

## Explanations

Each `reason` states evidence in plain language: count, window, engagement, method, and any risk
signal. Do not claim certainty about intent. Avoid quoting message content beyond a subject line.

## User preferences

Honour requests like "keep travel deals but remove shopping" by changing the affected candidates'
`recommended_action`/`reason` (to a safer action) and explaining the change. Preferences can never
make an excluded or high-risk sender unsubscribable.
