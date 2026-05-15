"""Scraper agent — TOOL CALL #1.

Live-fetches a sponsor-prospect listing page, extracts prospect cards, and
returns raw text blobs ready for the normalizer. Falls back to a cached
fixture if the network is unavailable mid-demo.

Default source: SponsorPitch-style public listings of "companies that
recently sponsored events" — we use a public, scrape-friendly source.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import httpx
from selectolax.parser import HTMLParser

FIXTURE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "fixtures"
FIXTURE_FILE = FIXTURE_DIR / "prospects.json"

# Live data source: Wikipedia's "List of companies of Indonesia" table.
# Rationale: stable, public, scrape-friendly (static HTML, no JS, robots-allowed),
# returns real Indonesian companies — the exact prospect universe an Indonesian
# event organizer should target. Each row gives us name, sector, and a one-line
# description we can hand to the LLM normalizer.
LIVE_URL = "https://en.wikipedia.org/wiki/List_of_companies_of_Indonesia"

UA = "SponsorUs/0.1 (+https://github.com/Hzxon/OpenClaw2026_duoBolang_SponsorUs)"


@dataclass
class RawProspect:
    """Raw scrape output before LLM normalization."""

    name: str
    blurb: str
    source_url: str

    def to_dict(self) -> dict:
        return {"name": self.name, "blurb": self.blurb, "source_url": self.source_url}


# Sector keywords we prefer (relevance bias toward likely event sponsors).
PREFERRED_SECTORS = {
    "tech", "technolog", "software", "internet", "telecom", "media",
    "financ", "bank", "fintech", "consumer", "retail", "e-commerce",
    "transport", "logistics", "education", "edutech",
}


def _parse_wikipedia_companies(html: str, base_url: str) -> list[RawProspect]:
    """Extract company rows from the Wikipedia list-of-companies wikitable.

    Columns observed: Rank | Image | Name | Industry | Headquarters | Revenue | Notes
    Some rows have an image cell, some don't — we key off cell content rather
    than fixed indices.
    """
    tree = HTMLParser(html)
    out: list[RawProspect] = []
    for tr in tree.css("table.wikitable tbody tr"):
        tds = tr.css("td")
        if len(tds) < 3:
            continue
        cells = [td.text(strip=True) for td in tds]
        # First cell is rank (digits). Skip image-only cells.
        non_empty = [c for c in cells if c]
        if len(non_empty) < 2:
            continue
        # Find the company-name cell: first non-numeric, non-empty cell.
        name = ""
        sector = ""
        notes = ""
        for c in non_empty:
            if not c.isdigit() and len(c) >= 2:
                name = c
                break
        if not name:
            continue
        # Sector and notes are usually the next two readable cells.
        rest = [c for c in non_empty if c != name and not c.isdigit()]
        if rest:
            sector = rest[0]
        if len(rest) >= 2:
            notes = rest[-1]
        # Pull the wiki link if present.
        link = tr.css_first("td a")
        href = link.attributes.get("href", "") if link else ""
        if href.startswith("/"):
            href = "https://en.wikipedia.org" + href
        blurb = (
            f"{name} — Indonesian company, sector: {sector}. "
            f"{notes if notes and notes != sector else ''}"
        ).strip()
        out.append(
            RawProspect(
                name=name[:80],
                blurb=blurb[:500],
                source_url=href or base_url,
            )
        )
    # Bias toward preferred sectors so we don't waste LLM calls on bad fits
    # (oil & gas, mining, etc.) for a student tech hackathon.
    def _pref(p: RawProspect) -> int:
        b = p.blurb.lower()
        return -sum(1 for kw in PREFERRED_SECTORS if kw in b)

    out.sort(key=_pref)
    # Dedup by name, preserve order
    seen: set[str] = set()
    uniq: list[RawProspect] = []
    for p in out:
        k = p.name.lower().strip()
        if k in seen or len(k) < 2:
            continue
        seen.add(k)
        uniq.append(p)
    return uniq


def fetch_live(url: str = LIVE_URL, timeout: float = 15.0) -> list[RawProspect]:
    """Hit the live URL. Raises on failure — caller decides fallback."""
    with httpx.Client(timeout=timeout, headers={"User-Agent": UA}, follow_redirects=True) as c:
        r = c.get(url)
        r.raise_for_status()
        html = r.text
    return _parse_wikipedia_companies(html, url)


def fetch_fixture() -> list[RawProspect]:
    if not FIXTURE_FILE.exists():
        return _seed_fixture()
    data = json.loads(FIXTURE_FILE.read_text())
    return [RawProspect(**d) for d in data]


def _seed_fixture() -> list[RawProspect]:
    """Hand-curated fallback fixture so the demo never depends on network."""
    seed = [
        {
            "name": "GitHub",
            "blurb": "GitHub — developer platform, frequent hackathon and student community sponsor; runs GitHub Education, Campus Experts, and Student Pack programs.",
            "source_url": "https://education.github.com/",
        },
        {
            "name": "DigitalOcean",
            "blurb": "DigitalOcean — cloud infrastructure provider, recurring sponsor of hackathons via DO Hatch and university clubs; targets developers and SaaS founders.",
            "source_url": "https://www.digitalocean.com/community/pages/hatch",
        },
        {
            "name": "MongoDB",
            "blurb": "MongoDB — document database company, sponsors student hackathons and AI events through MongoDB for Startups and university programs.",
            "source_url": "https://www.mongodb.com/students",
        },
        {
            "name": "Tokopedia",
            "blurb": "Tokopedia — Indonesian e-commerce unicorn, sponsors campus tech events and competitive programming contests across SEA universities.",
            "source_url": "https://www.tokopedia.com/about/",
        },
        {
            "name": "Bibit",
            "blurb": "Bibit — Indonesian fintech investment app, sponsors student finance and tech communities to reach Gen Z first-time investors.",
            "source_url": "https://bibit.id/",
        },
        {
            "name": "Pertamina",
            "blurb": "Pertamina — Indonesian state oil & gas; sponsors large national events and CSR-aligned conferences but rarely small student hackathons.",
            "source_url": "https://www.pertamina.com/",
        },
        {
            "name": "Niagahoster",
            "blurb": "Niagahoster — Indonesian web hosting; consistent sponsor of campus tech events with hosting credits and prizes for student developers.",
            "source_url": "https://www.niagahoster.co.id/",
        },
        {
            "name": "Ruangguru",
            "blurb": "Ruangguru — Indonesian edtech; sponsors student-focused academic and tech events; brand fit strongest with K-12 and university audiences.",
            "source_url": "https://www.ruangguru.com/",
        },
    ]
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    FIXTURE_FILE.write_text(json.dumps(seed, indent=2))
    return [RawProspect(**d) for d in seed]


def scrape(prefer_live: bool = True, max_results: int = 12) -> tuple[list[RawProspect], str]:
    """Public entrypoint. Returns (prospects, source_label).

    Tries live first when prefer_live=True. Falls back to fixture so the demo
    is reliable even if a portal goes down.
    """
    if prefer_live:
        try:
            live = fetch_live()
            if live:
                return live[:max_results], f"live:{LIVE_URL}"
        except Exception as e:  # noqa: BLE001 — demo robustness
            print(f"[scraper] live fetch failed: {e!r}; using fixture")
    fixture = fetch_fixture()
    return fixture[:max_results], "fixture:seed"
