"""Autonomous orchestrator — the AGENT LOOP.

Runs end-to-end without human intervention until the approval gate:
  1. Scrape live web for sponsor prospects.
  2. Normalize each into a SponsorProspect (LLM tool call).
  3. Persist to SQLite.
  4. Build a RAG index over the event profile.
  5. Fan out 3 scorer agents in parallel for each prospect.
  6. Aggregate + threshold decide pursue/archive.
  7. For each pursued prospect, draft outreach (LLM) and persist.
  8. Push every draft to Telegram for human approval.

Steps 1-7 are fully autonomous. Step 8 is the explicit
human-in-the-loop gate — required for any system that sends external email.
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
from sponsorus.agents.scrape import scrape
from sponsorus.rag import RAGIndex, event_profile_to_chunks
from sponsorus.schemas import OutreachDraft

load_dotenv()


def _log(msg: str) -> None:
    print(f"[pipeline] {msg}", flush=True)


def run_pipeline(
    prefer_live: bool = True,
    max_prospects: int = 8,
    threshold: Optional[float] = None,
    push_telegram: bool = True,
) -> dict:
    threshold = threshold if threshold is not None else float(os.environ.get("SCORE_THRESHOLD", "65"))
    run_id = uuid.uuid4().hex[:8]
    db.start_run(run_id)
    t0 = time.time()
    _log(f"run {run_id} started — threshold={threshold}, live={prefer_live}")

    profile = db.load_event_profile()
    if not profile:
        raise SystemExit("No event profile loaded. Run: python3 -m sponsorus.scripts.seed_event")
    _log(f"event: {profile['name']} ({profile.get('tagline')})")

    rag = RAGIndex.build(event_profile_to_chunks(profile))
    _log(f"RAG index built over {len(rag.chunks)} chunks")

    raw_list, source_label = scrape(prefer_live=prefer_live, max_results=max_prospects)
    _log(f"scraped {len(raw_list)} raw prospects from {source_label}")

    pursued: list[tuple[int, "OutreachDraft"]] = []
    archived = 0

    for i, raw in enumerate(raw_list, start=1):
        _log(f"[{i}/{len(raw_list)}] normalizing: {raw.name}")
        try:
            prospect = normalize(raw)
        except Exception as e:  # noqa: BLE001
            _log(f"  normalize failed: {e!r}")
            continue
        prospect_id = db.upsert_prospect(prospect.model_dump(mode="json"))

        ctx = ScoreContext(prospect=prospect, event_profile=profile, rag=rag)
        _log(f"  scoring {prospect.company_name} (3 agents in parallel)…")
        try:
            scores = score_all(ctx)
        except Exception as e:  # noqa: BLE001
            _log(f"  score failed: {e!r}")
            continue
        for s in scores:
            db.insert_score(prospect_id, s.dimension, s.score, s.reasoning, s.evidence)

        decision = aggregate(ctx, scores, threshold=threshold)
        db.insert_decision(
            prospect_id,
            weighted=decision.weighted_score,
            decision=decision.decision,
            rationale=decision.rationale,
        )
        _log(
            f"  → {decision.decision.upper()} "
            f"(weighted={decision.weighted_score:.1f}; "
            f"cap={decision.capability_fit}, strat={decision.strategic_fit}, "
            f"act={decision.activation_likelihood})"
        )

        if decision.decision == "pursue":
            try:
                draft = draft_outreach(prospect, profile, scores, rag)
                draft_id = db.insert_draft(
                    prospect_id,
                    draft.subject,
                    draft.body_markdown,
                    draft.personalization_notes,
                )
                pursued.append((draft_id, draft))
                _log(f"  drafted outreach #{draft_id}: {draft.subject!r}")
            except Exception as e:  # noqa: BLE001
                _log(f"  draft failed: {e!r}")
        else:
            archived += 1

    # Push to Telegram (best-effort — pipeline still succeeds if Telegram is down).
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
        "prospects_seen": len(raw_list),
        "prospects_pursued": len(pursued),
        "prospects_archived": archived,
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
        max_prospects=int(os.environ.get("MAX_PROSPECTS", "8")),
        push_telegram=os.environ.get("PUSH_TELEGRAM", "true").lower() in ("1", "true", "yes"),
    )
    print("\n=== PIPELINE STATS ===")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    sys.exit(0)


if __name__ == "__main__":
    main()
