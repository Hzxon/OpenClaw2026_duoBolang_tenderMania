# OpenClaw2026_duoBolang_SponsorUs

> # **TenderMania**
>
> Autonomous tender-hunting agent — finds compatible procurement opportunities for a company, scores fit through a multi-agent reasoning loop, and drafts personalized expressions of interest gated by human approval.


---

## What it does

A consultancy spends hours every week trawling LPSE, World Bank, and ministry portals for tenders that fit. Most don't. SponsorUs replaces that grind with an agent loop:

```
[live scrape]  →  [LLM normalize → Pydantic]  →  [3 parallel scorer agents]
                                                          ↓
                            [archive] ← below threshold ← [aggregator + hard gates]
                                                          ↓ above
                              [RAG-grounded EOI drafter]  →  [Telegram approval]  →  [SMTP send]
```

Every arrow is a tool call. The whole loop runs unattended on a single command. Only the final send is gated on a human tap.

There is no chat UI. The agents act on a schedule, score with reasoning, and produce concrete artifacts (drafts in SQLite, approval cards on Telegram).

---

## Architecture

### Multi-agent topology

```
                 ┌────────────────────────────────────────────┐
                 │  Scraper agents (one per source — tool calls)│
                 │  ┌─────────────────┐  ┌──────────────────┐ │
                 │  │ LPSE / PLN eProc │  │ World Bank API   │ │
                 │  │ (Indonesian BUMN)│  │ (global, 400k)   │ │
                 │  └────────┬────────┘  └────────┬─────────┘ │
                 │           └──────────┬─────────┘           │
                 └──────────────────────┼─────────────────────┘
                                        ▼
                              ┌──────────────────┐
                              │ Normalizer agent │  LLM + Pydantic → TenderOpportunity
                              └────────┬─────────┘
                                       ▼
       ┌───────────────────────────────┴────────────────────┐
       │     Multi-agent fan-out (asyncio)                  │
       ├──────────┬──────────────┬─────────────────────────┤
       │ capability│ eligibility │ win-prob                │   3 LLM calls in parallel
       │  scorer   │   scorer    │  scorer                 │   each cites RAG evidence
       └────┬─────┴───────┬─────┴───────┬──────────────────┘
            └─────────────┼─────────────┘
                          ▼
                ┌────────────────────┐
                │  Aggregator        │  hard-gates + weighted threshold
                │  (rule + LLM)      │  → pursue | archive
                └─────────┬──────────┘
                          ▼ pursue
                ┌────────────────────┐
                │  Drafter agent     │  RAG-grounded EOI in
                │  (LLM + RAG)       │  Bahasa or English
                └─────────┬──────────┘
                          ▼
                ┌────────────────────┐
                │  Approval gate     │  CLI (`scripts/approve`) or Telegram
                │                    │  inline buttons → callback
                └─────────┬──────────┘
                          ▼ approve
                ┌────────────────────┐
                │  Email sender      │  yagmail (DRY_RUN by default)
                └────────────────────┘
```

The system gives you two approval paths so the demo doesn't fight your existing tools:

- **CLI approval (no token conflicts):** `python3 -m sponsorus.scripts.approve` lists pending drafts, lets you approve, deny, or inspect by ID. The send tool only fires after approval.
- **Telegram approval (when the token is free):** `python3 -m sponsorus.telegram_bot` runs a long-poll bot. Pipeline pushes a card with ✅/❌ inline buttons; tapping ✅ moves the draft to `approved` and triggers the send tool.

### Hard gates (deterministic, not LLM-decided)

- `eligibility_fit < 30` → mandatory archive (cannot legally bid)
- `capability_fit < 35` → mandatory archive (clearly outside expertise)
- `weighted_score < threshold` → mandatory archive

The LLM only writes the rationale once a tender clears these rules. This is how we make the system auditable — every archive has a deterministic reason; only `pursue` decisions involve LLM judgment.

### Why BM25 instead of embeddings

Our local LLM gateway (9router) doesn't expose an embeddings endpoint. Rather than ship a 300MB sentence-transformers dep for ~25 profile chunks, we use a tiny BM25 index. For corpora this small, lexical retrieval is fast, deterministic, and grounds the scorers just as well. The `RAGIndex` interface is unchanged, so swapping in embeddings later is a one-file change.

---

## Live data sources

The pipeline pulls from two real, public, no-auth procurement endpoints in parallel:

1. **PLN e-Procurement** — `https://eproc.pln.co.id/portal/pengumuman_pengadaan/alldatakhs`
   Public DataTables JSON of *Kontrak Harga Satuan* (multi-year unit-price) tenders from PLN, Indonesia's national electricity BUMN. Includes pengadaan barang, jasa lainnya, jasa konsultansi, and pekerjaan konstruksi across regional units.

2. **World Bank Procurement Notices** — `https://search.worldbank.org/api/v2/procnotices`
   Public REST API exposing 400k+ live procurement notices across World-Bank-funded projects worldwide, including Indonesia, SEA, and global IT-development tenders.

Both sources have curated Indonesian-flavored fallback fixtures (`data/fixtures/`) so demos work without network. Switch sources with `SOURCES=lpse,worldbank` (default) or single-source via `SOURCES=lpse` / `SOURCES=worldbank`.

---

## Tech Stack

- **Python 3.11+**
- **Scrape:** `httpx` + Python `urllib` (World Bank API), `selectolax` for HTML fallback
- **Schemas:** `pydantic` v2 with strict JSON-mode prompts
- **RAG:** custom BM25 (no third-party dep)
- **Persistence:** SQLite via stdlib
- **Approval gate:** `python-telegram-bot` v22 (long-polling, callback queries)
- **Email:** `yagmail` (DRY_RUN bypass for safe demos)
- **Reliability:** `tenacity` retries on every LLM call

---

## Quick Start

```bash
git clone https://github.com/Hzxon/OpenClaw2026_duoBolang_SponsorUs.git
cd OpenClaw2026_duoBolang_SponsorUs

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
#  edit .env:
#    OPENAI_API_KEY=...           (or SPONSORUS_LLM_BASE_URL for a local gateway)
#    TELEGRAM_BOT_TOKEN=...       (optional — drafts still persist without it)
#    TELEGRAM_OPERATOR_CHAT_ID=...

python3 -m sponsorus.scripts.init_db
python3 -m sponsorus.scripts.seed_company

#  one autonomous cycle (scrape → score → draft)
python3 -m sponsorus.run_pipeline

#  list pending drafts
python3 -m sponsorus.scripts.approve

#  inspect / approve / deny a draft (the human-in-the-loop gate)
python3 -m sponsorus.scripts.approve 1 show
python3 -m sponsorus.scripts.approve 1 approve   # triggers send_email tool (DRY_RUN by default)
python3 -m sponsorus.scripts.approve 1 deny

#  optional — Telegram approval bot (long-poll). Only run if the bot
#  token is not already in use by another service (e.g. Hermes Gateway).
python3 -m sponsorus.telegram_bot
```

### Environment variables

| Var | Default | Purpose |
|-----|---------|---------|
| `OPENAI_API_KEY` | `sk-9router-local` | Bearer for the LLM endpoint |
| `SCORE_THRESHOLD` | `60` | Weighted-score gate |
| `MAX_TENDERS` | `5` | Tenders processed per run |
| `PREFER_LIVE` | `true` | Live scrape vs cached fixture |
| `PUSH_TELEGRAM` | `true` | Push approvals to Telegram |
| `DRY_RUN` | `true` | Print emails instead of sending |
| `TELEGRAM_BOT_TOKEN` | — | BotFather token |
| `TELEGRAM_OPERATOR_CHAT_ID` | — | Where approval cards land |

---

## Repo layout

```
sponsorus/
  agents/
    scrape.py          live World Bank tender API + fixture fallback
    normalize.py       LLM → Pydantic TenderOpportunity
    score.py           3 scorer agents + aggregator (hard gates)
    draft.py           RAG-grounded EOI drafter
    send.py            yagmail SMTP, DRY_RUN safe
  schemas.py           Pydantic contracts between agents
  rag.py               BM25 index over company profile
  llm.py               Provider-agnostic structured output
  db.py                SQLite layer
  telegram_bot.py      Approval gate (push + callbacks)
  run_pipeline.py      Autonomous orchestrator (the agent loop)
  scripts/
    init_db.py         One-shot DB setup
    seed_company.py    Load company profile from YAML
    approve.py         CLI approve/deny/inspect for pending drafts
    demo.py            One-cycle demo runner
    seed_event.py      [legacy compat shim — redirects to seed_company]
data/
  company_profile.yaml The company on whose behalf the agent hunts
  fixtures/            Cached scrape blob for offline demo
prompts/               (versioned prompt drafts; live prompts inline in agents)
```

---

## Sample run output

```
[pipeline] run 209459b8 started — threshold=55.0, live=True
[pipeline] company: Bolang Solutions
[pipeline] RAG index built over 23 chunks
[pipeline] scraped 4 raw tenders from live:worldbank-procnotices
[pipeline] [1/4] normalizing: Pilot for design, development and implementation of VO, MS and ZS accounting...
[pipeline]   scoring (3 agents in parallel)…
[pipeline]   → PURSUE (weighted=62.5; cap=70, elig=58, win=51)
[pipeline]   drafted EOI #1
[pipeline] [2/4] normalizing: National Strategy for Financial Literacy
[pipeline]   → ARCHIVE (weighted=28.1; cap=25, elig=38, win=18)
[pipeline] [3/4] normalizing: Senior Spatial Data Coordinator (job posting)
[pipeline]   → ARCHIVE (weighted=39.5; cap=42, elig=45, win=24)
[pipeline] [4/4] normalizing: GIS Phase-2 Development
[pipeline]   → PURSUE (weighted=56.4; cap=68, elig=52, win=38)
[pipeline]   drafted EOI #2
[pipeline] run 209459b8 done in 66.1s
```

The agent correctly:
- archived a strategy/policy contract (no software deliverables)
- archived a job posting that surfaced through the procurement feed
- pursued two real software-development tenders

---

## License

MIT
