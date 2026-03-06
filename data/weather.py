"""
Match-day weather forecast via Open-Meteo (https://open-meteo.com).
Free, no API key required.

Fetches daily max precipitation, wind, and weather code for the stadium
location on match day. Used to flag rain/wind conditions that affect
Over/Under and Asian Handicap predictions.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_OPEN_METEO = "https://api.open-meteo.com/v1/forecast"

# Stadium coordinates (latitude, longitude) for major clubs.
# Key is lowercase team name or common alias.
_STADIUMS: dict[str, tuple[float, float]] = {
    # Premier League
    "arsenal": (51.5549, -0.1084),
    "aston villa": (52.5090, -1.8845),
    "brentford": (51.4882, -0.2886),
    "brighton": (50.8617, -0.0836),
    "burnley": (53.7891, -2.2300),
    "chelsea": (51.4816, -0.1909),
    "crystal palace": (51.3983, -0.0855),
    "everton": (53.4388, -2.9661),
    "fulham": (51.4749, -0.2218),
    "ipswich": (52.0545, 1.1446),
    "leicester": (52.6204, -1.1422),
    "liverpool": (53.4308, -2.9608),
    "luton": (51.8837, -0.4316),
    "manchester city": (53.4831, -2.2004),
    "manchester united": (53.4631, -2.2913),
    "newcastle": (54.9756, -1.6217),
    "nottingham forest": (52.9400, -1.1326),
    "sheffield united": (53.3703, -1.4700),
    "southampton": (50.9058, -1.3914),
    "tottenham": (51.6044, -0.0668),
    "west ham": (51.5386, 0.0164),
    "wolverhampton": (52.5901, -2.1302),
    "wolves": (52.5901, -2.1302),
    "bournemouth": (50.7352, -1.8383),
    # La Liga
    "real madrid": (40.4530, -3.6883),
    "barcelona": (41.3809, 2.1228),
    "atletico madrid": (40.4361, -3.5992),
    "sevilla": (37.3840, -5.9705),
    "real betis": (37.3561, -5.9811),
    "real sociedad": (43.3011, -1.9737),
    "villarreal": (39.9441, -0.1038),
    "athletic bilbao": (43.2640, -2.9494),
    "athletic club": (43.2640, -2.9494),
    "valencia": (39.4748, -0.3582),
    "osasuna": (42.7966, -1.6367),
    "getafe": (40.3259, -3.7136),
    "girona": (41.9609, 2.8262),
    "celta vigo": (42.2115, -8.7373),
    "rayo vallecano": (40.3917, -3.6636),
    "real valladolid": (41.6525, -4.7486),
    "mallorca": (39.5899, 2.6627),
    "espanyol": (41.3482, 2.0747),
    "alaves": (42.8487, -2.6731),
    "las palmas": (28.0997, -15.4634),
    "leganes": (40.3428, -3.7651),
    # Bundesliga
    "bayern munich": (48.2188, 11.6247),
    "borussia dortmund": (51.4926, 7.4519),
    "rb leipzig": (51.3459, 12.3483),
    "bayer leverkusen": (51.0384, 7.0022),
    "eintracht frankfurt": (50.0687, 8.6457),
    "sc freiburg": (47.9932, 7.8942),
    "wolfsburg": (52.4322, 10.8031),
    "vfl wolfsburg": (52.4322, 10.8031),
    "borussia monchengladbach": (51.1741, 6.3852),
    "vfb stuttgart": (48.7922, 9.2324),
    "stuttgart": (48.7922, 9.2324),
    "fc augsburg": (48.3231, 10.8861),
    "augsburg": (48.3231, 10.8861),
    "werder bremen": (53.0665, 8.8376),
    "bremen": (53.0665, 8.8376),
    "hoffenheim": (49.2388, 8.8882),
    "mainz": (49.9840, 8.2244),
    "union berlin": (52.4572, 13.5688),
    "heidenheim": (48.6839, 10.1493),
    "holstein kiel": (54.3659, 10.1218),
    "sv darmstadt": (49.8655, 8.6533),
    # Serie A
    "juventus": (45.1096, 7.6412),
    "inter milan": (45.4781, 9.1240),
    "internazionale": (45.4781, 9.1240),
    "ac milan": (45.4781, 9.1240),
    "milan": (45.4781, 9.1240),
    "napoli": (40.8279, 14.1931),
    "as roma": (41.9339, 12.4547),
    "roma": (41.9339, 12.4547),
    "lazio": (41.9339, 12.4547),
    "atalanta": (45.7090, 9.6814),
    "fiorentina": (43.7808, 11.2822),
    "torino": (45.0409, 7.6500),
    "bologna": (44.4920, 11.3097),
    "udinese": (46.0776, 13.1896),
    "cagliari": (39.2007, 9.1307),
    "lecce": (40.3550, 18.1790),
    "monza": (45.5845, 9.2740),
    "empoli": (43.7218, 10.9456),
    "hellas verona": (45.4349, 10.9699),
    "verona": (45.4349, 10.9699),
    "venezia": (45.4654, 12.3195),
    "parma": (44.7921, 10.4577),
    "genoa": (44.4159, 8.9509),
    "como": (45.8056, 9.0836),
    # Ligue 1
    "paris saint-germain": (48.8414, 2.2530),
    "psg": (48.8414, 2.2530),
    "olympique marseille": (43.2699, 5.3959),
    "marseille": (43.2699, 5.3959),
    "olympique lyonnais": (45.7651, 4.9822),
    "lyon": (45.7651, 4.9822),
    "monaco": (43.7272, 7.4155),
    "as monaco": (43.7272, 7.4155),
    "lille": (50.6119, 3.1302),
    "nice": (43.7050, 7.1924),
    "rennes": (48.1072, -1.7125),
    "lens": (50.4333, 2.8166),
    "stade de reims": (49.2469, 4.0263),
    "reims": (49.2469, 4.0263),
    "strasbourg": (48.5600, 7.7557),
    "toulouse": (43.5833, 1.4333),
    "nantes": (47.2564, -1.5251),
    "brest": (48.3895, -4.4880),
    "le havre": (49.4993, 0.1079),
    "montpellier": (43.6225, 3.8145),
    "saint-etienne": (45.4605, 4.3902),
    "angers": (47.4690, -0.5515),
}

# WMO weather interpretation codes → human label
_WMO: dict[int, str] = {
    0: "Clear", 1: "Mainly Clear", 2: "Partly Cloudy", 3: "Overcast",
    45: "Fog", 48: "Icy Fog",
    51: "Light Drizzle", 53: "Drizzle", 55: "Heavy Drizzle",
    61: "Light Rain", 63: "Rain", 65: "Heavy Rain",
    71: "Light Snow", 73: "Snow", 75: "Heavy Snow",
    77: "Snow Grains",
    80: "Rain Showers", 81: "Heavy Showers", 82: "Violent Showers",
    85: "Snow Showers", 86: "Heavy Snow Showers",
    95: "Thunderstorm", 96: "Thunderstorm w/ Hail", 99: "Thunderstorm w/ Heavy Hail",
}


@dataclass
class WeatherForecast:
    condition: str
    temperature_c: float
    wind_speed_kmh: float
    precipitation_mm: float
    impact: str  # Betting-relevant note John uses in analysis


def _get_coords(team_name: str) -> Optional[tuple[float, float]]:
    key = team_name.lower().strip()
    if key in _STADIUMS:
        return _STADIUMS[key]
    # Partial match — e.g. "FC Bayern Munich" → "bayern munich"
    for k, v in _STADIUMS.items():
        if k in key or key in k:
            return v
    return None


def _interpret(condition: str, wind_kmh: float, precip_mm: float) -> str:
    if precip_mm >= 5.0 or "Heavy Rain" in condition or "Violent" in condition:
        return (
            f"Heavy rain forecast ({precip_mm:.1f}mm) — expect disrupted passing, "
            "reduced goal count. Strong Under bias. Check pitch drainage."
        )
    if precip_mm >= 2.0 or "Rain" in condition or "Shower" in condition or "Drizzle" in condition:
        return (
            f"Rain likely ({precip_mm:.1f}mm) — minor Under bias, "
            "may favour direct/physical teams."
        )
    if "Snow" in condition:
        return (
            "Snow forecast — significantly disrupts play. "
            "Strong Under bias. Verify match is not postponed."
        )
    if wind_kmh >= 45:
        return (
            f"Strong wind ({wind_kmh:.0f} km/h) — long-ball and aerial game disrupted. "
            "Under bias, favours compact low-block sides."
        )
    if wind_kmh >= 28:
        return (
            f"Moderate wind ({wind_kmh:.0f} km/h) — minor effect on set pieces and crossing."
        )
    if "Thunderstorm" in condition:
        return "Thunderstorm possible — match may be delayed. Check kick-off status."
    return "Good conditions — no weather adjustment needed."


async def get_match_weather(
    home_team: str,
    match_datetime: Optional[datetime],
) -> Optional[WeatherForecast]:
    """
    Fetch weather forecast for the stadium on match day.
    Uses daily max stats (avoids timezone mismatch with SGT kick-off times).
    Returns None if the team's stadium coordinates are unknown or the API fails.
    """
    coords = _get_coords(home_team)
    if not coords or not match_datetime:
        return None

    lat, lon = coords
    date_str = match_datetime.strftime("%Y-%m-%d")

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                _OPEN_METEO,
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "daily": "weathercode,temperature_2m_max,precipitation_sum,windspeed_10m_max",
                    "start_date": date_str,
                    "end_date": date_str,
                    "timezone": "auto",
                },
                timeout=8.0,
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.error("Open-Meteo failed for %s: %s", home_team, e)
        return None

    daily = data.get("daily", {})
    try:
        code = int(daily["weathercode"][0])
        temp = float(daily["temperature_2m_max"][0])
        precip = float(daily["precipitation_sum"][0])
        wind = float(daily["windspeed_10m_max"][0])
    except (KeyError, IndexError, TypeError, ValueError) as e:
        logger.warning("Open-Meteo parse error for %s: %s", home_team, e)
        return None

    condition = _WMO.get(code, "Unknown")
    return WeatherForecast(
        condition=condition,
        temperature_c=round(temp, 1),
        wind_speed_kmh=round(wind, 1),
        precipitation_mm=round(precip, 1),
        impact=_interpret(condition, wind, precip),
    )
