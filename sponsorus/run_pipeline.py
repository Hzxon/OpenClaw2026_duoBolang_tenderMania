"""Autonomous orchestrator — the AGENT LOOP.

Runs end-to-end without human intervention until the approval gate:
  1. Scrape live tender notices from World Bank procurement API.
  2. Normalize each into a TenderOpportunity (LLM tool call).
  3. Persist to SQLite.
  4. Build a RAG index over the company profile.
  5. Fan out 3 scorer agents in parallel for each tender.
  6. Aggregate + threshold decide pursue/archive.
  7. For each pursued tender, draft an expression-of-interest (LLM) and persist.
  8. Push every draft to Telegram for human approval.

Steps 1-7 are fully autonomous. Step 8 is the human-in-the-loop gate —
required for any system that sends external email.
"""
from __future__ import annotations

import os
import sys
import time
import uuid
from typing import Optional

from dotenv import load_dotenv

from sponsorus import db
from sponsorus.agents.draft import draft_outreach
from sponsorus.agents.normalize import normalize
from sponsorus.agents.score import ScoreContext, aggregate, score_all
from sponsorus.agents.scrape import scrape as scrape_worldbank
from sponsorus.agents.scrape_lpse import scrape as scrape_lpse
from sponsorus.rag import RAGIndex, company_profile_to_chunks
from sponsorus.schemas import OutreachDraft

load_dotenv()


def _log(msg: str) -> None:
    print(f"[pipeline] {msg}", flush=True)


def _dispatch_scrape(sources: list[str], prefer_live: bool, per_source: int) -> tuple[list, list[str]]:
    """Run all configured scraper agents and merge their outputs.

    Each scraper is a tool: it returns a list of RawTender + a source label.
    The orchestrator dispatches them in sequence (small N, no benefit to
    parallelizing the I/O at this volume) and concatenates results.
    """
    raw_all: list = []
    labels: list[str] = []
    for src in sources:
        if src == "worldbank":
            raws, lbl = scrape_worldbank(prefer_live=prefer_live, max_results=per_source)
        elif src == "lpse":
            raws, lbl = scrape_lpse(prefer_live=prefer_live, max_results=per_source)
        else:
            print(f"[pipeline] unknown source: {src!r}; skipping")
            continue
        print(f"[pipeline] {src}: {len(raws)} raw tenders ({lbl})")
        raw_all.extend(raws)
        labels.append(lbl)
    return raw_all, labels


def run_pipeline(
    prefer_live: bool = True,
    max_tenders: int = 6,
    threshold: Optional[float] = None,
    push_telegram: bool = True,
    sources: Optional[list[str]] = None,
) -> dict:
    threshold = threshold if threshold is not None else float(os.environ.get("SCORE_THRESHOLD", "60"))
    if sources is None:
        sources_env = os.environ.get("SOURCES", "lpse,worldbank")
        sources = [s.strip() for s in sources_env.split(",") if s.strip()]
    run_id = uuid.uuid4().hex[:8]
    db.start_run(run_id)
    t0 = time.time()
    _log(f"run {run_id} started — threshold={threshold}, sources={sources}, live={prefer_live}")

    profile = db.load_company_profile()
    if not profile:
        raise SystemExit("No company profile loaded. Run: python3 -m sponsorus.scripts.seed_company")
    _log(f"company: {profile['name']} ({profile.get('tagline')})")

    rag = RAGIndex.build(company_profile_to_chunks(profile))
    _log(f"RAG index built over {len(rag.chunks)} chunks")

    per_source = max(2, max_tenders // max(1, len(sources)))
    raw_list, source_labels = _dispatch_scrape(sources, prefer_live, per_source)
    raw_list = raw_list[:max_tenders]
    source_label = " + ".join(source_labels) if source_labels else "none"
    _log(f"merged {len(raw_list)} tenders from {len(sources)} source(s): {source_label}")

    pursued: list[tuple[int, OutreachDraft]] = []
    archived = 0

    for i, raw in enumerate(raw_list, start=1):
        _log(f"[{i}/{len(raw_list)}] normalizing: {raw.title[:80]}")
        try:
            tender = normalize(raw)
        except Exception as e:  # noqa: BLE001
            _log(f"  normalize failed: {e!r}")
            continue
        tender_id = db.upsert_tender(tender.model_dump(mode="json"))

        ctx = ScoreContext(tender=tender, company_profile=profile, rag=rag)
        _log(f"  scoring (3 agents in parallel)…")
        try:
            scores = score_all(ctx)
        except Exception as e:  # noqa: BLE001
            _log(f"  score failed: {e!r}")
            continue
        for s in scores:
            db.insert_score(tender_id, s.dimension, s.score, s.reasoning, s.evidence)

        decision = aggregate(ctx, scores, threshold=threshold)
        db.insert_decision(
            tender_id,
            weighted=decision.weighted_score,
            decision=decision.decision,
            rationale=decision.rationale,
        )
        _log(
            f"  → {decision.decision.upper()} "
            f"(weighted={decision.weighted_score:.1f}; "
            f"cap={decision.capability_fit}, elig={decision.eligibility_fit}, "
            f"win={decision.win_probability})"
        )

        if decision.decision == "pursue":
            try:
                draft = draft_outreach(tender, profile, scores, rag)
                draft_id = db.insert_draft(
                    tender_id,
                    draft.subject,
                    draft.body_markdown,
                    draft.personalization_notes,
                )
                pursued.append((draft_id, draft))
                _log(f"  drafted EOI #{draft_id}: {draft.subject!r}")
            except Exception as e:  # noqa: BLE001
                _log(f"  draft failed: {e!r}")
        else:
            archived += 1

    pushed = 0
    if push_telegram and pursued and os.environ.get("TELEGRAM_BOT_TOKEN"):
        from sponsorus.telegram_bot import push_draft_blocking

        for did, _ in pursued:
            try:
                push_draft_blocking(did)
                pushed += 1
            except Exception as e:  # noqa: BLE001
                _log(f"  telegram push failed for draft {did}: {e!r}")

    stats = {
        "run_id": run_id,
        "elapsed_s": round(time.time() - t0, 1),
        "tenders_seen": len(raw_list),
        "tenders_pursued": len(pursued),
        "tenders_archived": archived,
        "drafts_pushed_to_telegram": pushed,
        "source": source_label,
    }
    db.finish_run(run_id, stats)
    _log(f"run {run_id} done in {stats['elapsed_s']}s — {stats}")
    return stats


def main() -> None:
    db.init_db()
    stats = run_pipeline(
        prefer_live=os.environ.get("PREFER_LIVE", "true").lower() in ("1", "true", "yes"),
        max_tenders=int(os.environ.get("MAX_TENDERS", os.environ.get("MAX_PROSPECTS", "5"))),
        push_telegram=os.environ.get("PUSH_TELEGRAM", "true").lower() in ("1", "true", "yes"),
    )
    print("\n=== PIPELINE STATS ===")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    sys.exit(0)


if __name__ == "__main__":
    main()
