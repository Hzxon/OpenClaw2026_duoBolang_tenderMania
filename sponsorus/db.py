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
CREATE TABLE IF NOT EXISTS company_profile (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    tagline TEXT,
    profile_json TEXT NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS tenders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    buyer TEXT,
    country TEXT,
    sector TEXT,
    submission_deadline TEXT,
    contact_email TEXT,
    public_url TEXT,
    payload_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    UNIQUE(title, buyer)
);

CREATE TABLE IF NOT EXISTS scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tender_id INTEGER NOT NULL,
    dimension TEXT NOT NULL,
    score INTEGER NOT NULL,
    reasoning TEXT,
    evidence_json TEXT,
    created_at REAL NOT NULL,
    FOREIGN KEY (tender_id) REFERENCES tenders(id)
);

CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tender_id INTEGER NOT NULL UNIQUE,
    weighted_score REAL NOT NULL,
    decision TEXT NOT NULL,
    rationale TEXT,
    created_at REAL NOT NULL,
    FOREIGN KEY (tender_id) REFERENCES tenders(id)
);

CREATE TABLE IF NOT EXISTS drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tender_id INTEGER NOT NULL,
    subject TEXT NOT NULL,
    body_markdown TEXT NOT NULL,
    personalization_json TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at REAL NOT NULL,
    decided_at REAL,
    sent_at REAL,
    FOREIGN KEY (tender_id) REFERENCES tenders(id)
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


def upsert_company_profile(name: str, tagline: str, profile: dict[str, Any]) -> None:
    with conn() as c:
        c.execute(
            """INSERT INTO company_profile (id, name, tagline, profile_json, updated_at)
               VALUES (1, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 name=excluded.name, tagline=excluded.tagline,
                 profile_json=excluded.profile_json, updated_at=excluded.updated_at""",
            (name, tagline, json.dumps(profile), time.time()),
        )


def load_company_profile() -> dict[str, Any] | None:
    with conn() as c:
        row = c.execute("SELECT * FROM company_profile WHERE id=1").fetchone()
        if not row:
            return None
        return {
            "name": row["name"],
            "tagline": row["tagline"],
            **json.loads(row["profile_json"]),
        }


def upsert_tender(t: dict[str, Any]) -> int:
    with conn() as c:
        cur = c.execute(
            """INSERT INTO tenders
               (title, buyer, country, sector, submission_deadline, contact_email, public_url, payload_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(title, buyer) DO UPDATE SET
                 country=excluded.country, sector=excluded.sector,
                 submission_deadline=excluded.submission_deadline,
                 contact_email=excluded.contact_email,
                 public_url=excluded.public_url,
                 payload_json=excluded.payload_json
               RETURNING id""",
            (
                t.get("title", ""),
                t.get("buyer", ""),
                t.get("country"),
                t.get("sector"),
                t.get("submission_deadline"),
                t.get("contact_email"),
                t.get("public_url"),
                json.dumps(t),
                time.time(),
            ),
        )
        return cur.fetchone()[0]


def insert_score(tender_id: int, dim: str, score: int, reasoning: str, evidence: list[str]) -> None:
    with conn() as c:
        c.execute(
            """INSERT INTO scores (tender_id, dimension, score, reasoning, evidence_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (tender_id, dim, score, reasoning, json.dumps(evidence), time.time()),
        )


def insert_decision(tender_id: int, weighted: float, decision: str, rationale: str) -> None:
    with conn() as c:
        c.execute(
            """INSERT INTO decisions (tender_id, weighted_score, decision, rationale, created_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(tender_id) DO UPDATE SET
                 weighted_score=excluded.weighted_score,
                 decision=excluded.decision,
                 rationale=excluded.rationale,
                 created_at=excluded.created_at""",
            (tender_id, weighted, decision, rationale, time.time()),
        )


def insert_draft(tender_id: int, subject: str, body: str, notes: list[str]) -> int:
    with conn() as c:
        cur = c.execute(
            """INSERT INTO drafts (tender_id, subject, body_markdown, personalization_json, status, created_at)
               VALUES (?, ?, ?, ?, 'pending', ?) RETURNING id""",
            (tender_id, subject, body, json.dumps(notes), time.time()),
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
            """SELECT d.*, t.title AS tender_title, t.buyer, t.contact_email AS tender_contact, t.country
               FROM drafts d JOIN tenders t ON t.id = d.tender_id
               WHERE d.id=?""",
            (draft_id,),
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        # Backwards-compat keys for the send tool.
        d["company_name"] = d["buyer"]  # tender's buyer is the recipient
        d["contact_email"] = d.get("tender_contact")
        return d


def list_pending_drafts() -> list[dict[str, Any]]:
    with conn() as c:
        rows = c.execute(
            """SELECT d.*, t.title AS tender_title, t.buyer, t.contact_email AS tender_contact, t.country
               FROM drafts d JOIN tenders t ON t.id = d.tender_id
               WHERE d.status='pending' ORDER BY d.created_at DESC"""
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["company_name"] = d["buyer"]
            d["contact_email"] = d.get("tender_contact")
            out.append(d)
        return out


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
