# NoThanks

Safely find newsletters and promotional email you no longer want.

NoThanks is an agent skill backed by deterministic Python scripts. It scans email headers, selects safe unsubscribe candidates, validates the plan, and performs the actions you authorize.

```text
SCAN → RECOMMEND → AUTHORIZE → EXECUTE → VERIFY
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

## Connect your mail

NoThanks does not include a mail connection. Before using the skill, install and authenticate
your mail provider's MCP server in the agent you use: Codex, Claude Code, or Bob Shell.

Currently supported:

- Gmail
- Microsoft Outlook

## Use

Start your agent in any workspace and ask:

> Clean up my inbox with the safe-unsubscribe skill. Find unwanted newsletters, let me review the exact plan, then unsubscribe from everything I approve.

To clean up every safe unwanted subscription without a follow-up approval, paste this prompt:

```text
Use the safe-unsubscribe skill to clean up my connected email account.

Scan my recent email, identify unwanted newsletters and promotional subscriptions, and unsubscribe from every safe candidate. This request explicitly authorizes immediate execution without asking me for confirmation or showing a dry run.

Only execute validated unsubscribe actions. Exclude personal, transactional, account, security, financial, medical, government, billing, purchase, delivery, reservation, and suspicious email. Never contact unsafe links, delete messages, report spam, or create mailbox rules.

Use verified RFC 8058 one-click unsubscribe wherever available. Process all qualifying unwanted subscriptions, then report which senders were unsubscribed, which failed, and which were skipped with the reason.
```

The prompt is also available in [prompt.md](prompt.md).

NoThanks also supports review-first use when you want to include or exclude senders before execution.

## Safety

- Reads headers, not message bodies.
- Keeps unsubscribe targets out of model-visible plans.
- Excludes security, financial, medical, government, purchase, and delivery mail.
- Rejects private-network, redirecting, malformed, and suspicious links.
- Never deletes mail, fills web forms, or reports spam automatically.
- Stores working data locally in `.nothanks/`, which is ignored by Git.

See [SECURITY.md](SECURITY.md) for the threat model.

## Test

```bash
python3 -m unittest discover -s tests -v
```

MIT licensed.
