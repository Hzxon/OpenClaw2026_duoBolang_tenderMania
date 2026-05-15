"""Email send tool. Strictly gated — only invoked after a draft has status='approved'."""
from __future__ import annotations

import os
from typing import Optional

from sponsorus import db


def send_email(draft_id: int, dry_run: Optional[bool] = None) -> dict:
    """Send the approved draft. Returns a result dict for the orchestrator log.

    DRY_RUN=true (default) prints the email and marks it sent in DB without
    actually emitting SMTP — the demo stays safe for judging.
    """
    if dry_run is None:
        dry_run = os.environ.get("DRY_RUN", "true").lower() in ("1", "true", "yes")

    draft = db.get_draft(draft_id)
    if not draft:
        return {"ok": False, "error": f"draft {draft_id} not found"}
    if draft["status"] != "approved":
        return {"ok": False, "error": f"draft {draft_id} status={draft['status']} (must be approved)"}

    to_addr = draft.get("contact_email") or "partnerships@example.com"
    subject = draft["subject"]
    body = draft["body_markdown"]

    if dry_run:
        print(f"\n=== [DRY_RUN] Would send email ===")
        print(f"To:      {to_addr}")
        print(f"Subject: {subject}")
        print(body)
        print("=================================\n")
        db.set_draft_status(draft_id, "sent")
        return {"ok": True, "dry_run": True, "to": to_addr, "subject": subject}

    user = os.environ.get("SMTP_USER")
    pw = os.environ.get("SMTP_APP_PASSWORD")
    if not (user and pw):
        return {"ok": False, "error": "SMTP_USER / SMTP_APP_PASSWORD not set; set DRY_RUN=true to bypass"}

    try:
        import yagmail  # local import — only needed for live send

        yag = yagmail.SMTP(user, pw)
        yag.send(to=to_addr, subject=subject, contents=body)
        db.set_draft_status(draft_id, "sent")
        return {"ok": True, "dry_run": False, "to": to_addr, "subject": subject}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"SMTP send failed: {e!r}"}
