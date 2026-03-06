# Astronomer Claude Code Skills

Claude Code skills for Astronomer sales intelligence. Research companies for Apache Airflow fit, score pipeline opportunities, and generate AE briefs — all from within Claude Code.

Built for the Astronomer sales team. The only hard requirement is Claude Code — every data source degrades gracefully, so you'll always get a report. More connections = richer output, but web search alone is enough to get started.

---

## Skills

### `account-research`
Researches a company for Astronomer (Apache Airflow) sales fitness. Runs 4 parallel data collection agents across Exa AI, Leadfeeder, Common Room, and Gong — then generates a scored report and pushes it to Apollo.

**Triggers**: "research [company]", "score [company]", "run batch account research"

**What it produces**:
- **Fit score** (0–20) across 5 dimensions: Orchestration Need · Data Platform Maturity · Stack Evidence · Scale & Compliance · Buying Signals
- **Letter grade** (A/B/C/D) and confidence level (HIGH/MEDIUM/LOW)
- **Full AE brief**: company overview, tech stack, hiring signals, pain points, key contacts, prior Gong conversations, website engagement, outreach hooks, persona talking points
- **Changelog** tracking score changes across re-runs
- **Apollo sync**: writes the full report to the `Account_Research` field in Apollo automatically

**Usage**:
```
# Single company
account-research "Acme Corp, acme.com"

# Batch mode (CSV with company_name, domain columns)
account-research "batch: ~/claude-work/research-assistant/inputs/accounts.csv"
```

---

### `account-question`
Answers any question about an account using Gong call transcripts and saved account files. Loads prior research and call history, answers the question, and saves output for future sessions.

**Triggers**: "what did we talk about with [company]", "what's going on with [account]", "draft an email for [account]", any question about calls/transcripts/deal status/pain points

**Usage**:
```
account-question "Iron Mountain — what are their pain points?"
account-question "BuildingMinds — draft a follow-up email"
account-question "Figure — what did we discuss in the last call?"
```

---

### `weekly-gong-review`
Generates a weekly call coaching report for an AE. Pulls every call they appeared on (not just calls they hosted), scores performance across 6 dimensions, surfaces coachable moments with deep links to the exact timestamp in each recording, and tracks week-over-week trends.

**Triggers**: `/weekly-gong-review`

**What it produces**:
- **Scorecard** — 6 dimensions scored 1–5 with trend vs. prior week: Discovery Depth · Next Step Quality · Talk Ratio · Technical Confidence · Competitive Handling · Multi-threading
- **One Thing to Focus On** — single highest-leverage behavioral change for the week, with a specific call example
- **This Week's Highlight** — exact quote from a strong moment, linked to the timestamp
- **Cross-Call Patterns** — themes seen in 2+ calls (highest coaching signal)
- **Call-by-Call** — what worked, what to work on, and a "Try instead" reframe — all with exact quotes and deep links
- **Score History** — rolling 4-week trend table

**Usage**:
```
# Review the current week
/weekly-gong-review

# Review a specific week
/weekly-gong-review week:2026-W09

# Review a different rep
/weekly-gong-review rep:"Alec Dolton"
/weekly-gong-review rep:alec.dolton@astronomer.io
```

**Requirements**:
- Gong API credentials (`$GONG_ACCESS_KEY` and `$GONG_SECRET_KEY` — see setup below)
- No MCP connections needed — uses the Gong REST API directly

**Install**:
```bash
mkdir -p ~/.claude/skills/weekly-gong-review
cp skills/weekly-gong-review/SKILL.md ~/.claude/skills/weekly-gong-review/SKILL.md
```

On first run, Claude will prompt for the rep's Astronomer email address, look up their Gong user ID, and cache it — subsequent runs skip this step entirely.

---

## Setup

### 1. Install the skills

```bash
mkdir -p ~/.claude/skills/account-research ~/.claude/skills/account-question ~/.claude/skills/weekly-gong-review
cp skills/account-research/SKILL.md ~/.claude/skills/account-research/SKILL.md
cp skills/account-question/SKILL.md ~/.claude/skills/account-question/SKILL.md
cp skills/weekly-gong-review/SKILL.md ~/.claude/skills/weekly-gong-review/SKILL.md
```

Restart Claude Code — the skills will appear automatically.

### 2. Set up the file structure

The skills expect this directory layout under `~/claude-work/`:

```
~/claude-work/
├── gong_account_transcripts.py        # Gong transcript script (see below)
├── gong-cache/                        # Auto-created by Gong script
│   └── all_calls/
│       └── calls.json                 # Global call index
└── research-assistant/
    ├── prompts/
    │   ├── 01_fit_scoring.md          # Fit scoring rubric ← copy from this repo
    │   └── 02_account_research.md     # AE brief template ← copy from this repo
    ├── inputs/
    │   └── accounts.csv               # Your batch input list (company_name, domain)
    └── outputs/
        └── accounts/
            └── <company_slug>/
                ├── report.md          # Generated per-company report
                └── interactions.md    # Email drafts, notes, follow-up actions
```

Create the directory structure and copy the prompts:

```bash
mkdir -p ~/claude-work/research-assistant/{prompts,inputs,outputs/accounts}
cp prompts/01_fit_scoring.md ~/claude-work/research-assistant/prompts/
cp prompts/02_account_research.md ~/claude-work/research-assistant/prompts/
```

Create your account list at `~/claude-work/research-assistant/inputs/accounts.csv`. The file needs two columns — `company_name` and `domain`.

**Getting the list**: Export a report from Salesforce with at least the Account Name and Website columns, then save it as a CSV. In Salesforce: Reports → New Report → Accounts → add the columns you want → Export → CSV format.

The file should look like this:

```csv
company_name,domain
Acme Corp,acme.com
Beta Inc,betainc.io
Gamma LLC,gamma.io
```

The `domain` column is used to pull website visit data from Leadfeeder and to match the correct Apollo record when writing reports back — so make sure it's the company's primary website domain (not a redirect or CDN domain).

### 3. Set up the Gong transcript script

The skills call a local Python script to fetch Gong call transcripts. Get it from the [claude-work repo](https://github.com/joeykenney-cpu/claude-work/tree/main/Gong-transcript-search-skill) and place it at `~/claude-work/gong_account_transcripts.py`.

The script requires Python 3 and the following dependencies:

```bash
pip install requests python-dateutil
```

Set your Gong API credentials as environment variables (add to `~/.zshrc` or `~/.bashrc`):

```bash
export GONG_ACCESS_KEY=your_gong_access_key
export GONG_SECRET_KEY=your_gong_secret_key
```

Get these from Gong → Settings → API → Access Keys. These credentials are used by both the transcript script and the `weekly-gong-review` skill.

### 4. Connect MCP servers (all optional)

Every connection below is optional. With nothing connected, the skill uses Claude's built-in web search and still produces a fit score, tech stack analysis, hiring signals, and outreach brief. Each connection you add makes the output richer:

| Connection | What it adds |
|------------|-------------|
| **Exa** | More targeted web searches with date filtering — marginal improvement over built-in search |
| **Gong** | Prior call history, pain points, objections, deal stage — highest value add |
| **Leadfeeder** | Website visit intent — which pages, how recently |
| **Common Room** | Known contacts and community activity |
| **Apollo** | Writes the report back to the `Account_Research` field in your CRM |

Set up whichever ones you have access to:

---

#### Apollo

Apollo is used to look up accounts and write research reports to the `Account_Research` field.

1. Get your Apollo API key from Apollo → Settings → Integrations → API Keys
2. Add the MCP server:

```bash
claude mcp add --transport http apollo https://mcp.apollo.io/mcp
```

Claude will open a browser window to complete OAuth authorization.

3. Set your API key as an env var (also used by the skill for direct REST calls):

```bash
# Add to ~/.zshrc or ~/.bashrc
export APOLLO_API_KEY=your_apollo_api_key
```

---

#### Gong

Gong is used to search past call transcripts and extract conversation intelligence.

```bash
claude mcp add --transport http gong https://mcp.gong.io/mcp
```

Claude will open a browser window to complete OAuth authorization. Use your Gong workspace credentials.

---

#### Common Room (optional)

Common Room is used to look up contacts, community activity, and website visit data. **This connection is optional** — if Common Room isn't set up, the skill skips that data source and generates the report from the remaining sources. Contact intelligence will be limited to what surfaces from Gong transcripts and web research.

To connect Common Room:

```bash
claude mcp add --transport http commonroom https://mcp.commonroom.io/mcp
```

Claude will open a browser window to complete OAuth authorization.

---

#### Exa AI (optional)

Exa is used for web research — company overviews, hiring signals, engineering blogs, news, and job postings. **This connection is optional** — if Exa isn't set up, the skill automatically falls back to Claude's built-in web search for all the same queries. Results are equivalent; Exa just provides more targeted filtering (e.g., date ranges, category filters on job postings).

To connect Exa for better results:

1. Get your Exa API key from [dashboard.exa.ai](https://dashboard.exa.ai)
2. Install the Exa MCP server:

```bash
npm install -g exa-mcp-server
claude mcp add --transport stdio exa -- npx exa-mcp-server
```

3. Set your API key:

```bash
# Add to ~/.zshrc or ~/.bashrc
export EXA_API_KEY=your_exa_api_key
```

---

#### Leadfeeder

Leadfeeder is used to pull website visit data — which companies are visiting astronomer.io, what pages they're viewing, and how recently.

1. Get your Leadfeeder API token from Leadfeeder → Settings → API Tokens
2. Download the MCP server script from [this repo's `mcp-servers/leadfeeder/`](mcp-servers/leadfeeder/) and place it at `~/.claude/mcp-servers/leadfeeder/index.js`
3. Install dependencies:

```bash
cd ~/.claude/mcp-servers/leadfeeder
npm install
```

4. Register the server with Claude Code:

```bash
claude mcp add leadfeeder --scope user \
  -e LEADFEEDER_API_TOKEN=your_token_here \
  -- node ~/.claude/mcp-servers/leadfeeder/index.js
```

---

### 5. Verify connections

After setup, confirm all MCP servers are registered:

```bash
claude mcp list
```

You should see: `apollo`, `gong`, `commonroom`, `exa`, `leadfeeder`

---

### 6. Export your account list from Salesforce

Once everything above is set up, pull the list of accounts you want to research:

1. In Salesforce, go to **Reports → New Report → Accounts**
2. Add at minimum: **Account Name** and **Website**
3. Filter to your territory or book of business
4. Click **Export → CSV**
5. Rename the columns in the file to `company_name` and `domain`, then save it to:

```
~/claude-work/research-assistant/inputs/accounts.csv
```

---

### 7. Run research

Open Claude Code and run:

```
# Single account
account-research "Acme Corp, acme.com"

# Full batch (all accounts in your CSV)
account-research "batch: ~/claude-work/research-assistant/inputs/accounts.csv"
```

Reports are saved to `~/claude-work/research-assistant/outputs/accounts/<company>/report.md` and written back to the `Account_Research` field in Apollo automatically.

---

## Data Sources

| Source | What it provides |
|--------|-----------------|
| **Exa AI** | Company research, orchestration/pipeline evidence, hiring signals, engineering blogs, product announcements, vendor case studies, job descriptions |
| **Leadfeeder** | astronomer.io website visit data — which pages, how often, how recently (Astronomer account ID: 281783) |
| **Common Room** | Community contacts, recent activity, website visits from known contacts |
| **Gong** | Prior Astronomer call transcripts — pain points, objections, tech stack mentions, deal stage |
| **Apollo** | Account lookup and research report storage (write-back to `Account_Research` field) |

---

## Apollo Notes

- Reports are written to the `Account_Research` custom field (field ID: `6998b33edacda9000deb48ca`) using `typed_custom_fields` — the name-keyed `custom_fields` format silently ignores writes
- Account lookup uses name search + domain validation before writing — avoids writing to the wrong account (the `q_organization_domain` API parameter is unreliable for some domains)

---

## Batch Input Format

CSV with a header row:

```csv
company_name,domain
Acme Corp,acme.com
Beta Inc,betainc.io
```

---

## Gong Cache

The Gong transcript script uses a two-tier cache:

1. **Global index** at `~/claude-work/gong-cache/all_calls/calls.json` — slim records (id, date, title, account name, participants). Synced incrementally on each query.
2. **Per-account transcripts** cached separately — full text fetched only for matched accounts.

To set up a daily sync cron (optional but recommended for large Gong instances):

```bash
# Add to crontab (crontab -e):
0 6 * * * python3 ~/claude-work/gong_account_transcripts.py --sync
```
