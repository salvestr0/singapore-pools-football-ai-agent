"""
Parlay correlation analysis.

Flags pairs of picks that share correlated risk factors so that John
can disclose the dependency to the bettor before they combine them
into a parlay/accumulator.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scraper.pools_scraper import Match


@dataclass
class CorrelationWarning:
    match1: str
    match2: str
    reason: str
    severity: str  # "HIGH" | "MEDIUM" | "LOW"


def analyze_parlay_correlation(matches: list) -> list[CorrelationWarning]:
    """
    Check a list of Match objects for correlated risk between pairs.
    Returns a (possibly empty) list of warnings.
    """
    warnings: list[CorrelationWarning] = []
    for i in range(len(matches)):
        for j in range(i + 1, len(matches)):
            warnings.extend(_check_pair(matches[i], matches[j]))
    return warnings


def _check_pair(a, b) -> list[CorrelationWarning]:
    warnings = []

    league_a = (a.league or "").lower().strip()
    league_b = (b.league or "").lower().strip()
    teams_a = {a.home_team.lower(), a.away_team.lower()}
    teams_b = {b.home_team.lower(), b.away_team.lower()}

    # ── HIGH: shared team — form/injury affects both bets ────────────────────
    shared = teams_a & teams_b
    if shared:
        team_name = next(iter(shared)).title()
        warnings.append(CorrelationWarning(
            match1=a.display_name,
            match2=b.display_name,
            reason=(
                f"{team_name} plays in both matches — injury, fatigue, or "
                "rotation in one directly affects your probability estimate in the other."
            ),
            severity="HIGH",
        ))

    # ── MEDIUM: same league, same matchday ───────────────────────────────────
    if league_a and league_a == league_b:
        same_date = (
            a.match_datetime and b.match_datetime
            and a.match_datetime.date() == b.match_datetime.date()
        )
        if same_date:
            warnings.append(CorrelationWarning(
                match1=a.display_name,
                match2=b.display_name,
                reason=(
                    f"Same league ({a.league}), same matchday — shared factors: "
                    "weather, referee pool, fixture congestion, table-position pressure."
                ),
                severity="MEDIUM",
            ))
        else:
            # Same league different dates — weaker correlation
            warnings.append(CorrelationWarning(
                match1=a.display_name,
                match2=b.display_name,
                reason=(
                    f"Same league ({a.league}) — systemic factors (referee tendencies, "
                    "league scoring tempo) create mild correlation."
                ),
                severity="LOW",
            ))

    return warnings


def format_correlation_warnings(warnings: list[CorrelationWarning]) -> str:
    """Format warnings as a concise block for John's briefing or Telegram."""
    if not warnings:
        return ""
    icon_map = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}
    lines = ["PARLAY CORRELATION WARNINGS:"]
    for w in warnings:
        icon = icon_map.get(w.severity, "⚪")
        lines.append(
            f"{icon} [{w.severity}] {w.match1} \u2194 {w.match2}\n"
            f"   {w.reason}"
        )
    return "\n".join(lines)
