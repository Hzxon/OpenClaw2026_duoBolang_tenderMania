"""CLI approval / denial of pending tender drafts.

Use when the Telegram bot can't run (e.g. token shared with another service).
Lists pending drafts, lets you approve or deny by ID, and on approval the
send_email tool is invoked (DRY_RUN by default — set DRY_RUN=false to send).

Usage:
    python3 -m sponsorus.scripts.approve            # list pending
    python3 -m sponsorus.scripts.approve 3 approve  # approve draft #3
    python3 -m sponsorus.scripts.approve 3 deny     # deny draft #3
    python3 -m sponsorus.scripts.approve 3 show     # full body
"""
from __future__ import annotations

import sys

from dotenv import load_dotenv

from sponsorus import db
from sponsorus.agents.send import send_email


def _list() -> int:
    pending = db.list_pending_drafts()
    if not pending:
        print("Inbox zero — no drafts awaiting approval.")
        return 0
    print(f"\n{len(pending)} draft(s) awaiting approval:\n")
    for d in pending:
        print(f"  #{d['id']:<3} {d['buyer'][:38]:<38} | {d['tender_title'][:60]}")
    print("\nApprove with: python3 -m sponsorus.scripts.approve <id> approve")
    print("Deny    with: python3 -m sponsorus.scripts.approve <id> deny")
    print("Inspect with: python3 -m sponsorus.scripts.approve <id> show")
    return 0


def _show(draft_id: int) -> int:
    d = db.get_draft(draft_id)
    if not d:
        print(f"Draft #{draft_id} not found.")
        return 1
    print(f"\nDraft #{d['id']} — status={d['status']}")
    print(f"Buyer:   {d['buyer']}  ({d.get('country')})")
    print(f"Tender:  {d['tender_title']}")
    print(f"Subject: {d['subject']}")
    print()
    print(d["body_markdown"])
    return 0


def _approve(draft_id: int) -> int:
    d = db.get_draft(draft_id)
    if not d:
        print(f"Draft #{draft_id} not found.")
        return 1
    if d["status"] != "pending":
        print(f"Draft #{draft_id} status={d['status']} — cannot approve.")
        return 1
    db.set_draft_status(draft_id, "approved")
    print(f"✅ Approved draft #{draft_id}. Triggering send tool…")
    result = send_email(draft_id)
    if result.get("ok"):
        mode = "DRY-RUN " if result.get("dry_run") else ""
        print(f"   {mode}sent: {result.get('subject')!r} → {result.get('to')}")
        return 0
    print(f"   ⚠️ Send failed: {result.get('error')}")
    return 2


def _deny(draft_id: int) -> int:
    d = db.get_draft(draft_id)
    if not d:
        print(f"Draft #{draft_id} not found.")
        return 1
    db.set_draft_status(draft_id, "denied")
    print(f"❌ Denied draft #{draft_id}.")
    return 0


def main() -> None:
    load_dotenv()
    args = sys.argv[1:]
    if not args:
        sys.exit(_list())
    try:
        draft_id = int(args[0])
    except ValueError:
        print("Usage: approve [<id> approve|deny|show]")
        sys.exit(2)
    action = args[1].lower() if len(args) > 1 else "show"
    handler = {"approve": _approve, "deny": _deny, "show": _show}.get(action)
    if not handler:
        print(f"Unknown action: {action}")
        sys.exit(2)
    sys.exit(handler(draft_id))


if __name__ == "__main__":
    main()
