# Mail MCP capabilities

The host must have an authenticated Gmail or Microsoft Outlook MCP connection. The skill needs
**headers only**. Save MCP results to a `.json` file as a list or `{"messages": [...]}` before
running `scan_mailbox.py`.

## Generic

```json
{"headers": {"From": "Shop <deals@shop.example>", "Subject": "Sale",
             "Date": "Mon, 05 Oct 2026 10:00:00 +0000",
             "List-Unsubscribe": "<https://...>", "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
             "Authentication-Results": "mx; spf=pass; dkim=pass; dmarc=pass"},
 "read": false}
```

## Gmail

Use `users.messages.list` (query e.g. `newer_than:90d (unsubscribe OR list:*)`), then
`users.messages.get` with `format=metadata` and `metadataHeaders` set to the headers above.
Pass the response objects unchanged: `payload.headers`, `labelIds` (absence of `UNREAD` ⇒ read),
and `internalDate` are understood. Scope: `gmail.readonly` for scanning. Creating filters needs
`gmail.settings.basic`; sending an unsubscribe email needs `gmail.send`. Request those only after
the user approves a plan that needs them. Rule = filter with `removeLabelIds: [INBOX]`
(archive) and optionally an `addLabelIds` folder; never delete.

## Microsoft Outlook (Graph)

`GET /me/messages?$select=subject,from,receivedDateTime,isRead,internetMessageHeaders&$filter=receivedDateTime ge ...`.
Pass message objects unchanged (`internetMessageHeaders`, `subject`, `isRead`,
`receivedDateTime`). Scope: `Mail.Read` to scan; `Mail.ReadWrite` for inbox rules (move to a
folder, not delete); `Mail.Send` for mailto unsubscribes.
Note: `internetMessageHeaders` is only returned when explicitly selected and can be heavy; page
through results.

## Capability matrix

| Capability | Gmail | Outlook |
|---|---|---|
| Header scan | yes | yes |
| Read/unread engagement | yes (`UNREAD` label) | yes (`isRead`) |
| One-click POST | yes (executor) | yes (executor) |
| Send mailto | host tool / `gmail.send` | host tool / `Mail.Send` |
| Create rule | filters API | inbox rules API |
| Open/click tracking | not available | not available |

Engagement is read-state only; open-tracking pixels are not used and are never loaded.
