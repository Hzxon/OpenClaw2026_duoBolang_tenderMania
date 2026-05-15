"""Drafter agent — composes a personalized cold-outreach email.

Grounds the draft in the event profile (RAG) and the scoring agents' cited
evidence. Output is a strict OutreachDraft (subject + body + personalization
notes) so the approval UI can show what hooks the agent leaned on.
"""
from __future__ import annotations

from sponsorus.llm import structured
from sponsorus.rag import RAGIndex
from sponsorus.schemas import DimensionScore, OutreachDraft, SponsorProspect

DRAFT_SYSTEM = """You are an OUTREACH DRAFTING agent for an event-sponsorship pipeline.

Compose a concise, personalized cold-outreach email asking the prospect to consider sponsoring the event.

Hard rules:
- Length: 120-180 words in the body.
- Tone: warm, professional, specific. No buzzwords ("synergy", "leverage", "ecosystem").
- Open with ONE concrete hook from the prospect's history or audience overlap (the scorer's evidence).
- Middle paragraph: state the event, audience size, date, and 1-2 sponsor tier options that fit.
- Close: a single clear ask (a 20-min intro call) with a proposed week.
- Sign off as the event organizing team. No real names invented.
- personalization_notes: list each fact you used and where it came from (evidence label or profile chunk).

Do NOT:
- Promise specific deliverables not in the event profile.
- Mention the score or that this email was AI-generated."""


def _hooks(scores: list[DimensionScore]) -> list[str]:
    out: list[str] = []
    for s in scores:
        for e in s.evidence:
            if e and e not in out:
                out.append(e)
    return out[:8]


def draft_outreach(
    prospect: SponsorProspect,
    event_profile: dict,
    scores: list[DimensionScore],
    rag: RAGIndex,
) -> OutreachDraft:
    hooks = _hooks(scores)
    retrieved = [c for c, _ in rag.topk(prospect.company_name + " " + prospect.industry, k=4)]
    user = (
        f"EVENT NAME: {event_profile.get('name')}\n"
        f"EVENT TAGLINE: {event_profile.get('tagline')}\n"
        f"EVENT DATE: {event_profile.get('event_date', 'TBD')}\n"
        f"AUDIENCE: {event_profile.get('audience', {})}\n"
        f"VALUE PROPS: {event_profile.get('value_props', [])}\n"
        f"SPONSORSHIP TIERS: {event_profile.get('sponsorship_tiers', [])}\n\n"
        f"RETRIEVED PROFILE CHUNKS:\n" + "\n".join(f"- {c}" for c in retrieved) + "\n\n"
        f"PROSPECT:\n"
        f"  Company: {prospect.company_name}\n"
        f"  Industry: {prospect.industry}\n"
        f"  Audience overlap: {', '.join(prospect.audience_overlap) or 'unknown'}\n"
        f"  Sponsorship history: {', '.join(prospect.sponsorship_history) or 'unknown'}\n"
        f"  Summary: {prospect.raw_summary}\n\n"
        f"SCORER-CITED EVIDENCE (use at least one as the opening hook):\n"
        + "\n".join(f"- {h}" for h in hooks)
        + "\n\nProduce the OutreachDraft JSON."
    )
    return structured(system=DRAFT_SYSTEM, user=user, schema=OutreachDraft, temperature=0.5)
