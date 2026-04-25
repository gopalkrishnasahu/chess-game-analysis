"""
Core analysis engine.
- Computes eval deltas and classifies moves as blunders/mistakes/inaccuracies.
- Aggregates per-game data into an AnalysisReport.
"""
import json
import re
import chess
from collections import defaultdict
from pathlib import Path
from typing import Optional

from .models import GameRecord, MoveRecord, AnalysisReport, OpeningStats, PatternFinding

# ECO code normalisation: merge A02/A03 → "Bird Opening" etc. at grouping time
_ECO_FILE   = Path(__file__).parent / "eco_names.json"
_ECO_NAMES: dict[str, str] = {}
_ECO_RE     = re.compile(r'^[A-E]\d{2}$')


def _normalise_family(raw: str) -> str:
    """If raw is a bare ECO code (e.g. 'A03'), convert to its English name so that
    A02 and A03 both group under 'Bird Opening' rather than as separate rows."""
    global _ECO_NAMES
    if not _ECO_RE.match(raw):
        return raw          # already a readable name like "Sicilian Defense"
    if not _ECO_NAMES:
        try:
            _ECO_NAMES = json.loads(_ECO_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return _ECO_NAMES.get(raw, raw)

# Centipawn loss thresholds (in pawns)
INACCURACY_THRESHOLD = 0.50
MISTAKE_THRESHOLD    = 1.00
BLUNDER_THRESHOLD    = 3.00

# If a position is already this bad before a move, don't count errors
# (avoids inflating blunder counts in already-lost positions)
ALREADY_LOSING_THRESHOLD = 3.00


def compute_eval_deltas(game: GameRecord) -> GameRecord:
    """
    Second-pass: computes eval_before, eval_delta, and error classification
    for every move in the game.
    """
    moves = game.moves
    for i, move in enumerate(moves):
        # eval_before = eval_after of the previous move
        if i > 0:
            move.eval_before = moves[i - 1].eval_after

        if move.eval_before is None or move.eval_after is None:
            continue

        # Delta: how much did the position worsen for the player who just moved?
        # Evals are always from White's perspective.
        if move.color == chess.WHITE:
            delta = move.eval_before - move.eval_after   # positive = White got worse
        else:
            delta = move.eval_after - move.eval_before   # positive = Black got worse (eval rose)

        move.eval_delta = max(0.0, delta)

        # Skip error classification if position was already lost/won before the move
        before_abs = abs(move.eval_before)
        if move.color == chess.WHITE and move.eval_before <= -ALREADY_LOSING_THRESHOLD:
            continue
        if move.color == chess.BLACK and move.eval_before >= ALREADY_LOSING_THRESHOLD:
            continue
        # Also skip if position was already winning (don't penalise "missing a win" as a blunder)
        if before_abs >= ALREADY_LOSING_THRESHOLD and move.eval_delta < BLUNDER_THRESHOLD:
            continue

        move.is_blunder    = move.eval_delta >= BLUNDER_THRESHOLD
        move.is_mistake    = MISTAKE_THRESHOLD    <= move.eval_delta < BLUNDER_THRESHOLD
        move.is_inaccuracy = INACCURACY_THRESHOLD <= move.eval_delta < MISTAKE_THRESHOLD

    return game


def aggregate_games(games: list[GameRecord], username: str) -> AnalysisReport:
    """
    Aggregates all processed GameRecords into an AnalysisReport.
    """
    games_with_evals = [g for g in games if g.has_evals]

    wins   = sum(1 for g in games if g.player_won)
    draws  = sum(1 for g in games if g.player_drew)
    losses = len(games) - wins - draws
    loss_types = _classify_losses(games)

    # Collect all player moves (only from games with evals for error stats)
    player_moves_eval = [
        m for g in games_with_evals
        for m in g.moves
        if m.color == g.player_color
    ]

    total_blunders    = sum(1 for m in player_moves_eval if m.is_blunder)
    total_mistakes    = sum(1 for m in player_moves_eval if m.is_mistake)
    total_inaccuracies = sum(1 for m in player_moves_eval if m.is_inaccuracy)

    n_eval = len(games_with_evals) or 1
    blunders_per_game = total_blunders / n_eval
    mistakes_per_game = total_mistakes / n_eval

    phase_error_rates = _compute_phase_error_rates(player_moves_eval)
    opening_stats     = _compute_opening_stats(games)
    time_stats        = _compute_time_stats(games)
    date_range        = _compute_date_range(games)

    return AnalysisReport(
        username=username,
        games_analyzed=len(games),
        games_with_evals=len(games_with_evals),
        date_range=date_range,
        wins=wins,
        draws=draws,
        losses=losses,
        losses_by_time=loss_types["time"],
        losses_by_collapse=loss_types["collapse"],
        losses_by_resignation_clean=loss_types["clean"],
        total_blunders=total_blunders,
        total_mistakes=total_mistakes,
        total_inaccuracies=total_inaccuracies,
        blunders_per_game=blunders_per_game,
        mistakes_per_game=mistakes_per_game,
        phase_error_rates=phase_error_rates,
        opening_stats=opening_stats,
        time_pressure_games=time_stats["time_pressure_games"],
        time_pressure_blunders=time_stats["time_pressure_blunders"],
        avg_time_opening=time_stats["avg_time_opening"],
        avg_time_middlegame=time_stats["avg_time_middlegame"],
        avg_time_endgame=time_stats["avg_time_endgame"],
        weaknesses=[],   # filled by patterns.py
        strengths=[],    # filled by patterns.py
        recommendations=[],
    )


def _compute_phase_error_rates(player_moves: list[MoveRecord]) -> dict[str, float]:
    """Returns (blunders + mistakes) per 10 moves, grouped by phase."""
    counts: dict[str, dict] = defaultdict(lambda: {"errors": 0, "total": 0})
    for m in player_moves:
        counts[m.phase]["total"] += 1
        if m.is_blunder or m.is_mistake:
            counts[m.phase]["errors"] += 1
    return {
        phase: (v["errors"] / v["total"] * 10) if v["total"] > 0 else 0.0
        for phase, v in counts.items()
    }


def _compute_opening_stats(games: list[GameRecord]) -> dict[str, OpeningStats]:
    stats: dict[str, OpeningStats] = {}

    for game in games:
        family = _normalise_family(game.opening_family or "Unknown")
        if family not in stats:
            stats[family] = OpeningStats(
                family=family,   # already normalised (readable name or ECO→name)
                games_played=0,
                wins=0,
                draws=0,
                losses=0,
                total_blunders=0,
                total_mistakes=0,
                games_with_evals=0,
                eval_sum_at_move10=0.0,
                as_white=0,
                as_black=0,
            )
        s = stats[family]
        s.games_played += 1
        if game.player_won:
            s.wins += 1
        elif game.player_drew:
            s.draws += 1
        else:
            s.losses += 1

        if game.player_color == chess.WHITE:
            s.as_white += 1
        else:
            s.as_black += 1

        # Count player's errors in this game
        for m in game.moves:
            if m.color != game.player_color:
                continue
            if m.is_blunder:
                s.total_blunders += 1
            if m.is_mistake:
                s.total_mistakes += 1

        # Eval at move 10 (ply 19 = after Black's 10th move, ply 20 = after White's 10th+1)
        # We look for the move closest to ply 20 with an eval
        if game.has_evals:
            eval_at10 = _get_eval_near_ply(game.moves, target_ply=20, player_color=game.player_color)
            if eval_at10 is not None:
                s.games_with_evals += 1
                s.eval_sum_at_move10 += eval_at10

    return stats


def _get_eval_near_ply(moves: list[MoveRecord], target_ply: int, player_color: bool) -> Optional[float]:
    """Returns eval at roughly move 10 from the player's perspective."""
    best = None
    for i, m in enumerate(moves):
        ply = i + 1
        if m.eval_after is not None and abs(ply - target_ply) <= 4:
            # Flip sign for Black so positive always means player is doing well
            val = m.eval_after if player_color == chess.WHITE else -m.eval_after
            if best is None or abs(ply - target_ply) < abs(best[0] - target_ply):
                best = (ply, val)
    return best[1] if best else None


def _compute_time_stats(games: list[GameRecord]) -> dict:
    time_pressure_games = 0
    time_pressure_blunders = 0
    time_sums: dict[str, float] = defaultdict(float)
    time_counts: dict[str, int] = defaultdict(int)

    for game in games:
        had_time_pressure = False
        for m in game.moves:
            if m.color != game.player_color:
                continue
            if m.time_spent is not None and m.time_spent >= 0:
                time_sums[m.phase] += m.time_spent
                time_counts[m.phase] += 1
            if m.clock_remaining is not None and m.clock_remaining < 15 and m.is_blunder:
                time_pressure_blunders += 1
                had_time_pressure = True
        if had_time_pressure:
            time_pressure_games += 1

    def avg_or_none(phase: str) -> Optional[float]:
        return time_sums[phase] / time_counts[phase] if time_counts[phase] > 0 else None

    return {
        "time_pressure_games": time_pressure_games,
        "time_pressure_blunders": time_pressure_blunders,
        "avg_time_opening":    avg_or_none("opening"),
        "avg_time_middlegame": avg_or_none("middlegame"),
        "avg_time_endgame":    avg_or_none("endgame"),
    }


def _compute_date_range(games: list[GameRecord]) -> tuple[str, str]:
    dates = [g.date for g in games if g.date and g.date != "????.??.??"]
    if not dates:
        return ("unknown", "unknown")
    dates.sort()
    return (dates[-1], dates[0])  # newest first


def _classify_losses(games: list[GameRecord]) -> dict[str, int]:
    """
    Splits losses into three categories:
      - 'time':     lost_by_time is True
      - 'collapse': NOT time, has eval data, player made >= 2 blunders in that game
      - 'clean':    everything else (no eval data OR <= 1 blunder in loss)
    """
    counts = {"time": 0, "collapse": 0, "clean": 0}
    for g in games:
        if g.player_won or g.player_drew:
            continue
        if g.lost_by_time:
            counts["time"] += 1
        elif g.has_evals and sum(
            1 for m in g.moves if m.color == g.player_color and m.is_blunder
        ) >= 2:
            counts["collapse"] += 1
        else:
            counts["clean"] += 1
    return counts
