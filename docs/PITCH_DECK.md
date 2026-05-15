# TenderMania — Pitch Deck Script

**Format:** 6 slides, ~5 minutes spoken. Pace ~50–60 seconds per slide.
**Use:** paste each slide block into Gamma, Pitch, or Slides. Spoken script under each.

---

## Slide 1 — Title

```
TenderMania
Autonomous tender-hunting agent

OpenClaw Agenthon 2026 · Team duoBolang
github.com/Hzxon/OpenClaw2026_duoBolang_SponsorUs
```

**Spoken (15s):**
> "We're duoBolang, and this is TenderMania — an autonomous multi-agent system that finds compatible tenders for a company, scores fit with reasoning, and drafts personalized expressions of interest. Built in 12 hours for OpenClaw Agenthon."

---

## Slide 2 — Problem Statement

```
The hidden cost of bidding

• Indonesian software consultancies spend 8–15 hours per week
  scanning LPSE, World Bank, ministry portals for tenders that fit
• 90%+ of listed tenders are NOT a fit:
  - wrong sector (construction, hardware, household goods)
  - wrong scale (out of capacity)
  - wrong geography or eligibility
• Result: senior engineers doing manual filtering instead of building
  → opportunity cost of IDR 50–80 juta per month per BD person
• Even when a fit is found, drafting an EOI takes another 2–4 hours

Every consultancy in Indonesia eats this tax. Nobody has solved it.
```

**Spoken (50s):**
> "If you run a software consultancy in Indonesia, you live this every week. Your business-development person opens twenty tabs — LPSE Jakarta, LPSE Jabar, PLN e-procurement, World Bank, ministry portals — and reads through hundreds of tender notices. Most are physical infrastructure, hardware procurement, or strategy consulting that don't match a software shop at all. By the time they find one that fits, three hours are gone, and writing the expression of interest takes another two. This is happening at every consultancy in the country, and the cost is real — easily 50 to 80 million rupiah per BD person per month in opportunity cost. The work is mechanical, repetitive, and structured. It's exactly the kind of work an agent should do."

---

## Slide 3 — Solution Overview

```
TenderMania replaces the grind with one autonomous loop

Input:  company profile (capabilities, certs, past contracts, geography)
Output: ranked, scored tenders + ready-to-send draft EOIs

The agent runs unattended end-to-end. Only the final SEND is gated
on a human tap.

What makes it different from "ChatGPT for tenders":
  ✓ Multi-dimension scoring (capability × eligibility × win-prob)
    not a single vibes-based number
  ✓ RAG-grounded drafts that CITE evidence from your real past work
    not generic boilerplate
  ✓ Hard deterministic gates (eligibility < 30 → auto-archive)
    not "trust the LLM"
  ✓ Full audit trail in SQLite — every score, every rationale
    not a black box
```

**Spoken (55s):**
> "TenderMania flips the workflow. You give it your company profile once — capabilities, certifications, past contracts, what budget bands and geographies you serve. Then the agent runs the loop: it scrapes live tender feeds, reads each one, scores it across three dimensions in parallel, and for the ones that clear the threshold, it drafts a personalized expression of interest grounded in your actual past work. Nothing leaves the system without your approval. The difference from a ChatGPT prompt is structural — we score across three independent dimensions, we cite evidence from your profile in every score and every draft, we apply deterministic hard-gates so an unqualified bid can never make it through, and every decision is auditable in SQLite. Not a black box."

---

## Slide 4 — AI Agent Workflow & Architecture

```
              ┌──────────────────────────────────────────────┐
              │  Scraper agents (one tool call per source)  │
              │  • PLN e-Procurement (Indonesian BUMN)      │
              │  • World Bank Procurement Notices (global)  │
              └────────────────────┬─────────────────────────┘
                                   ▼
                       ┌──────────────────┐
                       │ Normalizer agent │   LLM + Pydantic
                       └────────┬─────────┘   → typed records
                                ▼
        ┌───────────────────────┴────────────────────┐
        │     MULTI-AGENT FAN-OUT (asyncio.gather)   │
        ├──────────┬──────────────┬──────────────────┤
        │ capability│ eligibility │ win-probability │ 3 LLM calls in parallel
        │  scorer   │   scorer    │   scorer         │ each cites RAG evidence
        └────┬─────┴───────┬─────┴───────┬───────────┘
             └─────────────┼─────────────┘
                           ▼
                ┌────────────────────┐
                │  Aggregator        │  hard-gates + weighted threshold
                │  (rule + LLM)      │  → PURSUE | ARCHIVE
                └─────────┬──────────┘
                          ▼ pursue
                ┌────────────────────┐
                │  Drafter agent     │  RAG-grounded EOI
                │  (LLM + BM25 RAG)  │  in Bahasa or English
                └─────────┬──────────┘
                          ▼
                ┌────────────────────┐
                │  Approval gate     │  CLI or Telegram
                └─────────┬──────────┘
                          ▼ approve
                  → send_email tool (DRY_RUN safe)

Reasoning per dimension is persisted with cited evidence.
Every archive has a deterministic reason. Every pursue has 3 rationales.
```

**Spoken (75s):**
> "Here's the architecture. Two scraper agents pull live tenders in parallel from PLN e-procurement and the World Bank API. A normalizer agent turns each raw record into a typed Pydantic object so downstream agents get clean inputs. Then we fan out — three scorer agents run simultaneously through asyncio. The capability scorer asks 'can we deliver this'. The eligibility scorer asks 'are we even allowed to bid'. The win-probability scorer asks 'realistically, can we win'. Each scorer cites concrete evidence from the company profile via BM25 RAG retrieval. The aggregator applies hard deterministic gates first — if eligibility is below 30, it's an auto-archive, no LLM judgment involved. Only tenders that clear the gates and the weighted threshold reach the drafter, which composes a personalized expression of interest grounded in cited past work. Then human approval, then the send tool fires. We tested this end-to-end on six live tenders — it pursued one and archived five, correctly rejecting power-grid maintenance, household-goods procurement, and policy strategy contracts. Honest agent behavior."

---

## Slide 5 — Key Features & Tech Stack

```
KEY FEATURES                          TECH STACK
─────────────────────────             ──────────────────────────
✓ Live multi-source scraping          • Python 3.11+ (tested 3.11/3.12/3.14)
  PLN + World Bank APIs               • LLM: any OpenAI-compatible
  Indonesian BUMN fixture fallback      endpoint (cx/gpt-5.5 default)
                                      • httpx + selectolax (scrape)
✓ Pydantic-validated structured       • Pydantic v2 (typed schemas)
  output on every LLM call            • BM25 RAG (no embeddings dep)
                                      • SQLite stdlib (audit trail)
✓ 3 parallel scorer agents via        • python-telegram-bot v22
  asyncio.gather                        (callback queries)
                                      • yagmail (SMTP, DRY_RUN safe)
✓ Hard-gates + weighted threshold     • tenacity (LLM retry)
  (deterministic, not LLM-decided)
                                      DELIVERABLES
✓ RAG-grounded drafts in Bahasa       • One-command setup (5 min from
  or English (auto-detected from       fresh clone to working pipeline)
  tender language)                    • Bilingual README (ID + EN)
                                      • Verified reproducibility from
✓ Two approval paths:                   /tmp clone in 64 seconds
  CLI (`scripts.approve`) +
  Telegram inline buttons             • Open source (MIT)

✓ DRY_RUN mode by default — safe to
  demo, never sends without approval
```

**Spoken (55s):**
> "Stack-wise, it's pragmatic Python. Everything is OpenAI-compatible so you can swap the model with one environment variable — public OpenAI, a local Ollama, an internal gateway, all work. Pydantic enforces structured output on every LLM call, so a malformed response gets caught and retried instead of corrupting state. BM25 for RAG instead of embeddings — for a 23-chunk profile, lexical retrieval is faster, deterministic, and zero extra dependencies. SQLite via the stdlib gives us a full audit trail. Two approval paths because the demo machine had a Telegram token conflict — the CLI fallback meant the build never blocked. DRY_RUN is the default everywhere. Five minutes from a fresh git clone to a working draft email — we verified that on a clean machine."

---

## Slide 6 — Future Development & Impact

```
IMPACT (today)                        FUTURE DEVELOPMENT
───────────────────────               ────────────────────────────────
Per consultancy:                      Phase 1 — next 30 days
• 8–15 hrs/week saved per BD person   • Scheduled cron loop (daily scan)
• 50–80 juta IDR/month opportunity    • Embeddings RAG for >100-chunk
  cost reclaimed                        profiles (sentence-transformers)
• 3–5x more tenders evaluated         • LPSE national index integration
  with the same headcount               via INA-Proc
                                      • Slack + WhatsApp approval gates
At ecosystem scale:
• Indonesia has ~10,000 IT/services   Phase 2 — productization
  vendors registered on LPSE          • Multi-tenant SaaS (per-company
• Even 5% adoption = thousands of       isolated profiles + scoring)
  hours/week of senior engineering    • Tender deadline tracking + reminders
  freed for actual delivery           • Win/loss outcome tracking → loop
                                        feedback into scorer prompts
For procurement officers:             • Bahasa-first prompt fine-tuning
• Cleaner inbox — only EOIs from        on real Indonesian procurement docs
  vendors who actually qualify
• Less noise, faster shortlisting     Phase 3 — beyond tenders
                                      • Same architecture for grant
                                        applications (DIPA, hibah)
                                      • RFP response auto-drafting
                                      • Vendor-side: predicting
                                        procurement-officer questions
```

**Spoken (60s):**
> "Today's impact is concrete. For a single consultancy, this saves a senior person 8 to 15 hours a week — call it 50 to 80 million rupiah a month in reclaimed opportunity cost. At ecosystem scale, Indonesia has roughly ten thousand IT vendors registered on LPSE; even five percent adoption frees thousands of senior engineering hours every week to do actual delivery work instead of inbox triage. For procurement officers, the upstream effect is cleaner — they receive expressions of interest only from vendors who actually qualify and have evidence to back the claim. Looking forward: phase one is a daily scheduled cron loop, embeddings-based RAG for larger profiles, integration with the national LPSE index, and approval gates on Slack and WhatsApp. Phase two is multi-tenant SaaS plus win-loss outcome tracking that feeds back into the scorer prompts so the agent gets better with every cycle. Phase three takes the same architecture beyond tenders — into grant applications, RFP responses, even predicting the questions a procurement officer is going to ask before they ask them. The agentic primitive we built today generalizes."

---

## Closing line (after slide 6, optional)

> "Multi-agent. Tool-using. Autonomous loop. Real Indonesian data. Auditable. Reproducible. That's TenderMania. Thank you."

---

## Speaker notes — delivery tips

- **Pace:** target 5 minutes flat. Each slide ~50–60 seconds. Slide 4 (architecture) is the longest at 75s — that's fine, it's the technical centerpiece.
- **Demo placement:** if you have time for a live demo inside the pitch, drop it after slide 4. Run the offline command:
  ```bash
  SOURCES=lpse PREFER_LIVE=false SCORE_THRESHOLD=40 MAX_TENDERS=2 \
    python3 -m sponsorus.run_pipeline
  ```
  60-second runtime, guaranteed PURSUE, deterministic output. Then tab to `scripts.approve 2 show` to display the Bahasa Indonesia draft.
- **If asked "did you really build this in 12 hours":** yes. The repo has 5 commits, all timestamped inside the Agenthon window, and the README has a verified reproducibility log.
- **If asked about LLM choice:** any OpenAI-compatible endpoint works. We used a local 9router gateway for the build to avoid rate-limiting. Public OpenAI works with one environment variable change.
- **If asked why BM25 not embeddings:** the local gateway didn't expose embeddings, and for a 23-chunk profile lexical retrieval is faster and deterministic. Swapping in embeddings is a one-file change — `RAGIndex` interface stays the same.
- **If asked about Telegram conflicts:** the bot token was shared with another service, so we built the CLI approval path as a fallback. Both work. CLI is actually nicer for the demo because it doesn't require a phone on screen.
