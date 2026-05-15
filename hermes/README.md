# Hermes Integration Layer

This directory contains everything needed to run TenderMania *as a first-class
Hermes Agent capability* — installable skill, schedulable cron job,
programmatic tool entrypoint.

## Files

| File | Purpose |
|------|---------|
| `cron_run.sh` | Helper script for `cronjob(...)` daily-hunt jobs. Stdout = JSON run summary, stderr = pipeline log. |
| `tool_run.py` | Programmatic entrypoint with CLI fallback. Used by `delegate_task` workers and Hermes-native tools. |

The skill manifest lives at `../SKILL.md` (one directory up, repo root).

## Three integration patterns

### 1. Install as a Hermes skill

```bash
hermes skills install https://raw.githubusercontent.com/Hzxon/OpenClaw2026_duoBolang_SponsorUs/main/SKILL.md
```

Now any Hermes session can `/skill tendermania` to load operator knowledge.

### 2. Schedule daily autonomous hunts

```python
cronjob(
  action="create",
  name="tendermania-daily-hunt",
  schedule="0 9 * * 1-5",
  prompt="Run TenderMania for the day...",
  script="~/tendermania/hermes/cron_run.sh",
  enabled_toolsets=["terminal", "file"],
)
```

The script runs deterministically (no LLM cost) and writes a structured
JSON summary to stdout. The Hermes agent then summarizes for delivery.

### 3. Programmatic invocation from any Python context

```python
import sys; sys.path.insert(0, "/Users/hazron/tendermania")
from hermes.tool_run import run_tendermania

result = run_tendermania(sources=["lpse"], max_tenders=4)
print(f"pursued {result['tenders_pursued']} of {result['tenders_seen']}")
```

Or via CLI:

```bash
python3 -m hermes.tool_run --sources lpse --max 4 --threshold 55
```

## Verifying the integration

```bash
# Skill discovery
hermes skills inspect https://raw.githubusercontent.com/Hzxon/OpenClaw2026_duoBolang_SponsorUs/main/SKILL.md

# Cron job dry run (without scheduling)
~/tendermania/hermes/cron_run.sh

# Programmatic entrypoint
cd ~/tendermania && source .venv/bin/activate && \
  python3 -m hermes.tool_run --no-live --max 2 --threshold 40
```

All three paths exit non-zero on failure and emit machine-readable JSON
on stdout for the success path.
