# Security policy

## Reporting a vulnerability

Please report security issues privately (GitHub private vulnerability reporting or the
maintainers' security contact) rather than opening a public issue. Include steps to reproduce
and the affected version. We aim to acknowledge reports within 5 working days.

## Security model

NoThanks handles mailbox metadata and triggers network requests derived from untrusted email
headers, so these invariants are treated as security-critical:

1. **No unapproved external action.** `execute_plan.py` refuses any plan that is not schema-valid,
   bound to the scan, and marked approved; it is dry-run by default.
2. **Plans contain IDs, not URLs.** Execution targets come from a local private file produced by
   the scanner, never from model output.
3. **Untrusted links are not followed.** HTTPS-only, public-DNS-only, connection pinned to the
   validated IP, no redirects, no cookies, no response body read. Suspicious senders are never
   contacted.
4. **No form submission, deletion, or spam reporting** is automated.
5. **Sensitive mail is excluded** from bulk actions in code, not only in prompts.
6. **Logs are redacted**; the private targets file is created with mode 0600.
7. **No full message bodies** are read or stored.

Known limitations: the registrable-domain logic is an approximation (no public-suffix list);
keyword exclusions are heuristic; the integrity digest guards against accidental/injected edits,
not a local attacker; one-click POST proves the sender received a request, not that it honoured it.

Reports that demonstrate a bypass of any invariant above are in scope.
