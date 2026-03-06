# Weekly Gong Review

Weekly call coaching report for an Astronomer AE. Pulls every call the rep was on (not just calls they hosted), scores 6 dimensions, surfaces specific coachable moments with Gong deep links, and tracks week-over-week trends.

## Input
The user has provided: {{args}}

- No args: review the current ISO week for the configured rep
- `week:2026-W09` — review a specific ISO week
- `rep:"Alec Dolton"` or `rep:alec.dolton@astronomer.io` — override config (for reviewing a different rep)

## Constants
- **Gong Base URL**: `https://api.gong.io/v2`
- **Gong Auth**: Basic Auth — `Authorization: Basic $(echo -n "$GONG_ACCESS_KEY:$GONG_SECRET_KEY" | base64)`
- **Output directory**: `~/claude-work/rep-coaching/`
- **Reports directory**: `~/claude-work/rep-coaching/reports/`
- **Scores file**: `~/claude-work/rep-coaching/scores.csv`
- **Config file**: `~/claude-work/rep-coaching/config.md`

---

## Step 1: Parse Input & Determine Date Range

Extract any `week:` or `rep:` arguments. Default to current ISO week if no week specified.

Compute date range from ISO week:
```bash
python3 -c "
import datetime, sys
week_str = '{{WEEK}}'  # e.g. '2026-W10'
year, week = int(week_str[:4]), int(week_str[6:])
monday = datetime.datetime.strptime(f'{year}-W{week:02d}-1', '%G-W%W-%u')
sunday = monday + datetime.timedelta(days=6, hours=23, minutes=59, seconds=59)
print(monday.strftime('%Y-%m-%dT00:00:00Z'))
print(sunday.strftime('%Y-%m-%dT23:59:59Z'))
"
```

---

## Step 2: Load Config & Resolve Rep

### 2a. Load config
Read `~/claude-work/rep-coaching/config.md`. Expected format:
```
Email: jake.thomer@astronomer.io
```

If file does not exist:
- Prompt: "No config found. What's your Astronomer email address?"
- Create the file with their response before proceeding
- Also create `~/claude-work/rep-coaching/reports/` if it doesn't exist

If a `rep:` argument was provided, use that instead of config (supports both name and email format).

### 2b. Resolve Gong user ID from email

Use the MCP `list_users` tool and paginate until a match is found:

```
mcp__gong__list_users()  # repeat with cursor until match found
```

Match priority:
1. Exact email match (case-insensitive)
2. If no exact match: infer name from email (`jake.thomer` → "Jake Thomer"), fuzzy-match against user display names
3. If still no match: tell the user "Could not find [email] in Gong. Please check that this matches your Gong account email." and stop.

Store: `REP_NAME`, `REP_USER_ID`, `REP_EMAIL`.

---

## Step 3: Fetch All Calls for the Week (REST API)

Paginate through ALL calls in the date range using the REST API. Do NOT use `search_calls` MCP — it only returns calls the rep hosted. We need every call they appeared on.

```bash
AUTH=$(echo -n "$GONG_ACCESS_KEY:$GONG_SECRET_KEY" | base64)
curl -s "https://api.gong.io/v2/calls?fromDateTime={FROM}&toDateTime={TO}&limit=100" \
  -H "Authorization: Basic $AUTH"
```

Paginate using `records.cursor` until all pages are fetched. For this workspace expect ~200-300 calls/week (~3 pages).

Filter the results to calls where `REP_USER_ID` appears in the `participants` array (check `userId` field on each participant).

### 3a. Drop noise calls

Exclude calls that won't produce useful coaching signal:
- Duration < 15 minutes
- All participants share `@astronomer.io` email domain (internal-only call)
- Rep's total speaking time < 10% of call duration (they were an observer)

To check speaking time without fetching full transcripts: use `get_call_summary` — it often includes talk ratio. If not available at this stage, keep the call and check after transcript fetch.

Store the filtered call list: `[{id, title, url, date, duration_seconds, account_name}]`

If 0 calls remain after filtering: output "No external calls found for {REP_NAME} in {WEEK}." and stop.

---

## Step 4: Fetch Call Summaries

For each filtered call, fetch the summary via MCP:
```
mcp__gong__get_call_summary(callId="{CALL_ID}")
```

Run sequentially. Extract: key topics, participants (names + companies), talk ratio if present, call outcome.

---

## Step 5: Fetch Timestamped Transcripts (REST API)

Fetch full transcripts with sentence-level timestamps for all filtered calls in a single batch request:

```bash
AUTH=$(echo -n "$GONG_ACCESS_KEY:$GONG_SECRET_KEY" | base64)
curl -s -X POST "https://api.gong.io/v2/calls/transcript" \
  -H "Authorization: Basic $AUTH" \
  -H "Content-Type: application/json" \
  -d '{"filter": {"callIds": ["CALL_ID_1", "CALL_ID_2", ...]}}'
```

Response structure per call:
```json
{
  "callId": "...",
  "transcript": [
    {
      "speakerId": "...",
      "sentences": [
        {"start": 45230, "end": 48100, "text": "Hopefully this makes sense for your team."}
      ]
    }
  ]
}
```

Build a speaker ID → name map from the participants data fetched in Step 3.

**Deep link format**: `{call.url}?t={sentence.start / 1000}`
Example: `https://app.gong.io/call?id=123456&t=45` links to the 45-second mark.

### 5a. Calculate talk ratio per call
Sum `(end - start)` ms for each speaker. Rep's talk ratio = rep_ms / total_ms. Flag calls where rep talked > 60% — meaningful signal.

---

## Step 6: Load Historical Scores

Read `~/claude-work/rep-coaching/scores.csv` if it exists:
```csv
week,discovery,next_steps,talk_ratio,technical_confidence,competitive,multithreading,overall,calls_reviewed
2026-W09,3,2,4,3,2,2,3,4
```

Load the last 4 weeks of scores for trend context. If no history exists, note "First week tracked."

---

## Step 7: Analyze & Generate Report

Using all call summaries, transcripts, talk ratios, and historical scores — generate the full coaching report in a single pass.

### Scoring Rubric (1–5 per dimension)

Score each dimension based on evidence across ALL calls this week. Cite the strongest supporting moments.

**Discovery Depth**
| Score | Evidence |
|-------|----------|
| 5 | Asks layered "why" questions, uncovers business impact and urgency, prospect talks 60%+ |
| 4 | Good questions but misses one layer (e.g. finds pain but not urgency or business impact) |
| 3 | Surface-level discovery — asks what/how but rarely why; accepts first answer |
| 2 | Jumps to pitch before understanding the problem |
| 1 | No meaningful discovery; led entire call with features |

**Next Step Quality**
| Score | Evidence |
|-------|----------|
| 5 | Specific, time-bound next step confirmed by prospect before end of call |
| 4 | Clear next step proposed and accepted, but not explicitly confirmed |
| 3 | Vague next step ("I'll follow up", "let's reconnect") |
| 2 | Call ended without any next step discussed |
| 1 | Multiple calls ended without next steps this week |

**Talk Ratio**
| Score | Evidence |
|-------|----------|
| 5 | Rep spoke < 40% consistently |
| 4 | Rep spoke 40–50% |
| 3 | Rep spoke 50–60% |
| 2 | Rep spoke 60–70% on multiple calls |
| 1 | Rep dominated conversations > 70% |

**Technical Confidence**
| Score | Evidence |
|-------|----------|
| 5 | Engages fluently on Airflow/orchestration details; uses customer's technical context accurately |
| 4 | Handles most technical questions; defers on edge cases appropriately |
| 3 | Comfortable with surface-level technical conversation; deflects specifics to SE |
| 2 | Noticeably uncertain on product or Airflow details; prospect leads technical discussion |
| 1 | Avoids technical questions entirely or gives inaccurate information |

**Competitive Handling**
| Score | Evidence |
|-------|----------|
| 5 | Names competitor directly, gives specific differentiated counter tied to prospect's situation |
| 4 | Acknowledges competitor, gives general counter |
| 3 | Vague differentiation ("we're more enterprise-ready") without specifics |
| 2 | Avoids or deflects when competitor comes up |
| 1 | Concedes ground to competitor without a counter |
| N/A | No competitor mentioned this week |

**Multi-threading**
| Score | Evidence |
|-------|----------|
| 5 | Actively engaged 3+ stakeholders; referenced economic buyer by name |
| 4 | Two stakeholders engaged; asked about decision process/economic buyer |
| 3 | One primary contact; asked about other stakeholders but didn't pursue |
| 2 | Single contact; no attempt to expand |
| 1 | Single contact; explicitly avoided expanding when opportunity arose |

---

### Report Format

```markdown
# Weekly Call Review: {REP_NAME}
**Week**: {WEEK} ({date range})
**Calls reviewed**: {N} ({total call list before filtering} total, {N} external calls > 15 min)

---

## Scorecard

| Dimension | This Week | Last Week | Trend |
|-----------|-----------|-----------|-------|
| Discovery Depth | {X}/5 | {X}/5 | up/down/flat |
| Next Step Quality | {X}/5 | {X}/5 | up/down/flat |
| Talk Ratio | {X}/5 | {X}/5 | up/down/flat |
| Technical Confidence | {X}/5 | {X}/5 | up/down/flat |
| Competitive Handling | {X}/5 or N/A | {X}/5 | up/down/flat |
| Multi-threading | {X}/5 | {X}/5 | up/down/flat |
| **Overall** | **{X}/5** | **{X}/5** | up/down/flat |

> Confidence: {HIGH if 4+ calls / MEDIUM if 2-3 / LOW if 1}

---

## One Thing to Focus on This Week

**{Single most impactful change — one sentence, specific and behavioral}**

[2-3 sentences: why this dimension matters most right now, what pattern was observed, what to do differently. Reference a specific call moment.]

---

## This Week's Highlight

> "[Exact quote from a strong moment]" — {Account}, {date} ([link]({deep_link}))

[1 sentence on why this worked and what to repeat.]

---

## Cross-Call Patterns
*Themes that appeared in 2+ calls — highest coaching signal*

**{Pattern title}** (seen in {N} calls)
[2 sentences describing the pattern with specific examples]
- {Account 1}, {date}: "[quote]" ([link]({deep_link}))
- {Account 2}, {date}: "[quote]" ([link]({deep_link}))
**Try instead**: "[Suggested reframe]"

[Repeat for each pattern. Only include patterns seen in 2+ calls. Skip if fewer than 2 calls this week.]

---

## Call-by-Call

### {Account Name} — {date} ({duration})
**Participants**: {their names/titles} | {Astronomer participants}
**Topics**: {2-3 topics from summary}
**Talk ratio**: Rep {X}% / Prospect {X}%

**What worked**
- [Specific moment] ([link]({deep_link}))
  > "{exact quote}"

**What to work on**
- [Specific moment] ([link]({deep_link}))
  > "{exact quote}"
  **Try instead**: "[Suggested reframe]"

[Repeat for each call. Maximum 2 "what worked" and 2 "what to work on" per call. Don't force it — if a call was clean, say so.]

---

## Score History

| Week | Discovery | Next Steps | Talk Ratio | Technical | Competitive | Threading | Overall |
|------|-----------|------------|------------|-----------|-------------|-----------|---------|
{last 4 weeks of scores, newest first}
```

---

## Step 8: Save Report & Update Scores

**Save report**:
```
~/claude-work/rep-coaching/reports/{WEEK}.md
```

**Update scores.csv** — append a new row (or overwrite if same week already exists):
```
{WEEK},{discovery},{next_steps},{talk_ratio},{technical_confidence},{competitive},{multithreading},{overall},{calls_reviewed}
```

Keep the CSV sorted newest-first.

---

## Step 9: Display Report

Output the full report. No preamble — start directly with the report content.

---

## Graceful Degradation

| Issue | Behavior |
|-------|----------|
| Config missing | Prompt for email, create config, proceed |
| Email not found in Gong | Try name inference from email; if still not found, tell user to check their Gong account email |
| 0 qualifying calls | "No external calls found for {REP_NAME} in {WEEK}." |
| Transcript fetch fails for a call | Note "Transcript unavailable" for that call; still include summary-based observations |
| No history in scores.csv | Skip trend column; note "First week tracked" |
| Competitor not mentioned | Score competitive as N/A, exclude from overall average |
| Talk ratio unavailable | Calculate from transcript timestamps; if transcript also unavailable, omit dimension for that call |

---

## Important Guidelines

- Every coachable observation MUST include an exact quote and a deep link. No vague observations without evidence.
- Every negative observation MUST include a "Try instead" reframe — not just criticism.
- The "One Thing to Focus On" must be the single highest-leverage change. Do not list multiple things here.
- Cross-call patterns only if seen in 2+ calls. Don't manufacture patterns from a single instance.
- Keep per-call sections tight — max 2 positives + 2 coaching points per call. Quality over quantity.
- Overall score = average of scored dimensions (exclude N/A dimensions from average).
- Internal calls (all @astronomer.io participants) are excluded entirely — do not reference them in the report.

---

**Begin review for:** {{args}}
