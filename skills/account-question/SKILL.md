---
name: account-question
description: Answer questions about any account using internal data sources (Gong call transcripts and saved account files). Use this skill whenever the user asks about an account's calls, what was discussed, pain points, tech stack, stakeholders, deal status, objections, competitors, or anything that would be answered by reviewing internal sales data. Also trigger when the user mentions "Gong", "calls", "transcripts", or asks things like "what did we talk about with [company]", "what's going on with [account]", or "draft an email for [account]". Even if the user doesn't explicitly say "Gong", if they're asking a question about an account that sounds like it needs internal conversation history to answer, use this skill.
---

# Account Question

Answer questions about an account using internal data: Gong call transcripts and saved account context from prior conversations.

## Architecture

- **Gong transcripts**: Two-tier cache at `~/claude-work/gong-cache/` (global call index + per-account transcripts)
- **Gong emails**: Fetched automatically alongside transcripts. Cached per-account. Gracefully skipped if Gong email integration is not configured in the workspace.
- **Account files**: `~/claude-work/research-assistant/outputs/accounts/<account_name>/` (report.md, interactions.md)

## Input
The user has provided: {{args}}

This could be:
- An account name with a question: "Iron Mountain - what are their pain points?"
- Just an account name: "Iron Mountain" (give a general overview)
- A follow-up question about a previously loaded account

## Steps

### 0. Load Prior Context

Before fetching anything, convert the account name to snake_case and check for existing files:
- `~/claude-work/research-assistant/outputs/accounts/<account_name>/report.md` — prior research, fit score, pain points, contacts, objections
- `~/claude-work/research-assistant/outputs/accounts/<account_name>/interactions.md` — prior email drafts, notes, action items from past conversations

Read whatever exists. This gives you the full history so you don't repeat prior analysis and can build on previous conversations.

### 1. Fetch Gong Transcripts

Run the script to pull all calls and transcripts for the account:

```bash
python3 -u /Users/joeykenney/claude-work/gong_account_transcripts.py "ACCOUNT_NAME" --stdout
```

The script automatically checks the global call index cache and does an incremental update if needed.

If unsure of the exact account name, list available accounts:
```bash
python3 /Users/joeykenney/claude-work/gong_account_transcripts.py --list-accounts
```

For very large accounts, narrow the time window:
```bash
python3 -u /Users/joeykenney/claude-work/gong_account_transcripts.py "ACCOUNT_NAME" --months 3 --stdout
```

### 2. Answer the Question

Use all available context — saved account files, Gong transcripts, and Gong email history — to answer whatever the user asked.

**Email history** appears in the script output under `## Email History`. If emails were captured, include relevant email threads (subject lines, direction, key content) when summarizing the account relationship. If emails are unavailable (integration not configured), note it briefly and move on.

If no specific question was asked, provide a brief overview:
- What recent calls covered
- Key contacts and their roles
- Current state of the relationship

### 3. Save Output

After answering, append a dated entry to the account's interactions log:
`~/claude-work/research-assistant/outputs/accounts/<account_name>/interactions.md`

- Use snake_case for the folder name (e.g., `oto_crm`)
- Create the folder/file if it doesn't exist
- Only save NEW outputs (the answer, email drafts, action items). Don't duplicate `report.md` content.
- Format: `## YYYY-MM-DD — <brief topic>` followed by the output

### 4. Stay Ready for Follow-Ups

The user will likely ask follow-up questions. The data is already in context, so answer directly — no need to re-fetch. Save follow-up outputs to the same interactions file.

## Notes
- Global Gong call index is synced daily via cron (6 AM) and incrementally on each query
- Per-account transcripts and emails are cached separately and updated when new calls appear
- Email history appears under `## Email History` in script output; gracefully skipped if Gong email integration is not active
- Use `--no-cache` to bypass all Gong caches if you need completely fresh data
- Use `--refresh-cache` to force a full rebuild of the global call index
- Use `--sync` to just update the global index without querying an account

---

**Begin:** {{args}}
