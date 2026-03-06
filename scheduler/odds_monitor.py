"""
Odds movement monitor.

Polls Singapore Pools every ODDS_MONITOR_INTERVAL_MINUTES minutes,
compares current odds against the last stored snapshot, and pushes
a Telegram alert when any line moves by more than ODDS_MOVE_THRESHOLD %.

Snapshots are stored in the SQLite tracker DB so history survives restarts.
"""
from __future__ import annotations

import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from telegram import Bot
from telegram.error import TelegramError

from config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    ODDS_MOVE_THRESHOLD,
    ODDS_MONITOR_INTERVAL_MINUTES,
    SCHEDULER_TIMEZONE,
)
from data.tracker import make_match_id, save_odds_snapshot, get_last_snapshot
from scraper.pools_scraper import scrape_matches

logger = logging.getLogger(__name__)


def _pct_change(old: float, new: float) -> float:
    """Absolute percentage change between two odds values."""
    if old == 0:
        return 0.0
    return abs(new - old) / old * 100.0


def _direction(old: float, new: float) -> str:
    return "⬆️" if new > old else "⬇️"


def _build_alert(match, changes: list[str]) -> str:
    lines = [
        "⚡ <b>ODDS MOVEMENT ALERT</b>",
        f"⚽ {match.home_team} vs {match.away_team}",
        f"📅 {match.datetime_sgt}",
        "",
    ]
    lines.extend(changes)
    lines.append("")
    lines.append(
        f"Current: H <b>{match.odds_home}</b> | "
        f"D <b>{match.odds_draw}</b> | "
        f"A <b>{match.odds_away}</b>"
    )
    if match.ou_line:
        lines.append(
            f"O/U {match.ou_line}: Over {match.odds_over} | Under {match.odds_under}"
        )
    return "\n".join(lines)


async def check_odds_movements() -> None:
    """
    Scrape SP, compare against last snapshot, send alerts for significant moves.
    Always saves a fresh snapshot so next run has a baseline.
    """
    if not TELEGRAM_CHAT_ID:
        logger.debug("TELEGRAM_CHAT_ID not set — skipping odds monitor")
        return

    try:
        matches = await scrape_matches()
    except Exception as e:
        logger.error("Odds monitor: scrape failed: %s", e)
        return

    bot = Bot(token=TELEGRAM_BOT_TOKEN)

    for match in matches:
        dt_str = (
            match.match_datetime.isoformat()
            if match.match_datetime
            else datetime.now().isoformat()
        )
        match_id = make_match_id(match.home_team, match.away_team, dt_str)

        # Read the PREVIOUS snapshot before overwriting it
        last = get_last_snapshot(match_id)

        # Save current state so next run has a baseline to compare against
        save_odds_snapshot(
            home_team=match.home_team,
            away_team=match.away_team,
            league=match.league,
            match_datetime=dt_str,
            sp_home_odds=match.odds_home,
            sp_draw_odds=match.odds_draw,
            sp_away_odds=match.odds_away,
            ou_line=match.ou_line,
            odds_over=match.odds_over,
            odds_under=match.odds_under,
        )

        if not last:
            continue  # First snapshot — nothing to compare against yet

        # Check 1X2 movements
        changes: list[str] = []
        pairs = [
            ("Home Win", "sp_home_odds", match.odds_home),
            ("Draw",     "sp_draw_odds", match.odds_draw),
            ("Away Win", "sp_away_odds", match.odds_away),
        ]
        for label, key, new_val in pairs:
            old_val = last.get(key)
            if old_val and new_val:
                old_f = float(old_val)
                pct = _pct_change(old_f, new_val)
                if pct >= ODDS_MOVE_THRESHOLD:
                    changes.append(
                        f"{_direction(old_f, new_val)} <b>{label}</b>: "
                        f"{old_f:.2f} → {new_val:.2f} "
                        f"({pct:.1f}% move)"
                    )

        if changes:
            alert_text = _build_alert(match, changes)
            try:
                await bot.send_message(
                    chat_id=TELEGRAM_CHAT_ID,
                    text=alert_text,
                    parse_mode="HTML",
                )
                logger.info(
                    "Odds alert sent: %s vs %s — %d change(s)",
                    match.home_team, match.away_team, len(changes),
                )
            except TelegramError as e:
                logger.error("Telegram alert failed for %s: %s", match.display_name, e)


def register_odds_monitor(scheduler: AsyncIOScheduler) -> None:
    """Add the odds monitoring job to an existing AsyncIOScheduler."""
    scheduler.add_job(
        check_odds_movements,
        trigger=IntervalTrigger(
            minutes=ODDS_MONITOR_INTERVAL_MINUTES,
            timezone=SCHEDULER_TIMEZONE,
        ),
        id="odds_monitor",
        name="SP odds movement monitor",
        replace_existing=True,
        misfire_grace_time=60,
    )
    logger.info(
        "Odds monitor registered — polling SP every %d min",
        ODDS_MONITOR_INTERVAL_MINUTES,
    )
