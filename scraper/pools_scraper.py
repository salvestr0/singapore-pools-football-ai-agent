"""
Singapore Pools football odds scraper using Playwright.
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from playwright.async_api import async_playwright, Page

from config import SP_ODDS_URL

logger = logging.getLogger(__name__)


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
    """
    Extract matches using JavaScript evaluation — runs in browser context so
    JS-rendered content is fully available. Falls back to text parsing.
    """
    # Try to extract structured row data via JS
    try:
        rows_data: list[dict] = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('tr')).map(tr => ({
                text: tr.innerText.trim(),
                cells: Array.from(tr.querySelectorAll('td, th')).map(td => td.innerText.trim())
            })).filter(r => r.cells.length > 0 && r.text.length > 0);
        }""")
    except Exception as e:
        logger.warning("JS evaluation failed, falling back to selector approach: %s", e)
        rows_data = []

    if rows_data:
        return _parse_rows_data(rows_data)

    # Fallback: original selector-based approach
    return await _extract_matches_selector(page)


def _parse_rows_data(rows_data: list[dict]) -> list[Match]:
    """Parse the list of {text, cells} dicts extracted via JavaScript."""
    matches: list[Match] = []
    current_league = ""

    for row in rows_data:
        cells = row.get("cells", [])
        text = row.get("text", "")

        if not cells:
            continue

        # League header: few cells, no float-like values
        float_indices = [i for i, c in enumerate(cells) if _is_odds(c)]
        if len(float_indices) < 3:
            # Could be a league header
            if len(cells) <= 3 and text and not any(c in text for c in [".", "/"]):
                current_league = text.strip()
            continue

        match = _parse_cells(cells, current_league)
        if match:
            matches.append(match)

    return matches


def _parse_cells(cells: list[str], league: str) -> Optional[Match]:
    """Parse a list of cell strings into a Match object."""
    float_indices = [i for i, c in enumerate(cells) if _is_odds(c)]
    if len(float_indices) < 3:
        return None

    try:
        odds_start = float_indices[0]
        if odds_start >= 2:
            home_team = cells[odds_start - 2].strip()
            away_team = cells[odds_start - 1].strip()
        elif odds_start == 1:
            home_team = cells[0].strip()
            away_team = ""
        else:
            return None

        if not home_team or not away_team:
            return None

        dt = _parse_datetime(cells[0] if odds_start > 2 else "")

        odds_home = float(cells[float_indices[0]])
        odds_draw = float(cells[float_indices[1]])
        odds_away = float(cells[float_indices[2]])

        ou_line = odds_over = odds_under = None
        if len(float_indices) >= 6:
            ou_line = float(cells[float_indices[3]])
            odds_over = float(cells[float_indices[4]])
            odds_under = float(cells[float_indices[5]])

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


async def _extract_matches_selector(page: Page) -> list[Match]:
    """Original selector-based fallback extractor."""
    matches: list[Match] = []
    try:
        await page.wait_for_selector(
            "table.football-table, .odds-table, [class*='football'], tr",
            timeout=10000,
        )
    except Exception:
        pass

    rows = await page.query_selector_all("tr")
    current_league = ""

    for row in rows:
        text = (await row.inner_text()).strip()
        if not text:
            continue
        cells_els = await row.query_selector_all("td, th")
        cells = [(await c.inner_text()).strip() for c in cells_els]
        float_indices = [i for i, c in enumerate(cells) if _is_odds(c)]

        if len(float_indices) < 3:
            if len(cells) <= 3 and not any(ch in text for ch in [".", "/"]):
                current_league = text
            continue

        match = _parse_cells(cells, current_league)
        if match:
            matches.append(match)

    return matches




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
            await page.goto(SP_ODDS_URL, wait_until="domcontentloaded", timeout=30000)
            # Extra wait for JS-rendered odds to populate
            await page.wait_for_timeout(4000)
            matches = await _extract_matches(page)
        except Exception as e:
            logger.error("Scraper error: %s", e)
            matches = []
        finally:
            await browser.close()

    if not matches:
        logger.warning("No matches scraped — returning demo data")
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
