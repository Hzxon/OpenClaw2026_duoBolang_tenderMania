"""Demo helper — runs a single-prospect autonomous cycle, prints a tidy log,
and pushes the resulting draft (if any) to Telegram for approval.

Use this for the 2-minute demo recording. Pass a company name to force focus
on a specific prospect; otherwise it runs the live-scrape pipeline normally.
"""
from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv

from sponsorus import db
from sponsorus.run_pipeline import run_pipeline


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="SponsorUs demo cycle.")
    parser.add_argument("--max", type=int, default=int(os.environ.get("MAX_PROSPECTS", "3")))
    parser.add_argument("--threshold", type=float, default=float(os.environ.get("SCORE_THRESHOLD", "60")))
    parser.add_argument("--no-tg", action="store_true", help="Skip Telegram push (offline demo)")
    parser.add_argument("--fixture", action="store_true", help="Force fixture (no live scrape)")
    args = parser.parse_args()

    db.init_db()
    if not db.load_event_profile():
        from sponsorus.scripts.seed_event import main as seed_main

        seed_main()

    print("\n" + "=" * 64)
    print(" SponsorUs — autonomous sponsor-matching pipeline")
    print("=" * 64)
    stats = run_pipeline(
        prefer_live=not args.fixture,
        max_prospects=args.max,
        threshold=args.threshold,
        push_telegram=not args.no_tg,
    )
    print("\n=== RUN COMPLETE ===")
    for k, v in stats.items():
        print(f"  {k:<28} {v}")
    print()
    sys.exit(0 if stats.get("prospects_seen", 0) > 0 else 1)


if __name__ == "__main__":
    main()
