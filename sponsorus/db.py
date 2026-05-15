"""SQLite layer. Plain stdlib — no ORM, fewer moving parts at hackathon speed."""
from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "sponsorus.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS event_profile (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    tagline TEXT,
    profile_json TEXT NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS prospects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_name TEXT NOT NULL,
    industry TEXT,
    contact_email TEXT,
    public_url TEXT,
    payload_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    UNIQUE(company_name)
);

CREATE TABLE IF NOT EXISTS scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prospect_id INTEGER NOT NULL,
    dimension TEXT NOT NULL,
    score INTEGER NOT NULL,
    reasoning TEXT,
    evidence_json TEXT,
    created_at REAL NOT NULL,
    FOREIGN KEY (prospect_id) REFERENCES prospects(id)
);

CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prospect_id INTEGER NOT NULL UNIQUE,
    weighted_score REAL NOT NULL,
    decision TEXT NOT NULL,
    rationale TEXT,
    created_at REAL NOT NULL,
    FOREIGN KEY (prospect_id) REFERENCES prospects(id)
);

CREATE TABLE IF NOT EXISTS drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prospect_id INTEGER NOT NULL,
    subject TEXT NOT NULL,
    body_markdown TEXT NOT NULL,
    personalization_json TEXT,
    status TEXT NOT NULL DEFAULT 'pending',  -- pending | approved | denied | sent
    created_at REAL NOT NULL,
    decided_at REAL,
    sent_at REAL,
    FOREIGN KEY (prospect_id) REFERENCES prospects(id)
);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT UNIQUE NOT NULL,
    started_at REAL NOT NULL,
    finished_at REAL,
    stats_json TEXT
);
"""


@contextmanager
def conn() -> Iterator[sqlite3.Connection]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init_db() -> None:
    with conn() as c:
        c.executescript(SCHEMA)


def upsert_event_profile(name: str, tagline: str, profile: dict[str, Any]) -> None:
    with conn() as c:
        c.execute(
            """INSERT INTO event_profile (id, name, tagline, profile_json, updated_at)
               VALUES (1, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 name=excluded.name, tagline=excluded.tagline,
                 profile_json=excluded.profile_json, updated_at=excluded.updated_at""",
            (name, tagline, json.dumps(profile), time.time()),
        )


def load_event_profile() -> dict[str, Any] | None:
    with conn() as c:
        row = c.execute("SELECT * FROM event_profile WHERE id=1").fetchone()
        if not row:
            return None
        return {
            "name": row["name"],
            "tagline": row["tagline"],
            **json.loads(row["profile_json"]),
        }


def upsert_prospect(p: dict[str, Any]) -> int:
    with conn() as c:
        cur = c.execute(
            """INSERT INTO prospects (company_name, industry, contact_email, public_url, payload_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(company_name) DO UPDATE SET
                 industry=excluded.industry,
                 contact_email=excluded.contact_email,
                 public_url=excluded.public_url,
                 payload_json=excluded.payload_json
               RETURNING id""",
            (
                p["company_name"],
                p.get("industry"),
                p.get("contact_email"),
                p.get("public_url"),
                json.dumps(p),
                time.time(),
            ),
        )
        return cur.fetchone()[0]


def insert_score(prospect_id: int, dim: str, score: int, reasoning: str, evidence: list[str]) -> None:
    with conn() as c:
        c.execute(
            """INSERT INTO scores (prospect_id, dimension, score, reasoning, evidence_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (prospect_id, dim, score, reasoning, json.dumps(evidence), time.time()),
        )


def insert_decision(prospect_id: int, weighted: float, decision: str, rationale: str) -> None:
    with conn() as c:
        c.execute(
            """INSERT INTO decisions (prospect_id, weighted_score, decision, rationale, created_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(prospect_id) DO UPDATE SET
                 weighted_score=excluded.weighted_score,
                 decision=excluded.decision,
                 rationale=excluded.rationale,
                 created_at=excluded.created_at""",
            (prospect_id, weighted, decision, rationale, time.time()),
        )


def insert_draft(prospect_id: int, subject: str, body: str, notes: list[str]) -> int:
    with conn() as c:
        cur = c.execute(
            """INSERT INTO drafts (prospect_id, subject, body_markdown, personalization_json, status, created_at)
               VALUES (?, ?, ?, ?, 'pending', ?) RETURNING id""",
            (prospect_id, subject, body, json.dumps(notes), time.time()),
        )
        return cur.fetchone()[0]


def set_draft_status(draft_id: int, status: str) -> None:
    with conn() as c:
        ts = time.time()
        if status in ("approved", "denied"):
            c.execute("UPDATE drafts SET status=?, decided_at=? WHERE id=?", (status, ts, draft_id))
        elif status == "sent":
            c.execute("UPDATE drafts SET status='sent', sent_at=? WHERE id=?", (ts, draft_id))
        else:
            c.execute("UPDATE drafts SET status=? WHERE id=?", (status, draft_id))


def get_draft(draft_id: int) -> dict[str, Any] | None:
    with conn() as c:
        row = c.execute(
            """SELECT d.*, p.company_name, p.contact_email
               FROM drafts d JOIN prospects p ON p.id = d.prospect_id
               WHERE d.id=?""",
            (draft_id,),
        ).fetchone()
        if not row:
            return None
        return dict(row)


def list_pending_drafts() -> list[dict[str, Any]]:
    with conn() as c:
        rows = c.execute(
            """SELECT d.*, p.company_name, p.contact_email
               FROM drafts d JOIN prospects p ON p.id = d.prospect_id
               WHERE d.status='pending' ORDER BY d.created_at DESC"""
        ).fetchall()
        return [dict(r) for r in rows]


def start_run(run_id: str) -> None:
    with conn() as c:
        c.execute(
            "INSERT INTO runs (run_id, started_at) VALUES (?, ?)",
            (run_id, time.time()),
        )


def finish_run(run_id: str, stats: dict[str, Any]) -> None:
    with conn() as c:
        c.execute(
            "UPDATE runs SET finished_at=?, stats_json=? WHERE run_id=?",
            (time.time(), json.dumps(stats), run_id),
        )
