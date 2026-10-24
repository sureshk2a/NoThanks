# NoThanks

Safely find newsletters and promotional email you no longer want.

NoThanks is an agent skill backed by deterministic Python scripts. It scans email headers, explains its recommendations, waits for approval, dry-runs the exact plan, and only then performs approved actions.

```text
SCAN → RECOMMEND → APPROVE → DRY RUN → EXECUTE → VERIFY
```

## Install for Bob

```bash
git clone https://github.com/sureshk2a/NoThanks.git
mkdir -p ~/.bob/skills
cp -R NoThanks/skills/safe-unsubscribe ~/.bob/skills/
```

Requirements: Bob Shell, Python 3.9+, and either a configured Gmail/Outlook MCP connection or an exported `.eml`/`.mbox` mailbox.

## Use

Start Bob in any workspace and ask:

> Use the safe-unsubscribe skill. Scan my email from the last 90 days and show recommendations only. Do not make changes.

Nothing is changed during scanning. To continue, tell Bob exactly which recommendations to include or exclude. NoThanks will show and validate a dry run before asking for final approval.

For a local mailbox export:

```bash
python3 ~/.bob/skills/safe-unsubscribe/scripts/scan_mailbox.py \
  --source ~/Mail/export.mbox --out-dir .nothanks/scan --table
```

## Safety

- Reads headers, not message bodies.
- Keeps unsubscribe targets out of model-visible plans.
- Excludes security, financial, medical, government, purchase, and delivery mail.
- Rejects private-network, redirecting, malformed, and suspicious links.
- Never deletes mail, submits forms, or reports spam automatically.
- Stores working data locally in `.nothanks/`, which is ignored by Git.

See [SECURITY.md](SECURITY.md) for the threat model.

## Test

```bash
python3 -m unittest discover -s tests -v
```

MIT licensed.
