# Safety policy

This policy is enforced in code by `scripts/validate_plan.py` and `scripts/execute_plan.py`.
The model cannot override it by editing the plan.

## Action levels

| Level | Condition | What happens |
|---|---|---|
| 1. Verified one-click | `https` URL passes static checks **and** `List-Unsubscribe-Post: List-Unsubscribe=One-Click` is present **and** the message passed DKIM or DMARC | Executor POSTs `List-Unsubscribe=One-Click` (RFC 8058) |
| 2. Mailto | Single valid recipient; only `subject`/`body` fields | Exact preview shown; host agent sends after approval. Executor never sends |
| 3. Preference page | `https` URL passes static checks but no one-click metadata | Hand-off only. The user opens it. No form is ever submitted |
| 4. No trustworthy method | No usable header | Suggest a move/archive mailbox rule |
| 5. Probable spam/phishing | `risk = high` | Never contact the unsubscribe target. Recommend block/report (manual) |
| 6. Important/transactional | Any `excluded_reasons` | Never part of a bulk unsubscribe |

## URL rules (`common.check_https_url`)

Reject: non-`https`; credentials in URL; non-443 ports; IP-literal hosts; `localhost` or hosts
without a dot or with `.local/.internal/.lan/.home/.corp`; punycode/non-ASCII hosts; control
characters or spaces; URLs over 2048 chars.

At execution time the executor additionally: resolves DNS and refuses any non-global address
(SSRF/DNS-rebinding defence), pins the TCP connection to the validated IP, verifies the TLS
certificate for the original hostname, sends no cookies, does **not** follow redirects, and does
not read the response body. A 3xx counts as failure.

## Risk signals

High risk (blocks unsubscribe): `dmarc_fail`, `auth_failed` (SPF and DKIM both failing),
`display_name_spoof` (display name contains a domain different from the sending domain),
`invalid_unsubscribe_url`, `unsupported_scheme` (e.g. `javascript:`).

Medium: `auth_unknown`, `partial_auth_failure`, `reply_to_mismatch`, `insecure_http_unsubscribe`,
`malformed_list_unsubscribe`, `invalid_mailto`. One-click additionally requires a DKIM or DMARC
pass, so unauthenticated mail falls back to a preference-page hand-off or a mailto.

## Hard exclusions

Subjects or sender roles that suggest: security/sign-in/verification codes, financial
(invoice, receipt, statement, bank), purchase/delivery (order, shipping, booking), medical,
government. Roles such as `security@`, `billing@`, `orders@`. Exclusion is by keyword and is
deliberately over-inclusive: a false positive keeps a sender; a false negative could cut off
something important. Users can still unsubscribe manually.

## Plan integrity

- `candidates.json` carries `immutable_sha256` over all script-derived fields. Editing risk,
  method, exclusions or counts invalidates it. Only `category`, `recommended_action`,
  `confidence` and `reason` may be refined.
- A plan stores the SHA-256 of the scan it was built from and holds candidate IDs only; the
  `action-plan` schema rejects extra properties such as `url`.
- The executor re-validates the plan (including approval) itself and refuses otherwise.
- This integrity digest is tamper-evidence against mistakes and prompt-injection edits, not
  protection against a local attacker with file access.

## Privacy and logging

- Only headers and short subject samples are processed; bodies are never read or stored.
- `targets.private.json` is mode 0600 and read only by `execute_plan.py`.
- Results and logs use `redact_url`/`redact_email`: token-like path segments and entire query
  strings are masked.
- Nothing is sent to any third party by these scripts except the approved one-click POST.
- No automatic deletion, spam reporting, or web-form submission.
