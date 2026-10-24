# Provider capabilities

The portable skill needs **headers only**. `scan_mailbox.py` accepts these shapes in a `.json`
file (a list, or `{"messages": [...]}`):

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

## Local files

- Directory of `.eml` files, or an `.mbox` file. Read state is taken from the `Status:` header
  if present, otherwise engagement is `unknown`.

## Capability matrix

| Capability | Gmail | Outlook | Local files |
|---|---|---|---|
| Header scan | yes | yes | yes |
| Read/unread engagement | yes (`UNREAD` label) | yes (`isRead`) | only with `Status:` |
| One-click POST | yes (executor) | yes (executor) | yes (executor) |
| Send mailto | host tool / `gmail.send` | host tool / `Mail.Send` | no |
| Create rule | filters API | inbox rules API | no |
| Open/click tracking | not available | not available | no |

Engagement is read-state only; open-tracking pixels are not used and are never loaded.
