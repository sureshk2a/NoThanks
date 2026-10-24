# Outlook adapter (planned)

Today the skill uses whatever Microsoft 365 / Outlook tool the host agent provides. See
[provider capabilities](../../skills/safe-unsubscribe/references/provider-capabilities.md#microsoft-outlook-graph).

A standalone adapter would page `GET /me/messages` with `internetMessageHeaders` selected, write
`messages.json`, and later create move-to-folder inbox rules. Start with `Mail.Read`.
