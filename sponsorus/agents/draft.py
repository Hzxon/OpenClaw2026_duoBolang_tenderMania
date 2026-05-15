"""Drafter agent — composes a personalized expression-of-interest email
to a procurement officer.

Grounds the draft in the company profile (RAG) and the scoring agents' cited
evidence. Output is a strict OutreachDraft (subject + body + personalization
notes) so the approval UI shows what hooks the agent leaned on.
"""
from __future__ import annotations

from sponsorus.llm import structured
from sponsorus.rag import RAGIndex
from sponsorus.schemas import DimensionScore, OutreachDraft, TenderOpportunity

DRAFT_SYSTEM = """You are an OUTREACH DRAFTING agent for a tender-hunting pipeline.

Compose a concise expression-of-interest email from the COMPANY to the procurement officer
of the TENDER, asking for the tender documents and a clarification meeting.

Hard rules:
- Length: 130-200 words in the body.
- Tone: professional, deferential, specific. No buzzwords ("synergy", "leverage", "ecosystem").
- Open with a precise statement of interest in the tender (cite the tender title).
- Middle: 2-3 specific capability matches drawn from the scorer's cited evidence
  (past contracts, certifications, team size). Anchor every claim to a profile chunk.
- Close: a single clear ask — request for the lengkap (complete) tender documents
  and a 20-min clarification call with the procurement team.
- Sign off as the company. Use the language matching the tender's country
  (Bahasa Indonesia for Indonesian buyers, English otherwise).
- personalization_notes: list each fact you used and where it came from.

Do NOT:
- Promise specific deliverables or pricing not justified by the company profile.
- Invent certifications or past projects.
- Mention the AI / score / pipeline."""


def _hooks(scores: list[DimensionScore]) -> list[str]:
    out: list[str] = []
    for s in scores:
        for e in s.evidence:
            if e and e not in out:
                out.append(e)
    return out[:8]


def draft_outreach(
    tender: TenderOpportunity,
    company_profile: dict,
    scores: list[DimensionScore],
    rag: RAGIndex,
) -> OutreachDraft:
    hooks = _hooks(scores)
    retrieved = [
        c for c, _ in rag.topk(tender.title + " " + (tender.sector or ""), k=4)
    ]
    user = (
        f"COMPANY:\n"
        f"  Name: {company_profile.get('name')}\n"
        f"  Tagline: {company_profile.get('tagline')}\n"
        f"  Team size: {company_profile.get('team_size')}\n"
        f"  Capabilities: {company_profile.get('capabilities', [])}\n"
        f"  Certifications: {company_profile.get('certifications', [])}\n"
        f"  Past contracts: {company_profile.get('past_contracts', [])}\n"
        f"  Contact: {company_profile.get('contact', {})}\n\n"
        f"RETRIEVED PROFILE CHUNKS:\n" + "\n".join(f"- {c}" for c in retrieved) + "\n\n"
        f"TENDER:\n"
        f"  Title: {tender.title}\n"
        f"  Buyer: {tender.buyer}\n"
        f"  Country: {tender.country}\n"
        f"  Notice type: {tender.notice_type}\n"
        f"  Deadline: {tender.submission_deadline or 'TBD'}\n"
        f"  Estimated value IDR: {tender.estimated_value_idr or 'unknown'}\n"
        f"  Scope: {tender.scope_summary}\n"
        f"  Source: {tender.public_url}\n\n"
        f"SCORER-CITED EVIDENCE (use at least two as concrete capability hooks):\n"
        + "\n".join(f"- {h}" for h in hooks)
        + "\n\nProduce the OutreachDraft JSON. "
        "If the tender country is Indonesia, write the body in Bahasa Indonesia; otherwise English."
    )
    return structured(system=DRAFT_SYSTEM, user=user, schema=OutreachDraft, temperature=0.5)
