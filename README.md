# OpenClaw2026_duoBolang_tenderMania

> # **TenderMania**
>
> Autonomous tender-hunting agent — finds compatible procurement opportunities for a company, scores fit through a multi-agent reasoning loop, and drafts personalized expressions of interest gated by human approval.


---

## What it does

A consultancy spends hours every week trawling LPSE, World Bank, and ministry portals for tenders that fit. Most don't. tenderMania replaces that grind with an agent loop:

```
[live scrape]  →  [LLM normalize → Pydantic]  →  [3 parallel scorer agents]
                                                          ↓
                            [archive] ← below threshold ← [aggregator + hard gates]
                                                          ↓ above
                              [RAG-grounded EOI drafter]  →  [Telegram approval]  →  [SMTP send]
```

Every arrow is a tool call. The whole loop runs unattended on a single command. Only the final send is gated on a human tap.

There is no chat UI. The agents act on a schedule, score with reasoning, and produce concrete artifacts (drafts in SQLite, approval cards on Telegram).

---

## Architecture

### Multi-agent topology

```
                 ┌────────────────────────────────────────────┐
                 │  Scraper agents (one per source — tool calls)│
                 │  ┌─────────────────┐  ┌──────────────────┐ │
                 │  │ LPSE / PLN eProc │  │ World Bank API   │ │
                 │  │ (Indonesian BUMN)│  │ (global, 400k)   │ │
                 │  └────────┬────────┘  └────────┬─────────┘ │
                 │           └──────────┬─────────┘           │
                 └──────────────────────┼─────────────────────┘
                                        ▼
                              ┌──────────────────┐
                              │ Normalizer agent │  LLM + Pydantic → TenderOpportunity
                              └────────┬─────────┘
                                       ▼
       ┌───────────────────────────────┴────────────────┐
       │     Multi-agent fan-out (asyncio)              │
       ├───────────┬─────────────┬──────────────────────┤
       │ capability│ eligibility │ win-prob             │   3 LLM calls in parallel
       │  scorer   │   scorer    │  scorer              │   each cites RAG evidence
       └────┬──────┴──────┬──────┴──────┬───────────────┘
            └─────────────┼─────────────┘
                          ▼
                ┌────────────────────┐
                │  Aggregator        │  hard-gates + weighted threshold
                │  (rule + LLM)      │  → pursue | archive
                └─────────┬──────────┘
                          ▼ pursue
                ┌────────────────────┐
                │  Drafter agent     │  RAG-grounded EOI in
                │  (LLM + RAG)       │  Bahasa or English
                └─────────┬──────────┘
                          ▼
                ┌────────────────────┐
                │  Approval gate     │  CLI (`scripts/approve`) or Telegram
                │                    │  inline buttons → callback
                └─────────┬──────────┘
                          ▼ approve
                ┌────────────────────┐
                │  Email sender      │  yagmail (DRY_RUN by default)
                └────────────────────┘
```

The system gives you two approval paths so the demo doesn't fight your existing tools:

- **CLI approval (no token conflicts):** `python3 -m sponsorus.scripts.approve` lists pending drafts, lets you approve, deny, or inspect by ID. The send tool only fires after approval.
- **Telegram approval (when the token is free):** `python3 -m sponsorus.telegram_bot` runs a long-poll bot. Pipeline pushes a card with ✅/❌ inline buttons; tapping ✅ moves the draft to `approved` and triggers the send tool.

### Hard gates (deterministic, not LLM-decided)

- `eligibility_fit < 30` → mandatory archive (cannot legally bid)
- `capability_fit < 35` → mandatory archive (clearly outside expertise)
- `weighted_score < threshold` → mandatory archive

The LLM only writes the rationale once a tender clears these rules. This is how we make the system auditable — every archive has a deterministic reason; only `pursue` decisions involve LLM judgment.

### Why BM25 instead of embeddings

Our local LLM gateway doesn't expose an embeddings endpoint. Rather than ship a 300MB sentence-transformers dep for ~25 profile chunks, we use a tiny BM25 index. For corpora this small, lexical retrieval is fast, deterministic, and grounds the scorers just as well. The `RAGIndex` interface is unchanged, so swapping in embeddings later is a one-file change.

---

## Live data sources -- temporary only support these 2 :(

The pipeline pulls from two real, public, no-auth procurement endpoints in parallel:

1. **PLN e-Procurement** — `https://eproc.pln.co.id/portal/pengumuman_pengadaan/alldatakhs`
   Public DataTables JSON of *Kontrak Harga Satuan* (multi-year unit-price) tenders from PLN, Indonesia's national electricity BUMN. Includes pengadaan barang, jasa lainnya, jasa konsultansi, and pekerjaan konstruksi across regional units.

2. **World Bank Procurement Notices** — `https://search.worldbank.org/api/v2/procnotices`
   Public REST API exposing 400k+ live procurement notices across World-Bank-funded projects worldwide, including Indonesia, SEA, and global IT-development tenders.

Both sources have curated Indonesian-flavored fallback fixtures (`data/fixtures/`) so demos work without network. Switch sources with `SOURCES=lpse,worldbank` (default) or single-source via `SOURCES=lpse` / `SOURCES=worldbank`.

---

## Tech Stack

- **Python 3.11+**
- **Scrape:** `httpx` + Python `urllib` (World Bank API), `selectolax` for HTML fallback
- **Schemas:** `pydantic` v2 with strict JSON-mode prompts
- **RAG:** custom BM25 (no third-party dep)
- **Persistence:** SQLite via stdlib
- **Approval gate:** `python-telegram-bot` v22 (long-polling, callback queries)
- **Email:** `yagmail` (DRY_RUN bypass for safe demos)
- **Reliability:** `tenacity` retries on every LLM call

---

## Quick Start (untuk juri / for reviewers)

> **TL;DR untuk juri:** dengan satu API key OpenAI, repo ini berjalan dari klon-segar sampai menghasilkan draf email tender yang siap di-approve dalam **kurang dari 5 menit**. Mode default sudah aman: `DRY_RUN=true` + `PUSH_TELEGRAM=false`, jadi tidak ada email atau pesan Telegram yang benar-benar terkirim sampai Anda sengaja mematikannya.

### Prasyarat / Prerequisites

- **Python 3.11 atau lebih baru** (`python3 --version` harus menampilkan ≥ 3.11).
- **`git`**
- **API key dari endpoint yang OpenAI-compatible.** Public OpenAI (`sk-...`) bekerja langsung. Endpoint lokal seperti Ollama, LM Studio, atau gateway internal juga bekerja — cukup ubah `SPONSORUS_LLM_BASE_URL` di `.env`.
- *(Opsional)* Bot Telegram + chat ID jika ingin gerbang persetujuan via Telegram. Tanpa ini, persetujuan dilakukan via CLI.
- *(Opsional)* Akun Gmail + app password jika ingin benar-benar mengirim email. Tanpa ini, mode DRY-RUN akan mencetak email ke terminal.

### Step 1 — Clone & install

```bash
git clone https://github.com/Hzxon/OpenClaw2026_duoBolang_SponsorUs.git
cd OpenClaw2026_duoBolang_SponsorUs

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 2 — Configure environment

```bash
cp .env.example .env
# Buka .env di editor favorit dan isi minimal OPENAI_API_KEY.
# Default lain (SOURCES, SCORE_THRESHOLD, DRY_RUN, dst.) sudah aman.
```

Isi minimum di `.env` agar pipeline jalan:

```
OPENAI_API_KEY=sk-...                              # WAJIB
SPONSORUS_LLM_BASE_URL=https://api.openai.com/v1   # ganti jika pakai gateway lokal
SPONSORUS_LLM_MODEL=gpt-4o-mini                    # atau model lain yang Anda punya
```

### Step 3 — Initialize database & seed company profile

```bash
python3 -m sponsorus.scripts.init_db          # buat schema SQLite di data/sponsorus.db
python3 -m sponsorus.scripts.seed_company     # muat profil perusahaan dari data/company_profile.yaml
```

Output yang diharapkan:
```
DB initialized at /path/to/data/sponsorus.db
Company profile loaded: 'Bolang Solutions'
```

### Step 4 — Run satu siklus autonomous loop

```bash
python3 -m sponsorus.run_pipeline
```

Selama ±60–120 detik agent akan:
1. **Scrape** tender real-time dari **PLN e-Procurement** + **World Bank Procurement Notices**.
2. **Normalize** tiap tender ke `TenderOpportunity` (validasi Pydantic).
3. **Score** secara paralel dengan 3 agen: capability / eligibility / win-probability.
4. **Aggregate** dengan hard-gates → keputusan `PURSUE` atau `ARCHIVE`.
5. **Draft** Expression of Interest (Bahasa atau English, tergantung tender) untuk yang `PURSUE`.

Output yang diharapkan (contoh):
```
[pipeline] run a8f3b56b started — threshold=55.0, sources=['lpse', 'worldbank'], live=True
[pipeline] company: Bolang Solutions
[pipeline] RAG index built over 23 chunks
[pipeline] lpse: 3 raw tenders (live:pln-eproc)
[pipeline] worldbank: 3 raw tenders (live:worldbank-procnotices)
[pipeline] [1/6] normalizing: KHS PEKERJAAN JASA PEMELIHARAAN ROW UPT MANADO
[pipeline]   → ARCHIVE (weighted=23.8; cap=18, elig=38, win=12)
...
[pipeline] [4/6] normalizing: Pilot for VO/MS/ZS Accounting Implementation
[pipeline]   → PURSUE (weighted=58.5; cap=68, elig=58, win=38)
[pipeline]   drafted EOI #1
[pipeline] run a8f3b56b done in 93.5s
```

> **Tidak ada tender yang di-PURSUE?** Ini adalah perilaku **jujur** — tender real hari ini mungkin tidak cocok. Coba: `SCORE_THRESHOLD=40 python3 -m sponsorus.run_pipeline` atau `PREFER_LIVE=false python3 -m sponsorus.run_pipeline` (memakai fixture Indonesian BUMN bawaan untuk demo deterministik).

### Step 5 — Review & approve drafts (gerbang human-in-the-loop)

Setelah pipeline selesai, draf disimpan di SQLite dengan status `pending`. Approve via **CLI** (cara default, paling simpel):

```bash
# Lihat semua draf yang menunggu approval
python3 -m sponsorus.scripts.approve

# Inspeksi isi draf #1
python3 -m sponsorus.scripts.approve 1 show

# Setujui (memicu tool send_email — di mode DRY_RUN hanya mencetak ke terminal)
python3 -m sponsorus.scripts.approve 1 approve

# Tolak
python3 -m sponsorus.scripts.approve 1 deny
```

*Atau* via **Telegram bot** (jika `TELEGRAM_BOT_TOKEN` + `TELEGRAM_OPERATOR_CHAT_ID` terisi):

```bash
# Terminal 1: bot polling
python3 -m sponsorus.telegram_bot

# Terminal 2: push semua draf pending sebagai kartu approval ke Telegram
python3 -c "from sponsorus import db; from sponsorus.telegram_bot import push_draft_blocking; \
[push_draft_blocking(d['id']) for d in db.list_pending_drafts()]"
```
Lalu tap ✅ atau ❌ di Telegram.

### Verifikasi cepat (sanity check)

Setelah Step 4 selesai, jalankan:
```bash
python3 -c "import sqlite3; c = sqlite3.connect('data/sponsorus.db'); \
print('runs:    ', c.execute('SELECT COUNT(*) FROM runs').fetchone()[0]); \
print('tenders: ', c.execute('SELECT COUNT(*) FROM tenders').fetchone()[0]); \
print('drafts:  ', c.execute('SELECT COUNT(*) FROM drafts').fetchone()[0]); \
print('scores:  ', c.execute('SELECT COUNT(*) FROM scores').fetchone()[0])"
```
Harus muncul angka non-nol untuk `runs`, `tenders`, dan `scores`. Jika `drafts: 0` itu normal (semua tender di-archive — lihat catatan di atas tentang `SCORE_THRESHOLD`).

### Demo cepat 100% offline (tidak perlu internet)

Jika juri ingin reproducible run tanpa bergantung pada network atau availability tender real-time:

```bash
PREFER_LIVE=false SCORE_THRESHOLD=40 SOURCES=lpse python3 -m sponsorus.run_pipeline
```

Memakai fixture Indonesian BUMN bawaan (PLN, Pemkot Bandung, Kemendikbud, dll. — semua dimodelkan sesuai format LPSE/SPSE asli). Dijamin `PURSUE ≥ 1` dan deterministik.

### Environment variables

| Variable | Default | Wajib? | Purpose |
|----------|---------|--------|---------|
| `OPENAI_API_KEY` | — | **WAJIB** | Bearer token untuk endpoint LLM |
| `SPONSORUS_LLM_BASE_URL` | `http://localhost:20128/v1` | tidak | Base URL OpenAI-compatible (set ke `https://api.openai.com/v1` untuk public OpenAI) |
| `SPONSORUS_LLM_MODEL` | `cx/gpt-5.5` | tidak | Model untuk chat completion |
| `SOURCES` | `lpse,worldbank` | tidak | Sumber tender: `lpse`, `worldbank`, atau keduanya |
| `MAX_TENDERS` | `6` | tidak | Jumlah tender per siklus |
| `PREFER_LIVE` | `true` | tidak | `true` = scrape real, `false` = fixture |
| `SCORE_THRESHOLD` | `55` | tidak | Cutoff weighted-score untuk PURSUE |
| `PUSH_TELEGRAM` | `true` | tidak | Push kartu approval ke Telegram |
| `DRY_RUN` | `true` | tidak | `true` = print email; `false` = kirim SMTP beneran |
| `TELEGRAM_BOT_TOKEN` | — | opsional | Token dari @BotFather |
| `TELEGRAM_OPERATOR_CHAT_ID` | — | opsional | Chat ID tujuan kartu approval |
| `SMTP_USER` | — | opsional | Gmail address (hanya jika `DRY_RUN=false`) |
| `SMTP_APP_PASSWORD` | — | opsional | Google app password |

### Troubleshooting

| Gejala | Penyebab & solusi |
|--------|-------------------|
| `ModuleNotFoundError: No module named 'sponsorus'` | Virtualenv belum diaktifkan. Jalankan `source .venv/bin/activate` lebih dulu. |
| `openai.AuthenticationError: 401` | `OPENAI_API_KEY` di `.env` salah/expired. Cek dengan `curl -H "Authorization: Bearer $OPENAI_API_KEY" $SPONSORUS_LLM_BASE_URL/models`. |
| `openai.NotFoundError: model not found` | `SPONSORUS_LLM_MODEL` tidak tersedia di endpoint Anda. Untuk public OpenAI gunakan `gpt-4o-mini` atau `gpt-4o`. |
| Pipeline `live` gagal connect ke PLN/World Bank | Network blocked. Jalankan dengan `PREFER_LIVE=false` — fixture Indonesian BUMN akan dipakai otomatis. |
| Telegram bot error `Conflict: terminated by other getUpdates` | Token Telegram dipakai oleh proses lain. Hentikan service lain, atau pakai approval via CLI. |
| Email tidak terkirim | Default `DRY_RUN=true` — email hanya dicetak ke terminal. Untuk benar-benar kirim, set `DRY_RUN=false` + isi `SMTP_USER`/`SMTP_APP_PASSWORD`. |

---

## Repo layout

```
sponsorus/
  agents/
    scrape.py          live World Bank tender API + fixture fallback
    normalize.py       LLM → Pydantic TenderOpportunity
    score.py           3 scorer agents + aggregator (hard gates)
    draft.py           RAG-grounded EOI drafter
    send.py            yagmail SMTP, DRY_RUN safe
  schemas.py           Pydantic contracts between agents
  rag.py               BM25 index over company profile
  llm.py               Provider-agnostic structured output
  db.py                SQLite layer
  telegram_bot.py      Approval gate (push + callbacks)
  run_pipeline.py      Autonomous orchestrator (the agent loop)
  scripts/
    init_db.py         One-shot DB setup
    seed_company.py    Load company profile from YAML
    approve.py         CLI approve/deny/inspect for pending drafts
    demo.py            One-cycle demo runner
    seed_event.py      [legacy compat shim — redirects to seed_company]
data/
  company_profile.yaml The company on whose behalf the agent hunts
  fixtures/            Cached scrape blob for offline demo
prompts/               (versioned prompt drafts; live prompts inline in agents)
```

---

## Sample run output

```
[pipeline] run 209459b8 started — threshold=55.0, live=True
[pipeline] company: Bolang Solutions
[pipeline] RAG index built over 23 chunks
[pipeline] scraped 4 raw tenders from live:worldbank-procnotices
[pipeline] [1/4] normalizing: Pilot for design, development and implementation of VO, MS and ZS accounting...
[pipeline]   scoring (3 agents in parallel)…
[pipeline]   → PURSUE (weighted=62.5; cap=70, elig=58, win=51)
[pipeline]   drafted EOI #1
[pipeline] [2/4] normalizing: National Strategy for Financial Literacy
[pipeline]   → ARCHIVE (weighted=28.1; cap=25, elig=38, win=18)
[pipeline] [3/4] normalizing: Senior Spatial Data Coordinator (job posting)
[pipeline]   → ARCHIVE (weighted=39.5; cap=42, elig=45, win=24)
[pipeline] [4/4] normalizing: GIS Phase-2 Development
[pipeline]   → PURSUE (weighted=56.4; cap=68, elig=52, win=38)
[pipeline]   drafted EOI #2
[pipeline] run 209459b8 done in 66.1s
```

The agent correctly:
- archived a strategy/policy contract (no software deliverables)
- archived a job posting that surfaced through the procurement feed
- pursued two real software-development tenders

---

## License

MIT
