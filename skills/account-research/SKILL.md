---
name: account-research
description: Research a company for Astronomer sales fitness using Exa AI, Leadfeeder, and Common Room. Generates a fit score and AE brief with evidence from all three sources. Use when the user asks to research an account, score a company, or run batch account research.
version: 1.0.0
---

# Account Research Orchestrator

Research companies for Astronomer (Apache Airflow) sales fitness using four data sources: Exa AI (public research), Leadfeeder (website visit intent), Common Room (community/contact intelligence), and Gong (prior call history).

## Input
The user has provided: {{args}}

This could be:
- Single company: `{COMPANY}, {DOMAIN}` (e.g., "Acme Corp, acme.com")
- Batch mode: `batch: /path/to/file.csv` (CSV with columns: company_name, domain)

## Constants
- **Leadfeeder Account ID**: `281783`
- **Today's Date**: Use current date in YYYY-MM-DD format
- **Prompts Directory**: `~/claude-work/research-assistant/prompts/`
- **Output Directory**: `~/claude-work/research-assistant/outputs/accounts/`

---

## SINGLE COMPANY MODE

### Step 1: Parse Input
Extract `COMPANY_NAME` and `DOMAIN` from the input. If only a name is given, use Exa to find the domain.

### Step 2: Collect Data (Parallel)

Run all five source collections in parallel using the Agent tool with subagent_type="general-purpose". Launch 5 agents simultaneously:

#### Agent 1: Exa AI Research
Run these 9 Exa calls (parallel where possible):

1. **Company Research**:
   ```
   mcp__exa__company_research_exa(companyName=COMPANY_NAME)
   ```

2. **Orchestration/Pipeline Evidence**:
   ```
   mcp__exa__web_search_advanced_exa(
     query="{COMPANY_NAME} data pipeline orchestration airflow dagster prefect",
     startPublishedDate=[12 months ago, YYYY-MM-DD],
     numResults=5
   )
   ```

3. **Hiring Signals**:
   ```
   mcp__exa__web_search_advanced_exa(
     query="{COMPANY_NAME} hiring data engineer platform engineer",
     category="company",
     startPublishedDate=[6 months ago, YYYY-MM-DD],
     numResults=5
   )
   ```

4. **Recent News**:
   ```
   mcp__exa__web_search_exa(
     query="{COMPANY_NAME} corporate strategy news 2025 2026",
     numResults=5
   )
   ```

5. **Website Crawl**:
   ```
   mcp__exa__crawling_exa(url="https://{DOMAIN}", maxCharacters=5000)
   ```

6. **Engineering & Data Blog Posts**:
   ```
   mcp__exa__web_search_advanced_exa(
     query="{COMPANY_NAME} engineering blog data infrastructure pipeline platform",
     startPublishedDate=[18 months ago, YYYY-MM-DD],
     numResults=5
   )
   ```

7. **Product Announcements**:
   ```
   mcp__exa__web_search_advanced_exa(
     query="{COMPANY_NAME} product launch announcement new feature release",
     startPublishedDate=[12 months ago, YYYY-MM-DD],
     numResults=5
   )
   ```

8. **Case Studies & Third-Party Mentions**:
   ```
   mcp__exa__web_search_advanced_exa(
     query="{COMPANY_NAME} case study customer story",
     numResults=5
   )
   ```
   Also search for vendor-specific case studies that may reveal stack details:
   ```
   mcp__exa__web_search_advanced_exa(
     query="{COMPANY_NAME} Snowflake OR Databricks OR dbt OR AWS OR Google Cloud OR Azure case study OR customer OR partner",
     numResults=5
   )
   ```

9. **Job Description Details** (for top 1-2 relevant postings found in search 3):
   ```
   mcp__exa__crawling_exa(url="[JOB_POSTING_URL]", maxCharacters=5000)
   ```
   Crawl the most relevant data engineering / platform engineering job posting URLs found in the hiring signals search. Extract specific requirements, responsibilities, and tech stack mentions. If no relevant postings found, skip this step.

#### Agent 2: Leadfeeder Lookup

**IMPORTANT: For single company mode, paginate through leads to find a match.**

1. Search for the company in Leadfeeder leads:
   ```
   mcp__leadfeeder__get_leads(
     account_id="281783",
     start_date=[6 months ago, YYYY-MM-DD],
     end_date=[today, YYYY-MM-DD],
     page_size=100,
     page=1
   )
   ```

2. Check each page of results for a lead whose name or website domain matches `DOMAIN`. Paginate up to 5 pages (page=1 through page=5). Stop as soon as a match is found.

3. **If match found** — get lead details and visits:
   ```
   mcp__leadfeeder__get_lead(account_id="281783", lead_id=MATCHED_LEAD_ID)
   mcp__leadfeeder__get_lead_visits(
     account_id="281783",
     lead_id=MATCHED_LEAD_ID,
     start_date=[6 months ago, YYYY-MM-DD],
     end_date=[today, YYYY-MM-DD]
   )
   ```

4. **If no match after 5 pages** — record "No Leadfeeder data found for {COMPANY_NAME}."

#### Agent 3: Common Room Lookup

1. **Organization lookup by domain**:
   ```
   mcp__commonroom__commonroom_list_objects(
     objectType="Organization",
     filter={
       type: "and",
       clauses: [{
         type: "stringFilter",
         field: "companyWebsite",
         params: { op: "like", value: "{DOMAIN}" }
       }]
     },
     properties=["about", "employees", "location", "subIndustry", "revenueRangeMin", "revenueRangeMax", "leadScores", "topContacts", "contactsCount", "tags", "researchResults"],
     limit=1
   )
   ```

2. **Contacts at the organization** (if org found):
   ```
   mcp__commonroom__commonroom_list_objects(
     objectType="Contact",
     filter={
       type: "and",
       clauses: [{
         type: "stringFilter",
         field: "companyWebsite",
         params: { op: "like", value: "{DOMAIN}" }
       }]
     },
     properties=["primaryEmail", "title", "fullName", "recentActivities", "recentWebPages", "recentWebVisitsNumber", "leadScores", "profiles", "sparkSummary"],
     sort="latest_activity",
     direction="desc",
     limit=10
   )
   ```

3. **Recent activity from the organization** (if org found, use orgId from step 1):
   ```
   mcp__commonroom__commonroom_list_objects(
     objectType="Activity",
     filter={
       type: "and",
       clauses: [
         {
           type: "stringFilter",
           field: "orgId",
           params: { op: "eq", value: "{ORG_ID}" }
         },
         {
           type: "dateRangeFilter",
           field: "activityTime",
           params: { op: "in", value: "P90D", min: null, max: null }
         }
       ]
     },
     properties=["content", "url", "activityTime", "providerName"],
     sort="activityTime",
     direction="desc",
     limit=20
   )
   ```

4. **Website visits from the organization's contacts** (if contacts found):
   ```
   mcp__commonroom__commonroom_list_objects(
     objectType="WebsiteVisit",
     filter={
       type: "and",
       clauses: [
         {
           type: "and",
           target: "Contact",
           objectConfigId: null,
           targetAssocPaths: null,
           clauses: [{
             type: "stringFilter",
             field: "companyWebsite",
             params: { op: "like", value: "{DOMAIN}" }
           }]
         },
         {
           type: "dateRangeFilter",
           field: "visitTime",
           params: { op: "in", value: "P90D", min: null, max: null }
         }
       ]
     },
     properties=["url"],
     limit=20
   )
   ```

#### Agent 4: Gong Call History

Search for any prior Astronomer conversations with this company. This is the highest-value source — if we've already talked to them, the email must reference that context.

1. Run the Gong transcript script:
   ```bash
   python3 -u /Users/joeykenney/claude-work/gong_account_transcripts.py "COMPANY_NAME" --stdout
   ```

2. If the exact name doesn't match, try variations (e.g., "Runway" vs "Runway AI" vs "RunwayML"). You can list available accounts:
   ```bash
   python3 /Users/joeykenney/claude-work/gong_account_transcripts.py --list-accounts
   ```

3. If calls are found, extract:
   - Call dates and participants (who from Astronomer, who from their side)
   - Key topics discussed (pain points, use cases, objections, current tools)
   - Tech stack mentioned in conversations (specific tools, platforms, cloud providers, orchestration tools they said they use or are evaluating)
   - Deal stage / outcome if mentioned
   - Any follow-up items or commitments made

4. If no calls found, record: "No prior Gong calls found for {COMPANY_NAME}. This is a cold outreach."

### Step 3: Assemble RAW INTELLIGENCE Block

Combine all results into a structured markdown block:

```markdown
---
# RAW INTELLIGENCE: {COMPANY_NAME} ({DOMAIN})
# Collected: {TODAY_DATE}
---

## SOURCE: EXA AI

### Company Research
[Insert company_research_exa results]

### Orchestration & Pipeline Evidence
[Insert web_search_advanced results for orchestration query]

### Hiring Signals
[Insert web_search_advanced results for hiring query]

### Recent News
[Insert web_search results for news query]

### Website Content
[Insert crawling_exa results]

### Engineering & Data Blog Posts
[Insert results — titles, URLs, key excerpts about their data stack, infrastructure decisions, or technical challenges]

### Product Announcements
[Insert results — recent product launches, features, or platform changes that may imply new data pipeline needs]

### Case Studies & Third-Party Mentions
[Insert results — any case studies by vendors (Snowflake, dbt, Databricks, etc.) featuring the company, or blog posts from other companies referencing their stack. These often contain detailed tech stack and architecture info.]

### Job Description Details
[Insert crawled job posting text for relevant data/platform roles — specific requirements, responsibilities, tools mentioned. If no postings crawled, note "No relevant job postings crawled."]

---

## SOURCE: LEADFEEDER

### Lead Match
[Found / Not Found]

### Lead Details
[Insert lead details if found, or "No Leadfeeder data found for {COMPANY_NAME}."]

### Page Visits
[Insert visit details — URLs, dates, frequency — if found]

---

## SOURCE: COMMON ROOM

### Organization Profile
[Insert org details if found, or "No Common Room organization found for {DOMAIN}."]

### Contacts (Top 10 by recent activity)
[Insert contact list with titles, emails, activity summaries]

### Recent Community Activity (Last 90 Days)
[Insert activity feed with content, source, dates]

### Website Visits (Last 90 Days)
[Insert website visit URLs and dates]

---

## SOURCE: GONG

### Prior Conversations
[Found / Not Found — if not found, note "No prior Gong calls found. Cold outreach."]

### Call Summary
[If calls found: list each call with date, participants (Astronomer + prospect), and 2-3 sentence summary of what was discussed]

### Key Intelligence from Calls
[If calls found: pain points mentioned, objections raised, decision-makers identified, deal stage, follow-up items. If not found, omit this section.]

### Tech Stack from Calls
[If calls found: specific tools, platforms, cloud providers, data warehouses, orchestration tools, and other technologies they mentioned using or evaluating during conversations. Tag each with the call date it was mentioned in. If not found, omit this section.]

```

### Step 4: Generate Fit Score

Read the prompt template from `~/claude-work/research-assistant/prompts/01_fit_scoring.md`.

Replace `{COMPANY_NAME}` and `{DOMAIN}` with actual values.

Prepend the RAW INTELLIGENCE block to the prompt, then evaluate the company according to the scoring rubric. Generate the fit score output.

### Step 5: Generate Account Research Summary

Read the prompt template from `~/claude-work/research-assistant/prompts/02_account_research.md`.

Replace `{COMPANY_NAME}` and `{DOMAIN}` with actual values.

Prepend the RAW INTELLIGENCE block to the prompt, then generate the account research summary.

### Step 6: Compose Final Report

**Generate company slug**: lowercase company name, replace spaces with underscores, remove special characters.

**Changelog detection** — Before writing, check if a previous report exists at `~/claude-work/research-assistant/outputs/accounts/{company_slug}/report.md`:

1. Read the existing report file (if it exists)
2. Extract from the old report: total score, grade, confidence, and existing changelog entries
3. Compare against the new report
4. **Significant changes** (generate new changelog entry if any):
   - Score changed by >=2 points
   - Grade letter changed (e.g., B → A)
   - New Leadfeeder visits to pricing, demo, or docs pages
   - New hiring signals mentioning Airflow, orchestration, or data platform
   - New Common Room contacts with relevant titles (VP Eng, Head of Data, etc.)
   - New funding rounds or acquisitions

Combine the fit score, account research, and changelog into a single report:

```markdown
# Account Research Report: {COMPANY_NAME}

**Generated**: {TODAY_DATE}
**Website**: https://{DOMAIN}
**Sources**: Exa AI ✓/✗ | Leadfeeder ✓/✗ | Common Room ✓/✗ | Gong ✓/✗

---

[Fit Score section from Step 4]

---

[Account Research section from Step 5]

---

## Changelog

[All changelog entries, newest first]
```

**Changelog entries format** (within the report):
```markdown
### {TODAY_DATE}
- [Change description]
- [Change description]
```

If no previous report exists, add a single changelog entry:
```markdown
### {TODAY_DATE}
- First research generated. Grade: {GRADE}, Score: {SCORE}/20, Confidence: {CONFIDENCE}
```

If no significant changes detected (re-run):
```markdown
### {TODAY_DATE}
- Re-evaluated. No significant changes. Grade: {GRADE}, Score: {SCORE}/20
```

When re-running, **preserve all previous changelog entries** from the old report's Changelog section and prepend the new entry above them.

### Step 7: Save Report

**Report file** (overwrite):
```
~/claude-work/research-assistant/outputs/accounts/{company_slug}/report.md
```

### Step 8: Update Apollo Account_Research Field

After saving the report, write the full report content to the `Account_Research` custom field in Apollo.

- **Account_Research field ID**: `6998b33edacda9000deb48ca`
- **IMPORTANT**: Use `typed_custom_fields` (keyed by field ID), NOT `custom_fields` (keyed by name) — the name-keyed format silently ignores writes.

1. **Find the Apollo account ID — search by name, confirm by domain**:
   ```bash
   curl -s -X POST "https://api.apollo.io/v1/accounts/search" \
     -H "Content-Type: application/json" \
     -d "{\"api_key\": \"$APOLLO_API_KEY\", \"q_organization_name\": \"{COMPANY_NAME}\", \"per_page\": 10}"
   ```
   From the results, find the account whose `domain` field **exactly matches** `{DOMAIN}`. Extract its `id`.

   **IMPORTANT**: Do NOT use the first result blindly. You MUST verify `account.domain == "{DOMAIN}"` before writing. If no account passes this domain check, skip the Apollo update and log: "Apollo: No account found matching domain {DOMAIN} — skipping update."

   > Why: `q_organization_domain` search can return wrong accounts (e.g., querying `runwayml.com` returned Amazon). Name search + explicit domain validation is the reliable pattern.

2. **Write the full report to the Account_Research field**:

   Read the saved report file and write its full contents to the field:
   ```bash
   ACCOUNT_ID="{APOLLO_ACCOUNT_ID}"
   FIELD_ID="6998b33edacda9000deb48ca"
   REPORT=$(cat ~/claude-work/research-assistant/outputs/accounts/{COMPANY_SLUG}/report.md)
   curl -s -X PUT "https://api.apollo.io/v1/accounts/${ACCOUNT_ID}" \
     -H "Content-Type: application/json" \
     -d "{\"api_key\": \"$APOLLO_API_KEY\", \"typed_custom_fields\": {\"${FIELD_ID}\": $(echo "$REPORT" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')}}"
   ```

   Verify success by checking `typed_custom_fields["6998b33edacda9000deb48ca"]` in the response has non-zero length.

3. If the account is not found in Apollo or the update fails, log a note but do not block report generation.

### Step 9: Present Results

Display the final report to the user. Highlight:
- The fit score and grade prominently
- Any notable buying signals
- Changelog entries if this is a re-run

---

## BATCH MODE

When input starts with `batch:`, process multiple companies from a CSV file.

### Batch Step 1: Load CSV
Read the CSV file. Expected columns: `company_name`, `domain` (or `company`, `domain`; be flexible with header names). Skip header row.

### Batch Step 2: Pre-fetch Leadfeeder Data (Optimization)

Pull ALL Leadfeeder leads upfront to avoid re-paginating per company:

```
page = 1
all_leads = []
while page <= 20:  # Safety cap
    results = mcp__leadfeeder__get_leads(
        account_id="281783",
        start_date=[6 months ago],
        end_date=[today],
        page_size=100,
        page=page
    )
    all_leads.extend(results)
    if len(results) < 100:
        break  # Last page
    page += 1
```

Store the full lead list in memory for matching during per-company processing.

### Batch Step 3: Check for Resume

Read `~/claude-work/research-assistant/outputs/batch_summary.csv` if it exists. If a company was already processed today (last_updated matches today's date), skip it. This enables resume after interruption.

### Batch Step 4: Process Companies Sequentially

For each company NOT already processed today:

1. Run the single-company flow (Steps 2-8), but for Leadfeeder: match against the pre-fetched lead list instead of paginating.
2. After each company, update the batch summary CSV.
3. Pause 2 seconds between companies (rate limit management).

### Batch Step 5: Chunking (300+ accounts)

If the CSV has more than 50 companies:
- Process in chunks of 50
- After each chunk, pause 10 seconds
- Log progress: "Processed {N}/{TOTAL} companies. Next chunk starting..."

### Batch Step 6: Generate Batch Summary

Write/update `~/claude-work/research-assistant/outputs/batch_summary.csv`:

```csv
company,domain,score,grade,confidence,score_change,key_change,report_path,last_updated
Acme Corp,acme.com,16,A,HIGH,+3,New pricing page visits,accounts/acme_corp/report.md,2026-03-04
Beta Inc,beta.io,8,C,MEDIUM,0,No changes,accounts/beta_inc/report.md,2026-03-04
```

Columns:
- `company`: Company name
- `domain`: Company domain
- `score`: Fit score (0-20)
- `grade`: Letter grade (A/B/C/D)
- `confidence`: HIGH/MEDIUM/LOW
- `score_change`: Change from previous run (+N, -N, or 0). "NEW" if first run.
- `key_change`: One-line summary of most significant change, or "No changes" / "New account"
- `report_path`: Relative path to full report
- `last_updated`: Date of this evaluation (YYYY-MM-DD)

### Batch Step 7: Batch Summary Output

After all companies processed, display:
- Total processed count
- Grade distribution (A: N, B: N, C: N, D: N)
- Top 10 accounts by score
- Accounts with biggest score increases (if re-run)
- Any errors/failures

---

## Graceful Degradation

Each source fails independently. Handle failures gracefully:

| Source | Failure Behavior |
|--------|-----------------|
| **Exa AI** | Confidence drops to LOW. Report still generates from LF + CR data. Note "Exa research unavailable" in report header. |
| **Leadfeeder** | Buying Signals dimension caps at 1 (hiring signals only). Note "No website visit data" in Website Engagement section. |
| **Common Room** | Key Contacts section shows "No community contacts found." Stack Evidence dimension limited to EXA data. |
| **Gong** | Prior Conversations section shows "No prior Gong calls found. Cold outreach." Email Brief adjusts tone accordingly. |
| **All four fail** | Report cannot be generated. Log error and skip to next company in batch mode. |

---

## Important Guidelines

- The entire final report file MUST be under 1,000,000 characters. If raw intelligence is too large, truncate verbose sections (website crawl, news articles) before assembling the report. Prioritize keeping scoring rationale, contacts, and buying signals intact over raw source data.
- Use ONLY the MCP tools listed above — no direct API calls via Bash/curl
- Be thorough — search multiple sources per dimension
- Every claim must be tagged with its source
- Preserve existing changelog entries from previous reports when re-running
- In batch mode, save incrementally — don't wait until the end
- If a company slug collision occurs (two companies map to same slug), append a number

---

**Begin research for:** {{args}}
