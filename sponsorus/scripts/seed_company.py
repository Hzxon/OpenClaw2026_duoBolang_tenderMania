"""Seed the company profile from data/company_profile.yaml into SQLite."""
from pathlib import Path

import yaml

from sponsorus import db

PROFILE_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "company_profile.yaml"


def main() -> None:
    if not PROFILE_PATH.exists():
        raise SystemExit(f"Missing {PROFILE_PATH}")
    profile = yaml.safe_load(PROFILE_PATH.read_text())
    db.init_db()
    db.upsert_company_profile(
        name=profile["name"],
        tagline=profile.get("tagline", ""),
        profile=profile,
    )
    print(f"Company profile loaded: {profile['name']!r}")


if __name__ == "__main__":
    main()
