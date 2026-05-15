"""Pydantic schemas for the SponsorUs pipeline.

These define the contracts between agents — every LLM that produces structured
output is bound to one of these models, every DB row hydrates from one.
Strict schemas are how we keep multi-agent handoff debuggable.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, HttpUrl


class SponsorProspect(BaseModel):
    """A single sponsor candidate after normalization."""

    company_name: str = Field(description="Legal or commonly-used company name")
    industry: str = Field(description="Primary industry / vertical")
    headquarters: Optional[str] = Field(default=None, description="HQ city / country")
    employee_size: Optional[str] = Field(
        default=None, description="Approx headcount band, e.g. '50-200'"
    )
    audience_overlap: list[str] = Field(
        default_factory=list,
        description="Audience segments this sponsor wants to reach (e.g. 'university students', 'developers')",
    )
    sponsorship_history: list[str] = Field(
        default_factory=list,
        description="Notable events / programs this company has sponsored before",
    )
    contact_email: Optional[str] = Field(
        default=None, description="Best-guess marketing/partnerships email"
    )
    public_url: Optional[str] = Field(
        default=None, description="Source URL the prospect was scraped from"
    )
    raw_summary: str = Field(
        description="One-paragraph summary written by the normalizer LLM"
    )


class DimensionScore(BaseModel):
    """A single scoring dimension result with reasoning trace."""

    dimension: Literal["capability_fit", "strategic_fit", "activation_likelihood"]
    score: int = Field(ge=0, le=100, description="0-100 score")
    reasoning: str = Field(description="2-4 sentence justification, must cite evidence")
    evidence: list[str] = Field(
        default_factory=list,
        description="Concrete signals (audience tags, past sponsorships, sector match) that drove the score",
    )


class AggregateDecision(BaseModel):
    """Final decision after all dimensions are scored."""

    prospect_company: str
    capability_fit: int
    strategic_fit: int
    activation_likelihood: int
    weighted_score: float
    decision: Literal["pursue", "archive"]
    rationale: str = Field(description="Why pursue or archive — 2-3 sentences")


class OutreachDraft(BaseModel):
    """Email draft produced by the drafter agent."""

    subject: str = Field(max_length=120)
    body_markdown: str = Field(description="Email body in markdown, signed off")
    personalization_notes: list[str] = Field(
        default_factory=list,
        description="Specific personalization hooks the draft uses (sponsor's past events, audience alignment, etc.)",
    )


class PipelineRun(BaseModel):
    """A single end-to-end pipeline run record."""

    run_id: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    prospects_seen: int = 0
    prospects_pursued: int = 0
    drafts_written: int = 0
    drafts_approved: int = 0
    emails_sent: int = 0
    notes: str = ""
