"""Scorer agents — the multi-agent core.

Three independent scoring agents run in parallel via asyncio:
  - capability_fit   (RAG-grounded: company capabilities vs tender scope)
  - eligibility_fit  (hard requirements: certifications, geography, sector)
  - win_probability  (lead time, complexity vs company size, language)

Each returns a DimensionScore with reasoning + cited evidence. An aggregator
weight-combines, applies hard gates, and produces a pursue/archive decision.
Reasoning traces are persisted so a human reviewer can audit.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

from sponsorus.llm import structured
from sponsorus.rag import RAGIndex
from sponsorus.schemas import AggregateDecision, DimensionScore, TenderOpportunity

# ---- Weights ---------------------------------------------------------------
WEIGHTS = {
    "capability_fit": 0.45,
    "eligibility_fit": 0.35,
    "win_probability": 0.20,
}

# ---- Prompts ---------------------------------------------------------------
CAPABILITY_SYSTEM = """You are the CAPABILITY-FIT scorer in a tender-hunting pipeline.

Score 0–100 how well the COMPANY can deliver this TENDER.

Hard rules:
- Cite at least 2 concrete evidence items in `evidence` (matched capabilities, past contracts, sector experience) drawn from the retrieved company-profile chunks.
- If the tender's deliverables (e.g. construction, hardware, oil & gas EPC) are clearly outside the company's capabilities, score below 35.
- Reasoning must explicitly reference retrieved chunks. No vague filler."""

ELIGIBILITY_SYSTEM = """You are the ELIGIBILITY-FIT scorer.

Score 0–100 the company's eligibility to bid: required certifications / SBU classes,
geography (Indonesia/SEA priority), tender size relative to company revenue, and any
exclusionary requirements (manufacturing, defense, non-IT badan usaha).

Hard rules:
- If the tender REQUIRES a certification or class the company DOES NOT hold, score below 30.
- Penalize country mismatch (non-Indonesia/SEA) when the company only operates regionally.
- Penalize tender values >5x the company's annual revenue (capacity risk).
- Cite concrete evidence in `evidence`."""

WIN_SYSTEM = """You are the WIN-PROBABILITY scorer.

Score 0–100 how likely the company is to actually win if they bid.

Signals:
- Lead time before deadline (>21 days good, <14 days penalized).
- Past similar contracts in the company's history → boost.
- Language and locality match → boost.
- Heavy incumbent advantage (e.g. extensions of existing vendor work) → penalty.
- Tender complexity vs team size (28-engineer firm bidding for solo-developer scope is overkill, multi-100-engineer scope is overreach).

Cite concrete evidence."""

AGGREGATOR_SYSTEM = """You are the AGGREGATOR. You receive three dimension scores plus the company profile
and tender summary. Produce a final decision: 'pursue' or 'archive'.

Hard rules:
- If eligibility_fit < 30, decision MUST be 'archive' (cannot legally bid).
- If capability_fit < 35, decision MUST be 'archive'.
- If weighted_score < threshold (provided in user message), decision MUST be 'archive'.
- Otherwise 'pursue'.
- Rationale: 2-3 plain sentences, no marketing language."""


@dataclass
class ScoreContext:
    tender: TenderOpportunity
    company_profile: dict
    rag: RAGIndex


def _retrieve_chunks(rag: RAGIndex, tender: TenderOpportunity, k: int = 6) -> list[str]:
    query = (
        f"{tender.title} | {tender.sector or ''} | "
        f"deliverables: {', '.join(tender.deliverables)} | "
        f"required: {', '.join(tender.required_certifications)} | "
        f"{tender.scope_summary}"
    )
    return [c for c, _ in rag.topk(query, k=k)]


def _user_msg(ctx: ScoreContext, dim: str, retrieved: list[str]) -> str:
    return (
        f"DIMENSION: {dim}\n\n"
        f"COMPANY: {ctx.company_profile.get('name')}\n"
        f"  team_size: {ctx.company_profile.get('team_size')}\n"
        f"  annual_revenue_idr: {ctx.company_profile.get('annual_revenue_idr')}\n"
        f"  geographies: {', '.join(ctx.company_profile.get('geographies_served', []))}\n\n"
        f"RETRIEVED COMPANY-PROFILE CHUNKS (use as evidence):\n"
        + "\n".join(f"- {c}" for c in retrieved)
        + "\n\nTENDER:\n"
        f"  Title: {ctx.tender.title}\n"
        f"  Buyer: {ctx.tender.buyer}\n"
        f"  Country: {ctx.tender.country}\n"
        f"  Sector: {ctx.tender.sector}\n"
        f"  Notice type: {ctx.tender.notice_type}\n"
        f"  Deadline: {ctx.tender.submission_deadline or 'TBD'}\n"
        f"  Estimated value IDR: {ctx.tender.estimated_value_idr or 'unknown'}\n"
        f"  Required certifications: {', '.join(ctx.tender.required_certifications) or 'none stated'}\n"
        f"  Deliverables: {', '.join(ctx.tender.deliverables) or 'unspecified'}\n"
        f"  Scope: {ctx.tender.scope_summary}\n\n"
        "Score this dimension. Return JSON matching the DimensionScore schema."
    )


def _score_dim(ctx: ScoreContext, dimension: str, system_prompt: str) -> DimensionScore:
    retrieved = _retrieve_chunks(ctx.rag, ctx.tender)
    user = _user_msg(ctx, dimension, retrieved)
    result = structured(system=system_prompt, user=user, schema=DimensionScore)
    result.dimension = dimension  # type: ignore[assignment]
    return result


def score_capability(ctx: ScoreContext) -> DimensionScore:
    return _score_dim(ctx, "capability_fit", CAPABILITY_SYSTEM)


def score_eligibility(ctx: ScoreContext) -> DimensionScore:
    return _score_dim(ctx, "eligibility_fit", ELIGIBILITY_SYSTEM)


def score_winprob(ctx: ScoreContext) -> DimensionScore:
    return _score_dim(ctx, "win_probability", WIN_SYSTEM)


# ---- Parallel multi-agent fan-out ------------------------------------------
async def score_all_async(ctx: ScoreContext) -> list[DimensionScore]:
    """Run all 3 scorers concurrently. This is the multi-agent moment."""
    results = await asyncio.gather(
        asyncio.to_thread(score_capability, ctx),
        asyncio.to_thread(score_eligibility, ctx),
        asyncio.to_thread(score_winprob, ctx),
    )
    return list(results)


def score_all(ctx: ScoreContext) -> list[DimensionScore]:
    return asyncio.run(score_all_async(ctx))


# ---- Aggregator ------------------------------------------------------------
def aggregate(
    ctx: ScoreContext,
    scores: list[DimensionScore],
    threshold: float,
) -> AggregateDecision:
    by_dim = {s.dimension: s for s in scores}
    cap = by_dim["capability_fit"].score
    elig = by_dim["eligibility_fit"].score
    win = by_dim["win_probability"].score

    weighted = (
        cap * WEIGHTS["capability_fit"]
        + elig * WEIGHTS["eligibility_fit"]
        + win * WEIGHTS["win_probability"]
    )

    # Hard rules first — keep them deterministic, not LLM-decided.
    if elig < 30 or cap < 35 or weighted < threshold:
        decision = "archive"
        rationale = (
            f"Hard-gate archive. capability={cap}, eligibility={elig}, win={win}, "
            f"weighted={weighted:.1f} threshold={threshold}."
        )
        return AggregateDecision(
            tender_title=ctx.tender.title,
            capability_fit=cap,
            eligibility_fit=elig,
            win_probability=win,
            weighted_score=round(weighted, 1),
            decision=decision,
            rationale=rationale,
        )

    user = (
        f"Tender: {ctx.tender.title}\n"
        f"capability_fit={cap}, eligibility_fit={elig}, win_probability={win}\n"
        f"weighted_score={weighted:.1f}, threshold={threshold}\n\n"
        f"Per-dimension reasoning:\n"
        f"- capability:  {by_dim['capability_fit'].reasoning}\n"
        f"- eligibility: {by_dim['eligibility_fit'].reasoning}\n"
        f"- win:         {by_dim['win_probability'].reasoning}\n\n"
        "Produce final AggregateDecision JSON."
    )
    return structured(system=AGGREGATOR_SYSTEM, user=user, schema=AggregateDecision)
