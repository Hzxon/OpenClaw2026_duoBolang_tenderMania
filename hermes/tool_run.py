"""Programmatic entrypoint for Hermes tools / delegate_task subagents.

Exposes a single function `run_tendermania(...)` that runs a pipeline
cycle and returns a structured dict — designed to be called from a
Hermes tool wrapper, a `delegate_task` worker, or a `terminal()` call.

Usage from Hermes:
    terminal(command="cd ~/tendermania && source .venv/bin/activate && \
        python3 -m hermes.tool_run --sources lpse,worldbank --max 6")

Or from another Python process:
    from hermes.tool_run import run_tendermania
    result = run_tendermania(sources=["lpse"], max_tenders=4)
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any, Optional


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _set_env(key: str, value: str) -> None:
    if value is not None and value != "":
        os.environ[key] = str(value)


def run_tendermania(
    sources: Optional[list[str]] = None,
    max_tenders: int = 4,
    score_threshold: float = 60.0,
    prefer_live: bool = True,
    push_telegram: bool = False,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Run a single TenderMania pipeline cycle and return a summary dict.

    Returns
    -------
    dict with keys: run_id, elapsed_s, tenders_seen, tenders_pursued,
    tenders_archived, source, pending_drafts (list).
    """
    root = _project_root()
    os.chdir(root)

    if sources is None:
        sources = ["lpse", "worldbank"]

    _set_env("SOURCES", ",".join(sources))
    _set_env("MAX_TENDERS", str(max_tenders))
    _set_env("SCORE_THRESHOLD", str(score_threshold))
    _set_env("PREFER_LIVE", "true" if prefer_live else "false")
    _set_env("PUSH_TELEGRAM", "true" if push_telegram else "false")
    _set_env("DRY_RUN", "true" if dry_run else "false")

    # Lazy import — module assumes project root is on sys.path
    sys.path.insert(0, str(root))
    from sponsorus.run_pipeline import run_pipeline as _rp  # type: ignore

    stats = _rp(
        prefer_live=prefer_live,
        max_tenders=max_tenders,
        threshold=score_threshold,
        push_telegram=push_telegram,
        sources=sources,
    )

    # Read pending drafts from audit trail for richer return value
    db_path = root / "data" / "sponsorus.db"
    pending: list[dict[str, Any]] = []
    if db_path.exists():
        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT d.id, d.subject, t.buyer, t.title "
                "FROM drafts d JOIN tenders t ON d.tender_id = t.id "
                "WHERE d.status = 'pending' "
                "ORDER BY d.id DESC LIMIT 10"
            ).fetchall()
            pending = [dict(r) for r in rows]

    return {
        **(stats or {}),
        "pending_drafts": pending,
    }


def _cli() -> None:
    p = argparse.ArgumentParser(
        description="Hermes-friendly TenderMania entrypoint"
    )
    p.add_argument("--sources", default="lpse,worldbank",
                   help="Comma-separated source list")
    p.add_argument("--max", type=int, default=4, dest="max_tenders",
                   help="Max tenders per run")
    p.add_argument("--threshold", type=float, default=60.0,
                   dest="score_threshold",
                   help="Weighted-score threshold for pursue")
    p.add_argument("--no-live", action="store_true",
                   help="Use fixture corpus (offline-deterministic)")
    p.add_argument("--push-telegram", action="store_true",
                   help="Push approval cards to Telegram")
    p.add_argument("--no-dry-run", action="store_true",
                   help="Actually send emails (requires SMTP config)")
    args = p.parse_args()

    result = run_tendermania(
        sources=[s.strip() for s in args.sources.split(",") if s.strip()],
        max_tenders=args.max_tenders,
        score_threshold=args.score_threshold,
        prefer_live=not args.no_live,
        push_telegram=args.push_telegram,
        dry_run=not args.no_dry_run,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    _cli()
