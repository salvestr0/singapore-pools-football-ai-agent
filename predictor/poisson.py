"""
Poisson goal model for football match prediction.

Estimates expected goals (xG) for each team using attack/defense strength ratings,
then builds a probability matrix over possible scorelines.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.stats import poisson

from config import MAX_GOALS
from data.football_api import TeamStats, H2HRecord

# League average goals per game (home and away) — used to normalise strengths
LEAGUE_AVG_HOME = 1.50
LEAGUE_AVG_AWAY = 1.15


@dataclass
class PoissonResult:
    lambda_home: float          # Expected goals for home team
    lambda_away: float          # Expected goals for away team
    p_home_win: float
    p_draw: float
    p_away_win: float
    p_over_2_5: float
    p_under_2_5: float
    expected_total_goals: float
    score_matrix: np.ndarray    # [home_goals x away_goals] probability matrix


def compute_expected_goals(
    home_stats: TeamStats,
    away_stats: TeamStats,
    h2h: H2HRecord,
) -> tuple[float, float]:
    """
    Compute lambda_home and lambda_away using Dixon-Coles-style attack/defense strength.
    """
    # Attack strength = team avg scored / league avg
    home_attack = (home_stats.home_avg_scored or home_stats.avg_scored) / LEAGUE_AVG_HOME
    away_attack = (away_stats.away_avg_scored or away_stats.avg_scored) / LEAGUE_AVG_AWAY

    # Defense strength = team avg conceded / league avg (lower = better defense)
    home_defense = (home_stats.home_avg_conceded or home_stats.avg_conceded) / LEAGUE_AVG_AWAY
    away_defense = (away_stats.away_avg_conceded or away_stats.avg_conceded) / LEAGUE_AVG_HOME

    lambda_home = LEAGUE_AVG_HOME * home_attack * away_defense
    lambda_away = LEAGUE_AVG_AWAY * away_attack * home_defense

    # H2H adjustment: weight in historical average goals if we have enough matches
    if h2h.total_matches >= 3:
        h2h_weight = 0.2
        lambda_home = (1 - h2h_weight) * lambda_home + h2h_weight * h2h.avg_goals_home
        lambda_away = (1 - h2h_weight) * lambda_away + h2h_weight * h2h.avg_goals_away

    # Clamp to reasonable range
    lambda_home = max(0.3, min(lambda_home, 5.0))
    lambda_away = max(0.3, min(lambda_away, 5.0))

    return round(lambda_home, 3), round(lambda_away, 3)


def build_score_matrix(lambda_home: float, lambda_away: float) -> np.ndarray:
    """
    Build an (n+1) x (n+1) matrix where entry [i,j] = P(home scores i, away scores j).
    """
    n = MAX_GOALS
    matrix = np.zeros((n + 1, n + 1))
    for i in range(n + 1):
        for j in range(n + 1):
            matrix[i, j] = poisson.pmf(i, lambda_home) * poisson.pmf(j, lambda_away)
    # Normalise so probabilities sum to 1
    matrix /= matrix.sum()
    return matrix


def derive_probabilities(matrix: np.ndarray, ou_line: float = 2.5) -> dict:
    """Derive 1X2 and O/U probabilities from the score matrix."""
    n = matrix.shape[0] - 1

    p_home_win = float(np.sum(np.tril(matrix, -1)))   # home > away (below diagonal)
    p_draw = float(np.sum(np.diag(matrix)))
    p_away_win = float(np.sum(np.triu(matrix, 1)))    # away > home (above diagonal)

    # Over/Under
    p_over = 0.0
    p_under = 0.0
    for i in range(n + 1):
        for j in range(n + 1):
            total = i + j
            if total > ou_line:
                p_over += matrix[i, j]
            else:
                p_under += matrix[i, j]

    return {
        "p_home_win": round(p_home_win, 4),
        "p_draw": round(p_draw, 4),
        "p_away_win": round(p_away_win, 4),
        "p_over": round(p_over, 4),
        "p_under": round(p_under, 4),
    }


def most_likely_score(matrix: np.ndarray) -> tuple[int, int]:
    """Return (home_goals, away_goals) for the most probable scoreline."""
    idx = np.unravel_index(np.argmax(matrix), matrix.shape)
    return int(idx[0]), int(idx[1])


def run_poisson_model(
    home_stats: TeamStats,
    away_stats: TeamStats,
    h2h: H2HRecord,
    ou_line: float = 2.5,
) -> PoissonResult:
    """Full Poisson pipeline: stats -> xG -> matrix -> probabilities."""
    lambda_home, lambda_away = compute_expected_goals(home_stats, away_stats, h2h)
    matrix = build_score_matrix(lambda_home, lambda_away)
    probs = derive_probabilities(matrix, ou_line)

    expected_total = round(lambda_home + lambda_away, 2)

    return PoissonResult(
        lambda_home=lambda_home,
        lambda_away=lambda_away,
        p_home_win=probs["p_home_win"],
        p_draw=probs["p_draw"],
        p_away_win=probs["p_away_win"],
        p_over_2_5=probs["p_over"],
        p_under_2_5=probs["p_under"],
        expected_total_goals=expected_total,
        score_matrix=matrix,
    )


if __name__ == "__main__":
    from data.football_api import TeamStats, H2HRecord

    home = TeamStats(
        team_name="Manchester City",
        avg_scored=2.4,
        avg_conceded=0.9,
        home_avg_scored=2.6,
        home_avg_conceded=0.8,
        away_avg_scored=2.2,
        away_avg_conceded=1.1,
        form="WWWDW",
        matches_analyzed=10,
    )
    away = TeamStats(
        team_name="Arsenal",
        avg_scored=1.9,
        avg_conceded=1.1,
        home_avg_scored=2.1,
        home_avg_conceded=0.9,
        away_avg_scored=1.7,
        away_avg_conceded=1.3,
        form="WDWWL",
        matches_analyzed=10,
    )
    h2h = H2HRecord(home_wins=4, draws=2, away_wins=2, total_matches=8,
                    avg_goals_home=1.8, avg_goals_away=1.1)

    result = run_poisson_model(home, away, h2h)
    print(f"xG: {result.lambda_home:.2f} - {result.lambda_away:.2f}")
    print(f"P(Home Win): {result.p_home_win:.1%}")
    print(f"P(Draw):     {result.p_draw:.1%}")
    print(f"P(Away Win): {result.p_away_win:.1%}")
    print(f"P(Over 2.5): {result.p_over_2_5:.1%}")
    print(f"P(Under 2.5):{result.p_under_2_5:.1%}")
    print(f"E[Goals]:    {result.expected_total_goals}")
    h, a = most_likely_score(result.score_matrix)
    print(f"Most likely score: {h}-{a}")
