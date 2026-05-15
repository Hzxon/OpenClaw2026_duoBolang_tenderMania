"""Telegram approval gate — the human-in-the-loop interface.

Pipeline pushes a draft summary and inline Approve / Deny buttons to the
operator's Telegram chat. Callback handlers update DB status, and the
orchestrator's send step picks up approved drafts.

Run as a long-poll bot:
    python3 -m sponsorus.telegram_bot
"""
from __future__ import annotations

import asyncio
import logging
import os

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from sponsorus import db
from sponsorus.agents.send import send_email

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


# ---- Outbound ---------------------------------------------------------------
async def push_draft_for_approval(application: Application, draft_id: int) -> None:
    """Send a draft summary + approval buttons to the operator chat."""
    chat_id = int(os.environ["TELEGRAM_OPERATOR_CHAT_ID"])
    draft = db.get_draft(draft_id)
    if not draft:
        log.warning("push_draft_for_approval: draft %s not found", draft_id)
        return
    body_preview = draft["body_markdown"][:600]
    text = (
        f"*Sponsor outreach pending approval*\n"
        f"\n*To:* {draft['company_name']} ({draft['contact_email'] or 'no email'})"
        f"\n*Subject:* {draft['subject']}\n\n"
        f"```\n{body_preview}\n```"
    )
    kb = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Approve & send", callback_data=f"approve:{draft_id}"),
                InlineKeyboardButton("❌ Deny", callback_data=f"deny:{draft_id}"),
            ]
        ]
    )
    await application.bot.send_message(
        chat_id=chat_id, text=text, reply_markup=kb, parse_mode="Markdown"
    )


def push_draft_blocking(draft_id: int) -> None:
    """Sync wrapper used by the pipeline so it doesn't need its own event loop."""
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    app = Application.builder().token(token).build()

    async def _go() -> None:
        await app.initialize()
        await push_draft_for_approval(app, draft_id)
        await app.shutdown()

    asyncio.run(_go())


# ---- Inbound (long-poll bot) ------------------------------------------------
async def cmd_start(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
    pending = db.list_pending_drafts()
    if not pending:
        await update.message.reply_text("SponsorUs online. No drafts awaiting approval right now.")
        return
    await update.message.reply_text(
        f"SponsorUs online. {len(pending)} draft(s) awaiting approval. "
        "Use /pending to list them."
    )


async def cmd_pending(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
    pending = db.list_pending_drafts()
    if not pending:
        await update.message.reply_text("Inbox zero — no drafts awaiting approval.")
        return
    lines = [
        f"#{d['id']} → {d['company_name']} — {d['subject']}"
        for d in pending[:10]
    ]
    await update.message.reply_text("Pending drafts:\n" + "\n".join(lines))


async def on_callback(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    action, _, draft_id_str = (q.data or "").partition(":")
    if not draft_id_str:
        return
    draft_id = int(draft_id_str)

    if action == "approve":
        db.set_draft_status(draft_id, "approved")
        result = send_email(draft_id)
        if result.get("ok"):
            mode = "DRY-RUN " if result.get("dry_run") else ""
            await q.edit_message_text(
                f"✅ Approved & {mode}sent: {result.get('subject')} → {result.get('to')}"
            )
        else:
            await q.edit_message_text(
                f"⚠️ Approved but send failed: {result.get('error')}"
            )
    elif action == "deny":
        db.set_draft_status(draft_id, "denied")
        await q.edit_message_text("❌ Denied. Draft archived.")


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN not set")
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("pending", cmd_pending))
    app.add_handler(CallbackQueryHandler(on_callback))
    log.info("SponsorUs Telegram bot up. Long-polling…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
