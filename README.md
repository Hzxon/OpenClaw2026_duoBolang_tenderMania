# OpenClaw2026_duoBolang_SponsorUs

**SponsorUs** — autonomous multi-agent system that finds compatible sponsors for events/communities, scores fit with reasoning, and drafts personalized outreach emails gated by human Telegram approval.

Built for **OpenClaw Agenthon 2026** (RISTEK x Build Club), 12-hour build sprint, May 15 2026.

## Why this isn't a chatbot

Zero conversational UI. Pipeline runs on its own:

```
[scrape live web]  →  [normalize w/ LLM JSON]  →  [3 parallel scorers (multi-agent)]
                                                        ↓
                          [archive] ← below threshold ← [aggregator]
                                                        ↓ above
                          [RAG-grounded outreach drafter]  →  [Telegram approval]  →  [SMTP send]
```

Each arrow is a tool call. The whole loop runs unattended on a cron tick or one-shot CLI invocation.

## Architecture

- **Scraper agent** — `httpx` + `selectolax` against a live sponsor-prospect listing (with cached fixture fallback for demo reliability).
- **Normalizer agent** — OpenAI structured output (Pydantic schema) turns raw HTML blobs into `SponsorProspect` records.
- **Scorer trio (parallel, async)**:
  - *Capability fit* — RAG over the event's profile + past sponsors (cosine over OpenAI embeddings).
  - *Strategic fit* — sector / audience / budget alignment.
  - *Activation likelihood* — recency signals, deadline pressure, contactability.
- **Aggregator** — weighted combine, hard eligibility gate, threshold decision with cited reasoning.
- **Drafter agent** — composes a personalized cold-outreach email grounded in the event's unique value prop, citing sponsor-side hooks the scorer surfaced.
- **Approval gate** — Telegram bot pings the operator, who replies `/approve <id>` or `/deny <id>`. No auto-send in v1.
- **Sender tool** — yagmail SMTP, only fires after explicit approval.

Storage: SQLite (`data/sponsorus.db`). RAG vectors cached in-process.

## Tech Stack

- Python 3.11+
- OpenAI API (`gpt-4o-mini` for normalize/score, `text-embedding-3-small` for RAG)
- `httpx` + `selectolax` (scrape)
- `pydantic` (structured output validation)
- `python-telegram-bot` (approval gate)
- `yagmail` (SMTP send)
- SQLite stdlib
- Hermes Agent (orchestration / cron / gateway)

## Quick Start

```bash
git clone https://github.com/Hzxon/OpenClaw2026_duoBolang_SponsorUs.git
cd OpenClaw2026_duoBolang_SponsorUs
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in OPENAI_API_KEY, TELEGRAM_BOT_TOKEN, SMTP_*
python3 -m sponsorus.scripts.init_db
python3 -m sponsorus.scripts.seed_event
python3 -m sponsorus.run_pipeline   # one full autonomous cycle
```

## Demo

Demo video: see Devpost submission (Unlisted YouTube link).

## Repo layout

```
sponsorus/
  agents/         scrape, normalize, score, draft, send
  schemas.py      Pydantic models
  db.py           SQLite layer
  rag.py          embeddings + cosine
  pipeline.py     autonomous loop orchestrator
  telegram_bot.py approval gate
  scripts/        init_db, seed_event, demo
data/
  fixtures/       cached HTML for offline demo fallback
  event_profile.yaml
prompts/          versioned LLM prompts
```

## License

MIT
