# Pitch Deck Outline (5 slides)

Build with Gamma.app or Slides — paste these bullets into the prompt or the slide notes.

---

## Slide 1 — Title
**TenderMania**
*Autonomous tender-hunting agent*

OpenClaw Agenthon 2026 · Team duoBolang
- Hzxon (build / repo)
- (your teammate)

GitHub: github.com/Hzxon/OpenClaw2026_duoBolang_SponsorUs (repo retains legacy name)

---

## Slide 2 — Problem
Indonesian software consultancies waste 10–20 hours every week trawling LPSE, World Bank, and ministry tender portals. Most listings are wrong-fit (construction, hardware, oil & gas). The handful of real opportunities are buried in PDFs, in Indonesian and English, with overlapping deadlines and badan-usaha eligibility rules.

The cost of missing a fit is a five-figure-USD contract walking past. The cost of bidding on a bad fit is two engineer-weeks of wasted bid-writing.

---

## Slide 3 — Solution: a multi-agent loop
- **Scraper agent** — live tender feed (World Bank API → 400 k tenders, fallback fixture)
- **Normalizer agent** — LLM with strict Pydantic schema; refuses to invent fields
- **Three parallel scorer agents** — capability / eligibility / win-probability, RAG-grounded, evidence-cited
- **Aggregator** — deterministic hard gates + weighted threshold
- **Drafter agent** — RAG-grounded expression-of-interest, in Bahasa Indonesia or English by buyer country
- **Telegram approval gate** — inline ✅ / ❌ buttons; nothing sends without a human tap

End-to-end runtime per tender: **~15 seconds**, fully autonomous up to the approval step.

---

## Slide 4 — Architecture & tech

```
[scrape] → [normalize] → [score×3 parallel] → [aggregate] → [draft] → [Telegram] → [SMTP]
```

- LLM: any OpenAI-compatible endpoint (defaults to local 9router · `cx/gpt-5.5`)
- BM25 RAG over the company profile (no embeddings dep)
- SQLite full audit trail: scores, reasoning, evidence, decisions, drafts, sends
- Hard gates encoded in Python — LLM cannot override eligibility fail
- DRY_RUN by default — safe to demo

Why not a single big prompt? Decomposed scoring is auditable. A reviewer can see *which* dimension killed a tender, *why*, and *what evidence* was cited.

---

## Slide 5 — Impact & next steps

**Today**
- 1 live source (World Bank), 1 company profile, end-to-end loop, Telegram approval
- Verified: archives non-fit (financial-literacy strategy w=28, hardware procurement)
- Pursues fit (GIS development w=56, accounting platform w=62)

**Next 4 weeks**
- LPSE national + ministry-specific scrapers (Playwright + PDF OCR)
- Past-bid outcome learning loop → tunes scoring weights
- Multi-tenant: one Hermes profile per consultancy, isolated config + DB
- Cron-driven hourly tender ingestion + digest

**Stretch**
- Bid-document drafting agent (proposal skeleton from past wins)
- Proactive partner-matching (small firm → JV with bigger firm to clear team-size requirements)
