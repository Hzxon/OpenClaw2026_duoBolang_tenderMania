# Demo Recording Script (≤ 2 minutes)

Format: voice-over OBS screen capture. Three browser/terminal windows pre-arranged.

## Pre-recording setup
1. Reset DB so output is clean:
   ```bash
   rm -f data/sponsorus.db
   python3 -m sponsorus.scripts.init_db
   python3 -m sponsorus.scripts.seed_company
   ```
2. Open three windows side-by-side:
   - **Left:** terminal at the repo root, venv active.
   - **Top right:** `data/company_profile.yaml` open in editor.
   - **Bottom right:** Telegram desktop with the operator chat visible.
3. Start `python3 -m sponsorus.telegram_bot` in a fourth terminal (offscreen).

## Spoken narration (target 110 seconds)

```
0:00–0:08  "This is SponsorUs — an autonomous multi-agent system that finds
            compatible tenders for a company. Built in twelve hours for
            OpenClaw Agenthon 2026."

0:08–0:18  [show company_profile.yaml]
           "Here's our company — Bolang Solutions. 28 engineers, ISO 27001,
            past contracts with two ministries. The agent learns this profile
            once."

0:18–0:32  [run: python3 -m sponsorus.run_pipeline]
           "One command. The orchestrator scrapes the World Bank procurement
            API live — four hundred thousand real tenders.
            For each one, it calls a normalizer agent that produces strict
            Pydantic-validated JSON."

0:32–0:50  [point at "scoring (3 agents in parallel)" lines]
           "Then three scorer agents run in parallel via asyncio: capability,
            eligibility, and win probability. Each one is RAG-grounded against
            the company profile and must cite concrete evidence in its
            reasoning. Watch the decisions:"

0:50–1:05  [highlight ARCHIVE w=28 line]
           "A financial-literacy strategy gets archived — capability score 25,
            no software deliverables. The hard-gate aggregator blocks it
            deterministically — the LLM doesn't get to override hard rules."

1:05–1:18  [highlight PURSUE w=56 line]
           "A Uganda GIS development tender gets pursued — capability 68
            because we have React, FastAPI, and dashboard experience. The
            agent then drafts an expression of interest."

1:18–1:35  [switch to Telegram window]
           "The draft lands here. Notice it cites the actual past contracts
            and the ISO certification. Notice it also flags the Indonesia
            vs. Uganda geography risk honestly."

1:35–1:50  [tap ✅ Approve]
           "When I approve, the email sends — in dry-run for this demo.
            Without my tap, nothing leaves the system."

1:50–2:00  "Multi-agent. Tool-using. Autonomous loop. Real source. Audit trail.
            That's SponsorUs."
```

## Common pitfalls
- Don't show secrets — keep `.env` out of the recording frame.
- If the live scrape stalls, set `PREFER_LIVE=false` once before recording so the fixture is hot.
- Use `MAX_TENDERS=4` so the run stays under 75 seconds on screen.
