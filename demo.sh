#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
#  TenderMania — end-to-end demo script
#
#  Usage:
#    ./demo.sh           # interactive mode (press ENTER between steps)
#    ./demo.sh --auto    # auto mode (no pauses, ~90s total)
#
#  What it does:
#    1. Resets the DB and seeds the Bolang Solutions profile
#    2. Runs the autonomous multi-agent pipeline (offline-deterministic)
#    3. Lists pending drafts in SQLite
#    4. Inspects the AI Chatbot draft (Bahasa Indonesia, RAG-grounded)
#    5. Shows the per-dimension reasoning + cited evidence
#    6. Approves the draft → send_email tool fires in DRY_RUN
# ─────────────────────────────────────────────────────────────────────
set -e

# Resolve repo root no matter where the script is invoked from
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

AUTO=false
if [[ "${1:-}" == "--auto" ]]; then
    AUTO=true
fi

pause() {
    if [[ "$AUTO" == "true" ]]; then
        sleep 1
    else
        echo
        read -r -p "  ↵  Press ENTER to continue..."
        echo
    fi
}

banner() {
    echo
    echo "════════════════════════════════════════════════════════════"
    echo "  $1"
    echo "════════════════════════════════════════════════════════════"
}

# ─── activate venv + load .env ───────────────────────────────────────
if [[ ! -d ".venv" ]]; then
    echo "ERROR: .venv not found. Run: python3 -m venv .venv && pip install -r requirements.txt"
    exit 1
fi
# shellcheck disable=SC1091
source .venv/bin/activate

if [[ ! -f ".env" ]]; then
    echo "ERROR: .env not found. Run: cp .env.example .env  and fill OPENAI_API_KEY"
    exit 1
fi
set -a
# shellcheck disable=SC1091
source .env
set +a

# ─── reset state for a clean demo ────────────────────────────────────
clear
banner "TenderMania — autonomous tender-hunting agent"
echo
echo "  Resetting DB for a clean run..."
rm -f data/sponsorus.db
python3 -m sponsorus.scripts.init_db | sed 's/^/  /'
python3 -m sponsorus.scripts.seed_company | sed 's/^/  /'
pause

# ─── Step 1: company profile ─────────────────────────────────────────
banner "Step 1 — Company profile (the agent hunts on its behalf)"
sed -n '1,25p' data/company_profile.yaml
pause

# ─── Step 2: the autonomous loop ─────────────────────────────────────
banner "Step 2 — Autonomous multi-agent pipeline"
echo "  scrape → normalize → 3 parallel scorers → aggregate → draft"
echo
SOURCES=lpse \
PREFER_LIVE=false \
SCORE_THRESHOLD=40 \
MAX_TENDERS=2 \
PUSH_TELEGRAM=false \
python3 -m sponsorus.run_pipeline
pause

# ─── Step 3: list pending drafts ─────────────────────────────────────
banner "Step 3 — Drafts awaiting human approval"
python3 -m sponsorus.scripts.approve
pause

# ─── Step 4: inspect the showcase draft ──────────────────────────────
banner "Step 4 — Inspect draft #2 (Pemkot Bandung AI Chatbot)"
python3 -m sponsorus.scripts.approve 2 show
pause

# ─── Step 5: per-dimension reasoning trace ───────────────────────────
banner "Step 5 — Reasoning trace + cited RAG evidence"
python3 - <<'PY'
import sqlite3, json
c = sqlite3.connect('data/sponsorus.db')
c.row_factory = sqlite3.Row
rows = c.execute('''
    SELECT s.dimension, s.score, s.reasoning, s.evidence_json, t.title
    FROM scores s JOIN tenders t ON s.tender_id = t.id
    WHERE t.title LIKE "%Chatbot%"
    ORDER BY s.dimension
''').fetchall()
for r in rows:
    print(f'  {r["dimension"]:<16} {r["score"]:>5.1f}/100')
    print(f'    Reasoning: {r["reasoning"][:200]}...' if len(r["reasoning"]) > 200 else f'    Reasoning: {r["reasoning"]}')
    print(f'    Evidence cited:')
    for ev in json.loads(r["evidence_json"]):
        print(f'      • {ev[:110]}')
    print()
PY
pause

# ─── Step 6: approve → send tool fires ───────────────────────────────
banner "Step 6 — Human approval → send_email tool (DRY_RUN safe)"
python3 -m sponsorus.scripts.approve 2 approve

echo
echo "════════════════════════════════════════════════════════════"
echo "  Demo complete."
echo "  • Multi-agent autonomous loop: scrape → score → draft"
echo "  • Live data sources, audit trail in SQLite"
echo "  • Human-in-the-loop gate, DRY_RUN safe"
echo "  • github.com/Hzxon/OpenClaw2026_duoBolang_SponsorUs"
echo "════════════════════════════════════════════════════════════"
