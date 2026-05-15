---
name: tendermania
description: "Hunt compatible Indonesian government & World Bank tenders for a software consultancy and draft expression-of-interest emails."
version: 1.0.0
author: duoBolang (Hazron + team) for OpenClaw Agenthon 2026
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [agentic, multi-agent, tenders, indonesia, bumn, lpse, world-bank, procurement, agenthon]
    homepage: https://github.com/Hzxon/OpenClaw2026_duoBolang_SponsorUs
---

# TenderMania — Autonomous Tender Hunter

TenderMania is a multi-agent system that finds compatible procurement tenders
for an Indonesian software consultancy, scores them on three dimensions in
parallel, and drafts a personalized expression of interest in Bahasa Indonesia.

This skill teaches Hermes how to install, run, and operate TenderMania from
any session — locally, via cron schedule, or from a `delegate_task` subagent.

## Architecture (TL;DR)

```
LPSE / World Bank → Scraper → Normalizer → 3 Parallel Scorers
                                            (capability_fit, eligibility_fit, win_probability)
                                            ↓
                                            Aggregator → Drafter → Approval gate
                                                                    ↓
                                                                    send_email tool (DRY_RUN)
```

- **LLM:** any OpenAI-compatible endpoint (default: 9router at `http://localhost:20128/v1`)
- **RAG:** BM25 over a 23-chunk Bolang Solutions company profile
- **Storage:** SQLite (tenders, scores, drafts, runs)
- **Approval:** Telegram inline buttons + CLI fallback
- **Hackathon shipping date:** OpenClaw Agenthon 2026 (15-May-2026)

## Quick Install (for Hermes operators)

```bash
# 1. Clone the repo
git clone https://github.com/Hzxon/OpenClaw2026_duoBolang_SponsorUs.git ~/tendermania

# 2. Set up the venv (one-time)
cd ~/tendermania
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Configure
cp .env.example .env
# Edit .env — set OPENAI_API_KEY (or point SPONSORUS_LLM_BASE_URL at a local proxy)

# 4. Initialize SQLite + seed company profile
python3 -m sponsorus.scripts.init_db
python3 -m sponsorus.scripts.seed_company

# 5. Verify by running the demo
./demo.sh --auto
```

End-to-end run takes ~70s and produces 2 RAG-grounded EOI drafts in Bahasa Indonesia.

## How to use TenderMania from Hermes

### Pattern 1 — One-shot from any Hermes session

Run a complete pipeline cycle and report what got pursued:

```
terminal(command="cd ~/tendermania && source .venv/bin/activate && \
  set -a && source .env && set +a && \
  SOURCES=lpse,worldbank MAX_TENDERS=6 SCORE_THRESHOLD=55 \
  PUSH_TELEGRAM=true python3 -m sponsorus.run_pipeline", timeout=180)
```

After it returns, check the audit trail:
```
terminal(command="cd ~/tendermania && python3 -m sponsorus.scripts.approve")
```

### Pattern 2 — Daily autonomous hunt via Hermes cron

Schedule TenderMania to run every weekday morning, score new tenders, and
push approval cards to Telegram:

```
cronjob(
  action="create",
  name="tendermania-daily-hunt",
  schedule="0 9 * * 1-5",
  prompt="Run TenderMania for the day. Use the helper script at "
         "~/tendermania/hermes/cron_run.sh to scan LPSE + World Bank, "
         "then summarize the run: number scored, pursued vs archived, "
         "and the top-scored tender's title and score. "
         "Don't fabricate anything — read from the SQLite audit trail.",
  script="~/tendermania/hermes/cron_run.sh",
  enabled_toolsets=["terminal", "file"],
  deliver="origin"
)
```

The script collects fresh tenders deterministically; the agent summarizes
the run for delivery (Telegram, Discord, etc.) per `deliver=...`.

### Pattern 3 — Subagent delegation for triage + outreach

Spin up a focused worker that hunts for one specific sector and reports
back without spamming the main conversation context:

```
delegate_task(
  goal="Hunt tenders matching 'AI chatbot' or 'GIS' in Indonesia. "
       "Run the TenderMania pipeline with SCORE_THRESHOLD=60, "
       "list pending drafts, inspect the top-scored one, and "
       "report back: tender title, buyer, score breakdown, and "
       "a 2-sentence summary of why the agent thinks it's a fit.",
  context="TenderMania repo at ~/tendermania. Activate venv, source .env, "
          "use SOURCES=lpse PREFER_LIVE=true. Audit trail in "
          "data/sponsorus.db. Approve tool at "
          "python3 -m sponsorus.scripts.approve.",
  toolsets=["terminal", "file"]
)
```

### Pattern 4 — Approve from anywhere via Hermes

The CLI approval path is single-command and side-effect-aware:

```
terminal(command="cd ~/tendermania && source .venv/bin/activate && "
                  "python3 -m sponsorus.scripts.approve <draft_id> show")

terminal(command="cd ~/tendermania && source .venv/bin/activate && "
                  "python3 -m sponsorus.scripts.approve <draft_id> approve")
```

`approve` triggers the `send_email` tool. With `DRY_RUN=true` (the default
in `.env.example`) it prints the email instead of sending — safe for
production-adjacent demos.

## Environment variables

| Variable | Default | Required? | Purpose |
|----------|---------|-----------|---------|
| `OPENAI_API_KEY` | — | yes | Auth for the LLM endpoint |
| `SPONSORUS_LLM_BASE_URL` | `http://localhost:20128/v1` | no | OpenAI-compatible base URL |
| `SPONSORUS_LLM_MODEL` | `cx/gpt-5.5` | no | Model id passed to the endpoint |
| `SOURCES` | `lpse,worldbank` | no | Comma-separated source list |
| `PREFER_LIVE` | `true` | no | If `false`, use offline fixture corpus |
| `SCORE_THRESHOLD` | `60` | no | Weighted-score cutoff for `pursue` |
| `MAX_TENDERS` | `4` | no | Max tenders processed per run |
| `PUSH_TELEGRAM` | `true` | no | Push approval cards to Telegram |
| `DRY_RUN` | `true` | no | If `true`, send_email prints instead |
| `TELEGRAM_BOT_TOKEN` | — | iff push | Bot token from @BotFather |
| `TELEGRAM_OPERATOR_CHAT_ID` | — | iff push | Numeric chat id for approval cards |

## Pitfalls (real ones, found during build)

1. **Hermes Gateway and TenderMania can't both poll the same Telegram bot token.**
   Telegram only allows one `getUpdates` consumer per token. Two strategies:
   - Use `PUSH_TELEGRAM=true` only — outbound `sendMessage` doesn't conflict.
     CLI approval still triggers the actual send tool. (Current `demo.sh` setup.)
   - Or `hermes gateway stop` → run `python3 -m sponsorus.telegram_bot` →
     restore with `hermes gateway start` after demo.

2. **macOS Python 3.14 + LPSE.go.id TLS = sad.** Some `.go.id` portals use
   legacy ciphers Python's bundled OpenSSL rejects. PLN's e-procurement
   (`https://eproc.pln.co.id`) works fine and is the live source we ship.
   For unreachable portals, set `PREFER_LIVE=false` to use the fixture corpus.

3. **No embeddings endpoint at 9router** — we use BM25 (rank_bm25) instead
   of vector retrieval. Drafts cite real RAG chunks from the company profile
   and stay grounded.

4. **Perl LWP `head` shadows coreutils `head` on some macOS PATH setups.**
   `demo.sh` uses `sed -n '1,25p'` to avoid the failure.

5. **Pipeline is long — set `timeout=180+` on the `terminal()` call.** A
   2-tender run is ~70s. A 6-tender run is ~150s. Use `background=true` +
   `notify_on_complete=true` for runs over 60s in interactive sessions.

## File map

```
~/tendermania/
├── sponsorus/
│   ├── agents/         scrape, scrape_lpse, normalize, score, draft, send
│   ├── run_pipeline.py orchestrator
│   ├── scripts/        init_db, seed_company, approve
│   ├── rag.py          BM25 retrieval over company profile
│   ├── llm.py          OpenAI client, 9router-routed
│   ├── db.py           SQLite schema + helpers
│   ├── schemas.py      Pydantic v2 — TenderOpportunity, ScoringResult, OutreachDraft
│   └── telegram_bot.py polling bot for approval callbacks (optional)
├── data/
│   ├── company_profile.yaml  Bolang Solutions persona
│   ├── fixtures/             offline LPSE + World Bank seed corpus
│   └── sponsorus.db          SQLite audit trail (auto-created)
├── hermes/
│   ├── cron_run.sh     daily-hunt helper (used by cron pattern above)
│   └── tool_run.py     thin programmatic entrypoint for tools/subagents
├── docs/
│   ├── DEMO_SCRIPT.md  2-min recording walkthrough
│   └── PITCH_DECK.md   6-slide pitch deck script
├── demo.sh             one-command demo runner
└── README.md           jury-friendly setup guide
```

## Verification before claiming success

After invoking TenderMania, always verify the audit trail rather than
trusting stdout. The pipeline writes everything to SQLite; a clean run
produces 1 row in `runs`, N rows in `tenders`, 3·N rows in `scores` (3
dimensions per tender), and one `drafts` row per pursued tender:

```
python3 -c "import sqlite3; c=sqlite3.connect('data/sponsorus.db'); \
  print({t: c.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] \
         for t in ['runs','tenders','scores','drafts']})"
```

If counts don't match expectations, the run partially failed — check
`data/sponsorus.db` rows for a `runs.status` of `error`.

## Project credits

Built for OpenClaw Agenthon 2026 by team **duoBolang**. Repo:
https://github.com/Hzxon/OpenClaw2026_duoBolang_SponsorUs (renamed from
SponsorUs to TenderMania mid-build; URL preserved for commit attribution).
