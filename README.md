# Astronomer Claude Code Skills

Claude Code skills for Astronomer sales intelligence. Research companies for Apache Airflow fit, score pipeline opportunities, and generate AE briefs — all from within Claude Code.

## Skills

### `account-research`
Researches a company for Astronomer (Apache Airflow) sales fitness. Runs 4 parallel data collection agents across Exa AI, Leadfeeder, Common Room, and Gong — then generates a scored report and pushes it to Apollo.

**Triggers**: "research [company]", "score [company]", "run batch account research"

**What it produces**:
- **Fit score** (0–20) across 5 dimensions: Orchestration Need · Data Platform Maturity · Stack Evidence · Scale & Compliance · Buying Signals
- **Letter grade** (A/B/C/D) and confidence level (HIGH/MEDIUM/LOW)
- **Full AE brief**: company overview, tech stack, hiring signals, pain points, key contacts, prior conversations, website engagement, outreach hooks, persona talking points
- **Changelog** tracking score changes across re-runs
- **Apollo sync**: writes the full report to a custom `Account_Research` field in Apollo

**Usage**:
```
# Single company
account-research "Acme Corp, acme.com"

# Batch (CSV with company_name, domain columns)
account-research "batch: /path/to/accounts.csv"
```

---

### `account-question`
Answers any question about an account using Gong call transcripts and saved account files. Loads prior research reports, fetches call history, and saves the answer for future reference.

**Triggers**: "what did we talk about with [company]", "what's going on with [account]", "draft an email for [account]", any question about calls/transcripts/deal status

**What it does**:
1. Loads existing `report.md` and `interactions.md` for the account
2. Fetches Gong call transcripts via a two-tier cache (global call index + per-account transcripts)
3. Answers the question using all available context
4. Saves the output to `interactions.md` for future sessions

**Usage**:
```
account-question "Iron Mountain — what are their pain points?"
account-question "BuildingMinds — draft a follow-up email after the POV call"
account-question "Figure — what did we discuss in the last call?"
```

---

## Data Sources

| Source | What it provides |
|--------|-----------------|
| **Exa AI** | Company research, orchestration/pipeline evidence, hiring signals, engineering blogs, product announcements, vendor case studies, job posting details |
| **Leadfeeder** | astronomer.io website visit data — which pages, how often, how recently |
| **Common Room** | Community contacts, recent activity, website visits from known contacts |
| **Gong** | Prior Astronomer call transcripts — pain points, objections, tech stack mentions, deal stage |

---

## Requirements

- [Claude Code](https://claude.ai/code) with MCP servers configured for:
  - Exa AI (`mcp__exa__*`)
  - Leadfeeder (`mcp__leadfeeder__*`)
  - Common Room (`mcp__commonroom__*`)
  - Gong (`mcp__gong__*`)
- Apollo REST API key (`$APOLLO_API_KEY` env var) for account sync
- Gong transcript script at `~/claude-work/gong_account_transcripts.py` — see [Gong-transcript-search-skill](https://github.com/joeykenney-cpu/claude-work/tree/main/Gong-transcript-search-skill)
- Output directories:
  ```
  ~/claude-work/research-assistant/prompts/   # scoring + research prompt templates
  ~/claude-work/research-assistant/outputs/   # reports saved here
  ```

---

## Installation

1. Copy the skill files to your Claude Code skills directory:
   ```bash
   mkdir -p ~/.claude/skills/account-research ~/.claude/skills/account-question
   cp skills/account-research/SKILL.md ~/.claude/skills/account-research/SKILL.md
   cp skills/account-question/SKILL.md ~/.claude/skills/account-question/SKILL.md
   ```

2. Restart Claude Code — the skills will appear automatically.

3. Update the constants in each `SKILL.md` to match your environment:
   - Leadfeeder account ID
   - Output directory paths
   - Gong script path
   - Apollo field ID (if different)

---

## Apollo Notes

The skills write research reports to an `Account_Research` custom field in Apollo using `typed_custom_fields` (keyed by field UUID). Name-keyed `custom_fields` silently ignores writes — use the field UUID.

Apollo account lookup uses name search + explicit domain validation (`account.domain == target_domain`) to avoid writing to the wrong account. The `q_organization_domain` API parameter is unreliable and can match CDN/infrastructure owners instead of the actual company.
