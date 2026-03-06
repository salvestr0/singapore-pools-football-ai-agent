"""
Telegram command handlers.
"""
from __future__ import annotations

import asyncio
import logging
import time

from telegram import Update
from telegram.ext import ContextTypes, Application

from config import TELEGRAM_CHAT_ID
from scraper.pools_scraper import scrape_matches
from bot.formatter import (
    format_match_listing,
    format_matches_header,
    format_error,
    format_no_matches,
)
from bot.john import chat_with_john, clear_history, history_length, predict_match_with_john

logger = logging.getLogger(__name__)

# Max matches to predict in one /predict call
MAX_PREDICT = 5

# Rate limiting: minimum seconds between messages per user
_RATE_LIMIT_SECONDS = 3
_last_message_time: dict[int, float] = {}

# Max characters accepted per user message
_MAX_MESSAGE_LENGTH = 2000


def _is_authorized(update: Update) -> bool:
    """Allow only the configured TELEGRAM_CHAT_ID. If not set, allow all (dev mode)."""
    if not TELEGRAM_CHAT_ID:
        return True
    return str(update.effective_chat.id) == str(TELEGRAM_CHAT_ID)


def _is_rate_limited(user_id: int) -> bool:
    """Return True if this user sent a message too recently."""
    now = time.monotonic()
    last = _last_message_time.get(user_id, 0.0)
    if now - last < _RATE_LIMIT_SECONDS:
        return True
    _last_message_time[user_id] = now
    return False


def _safe_error(e: Exception) -> str:
    """Return a generic error string — never expose raw exception details to users."""
    logger.error("Internal error: %s", e)
    return "Something went wrong on my end. Try again in a moment."


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update):
        return
    await update.message.reply_text(
        "👋 *Singapore Pools Football Predictor*\n\n"
        "I scrape live odds from Singapore Pools and combine a Poisson statistical model "
        "with Claude AI to predict match outcomes\\.\n\n"
        "*Talk to John \\(Sports AI Agent\\):*\n"
        "Just send any message \\— John will respond\\.\n"
        "John is a professional football bettor powered by Gemini 2\\.5 Flash\\.\n\n"
        "*Commands:*\n"
        "/matches \\— List upcoming fixtures \\+ odds\n"
        "/predict \\— AI predictions for all matches\n"
        "/reset \\— Clear John's conversation history\n"
        "/help \\— Show this message",
        parse_mode="MarkdownV2",
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_start(update, context)


async def cmd_matches(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List upcoming SP fixtures with odds — no predictions."""
    if not _is_authorized(update):
        return

    msg = await update.message.reply_text("🔄 Fetching matches from Singapore Pools\\.\\.\\.", parse_mode="MarkdownV2")

    try:
        matches = await scrape_matches()
    except Exception as e:
        await msg.edit_text(format_error(_safe_error(e)), parse_mode="MarkdownV2")
        return

    if not matches:
        await msg.edit_text(format_no_matches(), parse_mode="MarkdownV2")
        return

    await msg.edit_text(format_matches_header(len(matches)), parse_mode="MarkdownV2")

    for match in matches:
        await update.message.reply_text(
            format_match_listing(match),
            parse_mode="MarkdownV2",
        )
        await asyncio.sleep(0.3)  # avoid Telegram rate limits


async def cmd_predict(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Generate John's predictions for upcoming matches (Poisson + live search + edge calc)."""
    if not _is_authorized(update):
        return

    chat_id = update.effective_chat.id
    msg = await update.message.reply_text(
        "Fetching matches and handing off to John. This takes ~30s per match while he researches injuries and lineups..."
    )

    try:
        matches = await scrape_matches()
    except Exception as e:
        await msg.edit_text(_safe_error(e))
        return

    if not matches:
        await msg.edit_text("No upcoming matches found on Singapore Pools right now.")
        return

    matches_to_predict = matches[:MAX_PREDICT]
    await msg.edit_text(
        f"John is analyzing {len(matches_to_predict)} match(es). Sending predictions one by one..."
    )

    for match in matches_to_predict:
        try:
            await context.bot.send_chat_action(chat_id=chat_id, action="typing")
            prediction = await predict_match_with_john(match)

            header = (
                f"⚽ {match.home_team} vs {match.away_team}\n"
                f"📅 {match.datetime_sgt}"
                + (f"\n🏆 {match.league}" if match.league else "")
                + "\n\n"
            )

            full_text = header + prediction
            if len(full_text) <= 4096:
                await update.message.reply_text(full_text)
            else:
                for i in range(0, len(full_text), 4096):
                    await update.message.reply_text(full_text[i:i + 4096])
                    await asyncio.sleep(0.3)

        except Exception as e:
            logger.error("Prediction failed for %s: %s", match.display_name, e)
            await update.message.reply_text(f"Could not predict {match.display_name}.")

        await asyncio.sleep(2)  # pace between matches


async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Clear John's conversation history for this chat."""
    if not _is_authorized(update):
        return
    clear_history(update.effective_chat.id)
    await update.message.reply_text("John's memory cleared. Fresh start.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Route all non-command text messages to John."""
    if not _is_authorized(update):
        return

    user_id = update.effective_user.id
    if _is_rate_limited(user_id):
        await update.message.reply_text("Slow down. One message at a time.")
        return

    user_message = update.message.text or ""

    # Enforce input length limit
    if len(user_message) > _MAX_MESSAGE_LENGTH:
        await update.message.reply_text(
            f"Message too long. Keep it under {_MAX_MESSAGE_LENGTH} characters."
        )
        return

    chat_id = update.effective_chat.id
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    reply = await chat_with_john(chat_id, user_message)

    # Telegram message limit is 4096 chars — split if needed
    if len(reply) <= 4096:
        await update.message.reply_text(reply)
    else:
        for i in range(0, len(reply), 4096):
            await update.message.reply_text(reply[i:i + 4096])
            await asyncio.sleep(0.3)


def register_handlers(app: Application) -> None:
    from telegram.ext import CommandHandler, MessageHandler, filters

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("matches", cmd_matches))
    app.add_handler(CommandHandler("predict", cmd_predict))
    app.add_handler(CommandHandler("reset", cmd_reset))
    # Free-text messages go to John — must be registered last
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
