"""
football-data.org REST client for team stats and head-to-head records.
Free tier: 10 requests/minute.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Optional

import httpx

from config import FOOTBALL_DATA_API_KEY, FOOTBALL_DATA_BASE_URL


@dataclass
class TeamStats:
    team_name: str
    avg_scored: float = 0.0       # average goals scored per game
    avg_conceded: float = 0.0     # average goals conceded per game
    home_avg_scored: float = 0.0
    home_avg_conceded: float = 0.0
    away_avg_scored: float = 0.0
    away_avg_conceded: float = 0.0
    form: str = ""                # last 5: e.g. "WWDLW"
    matches_analyzed: int = 0


@dataclass
class H2HRecord:
    home_wins: int = 0
    draws: int = 0
    away_wins: int = 0
    total_matches: int = 0
    avg_goals_home: float = 0.0
    avg_goals_away: float = 0.0


async def _get(client: httpx.AsyncClient, path: str, params: dict | None = None) -> dict:
    headers = {"X-Auth-Token": FOOTBALL_DATA_API_KEY}
    resp = await client.get(
        f"{FOOTBALL_DATA_BASE_URL}{path}",
        headers=headers,
        params=params or {},
        timeout=10.0,
    )
    resp.raise_for_status()
    return resp.json()


async def search_team_id(team_name: str) -> Optional[int]:
    """Search for a team by name and return its football-data.org ID."""
    if not FOOTBALL_DATA_API_KEY:
        return None

    async with httpx.AsyncClient() as client:
        try:
            data = await _get(client, "/teams", {"name": team_name, "limit": 1})
            teams = data.get("teams", [])
            if teams:
                return teams[0]["id"]
        except Exception as e:
            print(f"[football_api] search_team_id error for '{team_name}': {e}")
    return None


async def get_team_stats(team_id: int, is_home: bool) -> TeamStats:
    """Fetch last 10 matches for a team and compute attack/defense averages."""
    if not FOOTBALL_DATA_API_KEY or not team_id:
        return TeamStats(team_name=str(team_id))

    async with httpx.AsyncClient() as client:
        try:
            data = await _get(client, f"/teams/{team_id}/matches", {
                "status": "FINISHED",
                "limit": 10,
            })
        except Exception as e:
            print(f"[football_api] get_team_stats error for team {team_id}: {e}")
            return TeamStats(team_name=str(team_id))

    matches = data.get("matches", [])
    if not matches:
        return TeamStats(team_name=str(team_id))

    team_name = ""
    scored_all, conceded_all = [], []
    scored_home, conceded_home = [], []
    scored_away, conceded_away = [], []
    form_chars = []

    for m in matches:
        home_id = m.get("homeTeam", {}).get("id")
        away_id = m.get("awayTeam", {}).get("id")
        score = m.get("score", {}).get("fullTime", {})
        home_goals = score.get("home")
        away_goals = score.get("away")

        if home_goals is None or away_goals is None:
            continue

        if home_id == team_id:
            team_name = m.get("homeTeam", {}).get("name", str(team_id))
            g_scored, g_conceded = home_goals, away_goals
            scored_home.append(g_scored)
            conceded_home.append(g_conceded)
            if g_scored > g_conceded:
                form_chars.append("W")
            elif g_scored == g_conceded:
                form_chars.append("D")
            else:
                form_chars.append("L")
        else:
            team_name = m.get("awayTeam", {}).get("name", str(team_id))
            g_scored, g_conceded = away_goals, home_goals
            scored_away.append(g_scored)
            conceded_away.append(g_conceded)
            if g_scored > g_conceded:
                form_chars.append("W")
            elif g_scored == g_conceded:
                form_chars.append("D")
            else:
                form_chars.append("L")

        scored_all.append(g_scored)
        conceded_all.append(g_conceded)

    def avg(lst):
        return round(sum(lst) / len(lst), 2) if lst else 0.0

    return TeamStats(
        team_name=team_name,
        avg_scored=avg(scored_all),
        avg_conceded=avg(conceded_all),
        home_avg_scored=avg(scored_home),
        home_avg_conceded=avg(conceded_home),
        away_avg_scored=avg(scored_away),
        away_avg_conceded=avg(conceded_away),
        form="".join(form_chars[-5:]),
        matches_analyzed=len(scored_all),
    )


async def get_h2h(team1_id: int, team2_id: int) -> H2HRecord:
    """Fetch head-to-head record between two teams."""
    if not FOOTBALL_DATA_API_KEY or not team1_id or not team2_id:
        return H2HRecord()

    async with httpx.AsyncClient() as client:
        try:
            data = await _get(client, f"/teams/{team1_id}/matches", {
                "status": "FINISHED",
                "limit": 20,
            })
        except Exception as e:
            print(f"[football_api] get_h2h error: {e}")
            return H2HRecord()

    matches = data.get("matches", [])
    h2h_matches = [
        m for m in matches
        if m.get("homeTeam", {}).get("id") in (team1_id, team2_id)
        and m.get("awayTeam", {}).get("id") in (team1_id, team2_id)
    ]

    if not h2h_matches:
        return H2HRecord()

    home_wins = draws = away_wins = 0
    goals_team1 = []
    goals_team2 = []

    for m in h2h_matches:
        score = m.get("score", {}).get("fullTime", {})
        hg = score.get("home", 0) or 0
        ag = score.get("away", 0) or 0
        home_id = m.get("homeTeam", {}).get("id")

        if home_id == team1_id:
            goals_team1.append(hg)
            goals_team2.append(ag)
        else:
            goals_team1.append(ag)
            goals_team2.append(hg)

        winner = m.get("score", {}).get("winner")
        if winner == "HOME_TEAM":
            if home_id == team1_id:
                home_wins += 1
            else:
                away_wins += 1
        elif winner == "AWAY_TEAM":
            if home_id == team1_id:
                away_wins += 1
            else:
                home_wins += 1
        else:
            draws += 1

    def avg(lst):
        return round(sum(lst) / len(lst), 2) if lst else 0.0

    return H2HRecord(
        home_wins=home_wins,
        draws=draws,
        away_wins=away_wins,
        total_matches=len(h2h_matches),
        avg_goals_home=avg(goals_team1),
        avg_goals_away=avg(goals_team2),
    )


async def get_match_context(home_team: str, away_team: str) -> tuple[TeamStats, TeamStats, H2HRecord]:
    """
    Fetch team stats and H2H for a match.
    Returns (home_stats, away_stats, h2h).
    Uses dummy data if API key not set.
    """
    if not FOOTBALL_DATA_API_KEY:
        return _dummy_stats(home_team, True), _dummy_stats(away_team, False), H2HRecord()

    home_id, away_id = await asyncio.gather(
        search_team_id(home_team),
        search_team_id(away_team),
    )

    # Rate limit: small delay between API calls
    await asyncio.sleep(1)

    async def _wrap(value):
        return value

    home_stats, away_stats, h2h = await asyncio.gather(
        get_team_stats(home_id, is_home=True) if home_id else _wrap(_dummy_stats(home_team, True)),
        get_team_stats(away_id, is_home=False) if away_id else _wrap(_dummy_stats(away_team, False)),
        get_h2h(home_id, away_id) if home_id and away_id else _wrap(H2HRecord()),
    )

    return home_stats, away_stats, h2h


def _dummy_stats(team_name: str, is_home: bool) -> TeamStats:
    """Fallback stats when API unavailable — uses league average values."""
    return TeamStats(
        team_name=team_name,
        avg_scored=1.4,
        avg_conceded=1.2,
        home_avg_scored=1.7 if is_home else 1.1,
        home_avg_conceded=1.0 if is_home else 1.4,
        away_avg_scored=1.1,
        away_avg_conceded=1.4,
        form="WDWLW",
        matches_analyzed=10,
    )
