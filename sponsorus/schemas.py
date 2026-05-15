"""Pydantic schemas for the SponsorUs (tender-hunting) pipeline.

These define the contracts between agents — every LLM that produces structured
output is bound to one of these models, every DB row hydrates from one.
Strict schemas are how we keep multi-agent handoff debuggable.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class TenderOpportunity(BaseModel):
    """A single tender / RFP / procurement notice after normalization."""

    title: str = Field(description="Short title of the tender")
    buyer: str = Field(description="The procuring organization (ministry, BUMN, agency, etc.)")
    country: Optional[str] = Field(default=None, description="Issuing country")
    sector: Optional[str] = Field(default=None, description="Major sector / industry")
    scope_summary: str = Field(description="One-paragraph neutral summary of the scope")
    estimated_value_idr: Optional[int] = Field(
        default=None,
        description="Estimated contract value in IDR if discoverable; null otherwise",
    )
    submission_deadline: Optional[str] = Field(
        default=None, description="Deadline date in YYYY-MM-DD if known"
    )
    notice_type: Optional[str] = Field(
        default=None,
        description="RFP, RFQ, RFB, EOI, Contract Award, etc.",
    )
    required_certifications: list[str] = Field(
        default_factory=list,
        description="Certifications / SBU classes / registrations explicitly required",
    )
    deliverables: list[str] = Field(
        default_factory=list,
        description="Concrete deliverables mentioned (software, training, hardware, etc.)",
    )
    contact_email: Optional[str] = Field(
        default=None, description="Best-guess procurement contact email"
    )
    public_url: Optional[str] = Field(default=None, description="Source URL")


class DimensionScore(BaseModel):
    """A single scoring dimension result with reasoning trace."""

    dimension: Literal["capability_fit", "eligibility_fit", "win_probability"]
    score: int = Field(ge=0, le=100, description="0-100 score")
    reasoning: str = Field(description="2-4 sentence justification, must cite evidence")
    evidence: list[str] = Field(
        default_factory=list,
        description="Concrete signals (capability matches, certification matches, past contracts) that drove the score",
    )


class AggregateDecision(BaseModel):
    """Final decision after all dimensions are scored."""

    tender_title: str
    capability_fit: int
    eligibility_fit: int
    win_probability: int
    weighted_score: float
    decision: Literal["pursue", "archive"]
    rationale: str = Field(description="Why pursue or archive — 2-3 sentences")


class OutreachDraft(BaseModel):
    """Expression-of-interest email draft produced by the drafter agent."""

    subject: str = Field(max_length=140)
    body_markdown: str = Field(
        description="Email body in markdown, signed off by the company; "
        "addressed to the procurement officer."
    )
    personalization_notes: list[str] = Field(
        default_factory=list,
        description="Specific hooks the draft uses (matched capability, past contract, certification) and where each came from",
    )


class PipelineRun(BaseModel):
    """A single end-to-end pipeline run record."""

    run_id: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    tenders_seen: int = 0
    tenders_pursued: int = 0
    drafts_written: int = 0
    drafts_approved: int = 0
    emails_sent: int = 0
    notes: str = ""
