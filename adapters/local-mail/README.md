# Local mail (implemented)

No adapter is needed: point the scanner at a directory of `.eml` files or an `.mbox` export.

```bash
python3 skills/safe-unsubscribe/scripts/scan_mailbox.py --source ~/Mail/export.mbox --table
```

Headers only are read. Engagement is `unknown` unless messages carry a `Status:` header.
