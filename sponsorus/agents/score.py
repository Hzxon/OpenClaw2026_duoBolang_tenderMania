"""Scorer agents — the multi-agent core.

Three independent scoring agents run in parallel via asyncio:
  - capability_fit  (RAG-grounded; cites event-profile evidence)
  - strategic_fit   (sector / audience / geography alignment)
  - activation_likelihood (how likely they are to actually engage)

Each returns a DimensionScore with reasoning + cited evidence. An aggregator
then weight-combines, applies a hard threshold, and produces a pursue/archive
decision. Reasoning traces are persisted so a human reviewer can audit.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

from sponsorus.llm import structured
from sponsorus.rag import RAGIndex, event_profile_to_chunks
from sponsorus.schemas import AggregateDecision, DimensionScore, SponsorProspect

# ---- Weights (tune via config later) ---------------------------------------
WEIGHTS = {
    "capability_fit": 0.45,
    "strategic_fit": 0.35,
    "activation_likelihood": 0.20,
}

# ---- Prompts ---------------------------------------------------------------
CAPABILITY_SYSTEM = """You are the CAPABILITY-FIT scorer in a sponsor matching pipeline.

Score (0-100) how well this prospect's audience and goals match the EVENT's audience and value.

Hard rules:
- Cite at least 2 concrete evidence items in `evidence` (audience overlaps, past sponsorship patterns, value-prop alignment from the retrieved event-profile chunks).
- If the prospect's audience does not overlap with the event audience, score below 40.
- Reasoning must explicitly reference the retrieved chunks. No vague filler."""

STRATEGIC_SYSTEM = """You are the STRATEGIC-FIT scorer in a sponsor matching pipeline.

Score (0-100) the strategic alignment: sector match, geography (Indonesia / SEA priority for this event),
brand-tier alignment, and budget-tier feasibility relative to the event's sponsorship tiers.

Hard rules:
- Penalize geography mismatch (non-SEA brand for an Indonesia-only event) heavily.
- Penalize obvious tier mismatches (a Fortune-500 oil major for a 200-person student hackathon) — they will not sponsor.
- Cite concrete evidence in `evidence`."""

ACTIVATION_SYSTEM = """You are the ACTIVATION-LIKELIHOOD scorer.

Score (0-100) how likely this prospect is to actually engage if contacted now.

Signals:
- Recent (past 18 months) sponsorship history of similar events → boosts score.
- Public partnership / dev-rel / community programs → boost.
- No discoverable contact channel or no community-marketing arm → penalty.
- Lead time vs the event date — if event is <30 days out, penalize unless they've sponsored on short notice before.

Cite concrete evidence."""

AGGREGATOR_SYSTEM = """You are the AGGREGATOR. You receive three dimension scores plus the event profile
and prospect summary. Produce a final decision: 'pursue' or 'archive'.

Hard rules:
- If capability_fit < 40, decision MUST be 'archive'.
- If weighted_score < threshold (provided in user message), decision MUST be 'archive'.
- Otherwise 'pursue'.
- Rationale: 2-3 plain sentences, no marketing language."""


@dataclass
class ScoreContext:
    prospect: SponsorProspect
    event_profile: dict
    rag: RAGIndex


def _retrieve_chunks(rag: RAGIndex, prospect: SponsorProspect, k: int = 5) -> list[str]:
    query = (
        f"{prospect.company_name} | {prospect.industry} | "
        f"audience: {', '.join(prospect.audience_overlap)} | "
        f"history: {', '.join(prospect.sponsorship_history)}"
    )
    return [c for c, _ in rag.topk(query, k=k)]


def _user_msg(ctx: ScoreContext, dim: str, retrieved: list[str]) -> str:
    return (
        f"DIMENSION: {dim}\n\n"
        f"EVENT NAME: {ctx.event_profile.get('name')}\n"
        f"EVENT TAGLINE: {ctx.event_profile.get('tagline')}\n"
        f"EVENT DATE: {ctx.event_profile.get('event_date', 'TBD')}\n\n"
        f"RETRIEVED EVENT-PROFILE CHUNKS (use these as evidence):\n"
        + "\n".join(f"- {c}" for c in retrieved)
        + "\n\nPROSPECT:\n"
        f"  Company: {ctx.prospect.company_name}\n"
        f"  Industry: {ctx.prospect.industry}\n"
        f"  HQ: {ctx.prospect.headquarters}\n"
        f"  Audience overlap: {', '.join(ctx.prospect.audience_overlap) or 'unknown'}\n"
        f"  Sponsorship history: {', '.join(ctx.prospect.sponsorship_history) or 'unknown'}\n"
        f"  Summary: {ctx.prospect.raw_summary}\n\n"
        "Score this dimension. Return JSON matching the DimensionScore schema."
    )


# ---- Single-dimension scorers (sync but called via asyncio.to_thread) ------
def _score_dim(ctx: ScoreContext, dimension: str, system_prompt: str) -> DimensionScore:
    retrieved = _retrieve_chunks(ctx.rag, ctx.prospect)
    user = _user_msg(ctx, dimension, retrieved)
    result = structured(system=system_prompt, user=user, schema=DimensionScore)
    # Defensive: force the dimension field even if the LLM drifts.
    result.dimension = dimension  # type: ignore[assignment]
    return result


def score_capability(ctx: ScoreContext) -> DimensionScore:
    return _score_dim(ctx, "capability_fit", CAPABILITY_SYSTEM)


def score_strategic(ctx: ScoreContext) -> DimensionScore:
    return _score_dim(ctx, "strategic_fit", STRATEGIC_SYSTEM)


def score_activation(ctx: ScoreContext) -> DimensionScore:
    return _score_dim(ctx, "activation_likelihood", ACTIVATION_SYSTEM)


# ---- Parallel multi-agent fan-out ------------------------------------------
async def score_all_async(ctx: ScoreContext) -> list[DimensionScore]:
    """Run all 3 scorers concurrently. This is the multi-agent moment."""
    results = await asyncio.gather(
        asyncio.to_thread(score_capability, ctx),
        asyncio.to_thread(score_strategic, ctx),
        asyncio.to_thread(score_activation, ctx),
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
    strat = by_dim["strategic_fit"].score
    act = by_dim["activation_likelihood"].score

    weighted = (
        cap * WEIGHTS["capability_fit"]
        + strat * WEIGHTS["strategic_fit"]
        + act * WEIGHTS["activation_likelihood"]
    )

    # Hard rules first — keep them deterministic, not LLM-decided.
    if cap < 40 or weighted < threshold:
        decision = "archive"
        rationale = (
            f"Hard-gate archive. capability={cap}, strategic={strat}, "
            f"activation={act}, weighted={weighted:.1f} < threshold={threshold}."
        )
        return AggregateDecision(
            prospect_company=ctx.prospect.company_name,
            capability_fit=cap,
            strategic_fit=strat,
            activation_likelihood=act,
            weighted_score=round(weighted, 1),
            decision=decision,
            rationale=rationale,
        )

    # Above threshold → use LLM for a short qualitative rationale.
    user = (
        f"Prospect: {ctx.prospect.company_name}\n"
        f"capability_fit={cap}, strategic_fit={strat}, activation_likelihood={act}\n"
        f"weighted_score={weighted:.1f}, threshold={threshold}\n\n"
        f"Per-dimension reasoning:\n"
        f"- capability: {by_dim['capability_fit'].reasoning}\n"
        f"- strategic:  {by_dim['strategic_fit'].reasoning}\n"
        f"- activation: {by_dim['activation_likelihood'].reasoning}\n\n"
        "Produce final AggregateDecision JSON."
    )
    return structured(system=AGGREGATOR_SYSTEM, user=user, schema=AggregateDecision)
