# Gmail adapter (planned)

Today the skill uses whatever Gmail tool the host agent provides. See
[provider capabilities](../../skills/safe-unsubscribe/references/provider-capabilities.md#gmail)
for the exact API calls, scopes, and the response shape `scan_mailbox.py` accepts.

A standalone adapter would: list messages (`newer_than:90d`), fetch `format=metadata`, write
`messages.json`, and later create archive filters. Request `gmail.readonly` first; ask for
`gmail.settings.basic` / `gmail.send` only after a plan needing them is approved.
