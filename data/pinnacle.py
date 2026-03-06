"""
Pinnacle sharp lines via The Odds API (the-odds-api.com).

Used for Closing Line Value (CLV) tracking — compares SP odds against
Pinnacle's efficient market to identify where SP is offering genuine value.

Free tier: 500 requests/month. Each call fetches all events for a sport.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Optional

import httpx

from config import ODDS_API_KEY

logger = logging.getLogger(__name__)

THE_ODDS_API_BASE = "https://api.the-odds-api.com/v4"

# Map league display names → The Odds API sport keys
SPORT_KEY_MAP: dict[str, str] = {
    "english premier league": "soccer_england_premiership",
    "premier league": "soccer_england_premiership",
    "epl": "soccer_england_premiership",
    "championship": "soccer_england_league1",
    "la liga": "soccer_spain_la_liga",
    "spanish la liga": "soccer_spain_la_liga",
    "bundesliga": "soccer_germany_bundesliga",
    "german bundesliga": "soccer_germany_bundesliga",
    "serie a": "soccer_italy_serie_a",
    "italian serie a": "soccer_italy_serie_a",
    "ligue 1": "soccer_france_ligue_one",
    "french ligue 1": "soccer_france_ligue_one",
    "champions league": "soccer_uefa_champs_league",
    "uefa champions league": "soccer_uefa_champs_league",
    "europa league": "soccer_uefa_europa_league",
    "fa cup": "soccer_england_fa_cup",
}


@dataclass
class PinnacleOdds:
    home_odds: float
    draw_odds: float
    away_odds: float
    home_implied: float   # Implied probability %
    draw_implied: float
    away_implied: float
    margin: float         # Pinnacle's overround % — typically 2-3%


@dataclass
class CLVComparison:
    pinnacle: PinnacleOdds
    # SP vs Pinnacle edge: positive = SP is more generous than Pinnacle (value)
    # negative = SP is stingier than Pinnacle (no value)
    edge_home: float = 0.0
    edge_draw: float = 0.0
    edge_away: float = 0.0
    best_selection: str = ""
    best_edge: float = 0.0


def _sim(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def _resolve_sport_key(league_name: str) -> Optional[str]:
    key = league_name.lower().strip()
    if key in SPORT_KEY_MAP:
        return SPORT_KEY_MAP[key]
    for k, v in SPORT_KEY_MAP.items():
        if k in key or key in k:
            return v
    return None


async def _fetch_events(sport_key: str) -> list[dict]:
    if not ODDS_API_KEY:
        return []
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{THE_ODDS_API_BASE}/sports/{sport_key}/odds",
                params={
                    "apiKey": ODDS_API_KEY,
                    "regions": "eu",
                    "markets": "h2h",
                    "bookmakers": "pinnacle",
                    "oddsFormat": "decimal",
                },
                timeout=10.0,
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.error("The Odds API failed for %s: %s", sport_key, e)
        return []


def _extract_pinnacle(event: dict) -> Optional[PinnacleOdds]:
    for bookmaker in event.get("bookmakers", []):
        if bookmaker.get("key") != "pinnacle":
            continue
        for market in bookmaker.get("markets", []):
            if market.get("key") != "h2h":
                continue

            outcomes = {o["name"]: o["price"] for o in market.get("outcomes", [])}
            home_odds = outcomes.get(event.get("home_team", ""))
            away_odds = outcomes.get(event.get("away_team", ""))
            draw_odds = outcomes.get("Draw", 0.0)

            if not home_odds or not away_odds:
                continue

            hi = 1 / home_odds
            di = (1 / draw_odds) if draw_odds else 0.0
            ai = 1 / away_odds
            margin = round((hi + di + ai - 1) * 100, 2)

            return PinnacleOdds(
                home_odds=round(home_odds, 3),
                draw_odds=round(draw_odds, 3),
                away_odds=round(away_odds, 3),
                home_implied=round(hi * 100, 2),
                draw_implied=round(di * 100, 2),
                away_implied=round(ai * 100, 2),
                margin=margin,
            )
    return None


async def get_pinnacle_odds(
    home_team: str,
    away_team: str,
    league_name: str,
) -> Optional[PinnacleOdds]:
    """Fetch Pinnacle 1X2 odds for a match. Returns None if league unsupported."""
    sport_key = _resolve_sport_key(league_name)
    if not sport_key:
        return None

    events = await _fetch_events(sport_key)

    best_score, best_event = 0.0, None
    for event in events:
        score = (
            _sim(home_team, event.get("home_team", ""))
            + _sim(away_team, event.get("away_team", ""))
        ) / 2
        if score > best_score:
            best_score, best_event = score, event

    if not best_event or best_score < 0.5:
        return None

    return _extract_pinnacle(best_event)


def build_clv_comparison(
    pinnacle: PinnacleOdds,
    sp_home: Optional[float],
    sp_draw: Optional[float],
    sp_away: Optional[float],
) -> CLVComparison:
    """
    Compare SP odds against Pinnacle lines.

    Edge formula: (pinnacle_implied - sp_implied) / pinnacle_implied × 100
    Positive edge = SP is paying out MORE than Pinnacle's sharp price = value.
    """
    comp = CLVComparison(pinnacle=pinnacle)
    edges: dict[str, float] = {}

    if sp_home and pinnacle.home_odds:
        sp_impl = 1 / sp_home * 100
        edges["Home Win"] = round(
            (pinnacle.home_implied - sp_impl) / pinnacle.home_implied * 100, 2
        )
    if sp_draw and pinnacle.draw_odds:
        sp_impl = 1 / sp_draw * 100
        edges["Draw"] = round(
            (pinnacle.draw_implied - sp_impl) / pinnacle.draw_implied * 100, 2
        )
    if sp_away and pinnacle.away_odds:
        sp_impl = 1 / sp_away * 100
        edges["Away Win"] = round(
            (pinnacle.away_implied - sp_impl) / pinnacle.away_implied * 100, 2
        )

    comp.edge_home = edges.get("Home Win", 0.0)
    comp.edge_draw = edges.get("Draw", 0.0)
    comp.edge_away = edges.get("Away Win", 0.0)

    if edges:
        comp.best_selection = max(edges, key=edges.get)
        comp.best_edge = edges[comp.best_selection]

    return comp


def format_clv_for_briefing(clv: CLVComparison) -> str:
    pin = clv.pinnacle
    return (
        f"PINNACLE SHARP LINES (CLV reference):\n"
        f"Pinnacle: Home {pin.home_odds} ({pin.home_implied:.1f}%) | "
        f"Draw {pin.draw_odds} ({pin.draw_implied:.1f}%) | "
        f"Away {pin.away_odds} ({pin.away_implied:.1f}%)\n"
        f"Pinnacle margin: {pin.margin:.2f}%\n"
        f"\n"
        f"SP vs Pinnacle: "
        f"Home {clv.edge_home:+.1f}% | "
        f"Draw {clv.edge_draw:+.1f}% | "
        f"Away {clv.edge_away:+.1f}%\n"
        f"Best SP value vs Pinnacle: {clv.best_selection} ({clv.best_edge:+.1f}%)"
    )
