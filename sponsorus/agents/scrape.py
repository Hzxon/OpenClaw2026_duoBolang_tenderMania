"""Tender-hunting scraper.

Live source: World Bank procurement notices public API
  https://search.worldbank.org/api/v2/procnotices

Why this source:
- Real, public, no-auth REST endpoint with 400k+ live tenders.
- Returns structured JSON: project name, description, country, deadline, notice type, URL.
- Includes Indonesia, SEA, and global IT-development tenders relevant to a
  software consultancy bidding for World-Bank-funded work.

Falls back to a cached fixture when the network is unavailable so the demo
is reliable.
"""
from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

FIXTURE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "fixtures"
FIXTURE_FILE = FIXTURE_DIR / "tenders.json"

WB_API = (
    "https://search.worldbank.org/api/v2/procnotices"
    "?format=json&rows={rows}&srt=submission_deadline_date&order=asc"
    "&fl=id,bid_description,project_name,project_ctry_name,country_name,"
    "submission_deadline_date,notice_type,procurement_method,major_sector,"
    "proc_summary,notice_status,url,bid_reference_no,project_id"
)

UA = "SponsorUs/0.1 (+https://github.com/Hzxon/OpenClaw2026_duoBolang_SponsorUs)"

# Sectors a software consultancy could realistically bid on.
PREFERRED_SECTORS = {
    "information", "ict", "technology", "digital", "software",
    "public administration", "education", "finance",
}


@dataclass
class RawTender:
    """Raw scrape output — pre-LLM-normalization."""

    title: str
    blurb: str
    source_url: str
    country: str = ""
    deadline: str = ""
    notice_type: str = ""
    sector: str = ""

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "blurb": self.blurb,
            "source_url": self.source_url,
            "country": self.country,
            "deadline": self.deadline,
            "notice_type": self.notice_type,
            "sector": self.sector,
        }


def _ssl_ctx() -> ssl.SSLContext:
    # Some macOS Python builds fail TLS verification against gov.* certs;
    # we relax verification here because we never send credentials.
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def fetch_live(rows: int = 30, timeout: float = 15.0) -> list[RawTender]:
    """Hit the live World Bank procurement API."""
    url = WB_API.format(rows=rows)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout, context=_ssl_ctx()) as r:
        data = json.loads(r.read().decode("utf-8", errors="ignore"))
    items = data.get("procnotices", {})
    if isinstance(items, dict):
        items = list(items.values())
    out: list[RawTender] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        desc = (it.get("bid_description") or "").strip()
        proj = (it.get("project_name") or "").strip()
        if not (desc or proj):
            continue
        country = (it.get("country_name") or it.get("project_ctry_name") or "").strip()
        deadline = (it.get("submission_deadline_date") or "").strip()
        notice = (it.get("notice_type") or "").strip()
        sector = (it.get("major_sector") or "").strip()
        title = desc[:120] if desc else proj[:120]
        blurb = (
            f"{desc} | Project: {proj}. Country: {country}. Sector: {sector}. "
            f"Type: {notice}. Submission deadline: {deadline or 'TBD'}."
        ).strip()
        url_field = it.get("url") or "https://projects.worldbank.org/"
        out.append(
            RawTender(
                title=title,
                blurb=blurb[:600],
                source_url=url_field,
                country=country,
                deadline=deadline,
                notice_type=notice,
                sector=sector,
            )
        )
    # Skip already-awarded notices — they're non-actionable.
    out = [t for t in out if "award" not in t.notice_type.lower()]

    # Bias toward sectors a software consultancy could deliver on.
    def _pref(t: RawTender) -> int:
        b = (t.blurb + " " + t.sector).lower()
        return -sum(1 for kw in PREFERRED_SECTORS if kw in b)

    out.sort(key=_pref)
    return out


def fetch_fixture() -> list[RawTender]:
    if FIXTURE_FILE.exists():
        data = json.loads(FIXTURE_FILE.read_text())
        return [RawTender(**d) for d in data]
    return _seed_fixture()


def _seed_fixture() -> list[RawTender]:
    """Curated fallback so the demo never depends on network."""
    seed = [
        {
            "title": "Software development for ministerial e-reporting platform",
            "blurb": "Indonesia — Ministry of X seeks a vendor to build a realtime cross-province KPI reporting platform; scope includes data ingestion, dashboards, role-based access, and 12 months of support. Estimated value IDR 2.4B.",
            "source_url": "https://example.lpse.go.id/eproc4/lelang/1234/pengumuman",
            "country": "Indonesia",
            "deadline": "2026-06-12",
            "notice_type": "Request for Proposal",
            "sector": "Public Administration",
        },
        {
            "title": "AI-powered citizen-service chatbot for provincial government",
            "blurb": "Indonesia — Pemprov Y procures a Bahasa Indonesia chatbot with LLM tool-use, integrated with population ID verification; deliverables include code, training, and 6 months SLA. Budget IDR 950 juta.",
            "source_url": "https://example.lpse.go.id/eproc4/lelang/1235/pengumuman",
            "country": "Indonesia",
            "deadline": "2026-06-05",
            "notice_type": "Request for Proposal",
            "sector": "Information and Communications",
        },
        {
            "title": "Construction of district road segment 4.2 km",
            "blurb": "Indonesia — Pemkab Z procures asphalt road construction; includes drainage and signage. Budget IDR 18B. Requires construction-class SBU.",
            "source_url": "https://example.lpse.go.id/eproc4/lelang/1236/pengumuman",
            "country": "Indonesia",
            "deadline": "2026-06-20",
            "notice_type": "Request for Bid",
            "sector": "Transportation",
        },
        {
            "title": "Procurement of 200 desktop PCs and 50 printers",
            "blurb": "Indonesia — BUMN Q hardware procurement only, no software development scope. Budget IDR 1.6B.",
            "source_url": "https://example.lpse.go.id/eproc4/lelang/1237/pengumuman",
            "country": "Indonesia",
            "deadline": "2026-05-28",
            "notice_type": "Request for Quotation",
            "sector": "ICT — Hardware",
        },
        {
            "title": "Data analytics platform for higher-education student risk prediction",
            "blurb": "Indonesia — Universitas A seeks vendor to deliver a student-analytics dashboard with academic-risk model integration with SIAK-NG; deliverables include code + training + 12-month support. Budget IDR 720 juta.",
            "source_url": "https://example.lpse.go.id/eproc4/lelang/1238/pengumuman",
            "country": "Indonesia",
            "deadline": "2026-07-01",
            "notice_type": "Request for Proposal",
            "sector": "Education",
        },
    ]
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    FIXTURE_FILE.write_text(json.dumps(seed, indent=2))
    return [RawTender(**d) for d in seed]


def scrape(prefer_live: bool = True, max_results: int = 12) -> tuple[list[RawTender], str]:
    """Public entrypoint. Returns (tenders, source_label)."""
    if prefer_live:
        try:
            live = fetch_live(rows=max(max_results * 3, 30))
            if live:
                return live[:max_results], "live:worldbank-procnotices"
        except Exception as e:  # noqa: BLE001
            print(f"[scraper] live fetch failed: {e!r}; using fixture")
    fixture = fetch_fixture()
    return fixture[:max_results], "fixture:seed"
