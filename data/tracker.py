"""
SQLite-backed bet tracker.

Stores every prediction John makes, odds snapshots for movement detection,
and actual match results so ROI and calibration can be measured over time.

DB file: bets.db at project root (git-ignored).
"""
from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Generator, Optional

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent / "bets.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS predictions (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id         TEXT UNIQUE,
    home_team        TEXT,
    away_team        TEXT,
    league           TEXT,
    match_datetime   TEXT,
    predicted_outcome TEXT,
    confidence       REAL,
    kelly_stake      REAL,
    poisson_home_prob REAL,
    poisson_draw_prob REAL,
    poisson_away_prob REAL,
    sp_home_odds     REAL,
    sp_draw_odds     REAL,
    sp_away_odds     REAL,
    pinnacle_home_odds REAL,
    pinnacle_draw_odds REAL,
    pinnacle_away_odds REAL,
    best_edge        REAL,
    actual_result    TEXT,
    home_goals       INTEGER,
    away_goals       INTEGER,
    created_at       TEXT,
    resolved_at      TEXT
);

CREATE TABLE IF NOT EXISTS odds_snapshots (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id       TEXT,
    home_team      TEXT,
    away_team      TEXT,
    league         TEXT,
    match_datetime TEXT,
    sp_home_odds   REAL,
    sp_draw_odds   REAL,
    sp_away_odds   REAL,
    ou_line        REAL,
    odds_over      REAL,
    odds_under     REAL,
    snapshot_at    TEXT
);
"""


@dataclass
class ROISummary:
    total_bets: int
    resolved_bets: int
    wins: int
    win_rate: float           # fraction 0-1
    roi_percent: float
    avg_edge: float
    total_staked_kelly: float # sum of kelly_stake values
    best_win: Optional[str]
    worst_loss: Optional[str]


@contextmanager
def _conn() -> Generator[sqlite3.Connection, None, None]:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def init_db() -> None:
    """Create tables on first run. Safe to call every startup."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _conn() as con:
        con.executescript(_SCHEMA)
    logger.info("Tracker DB ready at %s", DB_PATH)


def make_match_id(home: str, away: str, dt_str: str) -> str:
    """Stable, unique ID for a match — used as the primary key."""
    date = dt_str[:10] if dt_str else "unknown"
    h = home.lower().replace(" ", "_")
    a = away.lower().replace(" ", "_")
    return f"{h}_vs_{a}_{date}"


# ── Predictions ──────────────────────────────────────────────────────────────

def save_prediction(
    home_team: str,
    away_team: str,
    league: str,
    match_datetime: str,
    predicted_outcome: str,
    confidence: float,
    kelly_stake: float,
    poisson_home_prob: float = 0.0,
    poisson_draw_prob: float = 0.0,
    poisson_away_prob: float = 0.0,
    sp_home_odds: Optional[float] = None,
    sp_draw_odds: Optional[float] = None,
    sp_away_odds: Optional[float] = None,
    pinnacle_home_odds: Optional[float] = None,
    pinnacle_draw_odds: Optional[float] = None,
    pinnacle_away_odds: Optional[float] = None,
    best_edge: float = 0.0,
) -> str:
    """Insert a prediction. Silently ignores duplicates (INSERT OR IGNORE).
    Returns the match_id."""
    match_id = make_match_id(home_team, away_team, match_datetime)
    now = datetime.now().isoformat()
    try:
        with _conn() as con:
            con.execute(
                """
                INSERT OR IGNORE INTO predictions (
                    match_id, home_team, away_team, league, match_datetime,
                    predicted_outcome, confidence, kelly_stake,
                    poisson_home_prob, poisson_draw_prob, poisson_away_prob,
                    sp_home_odds, sp_draw_odds, sp_away_odds,
                    pinnacle_home_odds, pinnacle_draw_odds, pinnacle_away_odds,
                    best_edge, created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    match_id, home_team, away_team, league, match_datetime,
                    predicted_outcome, confidence, kelly_stake,
                    poisson_home_prob, poisson_draw_prob, poisson_away_prob,
                    sp_home_odds, sp_draw_odds, sp_away_odds,
                    pinnacle_home_odds, pinnacle_draw_odds, pinnacle_away_odds,
                    best_edge, now,
                ),
            )
    except Exception as e:
        logger.error("save_prediction failed: %s", e)
    return match_id


def resolve_prediction(
    match_id: str,
    actual_result: str,
    home_goals: int,
    away_goals: int,
) -> bool:
    """Update a prediction with its actual result. Returns True if a row was updated."""
    now = datetime.now().isoformat()
    try:
        with _conn() as con:
            cur = con.execute(
                """
                UPDATE predictions
                SET actual_result=?, home_goals=?, away_goals=?, resolved_at=?
                WHERE match_id=? AND actual_result IS NULL
                """,
                (actual_result, home_goals, away_goals, now, match_id),
            )
            return cur.rowcount > 0
    except Exception as e:
        logger.error("resolve_prediction failed: %s", e)
        return False


def get_pending_predictions() -> list[dict]:
    """Return predictions that have no actual result yet."""
    try:
        with _conn() as con:
            rows = con.execute(
                "SELECT * FROM predictions WHERE actual_result IS NULL ORDER BY match_datetime ASC"
            ).fetchall()
            return [dict(r) for r in rows]
    except Exception as e:
        logger.error("get_pending_predictions failed: %s", e)
        return []


def get_recent_predictions(limit: int = 10) -> list[dict]:
    """Return the most recent N predictions (resolved or pending)."""
    try:
        with _conn() as con:
            rows = con.execute(
                "SELECT * FROM predictions ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]
    except Exception as e:
        logger.error("get_recent_predictions failed: %s", e)
        return []


def get_roi_summary() -> ROISummary:
    """Compute ROI, win rate, and calibration stats from all resolved predictions."""
    try:
        with _conn() as con:
            rows = con.execute("SELECT * FROM predictions").fetchall()
    except Exception as e:
        logger.error("get_roi_summary failed: %s", e)
        return ROISummary(0, 0, 0, 0.0, 0.0, 0.0, 0.0, None, None)

    total = len(rows)
    resolved = [r for r in rows if r["actual_result"] is not None]

    wins = 0
    total_staked = 0.0
    total_return = 0.0
    total_edge = 0.0
    best_win: Optional[str] = None
    worst_loss: Optional[str] = None

    for r in resolved:
        pred = r["predicted_outcome"]
        actual = r["actual_result"]
        stake = r["kelly_stake"] or 0.0
        total_staked += stake
        total_edge += r["best_edge"] or 0.0

        # Get odds for the predicted outcome
        if pred == "Home Win":
            odds = r["sp_home_odds"] or 0.0
        elif pred == "Draw":
            odds = r["sp_draw_odds"] or 0.0
        else:
            odds = r["sp_away_odds"] or 0.0

        label = f"{r['home_team']} vs {r['away_team']} ({(r['match_datetime'] or '')[:10]})"

        if pred == actual:
            wins += 1
            net = stake * (odds - 1)
            total_return += net
            best_win = label
        else:
            total_return -= stake
            worst_loss = label

    n = len(resolved)
    return ROISummary(
        total_bets=total,
        resolved_bets=n,
        wins=wins,
        win_rate=wins / n if n else 0.0,
        roi_percent=(total_return / total_staked * 100) if total_staked > 0 else 0.0,
        avg_edge=total_edge / n if n else 0.0,
        total_staked_kelly=total_staked,
        best_win=best_win,
        worst_loss=worst_loss,
    )


# ── Odds snapshots ────────────────────────────────────────────────────────────

def save_odds_snapshot(
    home_team: str,
    away_team: str,
    league: str,
    match_datetime: str,
    sp_home_odds: Optional[float],
    sp_draw_odds: Optional[float],
    sp_away_odds: Optional[float],
    ou_line: Optional[float] = None,
    odds_over: Optional[float] = None,
    odds_under: Optional[float] = None,
) -> None:
    match_id = make_match_id(home_team, away_team, match_datetime)
    now = datetime.now().isoformat()
    try:
        with _conn() as con:
            con.execute(
                """
                INSERT INTO odds_snapshots (
                    match_id, home_team, away_team, league, match_datetime,
                    sp_home_odds, sp_draw_odds, sp_away_odds,
                    ou_line, odds_over, odds_under, snapshot_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    match_id, home_team, away_team, league, match_datetime,
                    sp_home_odds, sp_draw_odds, sp_away_odds,
                    ou_line, odds_over, odds_under, now,
                ),
            )
    except Exception as e:
        logger.error("save_odds_snapshot failed: %s", e)


def get_last_snapshot(match_id: str) -> Optional[dict]:
    """Get the most recent odds snapshot for a match."""
    try:
        with _conn() as con:
            row = con.execute(
                "SELECT * FROM odds_snapshots WHERE match_id=? ORDER BY snapshot_at DESC LIMIT 1",
                (match_id,),
            ).fetchone()
            return dict(row) if row else None
    except Exception as e:
        logger.error("get_last_snapshot failed: %s", e)
        return None
