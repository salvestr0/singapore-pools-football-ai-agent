"""
Real-time lineup integration via API-Football (api-sports.io).

Fetches confirmed starting elevens up to ~1h before kick-off.
Falls back gracefully to empty lineups if API key not set or data unavailable.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from typing import Optional

import httpx

from config import API_FOOTBALL_KEY

logger = logging.getLogger(__name__)

BASE_URL = "https://v3.football.api-sports.io"


@dataclass
class PlayerInfo:
    name: str
    position: str  # G, D, M, F
    number: int = 0


@dataclass
class TeamLineup:
    team_name: str
    formation: str = ""
    starting_xi: list[PlayerInfo] = field(default_factory=list)
    substitutes: list[PlayerInfo] = field(default_factory=list)
    confirmed: bool = False  # True when lineup has been officially released


@dataclass
class MatchLineups:
    home: TeamLineup
    away: TeamLineup
    both_confirmed: bool = False
    referee_name: str = ""  # Assigned referee from API-Football fixture data


def _sim(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


async def _get(path: str, params: dict) -> dict:
    if not API_FOOTBALL_KEY:
        return {}
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{BASE_URL}{path}",
                headers={"x-apisports-key": API_FOOTBALL_KEY},
                params=params,
                timeout=10.0,
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.error("API-Football %s failed: %s", path, e)
        return {}


async def _find_fixture(
    home_team: str,
    away_team: str,
    match_date: str,
) -> tuple[Optional[int], str]:
    """Search for a fixture by team names on a given date (± 1 day window).
    Returns (fixture_id, referee_name). referee_name is "" if not available."""
    for date_offset in [0, 1, -1]:
        try:
            target = (
                datetime.strptime(match_date, "%Y-%m-%d") + timedelta(days=date_offset)
            ).strftime("%Y-%m-%d")
        except ValueError:
            target = match_date

        data = await _get("/fixtures", {"date": target})
        for fixture in data.get("response", []):
            api_home = fixture.get("teams", {}).get("home", {}).get("name", "")
            api_away = fixture.get("teams", {}).get("away", {}).get("name", "")
            if _sim(home_team, api_home) >= 0.6 and _sim(away_team, api_away) >= 0.6:
                fixture_id = fixture["fixture"]["id"]
                referee = fixture.get("fixture", {}).get("referee") or ""
                return fixture_id, referee

    return None, ""


def _parse_team_lineup(lineup_data: dict, expected_name: str) -> TeamLineup:
    team_name = lineup_data.get("team", {}).get("name", expected_name)
    formation = lineup_data.get("formation", "")

    starting = [
        PlayerInfo(
            name=p.get("player", {}).get("name", ""),
            position=p.get("player", {}).get("pos", ""),
            number=p.get("player", {}).get("number", 0),
        )
        for p in lineup_data.get("startXI", [])
    ]
    subs = [
        PlayerInfo(
            name=p.get("player", {}).get("name", ""),
            position=p.get("player", {}).get("pos", ""),
            number=p.get("player", {}).get("number", 0),
        )
        for p in lineup_data.get("substitutes", [])
    ]

    return TeamLineup(
        team_name=team_name,
        formation=formation,
        starting_xi=starting,
        substitutes=subs,
        confirmed=len(starting) > 0,
    )


async def get_match_lineups(
    home_team: str,
    away_team: str,
    match_datetime: Optional[datetime] = None,
) -> MatchLineups:
    """
    Fetch confirmed lineups for a match.
    Returns empty (unconfirmed) lineups if not yet available or API key not set.
    """
    empty = MatchLineups(
        home=TeamLineup(team_name=home_team),
        away=TeamLineup(team_name=away_team),
        both_confirmed=False,
    )

    if not API_FOOTBALL_KEY:
        return empty

    match_date = (
        match_datetime.strftime("%Y-%m-%d")
        if match_datetime
        else datetime.now().strftime("%Y-%m-%d")
    )

    fixture_id, referee_name = await _find_fixture(home_team, away_team, match_date)
    if not fixture_id:
        logger.info("No fixture found for %s vs %s on %s", home_team, away_team, match_date)
        return empty

    data = await _get("/fixtures/lineups", {"fixture": fixture_id})
    lineup_list = data.get("response", [])

    if not lineup_list:
        logger.info("Lineups not yet released for fixture %s", fixture_id)
        # Still return the referee even if lineups aren't confirmed
        empty.referee_name = referee_name
        return empty

    result = MatchLineups(
        home=TeamLineup(team_name=home_team),
        away=TeamLineup(team_name=away_team),
        referee_name=referee_name,
    )

    for lineup_data in lineup_list:
        api_name = lineup_data.get("team", {}).get("name", "")
        parsed = _parse_team_lineup(lineup_data, api_name)
        # Assign home vs away by similarity
        if _sim(api_name, home_team) >= _sim(api_name, away_team):
            result.home = parsed
        else:
            result.away = parsed

    result.both_confirmed = result.home.confirmed and result.away.confirmed
    return result


def format_lineup_for_briefing(lineups: MatchLineups) -> str:
    """Format lineup data for John's prediction briefing."""
    if not lineups.both_confirmed:
        return "LINEUPS: Not yet confirmed — search for injury/lineup news."

    lines = ["CONFIRMED LINEUPS:"]
    for team in [lineups.home, lineups.away]:
        if not team.confirmed:
            continue
        lines.append(f"\n{team.team_name} ({team.formation}):")
        by_pos: dict[str, list[str]] = {"G": [], "D": [], "M": [], "F": []}
        for p in team.starting_xi:
            pos = p.position if p.position in by_pos else "M"
            by_pos[pos].append(p.name)
        if by_pos["G"]:
            lines.append(f"  GK:  {', '.join(by_pos['G'])}")
        if by_pos["D"]:
            lines.append(f"  DEF: {', '.join(by_pos['D'])}")
        if by_pos["M"]:
            lines.append(f"  MID: {', '.join(by_pos['M'])}")
        if by_pos["F"]:
            lines.append(f"  FWD: {', '.join(by_pos['F'])}")

    return "\n".join(lines)
