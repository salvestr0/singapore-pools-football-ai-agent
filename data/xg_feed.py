"""
Understat xG data feed.

Scrapes team-level xG and xGA per game for the top 6 European leagues.
Uses Understat's public JSON endpoints embedded in their league pages.

Covered leagues: EPL, La Liga, Bundesliga, Serie A, Ligue 1, RFPL
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# Map display league names → Understat league IDs
LEAGUE_MAP: dict[str, str] = {
    "english premier league": "EPL",
    "premier league": "EPL",
    "epl": "EPL",
    "la liga": "La_liga",
    "spanish la liga": "La_liga",
    "laliga": "La_liga",
    "bundesliga": "Bundesliga",
    "german bundesliga": "Bundesliga",
    "serie a": "Serie_A",
    "italian serie a": "Serie_A",
    "ligue 1": "Ligue_1",
    "french ligue 1": "Ligue_1",
    "russian premier league": "RFPL",
    "rfpl": "RFPL",
}

CURRENT_SEASON = 2024

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/121.0.0.0 Safari/537.36"
)


@dataclass
class XGStats:
    team_name: str
    league: str
    season: int
    xg_per_game: float      # Expected goals scored per match
    xga_per_game: float     # Expected goals conceded per match
    xg_diff: float          # xG − xGA per game (positive = net attacking)
    matches_played: int
    source: str = "Understat"


def _sim(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def _resolve_league(league_name: str) -> Optional[str]:
    key = league_name.lower().strip()
    if key in LEAGUE_MAP:
        return LEAGUE_MAP[key]
    for k, v in LEAGUE_MAP.items():
        if k in key or key in k:
            return v
    return None


def _decode_understat_json(raw: str) -> dict:
    """
    Understat embeds JSON as JSON.parse('...') with unicode/hex escapes.
    Decode chain: unicode_escape → latin-1 → utf-8 handles multi-byte chars.
    """
    decoded = raw.encode("utf-8").decode("unicode_escape").encode("latin-1").decode("utf-8")
    return json.loads(decoded)


async def _fetch_league_teams(league_id: str, season: int) -> list[dict]:
    """Scrape team xG data from Understat league page."""
    url = f"https://understat.com/league/{league_id}/{season}"
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": _UA}, timeout=15.0)
            resp.raise_for_status()
    except Exception as e:
        logger.error("Understat fetch failed for %s/%s: %s", league_id, season, e)
        return []

    match = re.search(
        r"var\s+teamsData\s*=\s*JSON\.parse\('(.+?)'\)\s*;",
        resp.text,
        re.DOTALL,
    )
    if not match:
        logger.warning("teamsData not found on Understat page %s/%s", league_id, season)
        return []

    try:
        teams_dict = _decode_understat_json(match.group(1))
        return list(teams_dict.values())
    except Exception as e:
        logger.error("Understat JSON parse error for %s/%s: %s", league_id, season, e)
        return []


async def get_team_xg(
    team_name: str,
    league_name: str,
    season: int = CURRENT_SEASON,
) -> Optional[XGStats]:
    """
    Return xG and xGA per game for a team from Understat.
    Returns None if the league is not covered or team not found.
    """
    league_id = _resolve_league(league_name)
    if not league_id:
        return None  # League not in Understat's coverage

    teams = await _fetch_league_teams(league_id, season)
    if not teams:
        return None

    # Find closest team name match
    best_score, best_team = 0.0, None
    for team in teams:
        score = _sim(team_name, team.get("title", ""))
        if score > best_score:
            best_score, best_team = score, team

    if not best_team or best_score < 0.5:
        logger.info(
            "No Understat match for '%s' in %s (best %.2f)", team_name, league_id, best_score
        )
        return None

    try:
        history = best_team.get("history", [])
        if not history:
            return None

        total_xg = sum(float(m.get("xG", 0)) for m in history)
        total_xga = sum(float(m.get("xGA", 0)) for m in history)
        matches = len(history)

        xg_pg = round(total_xg / matches, 3)
        xga_pg = round(total_xga / matches, 3)

        return XGStats(
            team_name=best_team.get("title", team_name),
            league=league_id,
            season=season,
            xg_per_game=xg_pg,
            xga_per_game=xga_pg,
            xg_diff=round(xg_pg - xga_pg, 3),
            matches_played=matches,
        )
    except Exception as e:
        logger.error("Understat data error for %s: %s", team_name, e)
        return None
