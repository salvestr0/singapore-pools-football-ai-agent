"""
Format predictions and match listings as Telegram messages (MarkdownV2).
"""
from __future__ import annotations

import re

from scraper.pools_scraper import Match
from predictor.claude_predictor import Prediction


def _esc(text: str) -> str:
    """Escape special characters for Telegram MarkdownV2."""
    special = r"\_*[]()~`>#+-=|{}.!"
    return re.sub(f"([{re.escape(special)}])", r"\\\1", str(text))


def format_match_listing(match: Match) -> str:
    """Plain match info without prediction — for /matches command."""
    lines = [
        f"⚽ *{_esc(match.home_team)} vs {_esc(match.away_team)}*",
        f"📅 {_esc(match.datetime_sgt)}",
    ]
    if match.league:
        lines.append(f"🏆 {_esc(match.league)}")

    odds_parts = []
    if match.odds_home:
        odds_parts.append(f"Home {_esc(match.odds_home)}")
    if match.odds_draw:
        odds_parts.append(f"Draw {_esc(match.odds_draw)}")
    if match.odds_away:
        odds_parts.append(f"Away {_esc(match.odds_away)}")

    if odds_parts:
        lines.append(f"🎰 {' \\| '.join(odds_parts)}")

    if match.ou_line and match.odds_over and match.odds_under:
        lines.append(
            f"📈 O/U {_esc(match.ou_line)}: "
            f"Over {_esc(match.odds_over)} \\| Under {_esc(match.odds_under)}"
        )

    return "\n".join(lines)


def format_prediction(pred: Prediction) -> str:
    """Full prediction message — for /predict command."""
    match = pred.match

    lines = [
        f"⚽ *{_esc(match.home_team)} vs {_esc(match.away_team)}*",
        f"📅 {_esc(match.datetime_sgt)}",
    ]
    if match.league:
        lines.append(f"🏆 {_esc(match.league)}")

    lines.append("")
    lines.append("📊 *Prediction:*")
    lines.append(f"  Moneyline: *{_esc(pred.moneyline_pick)}* \\({pred.moneyline_confidence}% confidence\\)")
    lines.append(f"  Over/Under: *{_esc(pred.ou_pick)}* \\({pred.ou_confidence}% confidence\\)")
    lines.append(f"  Predicted Score: *{_esc(pred.predicted_score)}*")

    if pred.poisson:
        lines.append("")
        lines.append("🔢 *Model Probabilities:*")
        lines.append(
            f"  Home {_esc(f'{pred.poisson.p_home_win:.0%}')} \\| "
            f"Draw {_esc(f'{pred.poisson.p_draw:.0%}')} \\| "
            f"Away {_esc(f'{pred.poisson.p_away_win:.0%}')}"
        )
        lines.append(
            f"  xG: {_esc(f'{pred.poisson.lambda_home:.2f}')} \\- "
            f"{_esc(f'{pred.poisson.lambda_away:.2f}')}"
        )

    lines.append("")
    lines.append(f"💡 *Reasoning:* {_esc(pred.reasoning)}")

    odds_parts = []
    if match.odds_home:
        odds_parts.append(f"Home {_esc(match.odds_home)}")
    if match.odds_draw:
        odds_parts.append(f"Draw {_esc(match.odds_draw)}")
    if match.odds_away:
        odds_parts.append(f"Away {_esc(match.odds_away)}")
    if match.ou_line and match.odds_over and match.odds_under:
        odds_parts.append(
            f"O{_esc(match.ou_line)}: {_esc(match.odds_over)}/{_esc(match.odds_under)}"
        )

    if odds_parts:
        lines.append("")
        lines.append(f"🎰 *SP Odds:* {' \\| '.join(odds_parts)}")

    return "\n".join(lines)


def format_matches_header(count: int) -> str:
    return f"📋 *Upcoming Singapore Pools Matches* \\({count} found\\)\n"


def format_predictions_header(count: int) -> str:
    return f"🤖 *AI Predictions* \\({count} matches\\)\n"


def format_separator() -> str:
    return "\n" + "\\-" * 30 + "\n"


def format_error(message: str) -> str:
    return f"❌ {_esc(message)}"


def format_no_matches() -> str:
    return "😔 No upcoming matches found on Singapore Pools right now\\. Try again later\\."
