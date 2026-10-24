# NoThanks

Safely find newsletters and promotional email you no longer want.

NoThanks is an agent skill backed by deterministic Python scripts. It scans email headers, explains its recommendations, waits for approval, dry-runs the exact plan, and only then performs approved actions.

```text
SCAN → RECOMMEND → APPROVE → DRY RUN → EXECUTE → VERIFY
```

## Install

Codex and Claude Code:

```bash
npx skills@latest add sureshk2a/NoThanks \
  --skill safe-unsubscribe --global \
  --agent codex claude-code --yes
```

Bob Shell:

```bash
git clone https://github.com/sureshk2a/NoThanks.git
mkdir -p ~/.bob/skills
cp -R NoThanks/skills/safe-unsubscribe ~/.bob/skills/
```

## Use

Start your agent in any workspace and ask:

> Clean up my inbox with the safe-unsubscribe skill. Find unwanted newsletters, let me review the exact plan, then unsubscribe from everything I approve.

NoThanks scans first, lets you include or exclude senders, validates a dry run, and then performs only the actions you explicitly approve.

> **Current status:** scanning, planning, validation, and dry-run behavior are tested. Live unsubscribe execution still needs end-to-end testing with real providers.

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
