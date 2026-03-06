"""
Singapore Pools football odds scraper using Playwright.
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from playwright.async_api import async_playwright, Page

from config import SP_ODDS_URL


@dataclass
class Match:
    home_team: str
    away_team: str
    match_datetime: Optional[datetime]
    league: str = ""
    # 1X2 odds
    odds_home: Optional[float] = None
    odds_draw: Optional[float] = None
    odds_away: Optional[float] = None
    # Over/Under
    ou_line: Optional[float] = None
    odds_over: Optional[float] = None
    odds_under: Optional[float] = None

    @property
    def display_name(self) -> str:
        return f"{self.home_team} vs {self.away_team}"

    @property
    def datetime_sgt(self) -> str:
        if self.match_datetime:
            return self.match_datetime.strftime("%d %b %Y, %H:%M SGT")
        return "TBC"


async def _extract_matches(page: Page) -> list[Match]:
    """Parse the SP football odds page structure."""
    matches: list[Match] = []

    # Wait for odds table to load
    try:
        await page.wait_for_selector("table.football-table, .odds-table, [class*='football']", timeout=15000)
    except Exception:
        pass  # Continue and try to extract what we can

    # Try to find match rows — SP uses a table-based layout
    # We'll extract all text and parse it structurally
    rows = await page.query_selector_all("tr")

    current_league = ""
    i = 0
    while i < len(rows):
        row = rows[i]
        text = (await row.inner_text()).strip()

        # Skip empty rows
        if not text:
            i += 1
            continue

        # Detect league header rows (no odds, just league name)
        cells = await row.query_selector_all("td, th")
        if len(cells) <= 2 and text and not any(c in text for c in [".", "/"]):
            current_league = text
            i += 1
            continue

        # Try to extract a match row (has team names + odds)
        match = await _parse_match_row(row, current_league)
        if match:
            matches.append(match)

        i += 1

    return matches


async def _parse_match_row(row, league: str) -> Optional[Match]:
    """Attempt to parse a table row as a match with odds."""
    cells = await row.query_selector_all("td")
    if len(cells) < 5:
        return None

    texts = []
    for cell in cells:
        t = (await cell.inner_text()).strip()
        texts.append(t)

    # SP odds page typically has columns:
    # Date/Time | Home Team | Away Team | Home Odds | Draw Odds | Away Odds | [OU line | Over | Under]
    # Try to detect the pattern by finding float-like values
    float_indices = [i for i, t in enumerate(texts) if _is_odds(t)]

    if len(float_indices) < 3:
        return None

    try:
        # Find team name indices (non-float, non-date cells before odds)
        odds_start = float_indices[0]

        # Team names are likely in the cells just before the first odds
        if odds_start >= 2:
            home_team = texts[odds_start - 2].strip()
            away_team = texts[odds_start - 1].strip()
        elif odds_start == 1:
            # Maybe date is separate row; just use what we have
            home_team = texts[0].strip()
            away_team = ""
        else:
            return None

        if not home_team or not away_team:
            return None

        # Parse datetime from first cells
        dt = _parse_datetime(texts[0] if odds_start > 2 else "")

        # Odds: first three floats are 1X2
        odds_home = float(texts[float_indices[0]])
        odds_draw = float(texts[float_indices[1]])
        odds_away = float(texts[float_indices[2]])

        # O/U: next floats if present
        ou_line = None
        odds_over = None
        odds_under = None
        if len(float_indices) >= 6:
            ou_line = float(texts[float_indices[3]])
            odds_over = float(texts[float_indices[4]])
            odds_under = float(texts[float_indices[5]])

        return Match(
            home_team=home_team,
            away_team=away_team,
            match_datetime=dt,
            league=league,
            odds_home=odds_home,
            odds_draw=odds_draw,
            odds_away=odds_away,
            ou_line=ou_line,
            odds_over=odds_over,
            odds_under=odds_under,
        )
    except (ValueError, IndexError):
        return None


def _is_odds(text: str) -> bool:
    """Check if a string looks like betting odds (float between 1.0 and 50.0)."""
    try:
        v = float(text.replace(",", "."))
        return 1.0 <= v <= 50.0
    except ValueError:
        return False


def _parse_datetime(text: str) -> Optional[datetime]:
    """Try to parse a date/time string from SP format."""
    formats = [
        "%d/%m/%Y %H:%M",
        "%d %b %Y %H:%M",
        "%d/%m/%Y",
        "%d %b %Y",
    ]
    text = text.strip()
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


async def scrape_matches() -> list[Match]:
    """
    Launch headless Chromium, load SP football odds page, return parsed matches.
    Falls back to demo data if scraping fails (e.g., page structure changed).
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/121.0.0.0 Safari/537.36"
            )
        )
        page = await context.new_page()

        try:
            await page.goto(SP_ODDS_URL, wait_until="networkidle", timeout=30000)
            # Give JS-rendered content extra time
            await page.wait_for_timeout(3000)
            matches = await _extract_matches(page)
        except Exception as e:
            print(f"[scraper] Error: {e}")
            matches = []
        finally:
            await browser.close()

    if not matches:
        print("[scraper] No matches found — returning demo data")
        matches = _demo_matches()

    return matches


def _demo_matches() -> list[Match]:
    """Return sample matches for testing when scraping fails."""
    from datetime import timedelta
    now = datetime.now()
    tomorrow = now + timedelta(days=1)
    day_after = now + timedelta(days=2)

    return [
        Match(
            home_team="Manchester City",
            away_team="Arsenal",
            match_datetime=tomorrow.replace(hour=3, minute=0, second=0, microsecond=0),
            league="English Premier League",
            odds_home=1.85,
            odds_draw=3.40,
            odds_away=4.20,
            ou_line=2.5,
            odds_over=1.75,
            odds_under=2.05,
        ),
        Match(
            home_team="Real Madrid",
            away_team="Barcelona",
            match_datetime=tomorrow.replace(hour=23, minute=0, second=0, microsecond=0),
            league="La Liga",
            odds_home=2.10,
            odds_draw=3.20,
            odds_away=3.50,
            ou_line=2.5,
            odds_over=1.80,
            odds_under=1.95,
        ),
        Match(
            home_team="Bayern Munich",
            away_team="Borussia Dortmund",
            match_datetime=day_after.replace(hour=22, minute=30, second=0, microsecond=0),
            league="Bundesliga",
            odds_home=1.65,
            odds_draw=3.80,
            odds_away=5.00,
            ou_line=2.5,
            odds_over=1.60,
            odds_under=2.25,
        ),
    ]


if __name__ == "__main__":
    async def main():
        matches = await scrape_matches()
        print(f"Found {len(matches)} matches:")
        for m in matches:
            print(f"  {m.display_name} | {m.datetime_sgt} | "
                  f"H:{m.odds_home} D:{m.odds_draw} A:{m.odds_away} | "
                  f"O/U {m.ou_line}: {m.odds_over}/{m.odds_under}")

    asyncio.run(main())
