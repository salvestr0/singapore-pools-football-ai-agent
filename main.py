"""
Entry point: starts the Telegram bot + APScheduler daily report.
"""
from __future__ import annotations

import asyncio
import logging
import sys

from telegram.ext import Application

from config import TELEGRAM_BOT_TOKEN, ANTHROPIC_API_KEY, GEMINI_API_KEY
from bot.handlers import register_handlers
from scheduler.daily_report import create_scheduler
from data.tracker import init_db

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def _check_config() -> None:
    errors = []
    if not TELEGRAM_BOT_TOKEN:
        errors.append("TELEGRAM_BOT_TOKEN is not set")
    if not ANTHROPIC_API_KEY:
        errors.append("ANTHROPIC_API_KEY is not set")
    if not GEMINI_API_KEY:
        errors.append("GEMINI_API_KEY is not set (needed for John, the AI Agent)")
    if errors:
        for e in errors:
            logger.error("Config error: %s", e)
        sys.exit(1)


async def post_init(app: Application) -> None:
    scheduler = create_scheduler()
    scheduler.start()
    app.bot_data["scheduler"] = scheduler
    logger.info("Scheduler started — daily report at 08:00 SGT")


async def post_shutdown(app: Application) -> None:
    scheduler = app.bot_data.get("scheduler")
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")


def main() -> None:
    _check_config()
    init_db()

    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    register_handlers(app)

    logger.info("Starting Telegram bot (polling)...")
    app.run_polling(allowed_updates=["message"])


if __name__ == "__main__":
    main()
