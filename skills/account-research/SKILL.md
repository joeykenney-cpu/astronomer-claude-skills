---
name: account-research
description: Research a company for Astronomer sales fitness using Exa AI (or built-in web search), Leadfeeder, Common Room, and Gong. Generates a fit score and AE brief. Exa and Common Room are optional — the skill falls back gracefully without them. Use when the user asks to research an account, score a company, or run batch account research.
version: 1.0.0
---

# Account Research Orchestrator

Research companies for Astronomer (Apache Airflow) sales fitness using four data sources: Exa AI (public research), Leadfeeder (website visit intent), Common Room (community/contact intelligence), and Gong (prior call history).

## Input
The user has provided: {{args}}

- Single company: `{COMPANY}, {DOMAIN}` (e.g., "Acme Corp, acme.com")
- Batch mode: `batch: /path/to/file.csv` (CSV with columns: company_name, domain)

## Constants
- **Leadfeeder Account ID**: `281783`
- **Prompts Directory**: `~/claude-work/research-assistant/prompts/`
- **Output Directory**: `~/claude-work/research-assistant/outputs/accounts/`

---

## SINGLE COMPANY MODE

### Step 1: Parse Input
Extract `COMPANY_NAME` and `DOMAIN`. If only a name is given, use web search to find the domain.

### Step 2: Pre-flight Checks

Run before spawning agents:

**a) Gong index pre-check**:
```bash
python3 -c "
import json, os, sys
with open(os.path.expanduser('~/claude-work/gong-cache/all_calls/calls.json')) as f:
    calls = json.load(f)
matches = [c for c in calls if 'COMPANY_NAME'.lower() in (c.get('crm_account_name') or '').lower()]
print(f'GONG_MATCH: {len(matches)} calls found')
" 2>/dev/null || echo "GONG_MATCH: index unavailable"
```
If `0 calls found`, set `GONG_HAS_CALLS=false` — skip Gong in Agent 2 and record "No prior Gong calls found. Cold outreach." If index unavailable, run Gong as normal.

**b) Apollo key check**:
```bash
[ -n "$APOLLO_API_KEY" ] && echo "APOLLO: key set" || echo "APOLLO: no key — will skip Step 8"
```

### Step 3: Collect Data (2 Parallel Agents)

Launch both agents simultaneously using the Agent tool with subagent_type="general-purpose":

#### Agent 1: Public Research (Exa AI preferred, built-in web search as fallback)

If `mcp__exa__*` tools are available, use them. Otherwise, use Claude's built-in web search with the same queries.

Run these searches (parallel where possible):

1. **Company Research**: `mcp__exa__company_research_exa(companyName=COMPANY_NAME)`

2. **Orchestration/Pipeline Evidence**:
   ```
   mcp__exa__web_search_advanced_exa(
     query="{COMPANY_NAME} data pipeline orchestration airflow dagster prefect",
     startPublishedDate=[12 months ago], numResults=5
   )
   ```

3. **Hiring Signals**:
   ```
   mcp__exa__web_search_advanced_exa(
     query="{COMPANY_NAME} hiring data engineer platform engineer",
     category="company", startPublishedDate=[6 months ago], numResults=5
   )
   ```

4. **Recent News**:
   ```
   mcp__exa__web_search_exa(query="{COMPANY_NAME} corporate strategy news 2025 2026", numResults=3)
   ```

5. **Website Crawl**: `mcp__exa__crawling_exa(url="https://{DOMAIN}", maxCharacters=5000)`

6. **Engineering & Data Blog Posts**:
   ```
   mcp__exa__web_search_advanced_exa(
     query="{COMPANY_NAME} engineering blog data infrastructure pipeline platform",
     startPublishedDate=[18 months ago], numResults=5
   )
   ```

7. **Product Announcements**:
   ```
   mcp__exa__web_search_advanced_exa(
     query="{COMPANY_NAME} product launch announcement new feature release",
     startPublishedDate=[12 months ago], numResults=3
   )
   ```

8. **Case Studies & Third-Party Mentions**:
   ```
   mcp__exa__web_search_advanced_exa(query="{COMPANY_NAME} case study customer story", numResults=5)
   mcp__exa__web_search_advanced_exa(
     query="{COMPANY_NAME} Snowflake OR Databricks OR dbt OR AWS OR Google Cloud OR Azure case study OR customer OR partner",
     numResults=5
   )
   ```

9. **Job Description Details** — crawl the top 1-2 relevant data/platform engineering job postings found in search 3:
   ```
   mcp__exa__crawling_exa(url="[JOB_POSTING_URL]", maxCharacters=5000)
   ```
   Skip if no relevant postings found.

#### Agent 2: Internal Signals (Leadfeeder + Common Room + Gong)

Run all three lookups. Skip Gong if `GONG_HAS_CALLS=false`.

**Leadfeeder** — paginate up to 5 pages to find a match:
```
mcp__leadfeeder__get_leads(account_id="281783", start_date=[6mo ago], end_date=[today], page_size=100, page=1)
```
Match by name or domain against `DOMAIN`. If found:
```
mcp__leadfeeder__get_lead(account_id="281783", lead_id=MATCHED_LEAD_ID)
mcp__leadfeeder__get_lead_visits(account_id="281783", lead_id=MATCHED_LEAD_ID, start_date=[6mo ago], end_date=[today])
```
Keep only: `lead_id`, `name`, `website`, `visit_count`, `last_visited_at`, and per-visit `url`/`date`/`duration`.

**Common Room** (if connected) — run in parallel with Leadfeeder:

1. Org lookup:
   ```
   mcp__commonroom__commonroom_list_objects(
     objectType="Organization",
     filter={type:"and", clauses:[{type:"stringFilter", field:"companyWebsite", params:{op:"like", value:"{DOMAIN}"}}]},
     properties=["about","employees","location","subIndustry","revenueRangeMin","revenueRangeMax","leadScores","topContacts","contactsCount","tags","researchResults"],
     limit=1
   )
   ```

2. Contacts (if org found):
   ```
   mcp__commonroom__commonroom_list_objects(
     objectType="Contact",
     filter={type:"and", clauses:[{type:"stringFilter", field:"companyWebsite", params:{op:"like", value:"{DOMAIN}"}}]},
     properties=["primaryEmail","title","fullName","recentActivities","recentWebPages","recentWebVisitsNumber","leadScores","profiles","sparkSummary"],
     sort="latest_activity", direction="desc", limit=10
   )
   ```

3. Recent activity (if org found, use orgId):
   ```
   mcp__commonroom__commonroom_list_objects(
     objectType="Activity",
     filter={type:"and", clauses:[
       {type:"stringFilter", field:"orgId", params:{op:"eq", value:"{ORG_ID}"}},
       {type:"dateRangeFilter", field:"activityTime", params:{op:"in", value:"P90D", min:null, max:null}}
     ]},
     properties=["content","url","activityTime","providerName"],
     sort="activityTime", direction="desc", limit=20
   )
   ```

4. Website visits (if contacts found):
   ```
   mcp__commonroom__commonroom_list_objects(
     objectType="WebsiteVisit",
     filter={type:"and", clauses:[
       {type:"and", target:"Contact", objectConfigId:null, targetAssocPaths:null,
        clauses:[{type:"stringFilter", field:"companyWebsite", params:{op:"like", value:"{DOMAIN}"}}]},
       {type:"dateRangeFilter", field:"visitTime", params:{op:"in", value:"P90D", min:null, max:null}}
     ]},
     properties=["url"], limit=20
   )
   ```

**Gong** (only if `GONG_HAS_CALLS=true` or index was unavailable):
```bash
python3 -u ~/claude-work/gong_account_transcripts.py "COMPANY_NAME" --stdout
```
Try name variations if no match. The script automatically fetches email history alongside transcripts (gracefully skipped if Gong email integration is not configured). Extract from both calls and emails: call dates, participants, topics, pain points, tech stack mentions, deal stage, follow-up items, and any email thread context (subject lines, email direction, key content).

### Step 4: Assemble RAW INTELLIGENCE Block

```markdown
---
# RAW INTELLIGENCE: {COMPANY_NAME} ({DOMAIN})
# Collected: {TODAY_DATE}
---

## SOURCE: EXA AI

### Company Research
[company_research_exa results]

### Orchestration & Pipeline Evidence
[search results]

### Hiring Signals
[search results]

### Recent News
[search results]

### Website Content
[crawl results]

### Engineering & Data Blog Posts
[titles, URLs, key excerpts about data stack and infrastructure]

### Product Announcements
[recent product launches or platform changes]

### Case Studies & Third-Party Mentions
[vendor case studies featuring this company — often reveal stack details]

### Job Description Details
[crawled job posting text with requirements and tools. "No relevant job postings crawled." if none.]

---

## SOURCE: LEADFEEDER

### Lead Match
[Found / Not Found]

### Visit Summary
[total visits, date range, last_visited_at]

### Page Visits
[list of URLs with dates — flag any /pricing, /demo, /astro, /docs visits]

---

## SOURCE: COMMON ROOM

### Organization Profile
[employees, revenue range, industry, lead score, tags. Or "Not found."]

### Contacts (Top 10 by recent activity)
[Name | Title | Email | Recent activity summary]

### Recent Community Activity (Last 90 Days)
[activity content, source, date]

### Website Visits (Last 90 Days)
[list of visited URLs]

---

## SOURCE: GONG

### Prior Conversations
[Found / Not Found — if not found: "No prior Gong calls found. Cold outreach."]

### Call Summary
[each call: date, participants, 2-3 sentence summary]

### Key Intelligence from Calls
[pain points, objections, decision-makers, deal stage, follow-up items]

### Tech Stack from Calls
[tools mentioned, tagged with call date]

### Email History
[Found / Not Found — if not available: "Email integration not configured in this workspace."]
[If found: list emails with date, direction (inbound/outbound), subject, and key content excerpt]

### Full Transcripts
[full transcript text]
```

### Step 5: Generate Fit Score + Account Research (Single Pass)

Read both prompt templates:
- `~/claude-work/research-assistant/prompts/01_fit_scoring.md`
- `~/claude-work/research-assistant/prompts/02_account_research.md`

**Context order** (stable content first for prompt caching):
1. Prompt template 1 (fit scoring rubric)
2. Prompt template 2 (AE brief template)
3. RAW INTELLIGENCE block

In a single generation pass, produce the fit score section followed by the account research section.

### Step 6: Compose Final Report

**Generate company slug**: lowercase, spaces → underscores, remove special chars.

**Changelog detection** — check for existing report at `~/claude-work/research-assistant/outputs/accounts/{company_slug}/report.md`. If found, extract prior score/grade/confidence and changelog entries. Generate a new changelog entry if any significant change:
- Score changed ≥2 points
- Grade letter changed
- New Leadfeeder visits to pricing/demo/docs pages
- New hiring signals mentioning Airflow/orchestration/data platform
- New Common Room contacts with VP Eng / Head of Data titles
- New funding or acquisitions

```markdown
# Account Research Report: {COMPANY_NAME}

**Generated**: {TODAY_DATE}
**Website**: https://{DOMAIN}
**Sources**: Exa AI ✓/✗ | Leadfeeder ✓/✗ | Common Room ✓/✗ | Gong ✓/✗

---

[Fit Score section]

---

[Account Research section]

---

## Changelog

### {TODAY_DATE}
- [change or "First research generated. Grade: {GRADE}, Score: {SCORE}/20, Confidence: {CONFIDENCE}"]

[prior changelog entries preserved below, newest first]
```

### Step 7: Save Report

Overwrite: `~/claude-work/research-assistant/outputs/accounts/{company_slug}/report.md`

### Step 8: Update Apollo Account_Research Field

Skip entirely if no `APOLLO_API_KEY` (from pre-flight). Log "Apollo sync skipped — no API key."

- **Field ID**: `6998b33edacda9000deb48ca`
- Use `typed_custom_fields` (keyed by field ID), NOT `custom_fields` (silently ignored)

1. Find account — search by name, confirm by domain:
   ```bash
   curl -s -X POST "https://api.apollo.io/v1/accounts/search" \
     -H "Content-Type: application/json" \
     -d "{\"api_key\": \"$APOLLO_API_KEY\", \"q_organization_name\": \"{COMPANY_NAME}\", \"per_page\": 10}"
   ```
   Find the result where `account.domain == "{DOMAIN}"`. If none match, skip and log: "Apollo: No account found matching domain {DOMAIN}."

2. Write report:
   ```bash
   REPORT=$(cat ~/claude-work/research-assistant/outputs/accounts/{COMPANY_SLUG}/report.md)
   curl -s -X PUT "https://api.apollo.io/v1/accounts/{ACCOUNT_ID}" \
     -H "Content-Type: application/json" \
     -d "{\"api_key\": \"$APOLLO_API_KEY\", \"typed_custom_fields\": {\"6998b33edacda9000deb48ca\": $(echo "$REPORT" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')}}"
   ```

### Step 9: Present Results

Display the final report. Highlight fit score/grade, notable buying signals, and changelog if this is a re-run.

---

## BATCH MODE

### Batch Step 1: Load CSV
Columns: `company_name`, `domain`. Be flexible with header names.

### Batch Step 2: Pre-fetch Leadfeeder Data

Pull all leads upfront (up to 20 pages of 100):
```
mcp__leadfeeder__get_leads(account_id="281783", start_date=[6mo ago], end_date=[today], page_size=100, page=N)
```
Stop when a page returns <100 results. Store only: `id`, `name`, `website`, `visit_count`, `last_visited_at`.

### Batch Step 3: Check for Resume
Read `~/claude-work/research-assistant/outputs/batch_summary.csv`. Skip companies where `last_updated` matches today.

### Batch Step 4: Process Companies Sequentially

For each unprocessed company:
1. Run single-company flow (Steps 2–9), matching Leadfeeder from the pre-fetched list.
2. Update batch summary CSV after each company.
3. Pause 2 seconds between companies.

### Batch Step 5: Chunking
If CSV has >50 companies: process in chunks of 50, pause 10 seconds between chunks.

### Batch Step 6: Generate Batch Summary

`~/claude-work/research-assistant/outputs/batch_summary.csv`:
```csv
company,domain,score,grade,confidence,score_change,key_change,report_path,last_updated
```
`score_change`: `+N`, `-N`, `0`, or `NEW`. `key_change`: one-line summary or "No changes".

### Batch Step 7: Batch Summary Output

Display: total processed, grade distribution, top 10 by score, biggest score increases (if re-run), errors.

---

## Graceful Degradation

| Source | Failure Behavior |
|--------|-----------------|
| **Exa AI** | Fall back to Claude's built-in web search. Same queries, equivalent coverage. No confidence penalty. |
| **Common Room** | Key Contacts section: "No Common Room data found." Contact intelligence from Gong/web only. |
| **Leadfeeder** | Buying Signals caps at 1. Note "No website visit data" in Website Engagement section. |
| **Gong calls** | Prior Conversations: "No prior Gong calls found. Cold outreach." |
| **Gong emails** | Email History: "Email integration not configured in this workspace." Calls still used normally. |
| **Apollo** | Skip write-back. Report saves locally. Note "Apollo sync skipped." |
| **Nothing connected** | Run all research via Claude's built-in web search. Report generates with fit score, tech stack, hiring signals, and outreach brief. Confidence: MEDIUM or LOW. |

---

## Important Guidelines

- Report file MUST be under 1,000,000 characters. Truncate verbose sections (crawl, news) if needed — preserve scoring rationale, contacts, and buying signals.
- Every claim must be tagged with its source.
- Preserve all prior changelog entries when re-running.
- In batch mode, save incrementally after each company.
- If slug collision, append a number.

---

**Begin research for:** {{args}}
