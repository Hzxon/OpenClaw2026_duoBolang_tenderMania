"""Lightweight RAG layer.

Hackathon constraint: the local LLM gateway (9router) doesn't expose an
embeddings endpoint. We use BM25 lexical retrieval over the event profile —
fast, deterministic, zero network, and well-suited for a small corpus (~15
chunks). The capability scorer still gets evidence-grounded snippets to
reason over, which is the whole point of the RAG step.

If a real embedding endpoint becomes available later, swap the index impl —
the public surface (`RAGIndex.build`, `topk`) stays the same.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from math import log


_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tok(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


@dataclass
class RAGIndex:
    """In-memory BM25 index over event profile chunks."""

    chunks: list[str]
    _docs: list[list[str]] = field(default_factory=list)
    _df: dict[str, int] = field(default_factory=dict)
    _avgdl: float = 0.0
    _N: int = 0
    _k1: float = 1.5
    _b: float = 0.75

    @classmethod
    def build(cls, chunks: list[str]) -> "RAGIndex":
        idx = cls(chunks=chunks)
        idx._docs = [_tok(c) for c in chunks]
        idx._N = len(idx._docs)
        if idx._N == 0:
            return idx
        idx._avgdl = sum(len(d) for d in idx._docs) / idx._N
        df: dict[str, int] = {}
        for doc in idx._docs:
            for term in set(doc):
                df[term] = df.get(term, 0) + 1
        idx._df = df
        return idx

    def _idf(self, term: str) -> float:
        n = self._df.get(term, 0)
        # Smoothed Robertson-Sparck Jones IDF; clamp non-positive to a small floor
        # so common terms still contribute slightly.
        return max(log((self._N - n + 0.5) / (n + 0.5) + 1.0), 0.01)

    def _score(self, query_terms: list[str], doc: list[str]) -> float:
        if not doc:
            return 0.0
        dl = len(doc)
        # Build per-doc term frequency once.
        tf: dict[str, int] = {}
        for t in doc:
            tf[t] = tf.get(t, 0) + 1
        score = 0.0
        for q in query_terms:
            if q not in tf:
                continue
            f = tf[q]
            num = f * (self._k1 + 1)
            denom = f + self._k1 * (1 - self._b + self._b * dl / (self._avgdl or 1.0))
            score += self._idf(q) * (num / denom)
        return score

    def topk(self, query: str, k: int = 5) -> list[tuple[str, float]]:
        if not self.chunks:
            return []
        q = _tok(query)
        scored = [
            (self.chunks[i], self._score(q, self._docs[i]))
            for i in range(self._N)
        ]
        scored.sort(key=lambda x: -x[1])
        # Always return at least k items so the LLM has context, even if all
        # scores are zero (very short queries).
        return scored[:k]


def event_profile_to_chunks(profile: dict) -> list[str]:
    """Flatten the structured event profile into retrievable text chunks."""
    chunks: list[str] = []
    name = profile.get("name", "")
    tagline = profile.get("tagline", "")
    chunks.append(f"Event: {name}. Tagline: {tagline}.")

    if desc := profile.get("description"):
        chunks.append(f"Description: {desc}")

    aud = profile.get("audience", {})
    if aud:
        chunks.append(
            f"Audience: {aud.get('size', 'N/A')} attendees. "
            f"Demographics: {aud.get('demographics', 'N/A')}. "
            f"Geographies: {', '.join(aud.get('geographies', []))}."
        )

    for prop in profile.get("value_props", []):
        chunks.append(f"Value proposition: {prop}")

    for past in profile.get("past_sponsors", []):
        chunks.append(
            f"Past sponsor: {past.get('name')} — tier {past.get('tier')}. "
            f"Why they sponsored: {past.get('rationale', '')}"
        )

    for tier in profile.get("sponsorship_tiers", []):
        chunks.append(
            f"Sponsorship tier '{tier.get('name')}' (IDR {tier.get('price_idr', 'TBD')}): "
            f"deliverables — {', '.join(tier.get('deliverables', []))}."
        )

    if isp := profile.get("ideal_sponsor_profile"):
        chunks.append(f"Ideal sponsor profile: {isp}")

    return chunks
