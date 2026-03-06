"""
Claude AI predictor: synthesizes Poisson probabilities + SP odds + team context
into structured match predictions.
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Optional

import anthropic

logger = logging.getLogger(__name__)

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL
from scraper.pools_scraper import Match
from data.football_api import TeamStats, H2HRecord
from predictor.poisson import PoissonResult, most_likely_score


@dataclass
class Prediction:
    match: Match
    # Moneyline
    moneyline_pick: str          # "Home Win", "Draw", "Away Win"
    moneyline_confidence: int    # 0-100
    # Over/Under
    ou_pick: str                 # "Over X.X" or "Under X.X"
    ou_confidence: int
    # Scoreline
    predicted_score: str         # e.g. "2-1"
    # Reasoning
    reasoning: str
    # Model data (for reference)
    poisson: Optional[PoissonResult] = None
    home_stats: Optional[TeamStats] = None
    away_stats: Optional[TeamStats] = None


def _build_prompt(
    match: Match,
    home_stats: TeamStats,
    away_stats: TeamStats,
    h2h: H2HRecord,
    poisson: PoissonResult,
) -> str:
    ml_home, ml_away = most_likely_score(poisson.score_matrix)
    ou_line = match.ou_line or 2.5

    return f"""You are a football betting analyst. Analyze this match and provide a structured prediction.

MATCH: {match.home_team} vs {match.away_team}
League: {match.league}
Date: {match.datetime_sgt}

POISSON MODEL OUTPUT:
- Expected Goals: {poisson.lambda_home:.2f} (Home) - {poisson.lambda_away:.2f} (Away)
- P(Home Win): {poisson.p_home_win:.1%}
- P(Draw): {poisson.p_draw:.1%}
- P(Away Win): {poisson.p_away_win:.1%}
- P(Over {ou_line}): {poisson.p_over_2_5:.1%}
- P(Under {ou_line}): {poisson.p_under_2_5:.1%}
- Most likely scoreline: {ml_home}-{ml_away}

HOME TEAM ({match.home_team}):
- Avg goals scored: {home_stats.avg_scored} | Home avg: {home_stats.home_avg_scored}
- Avg goals conceded: {home_stats.avg_conceded} | Home avg: {home_stats.home_avg_conceded}
- Recent form: {home_stats.form or 'N/A'}
- Matches analyzed: {home_stats.matches_analyzed}

AWAY TEAM ({match.away_team}):
- Avg goals scored: {away_stats.avg_scored} | Away avg: {away_stats.away_avg_scored}
- Avg goals conceded: {away_stats.avg_conceded} | Away avg: {away_stats.away_avg_conceded}
- Recent form: {away_stats.form or 'N/A'}
- Matches analyzed: {away_stats.matches_analyzed}

HEAD-TO-HEAD (last {h2h.total_matches} meetings):
- {match.home_team} wins: {h2h.home_wins} | Draws: {h2h.draws} | {match.away_team} wins: {h2h.away_wins}
- Avg goals per game: {h2h.avg_goals_home:.1f} - {h2h.avg_goals_away:.1f}

SINGAPORE POOLS ODDS:
- Home: {match.odds_home} | Draw: {match.odds_draw} | Away: {match.odds_away}
- Over {ou_line}: {match.odds_over} | Under {ou_line}: {match.odds_under}

Respond ONLY with a JSON object in this exact format:
{{
  "moneyline_pick": "Home Win" | "Draw" | "Away Win",
  "moneyline_confidence": <integer 1-100>,
  "ou_pick": "Over {ou_line}" | "Under {ou_line}",
  "ou_confidence": <integer 1-100>,
  "predicted_score": "<home_goals>-<away_goals>",
  "reasoning": "<2-3 concise sentences explaining the key factors>"
}}"""


def _parse_response(text: str) -> dict:
    """Extract JSON from Claude's response."""
    text = text.strip()
    # Find JSON block
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError(f"No JSON found in response: {text[:200]}")
    return json.loads(text[start:end])


async def predict_match(
    match: Match,
    home_stats: TeamStats,
    away_stats: TeamStats,
    h2h: H2HRecord,
    poisson: PoissonResult,
) -> Prediction:
    """Call Claude to generate a structured prediction for a single match."""
    prompt = _build_prompt(match, home_stats, away_stats, h2h, poisson)

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    try:
        message = await asyncio.to_thread(
            client.messages.create,
            model=CLAUDE_MODEL,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text
        data = _parse_response(raw)
    except Exception as e:
        logger.error("claude_predictor error for %s: %s", match.display_name, e)
        # Fallback: derive from Poisson directly
        data = _fallback_prediction(match, poisson)

    ou_line = match.ou_line or 2.5

    return Prediction(
        match=match,
        moneyline_pick=data.get("moneyline_pick", "Home Win"),
        moneyline_confidence=int(data.get("moneyline_confidence", 50)),
        ou_pick=data.get("ou_pick", f"Over {ou_line}"),
        ou_confidence=int(data.get("ou_confidence", 50)),
        predicted_score=data.get("predicted_score", "1-1"),
        reasoning=data.get("reasoning", "Insufficient data for detailed analysis."),
        poisson=poisson,
        home_stats=home_stats,
        away_stats=away_stats,
    )


def _fallback_prediction(match: Match, poisson: PoissonResult) -> dict:
    """Derive prediction directly from Poisson when Claude is unavailable."""
    ou_line = match.ou_line or 2.5

    probs = {
        "Home Win": poisson.p_home_win,
        "Draw": poisson.p_draw,
        "Away Win": poisson.p_away_win,
    }
    ml_pick = max(probs, key=probs.get)
    ml_conf = round(probs[ml_pick] * 100)

    if poisson.p_over_2_5 > poisson.p_under_2_5:
        ou_pick = f"Over {ou_line}"
        ou_conf = round(poisson.p_over_2_5 * 100)
    else:
        ou_pick = f"Under {ou_line}"
        ou_conf = round(poisson.p_under_2_5 * 100)

    from predictor.poisson import most_likely_score
    h, a = most_likely_score(poisson.score_matrix)

    return {
        "moneyline_pick": ml_pick,
        "moneyline_confidence": ml_conf,
        "ou_pick": ou_pick,
        "ou_confidence": ou_conf,
        "predicted_score": f"{h}-{a}",
        "reasoning": (
            f"Poisson model gives {match.home_team} a {poisson.p_home_win:.1%} win probability "
            f"with {poisson.lambda_home:.1f} expected goals vs {poisson.lambda_away:.1f} for {match.away_team}. "
            f"Total expected goals: {poisson.expected_total_goals}."
        ),
    }
