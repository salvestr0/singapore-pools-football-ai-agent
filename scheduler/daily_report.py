"""
APScheduler daily report: fires at 08:00 SGT and pushes predictions to TELEGRAM_CHAT_ID.
"""
from __future__ import annotations

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram import Bot
from telegram.error import TelegramError

from config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    DAILY_REPORT_HOUR,
    DAILY_REPORT_MINUTE,
    SCHEDULER_TIMEZONE,
)
from scraper.pools_scraper import scrape_matches
from bot.john import predict_match_with_john

logger = logging.getLogger(__name__)


async def send_daily_report() -> None:
    """Fetch matches, run John's full analysis on each, push to configured chat."""
    if not TELEGRAM_CHAT_ID:
        logger.warning("TELEGRAM_CHAT_ID not set — skipping daily report")
        return

    bot = Bot(token=TELEGRAM_BOT_TOKEN)

    try:
        matches = await scrape_matches()
    except Exception as e:
        logger.error("Daily report scraper failed: %s", e)
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text="Daily report failed — could not fetch matches. Check scraper logs.",
        )
        return

    if not matches:
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text="No upcoming matches found on Singapore Pools today.",
        )
        return

    await bot.send_message(
        chat_id=TELEGRAM_CHAT_ID,
        text=f"Good morning. John's daily analysis — {len(matches)} match(es) today.",
    )

    for match in matches:
        try:
            prediction = await predict_match_with_john(match)

            header = (
                f"⚽ {match.home_team} vs {match.away_team}\n"
                f"📅 {match.datetime_sgt}"
                + (f"\n🏆 {match.league}" if match.league else "")
                + "\n\n"
            )

            full_text = header + prediction
            # Split if over Telegram's 4096 char limit
            if len(full_text) <= 4096:
                await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=full_text, parse_mode="HTML")
            else:
                for i in range(0, len(full_text), 4096):
                    await bot.send_message(
                        chat_id=TELEGRAM_CHAT_ID, text=full_text[i:i + 4096], parse_mode="HTML"
                    )
                    await asyncio.sleep(0.3)

        except TelegramError as e:
            logger.error("Telegram send error for %s: %s", match.display_name, e)
        except Exception as e:
            logger.error("John prediction error for %s: %s", match.display_name, e)
            try:
                await bot.send_message(
                    chat_id=TELEGRAM_CHAT_ID,
                    text=f"Could not generate prediction for {match.display_name}.",
                )
            except Exception:
                pass

        await asyncio.sleep(3)  # pace between matches — John does web searches per match


def create_scheduler() -> AsyncIOScheduler:
    """Create and configure the APScheduler instance."""
    scheduler = AsyncIOScheduler(timezone=SCHEDULER_TIMEZONE)
    scheduler.add_job(
        send_daily_report,
        trigger=CronTrigger(
            hour=DAILY_REPORT_HOUR,
            minute=DAILY_REPORT_MINUTE,
            timezone=SCHEDULER_TIMEZONE,
        ),
        id="daily_report",
        name="Daily football predictions",
        misfire_grace_time=300,  # allow 5 min late if system was down
    )
    return scheduler
