"""Normalizer agent — turns raw scrape blobs into SponsorProspect records.

Uses LLM structured output (Pydantic-validated) so downstream agents get clean,
typed records they can rely on. The prompt instructs the model to refuse
hallucination — unknown fields are left null rather than guessed.
"""
from __future__ import annotations

from sponsorus.agents.scrape import RawProspect
from sponsorus.llm import structured
from sponsorus.schemas import SponsorProspect

NORMALIZE_SYSTEM = """You are a data-normalization agent. Given a short blurb about a company
that has sponsored events in the past, extract structured information for a sponsor outreach pipeline.

Rules:
- Do not invent facts. If a field is not implied by the blurb, set it to null or an empty list.
- contact_email should be your best inferred *generic* address (e.g. partnerships@<domain>) only if
  a domain is obvious from the source URL — otherwise null.
- audience_overlap = audience segments this sponsor likely wants to reach (e.g. "university students",
  "developers", "startup founders", "Indonesian Gen-Z").
- raw_summary = one neutral sentence describing the company. No marketing fluff."""


def normalize(raw: RawProspect) -> SponsorProspect:
    user = (
        f"Company name (as scraped): {raw.name}\n"
        f"Source URL: {raw.source_url}\n"
        f"Blurb:\n{raw.blurb}\n\n"
        "Extract structured prospect info."
    )
    prospect = structured(system=NORMALIZE_SYSTEM, user=user, schema=SponsorProspect)
    # Always carry source URL through; don't trust the LLM to remember.
    prospect.public_url = raw.source_url
    if not prospect.company_name.strip():
        prospect.company_name = raw.name
    return prospect
