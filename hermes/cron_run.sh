#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
#  TenderMania — Hermes cron helper
#
#  Runs a deterministic pipeline tick suitable for daily scheduling.
#  Stdout is the structured run summary (consumed by the calling agent).
#  Stderr is silent in normal operation.
#
#  Used by:
#    cronjob(name="tendermania-daily-hunt", script="~/tendermania/hermes/cron_run.sh", ...)
# ─────────────────────────────────────────────────────────────────────
set -euo pipefail

# Resolve repo root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_DIR"

if [[ ! -d ".venv" ]]; then
    echo "ERROR: ~/tendermania/.venv missing. Run: python3 -m venv .venv && pip install -r requirements.txt" >&2
    exit 1
fi
# shellcheck disable=SC1091
source .venv/bin/activate

if [[ -f ".env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi

# Cron defaults — overridable via env at job creation time
: "${SOURCES:=lpse,worldbank}"
: "${MAX_TENDERS:=6}"
: "${SCORE_THRESHOLD:=60}"
: "${PREFER_LIVE:=true}"
: "${PUSH_TELEGRAM:=true}"

# Ensure DB exists (idempotent)
python3 -m sponsorus.scripts.init_db >/dev/null 2>&1 || true
python3 -m sponsorus.scripts.seed_company >/dev/null 2>&1 || true

# Run pipeline; stream pipeline log to stderr, capture stats for stdout
SOURCES="$SOURCES" \
MAX_TENDERS="$MAX_TENDERS" \
SCORE_THRESHOLD="$SCORE_THRESHOLD" \
PREFER_LIVE="$PREFER_LIVE" \
PUSH_TELEGRAM="$PUSH_TELEGRAM" \
python3 -m sponsorus.run_pipeline 1>&2

# Emit a clean machine-readable summary on stdout
python3 - <<'PY'
import sqlite3, json
c = sqlite3.connect('data/sponsorus.db')
c.row_factory = sqlite3.Row
last_run = c.execute(
    'SELECT * FROM runs ORDER BY started_at DESC LIMIT 1'
).fetchone()
if last_run is None:
    print(json.dumps({"error": "no runs in audit trail"}))
    raise SystemExit(0)

# Stats are stored as JSON blob in `stats_json`
try:
    stats = json.loads(dict(last_run).get("stats_json") or "{}")
except (ValueError, TypeError):
    stats = {}

pending = c.execute(
    'SELECT d.id, d.subject, t.buyer, t.title '
    'FROM drafts d JOIN tenders t ON d.tender_id = t.id '
    'WHERE d.status = "pending" '
    'ORDER BY d.id DESC LIMIT 10'
).fetchall()

summary = {
    "run_id":           stats.get("run_id"),
    "started_at":       dict(last_run).get("started_at"),
    "finished_at":      dict(last_run).get("finished_at"),
    "elapsed_s":        stats.get("elapsed_s"),
    "tenders_seen":     stats.get("tenders_seen"),
    "tenders_pursued":  stats.get("tenders_pursued"),
    "tenders_archived": stats.get("tenders_archived"),
    "source":           stats.get("source"),
    "drafts_pushed_to_telegram": stats.get("drafts_pushed_to_telegram"),
    "pending_drafts":   [dict(p) for p in pending],
}
print(json.dumps(summary, indent=2, ensure_ascii=False))
PY
