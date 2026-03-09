---
name: demo-prep
description: >
  Generates a structured demo prep brief for a sales engineer (SE) ahead of a product demo.
  Use this skill whenever the user asks to prep an engineer for a demo, prepare demo notes,
  brief an SE, or create demo prep for an account — even if they just say something like
  "prep the SE for [account]" or "/demo-prep [account]". The skill pulls Gong call transcripts
  to produce a ready-to-share doc covering attendees, current state, tech stack, use cases,
  what to demo, and watch-outs. All content is grounded in what the customer actually said.
---

# Demo Prep Skill

You are generating a demo prep brief that a sales engineer can read in 5 minutes and walk into a demo fully oriented. The goal is concise, opinionated, and directly useful — not a data dump.

## Step 1: Identify the account

Extract the account name from the user's message. Convert to snake_case for folder lookup (e.g., "Canal Insurance" → `canal_insurance`, "DOWC" → `dowc`).

## Step 2: Pull Gong transcripts

Run the transcript script:
```
python3 ~/claude-work/gong_account_transcripts.py "<Account Name>"
```

This fetches all Gong calls for the account and saves a markdown file to `~/claude-work/gong_<account>_<date>.md`. Read that file in full. Every section of the demo prep doc should be grounded in what the customer actually said — use their exact words and phrases wherever possible. Extract:
- Who attended each call (external names, titles)
- Pain points described in their own words
- What they specifically asked to see in the demo
- Technical constraints and requirements they mentioned
- Competitive tools they're evaluating
- Timeline, urgency, and budget signals
- Objections or concerns raised

## Step 3: Identify roles

From the transcripts, identify:
- **Champion**: The internal advocate pushing for the tool (usually the data/BI leader)
- **Technical Evaluator**: The person who will actually use the product day-to-day (usually the data engineer)
- **Approver/Economic Buyer**: The person who signs off (usually IT, VP, or C-suite)
- **Other attendees**: Anyone else who should be on the SE's radar

## Step 4: Generate the demo prep doc

Output the brief directly in the conversation using this exact structure:

---

## [Account Name] Demo Prep — [Date if known] @ [Time if known]

**Account:** [one-line description: industry, size, location]
**Opportunity:** [amount] | [stage] | Close [date]

[2-3 sentence plain-English summary of the overall situation: who they are, where they are in the evaluation, what the key dynamic is going into this call. Write it like a colleague briefing you in the hallway — what do you absolutely need to know before walking in?]

---

### Who's on the Call

| Name | Role | What They Care About |
|---|---|---|
| [Name] | [Title] | [1-line summary of their priorities] |

*(Include a note if there are expected attendees whose names you don't know yet, e.g., "Eric will forward the invite to the full IT org — expect a few people you don't know.")*

---

### Current State

Bullet points covering:
- Their existing setup and why it's failing them
- What they're moving from and to
- Team size and bandwidth constraints
- Any hard deadlines (security patches expiring, go-live pressure, etc.)

---

### Tech Stack

| Category | Technologies |
|---|---|
| [Category] | [Tools] |

Include categories relevant to the demo: orchestration, data warehouse, BI/reporting, cloud, source systems, languages, DevOps/git. Flag anything that affects the demo environment (e.g., Azure DevOps instead of GitHub, on-prem systems, specific cloud provider).

---

### Data Products / Business Use Cases

Numbered list of the specific pipelines and use cases they want to orchestrate. Be concrete — use their terminology and the actual systems involved. These are the things the SE should be able to speak to or ideally demo directly.

---

### What [Champion Name] Specifically Asked to See

Numbered list. Use direct quotes from the transcript where possible. This tells the SE exactly where to focus the demo for the person most likely to sell it internally.

---

### What [Technical Evaluator Name] Cares About

Bullet points focused on the builder's perspective: ease of getting started, reliability, logging/observability, integrations, day-to-day workflow. Frame around what will make their life easier.

---

### Suggested Demo Flow

Numbered list with suggested time allocations. Keep total to 45-60 minutes. Order by impact — lead with what matters most to this specific account, not a generic product tour.

Example format:
1. **Topic** (X min) — what to show and why it matters to them

---

### Things to Watch For

Bullet points covering:
- What NOT to demo (features they don't need or that would distract)
- Known objections or concerns to be ready for
- Competitive context (what else they're evaluating)
- Logistical notes (cloud preference, git provider, compliance requirements)
- Pricing — will it come up? Who handles it?

---

## Step 5: Save to interactions.md

After generating the brief in the conversation, append it to:
`~/claude-work/research-assistant/outputs/accounts/<snake_case>/interactions.md`

Use a dated header: `## [YYYY-MM-DD] — Demo Prep Brief for SE`

Create the file if it doesn't exist.

---

## Tone and style

- Write for a technical SE who is smart but has zero account context
- Be direct and opinionated — tell them what matters, don't hedge everything
- Use the champion's and evaluator's actual words and phrases from the transcript when possible; it helps the SE build rapport
- If something is unknown (e.g., Scott's last name), note it rather than omitting the person
- Keep sections tight — a 5-minute read, not a 20-minute read
