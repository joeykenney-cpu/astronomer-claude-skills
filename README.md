# Astronomer Claude Code Skills

Claude Code skills for the Astronomer sales team. Research accounts, review call history, and get weekly coaching reports — all from within Claude Code.

---

## Skills

### `account-research`
Research any company for Astronomer fit. Pulls data from Exa, Leadfeeder, Common Room, and Gong, then generates a scored AE brief and syncs it to Apollo.

**Run it**: type naturally — `"research Acme Corp, acme.com"` or `"score this account"`

**Output**: Fit score (0–20, letter grade A–D), full AE brief with tech stack, hiring signals, pain points, contacts, prior Gong conversations, website engagement, and outreach hooks. Saves to `~/claude-work/research-assistant/outputs/accounts/` and syncs to Apollo.

```
# Single company
account-research "Acme Corp, acme.com"

# Batch (CSV with company_name, domain columns)
account-research "batch: ~/claude-work/research-assistant/inputs/accounts.csv"
```

**Requires**: Claude Code + at least one data source connected (see [Setup](#setup-account-research))

---

### `account-question`
Ask anything about an account using Gong transcripts and saved research. Answers questions, drafts emails, and saves output for future sessions.

**Run it**: ask naturally — `"what did we discuss with Acme Corp?"` or `"draft a follow-up for Beta Inc"`

```
account-question "Acme Corp — what are their pain points?"
account-question "Beta Inc — draft a follow-up email"
account-question "Gamma LLC — what did we discuss in the last call?"
```

**Requires**: Claude Code + Gong transcript script (see [Setup](#setup-account-question))

---

### `weekly-gong-review`
Weekly call coaching report for an AE. Pulls every call they appeared on (not just ones they hosted), scores 6 dimensions, and links every coaching point to the exact timestamp in the recording.

**Run it**: `/weekly-gong-review`

**Output**: Scorecard (6 dimensions, 1–5, week-over-week trend) · One Thing to Focus On · This Week's Highlight · Cross-Call Patterns · Call-by-Call with exact quotes, deep links, and "Try instead" reframes · Score history

```
/weekly-gong-review                              # current week
/weekly-gong-review week:2026-W09               # specific week
/weekly-gong-review rep:"Alec Dolton"           # different rep
/weekly-gong-review rep:alec.dolton@astronomer.io
```

**Requires**: Claude Code + Gong API credentials (see [Setup](#setup-weekly-gong-review))

---

## Setup

Jump to the skill you want to use:

- [account-research](#setup-account-research)
- [account-question](#setup-account-question)
- [weekly-gong-review](#setup-weekly-gong-review)

---

### Setup: weekly-gong-review

This skill only needs Gong API credentials — no MCP servers required.

**1. Install the skill**

```bash
mkdir -p ~/.claude/skills/weekly-gong-review
cp skills/weekly-gong-review/SKILL.md ~/.claude/skills/weekly-gong-review/SKILL.md
```

Restart Claude Code.

**2. Add Gong API credentials**

Get your Access Key and Secret Key from Gong: **Settings → API → Access Keys**

```bash
# Add to ~/.zshrc or ~/.bash_profile
export GONG_ACCESS_KEY=your_access_key
export GONG_SECRET_KEY=your_secret_key
```

```bash
source ~/.zshrc
```

**3. Run it**

```
/weekly-gong-review
```

Claude will prompt for the rep's Astronomer email on first run, look up their Gong user ID, and cache it. Subsequent runs start immediately.

---

### Setup: account-question

**1. Install the skill**

```bash
mkdir -p ~/.claude/skills/account-question
cp skills/account-question/SKILL.md ~/.claude/skills/account-question/SKILL.md
```

Restart Claude Code.

**2. Set up the Gong transcript script**

```bash
# Install dependencies
pip install requests python-dateutil

# Place the script
cp gong_account_transcripts.py ~/claude-work/gong_account_transcripts.py
```

**3. Add Gong API credentials** (skip if already done for weekly-gong-review)

```bash
# Add to ~/.zshrc or ~/.bash_profile
export GONG_ACCESS_KEY=your_access_key
export GONG_SECRET_KEY=your_secret_key
```

**4. Run it**

```
account-question "Acme Corp — what are their pain points?"
```

---

### Setup: account-research

This skill works with any combination of data sources. Start with just web search and add connections as you get access.

| Source | What it adds | Required? |
|--------|-------------|-----------|
| Claude web search | Company overview, hiring signals, tech stack, news | Built-in — always on |
| **Gong** | Prior call history, pain points, objections, deal stage | Recommended |
| **Leadfeeder** | astronomer.io visit data — which pages, how recently | Recommended |
| **Apollo** | Writes report back to `Account_Research` field in CRM | Recommended |
| Common Room | Known contacts, community activity | Optional |
| Exa AI | More targeted web search with date filtering | Optional |

**1. Install the skill**

```bash
mkdir -p ~/.claude/skills/account-research
cp skills/account-research/SKILL.md ~/.claude/skills/account-research/SKILL.md
```

Also copy the prompt templates:

```bash
mkdir -p ~/claude-work/research-assistant/prompts
cp prompts/01_fit_scoring.md ~/claude-work/research-assistant/prompts/
cp prompts/02_account_research.md ~/claude-work/research-assistant/prompts/
```

Restart Claude Code.

**2. Connect data sources**

Set up whichever ones you have access to:

<details>
<summary><strong>Gong</strong></summary>

```bash
claude mcp add --transport http gong https://mcp.gong.io/mcp
```

Also set up the Gong transcript script (same as account-question setup above).

</details>

<details>
<summary><strong>Apollo</strong></summary>

```bash
claude mcp add --transport http apollo https://mcp.apollo.io/mcp
```

```bash
# Add to ~/.zshrc or ~/.bash_profile
export APOLLO_API_KEY=your_apollo_api_key
```

</details>

<details>
<summary><strong>Leadfeeder</strong></summary>

1. Get your API token from Leadfeeder → Settings → API Tokens
2. Place the MCP server from `mcp-servers/leadfeeder/` in this repo:

```bash
mkdir -p ~/.claude/mcp-servers/leadfeeder
cp mcp-servers/leadfeeder/index.js ~/.claude/mcp-servers/leadfeeder/
cd ~/.claude/mcp-servers/leadfeeder && npm install
```

3. Register it:

```bash
claude mcp add leadfeeder --scope user \
  -e LEADFEEDER_API_TOKEN=your_token \
  -- node ~/.claude/mcp-servers/leadfeeder/index.js
```

</details>

<details>
<summary><strong>Common Room (optional)</strong></summary>

```bash
claude mcp add --transport http commonroom https://mcp.commonroom.io/mcp
```

</details>

<details>
<summary><strong>Exa AI (optional)</strong></summary>

```bash
npm install -g exa-mcp-server
claude mcp add --transport stdio exa -- npx exa-mcp-server
```

```bash
# Add to ~/.zshrc or ~/.bash_profile
export EXA_API_KEY=your_exa_api_key
```

</details>

**3. Verify connections**

```bash
claude mcp list
```

**4. Create your account list** (for batch mode)

Export from Salesforce: Reports → New Report → Accounts → add Account Name + Website → Export CSV. Save it as:

```
~/claude-work/research-assistant/inputs/accounts.csv
```

The file needs two columns:

```csv
company_name,domain
Acme Corp,acme.com
Beta Inc,betainc.io
```

**5. Run it**

```
account-research "Acme Corp, acme.com"
account-research "batch: ~/claude-work/research-assistant/inputs/accounts.csv"
```

Reports save to `~/claude-work/research-assistant/outputs/accounts/<company>/report.md` and sync to Apollo automatically.

---

## Technical Notes

<details>
<summary>Apollo integration details</summary>

- Reports write to the `Account_Research` custom field (field ID: `6998b33edacda9000deb48ca`) using `typed_custom_fields` — the name-keyed `custom_fields` format silently ignores writes
- Account lookup uses name search + domain validation to avoid writing to the wrong record

</details>

<details>
<summary>Gong transcript cache</summary>

The transcript script uses a two-tier cache:
1. **Global index** at `~/claude-work/gong-cache/all_calls/calls.json` — slim records synced incrementally on each query
2. **Per-account transcripts** — full text fetched and cached separately per account

Optional daily sync cron (recommended for large Gong instances):

```bash
# crontab -e
0 6 * * * python3 ~/claude-work/gong_account_transcripts.py --sync
```

</details>
