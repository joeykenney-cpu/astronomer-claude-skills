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
- Batch force-rerun: `batch: /path/to/file.csv force` — re-researches all companies even if a complete report already exists (use after skill updates to refresh all reports)

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
import json, os, sys, time
company = sys.argv[1]
cache_path = os.path.expanduser('~/claude-work/gong-cache/all_calls/calls.json')
if not os.path.exists(cache_path):
    print('GONG_MATCH: index unavailable')
    sys.exit(0)
age_days = (time.time() - os.path.getmtime(cache_path)) / 86400
if age_days > 7:
    print(f'GONG_MATCH: index stale ({age_days:.0f} days old) — will query API directly')
    sys.exit(0)
with open(cache_path) as f:
    calls = json.load(f)
matches = [c for c in calls if company.lower() in (c.get('crm_account_name') or '').lower()]
print(f'GONG_MATCH: {len(matches)} calls found')
" "{COMPANY_NAME}" 2>/dev/null || echo "GONG_MATCH: index unavailable"
```
If `0 calls found`, set `GONG_HAS_CALLS=false` — skip Gong in Agent 2 and record "No prior Gong calls found. Cold outreach." If index is unavailable or stale (>7 days old), run Gong as normal.

**b) Prompt template check**:
```bash
for f in ~/claude-work/research-assistant/prompts/01_fit_scoring.md \
          ~/claude-work/research-assistant/prompts/02_account_research.md; do
  [ -f "$(eval echo $f)" ] \
    && echo "TEMPLATE OK: $f" \
    || { echo "TEMPLATE MISSING: $f — cannot generate report. Aborting."; exit 1; }
done
```
If either file is missing, stop immediately. Do not proceed — the report will be incomplete without the scoring rubric and AE brief template.

**c) Apollo key check**:
```bash
[ -n "$APOLLO_API_KEY" ] && echo "APOLLO: key set" || echo "APOLLO: no key — will skip Step 8"
```

### Step 3: Collect Data (2 Parallel Agents)

Launch both agents simultaneously using the Agent tool with subagent_type="general-purpose":

#### Agent 1: Public Research (Claude WebSearch + WebFetch as primary; Exa optional)

Use Claude's built-in **WebSearch** and **WebFetch** tools for all queries. If `mcp__exa__*` tools are also available, they can supplement but are not required. Never wait for Exa if WebSearch is already returning results.

**Execute in two batches to maximize parallelism:**

**Batch A — fire ALL of the following simultaneously (no dependencies between them):**

1. **Company Research** — two parallel calls:

   a) **Crunchbase fetch** — derive the slug from the domain (e.g., `bridgebio.com` → `bridge-bio`, `writer.com` → `writer`). Fetch:
   ```
   WebFetch("https://www.crunchbase.com/organization/{slug}")
   ```
   If the slug is uncertain, first run `WebSearch('"{COMPANY_NAME}" site:crunchbase.com/organization', numResults=1)` to find the exact URL, then fetch it.

   b) **General company search**:
   ```
   WebSearch('"{COMPANY_NAME}" company overview employees revenue funding 2025 2026')
   ```

   Extract from both: employee count + growth rate, revenue/funding stage (round + amount + date), industry vertical, business model (is the core product data-intensive?), any tech stack signals, how they describe themselves around data/AI.

2. **Orchestration/Pipeline Evidence** — two parallel searches:
   ```
   WebSearch('"{COMPANY_NAME}" "Apache Airflow" OR "Airflow DAG" OR "data orchestration" OR "dagster" OR "prefect"')
   WebSearch('"{COMPANY_NAME}" data pipeline orchestration airflow dagster prefect after:2025-03-09')
   ```

   Extract from each result: named orchestration tool (Airflow = existing user; Dagster/Prefect = competitor; Luigi/Argo/Kubeflow/custom = opportunity); data volume/scale (copy exact phrases); pipeline frequency (batch/streaming/real-time); migration stories ("moved from X to Y"); architecture signals (data mesh, lakehouse, microservices). Tag every finding with source URL and date.

3a. **Hiring Signals — job posting discovery** — three parallel searches, all in Batch A:

   **Title search** — broad role coverage on major job boards:
   ```
   WebSearch('"{COMPANY_NAME}" site:greenhouse.io OR site:lever.co OR site:ashbyhq.com ("data engineer" OR "data platform" OR "platform engineer" OR "ML engineer" OR "MLOps" OR "analytics engineer" OR "data architect" OR "data infrastructure" OR "data operations" OR "data reliability")')
   ```

   **Tool search** — orchestration mentions regardless of job title:
   ```
   WebSearch('"{COMPANY_NAME}" site:greenhouse.io OR site:lever.co OR site:ashbyhq.com ("Apache Airflow" OR "Airflow DAG" OR dagster OR prefect OR "data orchestration" OR "workflow orchestration")')
   ```
   This catches Airflow requirements embedded in ML Engineer, DevOps, Backend, or Staff Engineer roles that a title-only search would miss.

   **LinkedIn search** — catches postings not on Greenhouse/Lever/Ashby (many mid-market and non-US companies post exclusively here):
   ```
   WebSearch('site:linkedin.com/jobs "{COMPANY_NAME}" ("data engineer" OR "data platform" OR "MLOps" OR "Apache Airflow" OR "data infrastructure")')
   ```

   If all three return fewer than 2 combined results, also include in Batch A:
   ```
   WebSearch('site:{DOMAIN} ("data engineer" OR "data platform" OR "platform engineer" OR "ML engineer" OR "MLOps" OR "analytics engineer" OR "data architect" OR "data infrastructure")')
   ```

4. **Recent News**:
   ```
   WebSearch('"{COMPANY_NAME}" (funding OR acquisition OR "Series" OR layoff OR "new CTO" OR "Chief Data Officer") after:2025-03-09')
   ```

   Extract by type: **funding rounds** (stage + amount + stated use of funds — "investing in data infrastructure" is direct signal); **acquisitions** (especially data/AI companies = stack consolidation need); **leadership hires** (new VP Eng or Chief Data Officer = new buying motion); **layoffs/restructuring** (cost-cutting mode = harder sell); **product launches** (new AI/data product = more pipeline complexity); **partnerships** (cloud provider partnerships reveal stack). Tag each with source URL and date.

5. **Website Crawl**:
   ```
   WebFetch(url="https://{DOMAIN}", maxCharacters=2000)
   ```

   Extract: exact language they use to describe themselves around data/scale/automation; customer segments named (enterprise, SMB, regulated industries); any explicit tool or cloud partner mentions; data-intensity signals (copy verbatim: "real-time", "AI-powered", "processes X transactions"); scale claims ("serving 500 enterprise customers"); whether an Engineering or Platform section exists in the nav.

6. **Engineering & Data Blog Posts — discovery**:
   ```
   WebSearch('"{COMPANY_NAME}" (engineering blog OR "data infrastructure" OR "data platform" OR "pipeline") after:2024-09-09')
   ```

   Note the top 2-3 blog post URLs from the results — they will be fetched in full in Batch B. Do not extract from snippets alone.

7. **Product Announcements**:
   ```
   WebSearch('"{COMPANY_NAME}" ("product launch" OR "we launched" OR "now available" OR "announcing") after:2025-03-09')
   ```

   Extract: what launched; whether it increases data pipeline complexity (new AI feature, real-time capability, new data product = stronger fit signal). Tag with source URL and date.

8. **Case Studies & Third-Party Mentions**:
   ```
   WebSearch('"{COMPANY_NAME}" (Snowflake OR Databricks OR dbt OR AWS OR "Google Cloud" OR Azure) (case study OR customer OR partner)')
   ```

   For each case study found, extract: which vendor published it (confirms they are a customer of that tool); every tool/vendor named in the study; use case described (batch ETL / real-time / ML pipelines / etc.); scale numbers if present; exact business problem language (maps directly to Astronomer use cases). Tag with source URL.

9. **Tech Stack — StackShare**:
   ```
   WebSearch('"{COMPANY_NAME}" site:stackshare.io')
   ```
   If a StackShare profile URL is returned, fetch it:
   ```
   WebFetch(that URL, maxCharacters=3000)
   ```
   Extract: every tool listed, especially Airflow, Spark, dbt, Snowflake, Databricks, Kafka, Flink. If no StackShare profile found, record "No StackShare profile found."

10. **GitHub Org Search**:
   ```
   WebSearch('site:github.com "{COMPANY_NAME}" (airflow OR dbt OR dagster OR prefect OR "data pipeline")')
   ```
   If a company GitHub org URL is returned (e.g., `github.com/company-name`), fetch it (`maxCharacters=3000`). Extract: public repos confirming Airflow DAGs, dbt projects, data engineering tooling, or infrastructure-as-code. A public `airflow-dags`, `data-platform`, or similar repo is the strongest possible tech stack confirmation — treat it as equivalent to a job posting mentioning Airflow. If no GitHub org found, record "No public GitHub org found."

11. **Conference & Community Speaker Signals** — two parallel searches:
   ```
   WebSearch('"{COMPANY_NAME}" (site:airflowsummit.org OR "dbt Coalesce" OR "Data Council" OR "Spark+AI Summit" OR "DataEngConf" OR "PyData")')
   WebSearch('"{COMPANY_NAME}" employee speaker (airflow OR dbt OR spark OR kafka OR "data pipeline") (conference OR summit OR meetup) after:2024-01-01')
   ```
   Extract: speaker name + title; conference name; talk title; tools mentioned; date. A current employee speaking at Airflow Summit or dbt Coalesce is extremely high-confidence stack confirmation — treat as equivalent to a confirmed Airflow mention in a job posting. If nothing found, record "No conference speaker signals found."

**Batch B — fire after Batch A completes (depends on 3a and 6 results):**

3b. **Job Posting Crawls**: From the URLs returned by search 3a, WebFetch up to 4 postings (maxCharacters=5000 each). Prioritize: (1) any role from the tool search that mentions Airflow/Dagster/Prefect directly, (2) data platform / ML platform / MLOps roles, (3) data engineer / analytics engineer / data architect roles. Do not limit to "data engineer" and "platform engineer" titles — any role mentioning orchestration tools is worth crawling regardless of title.

   From each posting extract:
   - **Named tools** — Airflow, Dagster, Prefect, Spark, dbt, Snowflake, Databricks, Kafka, Flink, MLflow, Kubeflow (Airflow = highest signal)
   - **Scale language** — copy verbatim ("managing hundreds of DAGs", "processing 10M events/day")
   - **Orchestration explicitly mentioned** — quote the exact phrase if present
   - **Build vs. maintain framing** — "build our data platform from scratch" = greenfield; "maintain and scale existing pipelines" = rip-and-replace candidate
   - **Cloud platform** — AWS/GCP/Azure (affects Astro positioning)
   - **Pain point language** — verbatim: "reliability", "observability", "SLA", "on-call", "data quality"
   - **Team name** — Data Platform / ML Infrastructure / Data Engineering / MLOps / etc.
   - **Seniority** — Staff/Principal/Director = mature org; entry-level = early stage
   - **Role type** — note if this is a non-traditional role (e.g. ML Engineer, DevOps) that reveals orchestration need

   If 3a returned no relevant posting URLs, run this fallback search instead:
   ```
   WebSearch('"{COMPANY_NAME}" hiring ("data engineer" OR "ML engineer" OR "MLOps" OR "analytics engineer" OR "data architect" OR "platform engineer" OR "data operations") after:2025-09-09')
   ```

6b. **Engineering Blog Fetches**: WebFetch the top 1-2 blog post URLs identified in search 6 (maxCharacters=5000 each).

   Extract from full post text: specific tools named (exact names); scale/volume metrics; architecture decisions verbatim ("we chose X because Y"); pain points described; post date. If no blog post URLs were found in search 6, record "No public engineering blog found — signals lower data platform maturity."

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

   For each contact, assign a value tier based on title:
   - **HIGH** (decision-makers/champions): VP/Director of Engineering, Head/Director of Data, Data Platform Engineer/Manager, Data Architect, ML Platform, Staff/Principal Data Engineer
   - **MED** (users, not buyers): Data Engineer, Analytics Engineer, Data Scientist, Data Analyst
   - **LOW** (not relevant for outreach): Marketing, Sales, Finance, HR, other non-technical roles

   Flag any HIGH-tier contacts visiting Astronomer pages — that's an active buying signal.

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
python3 -u ~/claude-work/gong_account_transcripts.py "{COMPANY_NAME}" --stdout
```
Try name variations if no match. The script automatically fetches email history alongside transcripts (gracefully skipped if Gong email integration is not configured). Extract from both calls and emails: call dates, participants, topics, pain points, tech stack mentions, deal stage, follow-up items, and any email thread context (subject lines, email direction, key content).

**Gong transcript size cap**: If the returned transcripts total more than 30,000 words, keep only the 5 most recent calls and truncate each transcript body to 3,000 words. Preserve all metadata (date, participants, summary). Note the truncation in the RAW INTELLIGENCE block: "Transcripts truncated: kept 5 most recent of N total calls."

### Step 4: Assemble RAW INTELLIGENCE Block

```markdown
---
# RAW INTELLIGENCE: {COMPANY_NAME} ({DOMAIN})
# Collected: {TODAY_DATE}
---

## SOURCE: EXA AI

### Company Research
**Self-description**: [exact language they use about their product/mission]
**Employee count**: [N] (growth rate if available)
**Revenue / Funding stage**: [ARR or round + amount + date]
**Industry vertical**: [fintech / healthcare / logistics / SaaS / etc.]
**Business model**: [is the core product data-intensive? yes/no + one-line reason]
**Tech stack signals**: [any tools mentioned in profile]
**Data/AI positioning**: [do they call themselves data-driven, AI-powered, etc. — quote]

### Orchestration & Pipeline Evidence
For each relevant result:
- **Orchestration tool named**: [Airflow (existing user) / Dagster/Prefect (competitor) / Luigi/Argo/Kubeflow/custom (opportunity) / none found]
- **Data volume/scale**: [exact verbatim phrase — e.g. "processing 10M events/day"]
- **Pipeline frequency**: [batch (daily/hourly) / streaming / real-time / unknown]
- **Migration story**: [moved from X to Y — quote if found]
- **Architecture signals**: [data mesh / lakehouse / microservices / monolith]
- **Source**: [URL — date]

### Hiring Signals
**Job board search method**: [title search / tool search / domain search / fallback]
**Open roles (all data/ML/platform/infra titles)**: [list all role titles found — include ML Eng, MLOps, Analytics Eng, Data Architect, etc.]
**Roles mentioning orchestration tools**: [list any role — regardless of title — that names Airflow/Dagster/Prefect/etc.]
**Key tool requirements (verbatim from JDs)**:
- Orchestration: [Airflow / Dagster / Prefect / none mentioned — quote exact phrase if present]
- Data stack: [dbt / Spark / Snowflake / Databricks / Kafka / Flink / MLflow / etc.]
- Cloud: [AWS / GCP / Azure]
**Scale language (verbatim)**: [exact phrases — e.g. "managing hundreds of DAGs"]
**Orchestration explicitly mentioned**: [Yes — quote / No]
**Build vs. maintain framing**: [greenfield / scaling existing / unknown — quote]
**Pain point language (verbatim)**: [reliability / observability / SLA / on-call / data quality — quote]
**Team name**: [Data Platform / ML Infrastructure / Data Engineering / MLOps / etc.]
**Seniority signal**: [Staff/Principal/Director = mature org / entry-level = early stage]

### Recent News
For each relevant item:
- **Type**: [funding / acquisition / leadership hire / layoff / product launch / partnership]
- **Summary**: [1-2 sentences]
- **Signal for Astronomer**: [what this means — e.g. "Series C = budget for tooling", "new CDO = buying motion likely", "layoffs = cost-cutting mode"]
- **Source + date**: [URL — date]

### Website Content
**Self-description**: [exact language around data/scale/automation]
**Customer segments**: [enterprise / SMB / regulated industries / etc.]
**Tech/partner mentions**: [any tools or cloud logos visible]
**Data-intensity signals**: [verbatim — "real-time", "AI-powered", "processes X transactions"]
**Scale claims**: [verbatim — e.g. "serving 500 enterprise customers"]
**Engineering/Platform section in nav**: [Yes / No]

### Engineering & Data Blog Posts
For each post found:
- **Title + URL + date**:
- **Tools named**: [exact names]
- **Scale/volume metrics**: [if present]
- **Architecture decision**: [verbatim — "we chose X because Y"]
- **Pain points described**: [what problems they were solving]
- **Signal**: [what this tells us about Airflow fit]
[If no engineering blog found: "No public engineering blog found — signals lower data platform maturity."]

### Product Announcements
For each relevant item:
- **Announcement**: [what launched]
- **Data/AI relevance**: [does this increase pipeline complexity? yes/no + reason]
- **Source + date**: [URL — date]

### Case Studies & Third-Party Mentions
For each case study found:
- **Published by**: [Snowflake / dbt / AWS / etc. — confirms they are a customer]
- **Tools/vendors named**: [every tool mentioned]
- **Use case**: [batch ETL / real-time / ML pipelines / etc.]
- **Scale numbers**: [if present]
- **Business problem described**: [verbatim quote — maps to Astronomer use cases]
- **Source URL**:

### GitHub Org
**GitHub org found**: [Yes — URL / No]
**Relevant repos**: [list repo names — e.g. airflow-dags, data-platform, dbt-models, ml-pipelines]
**Stack confirmation**: [tools confirmed from repo names/contents — Airflow / dbt / Spark / etc.]
**Signal**: [e.g. "public airflow-dags repo = confirmed Airflow user" / "No GitHub org found"]

### Conference & Speaker Signals
For each signal found:
- **Speaker name + title**:
- **Conference + date**:
- **Talk title**:
- **Tools mentioned**:
- **Signal**: [e.g. "VP Data Engineering spoke at Airflow Summit 2025 = confirmed Airflow user and champion"]
[If nothing found: "No conference speaker signals found."]

---

## SOURCE: LEADFEEDER

### Lead Match
[Found / Not Found]

### Visit Summary
**Total visits**: [N] | **Date range**: [first–last] | **Last visited**: [date]

### Page Visits
[list of URLs with dates]
**High-intent flags**: [any /pricing, /demo, /astro, /docs, /trial visits — note date and whether repeated]

---

## SOURCE: COMMON ROOM

### Organization Profile
**Employees**: [N] | **Revenue range**: [min–max] | **Industry**: [industry]
**Lead score**: [score] | **Tags**: [list]
**About**: [1-2 sentence summary]

### Contacts (Top 10 by recent activity)
For each contact:
- **Name | Title | Email**
- **Value tier**: [HIGH / MED / LOW — see tier definitions in instructions]
- **Recent activity**: [what they did + date]
- **Astronomer site visits**: [Yes — URLs / No]

### Recent Community Activity (Last 90 Days)
For each activity:
- **Content**: [what they did]
- **Source**: [GitHub / Slack / community / etc.]
- **Signal**: [e.g. "starred apache/airflow repo" = existing Airflow interest]
- **Date**:

### Website Visits (Last 90 Days)
[list of visited URLs — flag /pricing, /demo, /docs, /astro]

---

## SOURCE: GONG

### Prior Conversations
[Found / Not Found — if not found: "No prior Gong calls found. Cold outreach."]

### Call Summary
For each call:
- **Date | Participants (name + title)**
- **Summary**: [2-3 sentences]

### Key Intelligence from Calls
- **Pain points**: [exact quotes where possible]
- **Objections raised**: [what they pushed back on]
- **Decision-makers identified**: [name + title]
- **Deal stage**: [prospecting / discovery / evaluation / negotiation / closed-lost]
- **Follow-up items**: [what was committed to]

### Tech Stack from Calls
[tool: mentioned in call dated X]

### Email History
[Found / Not Found — if not available: "Email integration not configured in this workspace."]
[If found: date | direction (inbound/outbound) | subject | key content excerpt]

### Full Transcripts
[full transcript text]
```

**Size constraint**: The entire RAW INTELLIGENCE block must be under 3,000 words. Fill in only the labeled field values — do NOT paste raw search result snippets, full crawl text, or unprocessed API responses verbatim. If a field has no data, write `[not found]`. Every entry should be a single extracted fact, quote, or short list.

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
- **Signal lost**: if a previously cited high-signal finding is no longer present in this run, note it explicitly — e.g. "Signal lost: Airflow job posting (Senior Data Engineer, cited 2026-01-15) no longer found — likely filled or expired" or "Signal lost: key contact [Name] no longer appears at company." This is critical context for score drops — the changelog entry should explain *why* the score changed, not just *that* it changed.

```markdown
# Account Research Report: {COMPANY_NAME}

**Generated**: {TODAY_DATE}
**Website**: https://{DOMAIN}
**Sources**: Web Search ✓ | Leadfeeder ✓/✗ | Common Room ✓/✗ | Gong ✓/✗

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

Create the directory if it doesn't exist, then write the file:
```bash
mkdir -p ~/claude-work/research-assistant/outputs/accounts/{company_slug}/
```
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

2. Write report and verify success:
   ```bash
   # Truncate for Apollo field limit (~65,000 chars). Drops Full Transcripts first,
   # then hard-truncates if still over. Local report.md is never modified.
   APOLLO_REPORT=$(python3 -c "
   import re, sys
   content = open(sys.argv[1]).read()
   if len(content) <= 60000:
       print(content); sys.exit(0)
   truncated = re.sub(
       r'(### Full Transcripts\n).*',
       r'\1[Truncated — see local report.md for full transcripts]',
       content, flags=re.DOTALL
   )
   if len(truncated) > 60000:
       truncated = truncated[:60000] + '\n\n[Report truncated at 60,000 chars for Apollo field limit]'
   print(truncated)
   " ~/claude-work/research-assistant/outputs/accounts/{COMPANY_SLUG}/report.md)

   RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" -X PUT "https://api.apollo.io/v1/accounts/{ACCOUNT_ID}" \
     -H "Content-Type: application/json" \
     -d "{\"api_key\": \"$APOLLO_API_KEY\", \"typed_custom_fields\": {\"6998b33edacda9000deb48ca\": $(echo "$APOLLO_REPORT" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))' )}}")
   HTTP_STATUS=$(echo "$RESPONSE" | grep "HTTP_STATUS:" | cut -d: -f2)
   if [ "$HTTP_STATUS" = "200" ]; then
     echo "Apollo: write succeeded"
   else
     echo "Apollo: write FAILED — HTTP $HTTP_STATUS"
     echo "$RESPONSE"
   fi
   ```

### Step 9: Present Results

Display the final report. Highlight fit score/grade, notable buying signals, and changelog if this is a re-run.

---

## BATCH MODE

### Batch Step 1: Load CSV
Columns: `company_name`, `domain`. Be flexible with header names.

### Batch Step 2: Pre-fetch Leadfeeder Data

**Check disk cache first** to avoid re-fetching on re-runs:
```bash
python3 -c "
import json, os, time
cache = os.path.expanduser('~/claude-work/leadfeeder-cache/leads.json')
if os.path.exists(cache):
    age_hours = (time.time() - os.path.getmtime(cache)) / 3600
    if age_hours < 24:
        data = json.load(open(cache))
        print(f'LEADFEEDER_CACHE_HIT: {len(data)} leads, {age_hours:.1f}h old')
        exit(0)
print('LEADFEEDER_CACHE_MISS')
"
```

If `LEADFEEDER_CACHE_HIT`: load leads from `~/claude-work/leadfeeder-cache/leads.json` and skip the API calls below.

If `LEADFEEDER_CACHE_MISS`: pull all leads via API (up to 20 pages of 100):
```
mcp__leadfeeder__get_leads(account_id="281783", start_date=[6mo ago], end_date=[today], page_size=100, page=N)
```
Stop when a page returns <100 results. Store only: `id`, `name`, `website`, `visit_count`, `last_visited_at`.

Then save to cache:
```bash
mkdir -p ~/claude-work/leadfeeder-cache/
# Write collected leads list to file:
python3 -c "
import json, os
# leads = [list of {id, name, website, visit_count, last_visited_at} dicts collected above]
with open(os.path.expanduser('~/claude-work/leadfeeder-cache/leads.json'), 'w') as f:
    json.dump(leads, f)
print(f'Cached {len(leads)} leads')
"
```

### Batch Step 3: Generate Slugs + Check for Resume

**Detect force flag**: if the input ends with ` force` (e.g., `batch: /path/file.csv force`), set `FORCE_RERUN=true`. In force mode, all companies are treated as `NEEDS_RUN` regardless of existing report state — skip the SKIP check in step (b). Prior changelog entries are still preserved (the report is re-read before overwriting in Step 6).

For each company in the CSV:

**a) Generate slug upfront** — do this before anything else. Rule: lowercase, spaces → underscores, remove all non-alphanumeric characters except underscores. Then check for collision:
```bash
python3 -c "
import os, re, sys
name = sys.argv[1]
base_slug = re.sub(r'[^a-z0-9_]', '', name.lower().replace(' ', '_'))
slug = base_slug
n = 2
while True:
    path = os.path.expanduser(f'~/claude-work/research-assistant/outputs/accounts/{slug}/report.md')
    if not os.path.exists(path):
        break  # directory is free
    content = open(path).read()
    # Check if the existing report is for the same company (case-insensitive name match)
    if name.lower() in content[:500].lower():
        break  # same company — safe to overwrite
    slug = f'{base_slug}_{n}'
    n += 1
print(slug)
" "{COMPANY_NAME}"
```
Store the result as `COMPANY_SLUG`.

**b) Check for a valid existing report** (skip entirely if `FORCE_RERUN=true`):
```bash
python3 -c "
import os, sys
path = os.path.expanduser('~/claude-work/research-assistant/outputs/accounts/{COMPANY_SLUG}/report.md')
if not os.path.exists(path):
    print('NEEDS_RUN')
    sys.exit(0)
content = open(path).read()
required = ['# Account Research Report:', '**Generated**:', '**Sources**:']
missing = [s for s in required if s not in content]
if missing or len(content) < 2000:
    print('NEEDS_RUN')  # file exists but is incomplete — rerun
else:
    print('SKIP')
" 2>/dev/null || echo "NEEDS_RUN"
```
Skip only companies that return `SKIP`. Incomplete or missing reports always run. In `FORCE_RERUN=true` mode, all companies return `NEEDS_RUN`.

### Batch Step 4: Process Companies (Groups of 5 Simultaneous Subagents)

Process companies in groups of 5. For each group of up to 5 unprocessed companies:

**a) Pre-match Leadfeeder for all companies in the group** (before spawning any subagents):
For each company, search the pre-fetched leads for a record where `name` or `website` matches `{COMPANY_NAME}` or `{DOMAIN}`. Store as `LEADFEEDER_MATCH`:
- If found: `{ lead_id, name, website, visit_count, last_visited_at }`
- If not found: `"no match"`

**b) Spawn all subagents in the group simultaneously** (parallel Agent calls — do not wait for one before starting the next):

The subagent has no access to this skill file. The task string must embed everything it needs. Construct the task as follows — substitute all `{variables}` before passing:

```
Agent(
  subagent_type="general-purpose",
  task="""
You are researching {COMPANY_NAME} ({DOMAIN}) for Astronomer sales fitness.
Save the final report to: ~/claude-work/research-assistant/outputs/accounts/{COMPANY_SLUG}/report.md
When finished, respond with only: "{COMPANY_NAME} complete" or "{COMPANY_NAME} error: [one-line reason]"
Do NOT return the report content in your response.

=== LEADFEEDER DATA (pre-fetched) ===
{LEADFEEDER_MATCH}
If a lead_id is provided above, call mcp__leadfeeder__get_lead_visits(account_id="281783", lead_id=<id>, start_date=<6mo ago>, end_date=<today>) to get page visit URLs.
If "no match", record "Not found" in the Leadfeeder section.

=== RESEARCH INSTRUCTIONS ===
[Embed the full text of SINGLE COMPANY MODE Steps 2–7 here, with {COMPANY_NAME}, {DOMAIN}, and {COMPANY_SLUG} substituted. Skip Step 2b Apollo key check — Apollo sync is handled separately after you complete. Skip Step 8 (Apollo) and Step 9 (display) entirely.]
"""
)
```

**Important**: Do not reference "the skill" or "Steps X-Y" in the task string. The subagent is isolated and will not find them. Embed the actual instructions inline.

**c) Verify the report:**
After the subagent responds (regardless of what it says), run:
```bash
python3 -c "
import os, sys
path = os.path.expanduser('~/claude-work/research-assistant/outputs/accounts/{COMPANY_SLUG}/report.md')
if not os.path.exists(path):
    print('FAIL: file missing')
    sys.exit(1)
content = open(path).read()
required = ['# Account Research Report:', '**Generated**:', '**Sources**:']
missing = [s for s in required if s not in content]
if missing:
    print(f'FAIL: missing sections {missing}')
    sys.exit(1)
if len(content) < 2000:
    print(f'FAIL: report too short ({len(content)} chars)')
    sys.exit(1)
print('OK')
" 2>&1
```

**d) Retry once if verification fails:**
If result is not `OK`, spawn the same agent one more time. Re-verify after. If it fails again, mark as `FAILED` with the verification error reason and move on — do not block the batch.

**e) Apollo sync (orchestrator runs this, not the subagent):**
Only run if verification returned `OK` and `$APOLLO_API_KEY` is set. Use the Apollo instructions from Step 8 of SINGLE COMPANY MODE with `{COMPANY_NAME}`, `{DOMAIN}`, and `{COMPANY_SLUG}` substituted. Check the HTTP response — log `Apollo: write succeeded` or `Apollo: write FAILED — HTTP {status}`.

**f) Log the result:**
Append to `~/claude-work/research-assistant/outputs/batch_run_log.txt`:
```
{TIMESTAMP} | {COMPANY_NAME} | {DOMAIN} | SUCCESS | Apollo: succeeded/failed/skipped
```
or on failure:
```
{TIMESTAMP} | {COMPANY_NAME} | {DOMAIN} | FAILED: [verification error]
```

**g) Update batch summary CSV for all companies in the group**, then pause 2 seconds before the next group.

### Batch Step 5: Chunking
If CSV has >50 companies: process in chunks of 50 (i.e. ~10 groups of 5), pause 10 seconds between chunks.

### Batch Step 6: Generate Batch Summary

`~/claude-work/research-assistant/outputs/batch_summary.csv`:
```csv
company,domain,score,grade,confidence,score_change,key_change,report_path,last_updated
```

Extract score/grade/confidence from each completed report:
```bash
python3 -c "
import re, sys
content = open(sys.argv[1]).read()
score = (re.search(r'Score[:\s]+(\d+)\s*/\s*20', content) or ['',''])[1] or \
        (re.search(r'\b(\d+)/20\b', content) or ['',''])[1]
grade = (re.search(r'Grade[:\s]+([A-F][+\-]?)', content) or ['',''])[1]
conf  = (re.search(r'Confidence[:\s]+(HIGH|MEDIUM|LOW)', content) or ['',''])[1]
print(f'{score}|{grade}|{conf}')
" ~/claude-work/research-assistant/outputs/accounts/{COMPANY_SLUG}/report.md
```

`score_change`: compare extracted score against prior value in `batch_summary.csv` — format as `+N`, `-N`, `0`, or `NEW`. `key_change`: one-line summary or "No changes". For `FAILED` companies, leave score/grade/confidence blank and set `key_change` to the failure reason.

### Batch Step 7: Batch Summary Output

Display:
- Total processed / succeeded / failed
- Grade distribution (successes only)
- Top 10 by score

If any companies failed, display a **clear remediation block** at the end:

```
--- COMPANIES REQUIRING RERUN ---

The following X companies did not produce a complete report after 2 attempts.
To rerun, use: /account-research batch: ~/claude-work/research-assistant/outputs/failed_rerun.csv

Companies:
- Acme Corp (acme.com) — error: [reason]
- Beta Inc (beta.com) — error: [reason]

Suggested fixes before rerunning:
- "file missing" or "report too short": likely a subagent timeout — retry should resolve
- "missing sections": check ~/claude-work/gong_account_transcripts.py is accessible
- Any API errors: verify APOLLO_API_KEY, Leadfeeder MCP, and Exa MCP are connected
```

Also write a `failed_rerun.csv` to `~/claude-work/research-assistant/outputs/` containing only the failed companies (same `company_name,domain` format as the input CSV), ready to pass directly back into the skill.

---

## Graceful Degradation

| Source | Failure Behavior |
|--------|-----------------|
| **Exa AI** | Optional enhancement only — Claude WebSearch + WebFetch are the primary research tools and require no fallback. If Exa MCP tools are available they can provide additional coverage. |
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
