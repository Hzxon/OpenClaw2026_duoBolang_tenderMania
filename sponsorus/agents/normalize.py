"""Normalizer agent — turns raw tender scrape blobs into TenderOpportunity records.

Uses LLM structured output (Pydantic-validated) so downstream agents get
clean, typed records. Prompt forbids hallucination — unknown fields stay null.
"""
from __future__ import annotations

from sponsorus.agents.scrape import RawTender
from sponsorus.llm import structured
from sponsorus.schemas import TenderOpportunity

NORMALIZE_SYSTEM = """You are a data-normalization agent for a tender-hunting pipeline.
Given a raw procurement-notice blurb, extract structured fields.

Hard rules:
- Do NOT invent facts. If a field isn't implied, set it to null or [].
- buyer = the procuring organization (ministry, agency, BUMN, university, World-Bank-funded project owner).
- estimated_value_idr: convert USD/EUR amounts to IDR using ~16,000 IDR/USD or ~17,000 IDR/EUR if explicitly stated; otherwise null.
- required_certifications: only include items the blurb explicitly demands (SBU classes, ISO certs, registrations).
- deliverables: extract concrete output types (software, hardware, training, services, construction, supplies).
- scope_summary: ONE neutral paragraph (≤80 words). No marketing language."""


def normalize(raw: RawTender) -> TenderOpportunity:
    user = (
        f"RAW TENDER NOTICE\n"
        f"Title: {raw.title}\n"
        f"Country: {raw.country}\n"
        f"Sector: {raw.sector}\n"
        f"Notice type: {raw.notice_type}\n"
        f"Submission deadline: {raw.deadline}\n"
        f"Source URL: {raw.source_url}\n\n"
        f"Blurb:\n{raw.blurb}\n\n"
        "Extract structured TenderOpportunity JSON."
    )
    tender = structured(system=NORMALIZE_SYSTEM, user=user, schema=TenderOpportunity)
    # Always carry ground-truth fields through; don't trust the LLM to remember.
    tender.public_url = raw.source_url
    if not tender.title.strip():
        tender.title = raw.title
    if raw.country and not tender.country:
        tender.country = raw.country
    if raw.deadline and not tender.submission_deadline:
        tender.submission_deadline = raw.deadline
    if raw.notice_type and not tender.notice_type:
        tender.notice_type = raw.notice_type
    return tender
