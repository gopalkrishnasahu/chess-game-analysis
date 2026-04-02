"""
Pattern detection: identifies recurring weaknesses and strengths across games.
Operates on a list of processed GameRecords and mutates the AnalysisReport in place.
"""
import chess
from collections import defaultdict

from .models import AnalysisReport, GameRecord, PatternFinding

MIN_GAMES_FOR_OPENING = 4    # minimum games per opening family to report on it
TIME_PRESSURE_SECS    = 15   # seconds threshold for "time pressure"
EARLY_MIDDLE_MOVES    = (15, 25)

MOVE_BUCKETS = [(1, 5), (6, 10), (11, 15), (16, 20), (21, 25), (26, 30), (31, 35), (36, 999)]

_OPENING_TACTICAL_THEMES: dict[str, list[str]] = {
    "Sicilian":       ["back-rank tactics", "knight outposts on d5/f5"],
    "French":         ["pawn chain breaks (e5/f6)", "bishop pair dynamics"],
    "Caro-Kann":      ["piece coordination after ...d5 exchanges", "minority attack"],
    "King's Indian":  ["kingside pawn storms", "piece sacrifices on h6"],
    "Queen's Gambit": ["hanging pawns", "minority attack on queenside"],
    "Ruy Lopez":      ["back-rank tricks", "d5 breakthrough"],
    "Italian":        ["f4-f5 kingside attack", "d4 central break"],
    "English":        ["d5 pawn lever", "knight outpost on e4"],
    "Nimzo-Indian":   ["doubled-pawn exploitation", "bishop pair dynamics"],
    "Dutch":          ["kingside attack with ...g5", "stonewall structure"],
    "Pirc":           ["g4-g5 kingside attacks", "d5 central thrusts"],
    "Modern":         ["g4-g5 kingside attacks", "queenside counterplay"],
}


def detect_patterns(report: AnalysisReport, games: list[GameRecord]) -> AnalysisReport:
    """Populates report.weaknesses, report.strengths, and report.recommendations."""
    games_with_evals = [g for g in games if g.has_evals]

    weaknesses: list[PatternFinding] = []
    strengths:  list[PatternFinding] = []

    weaknesses.extend(_time_pressure_pattern(games_with_evals))
    weaknesses.extend(_early_middlegame_collapse(games_with_evals))
    weaknesses.extend(_endgame_conversion_failures(games_with_evals))
    weaknesses.extend(_opening_struggles(report))
    weaknesses.extend(_piece_handling_issues(games_with_evals))
    weaknesses.extend(_worst_phase_pattern(report))
    weaknesses.extend(_loss_type_pattern(report))
    weaknesses.extend(_blunder_move_range_pattern(games_with_evals, report))

    strengths.extend(_opening_strengths(report))
    strengths.extend(_equal_position_accuracy(games_with_evals))

    report.weaknesses = sorted(weaknesses, key=lambda p: _severity_order(p.severity))
    report.strengths  = sorted(strengths,  key=lambda p: -p.frequency)
    report.recommendations = _build_recommendations(report, games)

    return report


# ----------------------------------------------
# Weakness detectors
# ----------------------------------------------

def _time_pressure_pattern(games: list[GameRecord]) -> list[PatternFinding]:
    hits = [
        (g, m) for g in games for m in g.moves
        if m.color == g.player_color
        and m.is_blunder
        and m.clock_remaining is not None
        and m.clock_remaining < TIME_PRESSURE_SECS
    ]
    if len(hits) < 3:
        return []
    example_ids = _unique_game_ids([g for g, _ in hits], limit=3)
    pct = int(len(hits) / max(1, sum(
        1 for g in games for m in g.moves
        if m.color == g.player_color and m.is_blunder
    )) * 100)
    return [PatternFinding(
        category="time_pressure",
        description=f"{len(hits)} blunders made with <{TIME_PRESSURE_SECS}s remaining ({pct}% of all your blunders)",
        frequency=len(hits),
        severity="critical" if len(hits) >= 8 else "moderate",
        example_game_ids=example_ids,
        recommendation=(
            "Manage your clock earlier. Aim to reach move 25 with at least 40s remaining in 3+2. "
            "In time pressure, play ANY reasonable move within 3 seconds rather than burning "
            "10+ seconds for the perfect move."
        ),
    )]


def _early_middlegame_collapse(games: list[GameRecord]) -> list[PatternFinding]:
    hits = [
        (g, m) for g in games for m in g.moves
        if m.color == g.player_color
        and m.is_blunder
        and EARLY_MIDDLE_MOVES[0] <= m.move_number <= EARLY_MIDDLE_MOVES[1]
    ]
    if len(hits) < 3:
        return []
    example_ids = _unique_game_ids([g for g, _ in hits], limit=3)
    return [PatternFinding(
        category="early_middlegame",
        description=f"{len(hits)} blunders on moves {EARLY_MIDDLE_MOVES[0]}-{EARLY_MIDDLE_MOVES[1]} (the transition out of the opening)",
        frequency=len(hits),
        severity="critical" if len(hits) >= 6 else "moderate",
        example_game_ids=example_ids,
        recommendation=(
            "You're struggling in the early middlegame transition (moves 15-25). "
            "After leaving your opening preparation, pause and ask: 'What is my opponent threatening?' "
            "before each move. Tactical puzzles focused on move 15-25 positions will help."
        ),
    )]


def _endgame_conversion_failures(games: list[GameRecord]) -> list[PatternFinding]:
    """Games where the player had a winning position in the endgame but didn't win."""
    failures = []
    for game in games:
        endgame_moves = [m for m in game.moves if m.phase == "endgame"]
        if not endgame_moves:
            continue
        # Find the eval for the player at the start of the endgame
        first_endgame_eval = next(
            (m.eval_after for m in endgame_moves if m.eval_after is not None), None
        )
        if first_endgame_eval is None:
            continue
        # Player's eval at endgame start (positive = player is winning)
        if game.player_color == chess.WHITE:
            player_eval = first_endgame_eval
        else:
            player_eval = -first_endgame_eval

        if player_eval >= 1.5 and not game.player_won:
            failures.append(game)

    if len(failures) < 2:
        return []
    example_ids = _unique_game_ids(failures, limit=3)
    return [PatternFinding(
        category="endgame_conversion",
        description=(
            f"Failed to convert {len(failures)} winning endgame positions "
            f"(had >=+1.5 eval entering endgame but didn't win)"
        ),
        frequency=len(failures),
        severity="critical" if len(failures) >= 5 else "moderate",
        example_game_ids=example_ids,
        recommendation=(
            "Your endgame technique needs work. Focus on: (1) Rook + King vs King, "
            "(2) Queen + King vs King, (3) King and pawn endgames. "
            "Practice on Lichess Endgame Practice or work through Silman's Endgame Course Part 1."
        ),
    )]


def _opening_struggles(report: AnalysisReport) -> list[PatternFinding]:
    patterns = []
    for family, s in report.opening_stats.items():
        if s.games_played < MIN_GAMES_FOR_OPENING:
            continue
        if not (s.win_rate < 0.40 and s.avg_blunders >= 1.8):
            continue
        desc = (
            f"{family}: {s.wins}W-{s.draws}D-{s.losses}L "
            f"({int(s.win_rate*100)}% win rate, {s.avg_blunders:.1f} blunders/game)"
        )
        themes = _lookup_opening_themes(family)
        if themes:
            tactic_hint = (
                f" In particular, study tactical motifs common to this opening: "
                f"{', '.join(themes[:2])}."
            )
        else:
            tactic_hint = ""
        patterns.append(PatternFinding(
            category="opening_struggle",
            description=desc,
            frequency=s.games_played,
            severity="moderate",
            example_game_ids=[],
            recommendation=(
                f"You're struggling in the {family}. Pick one solid variation and study it "
                f"to move 15 rather than playing it by feel.{tactic_hint}"
            ),
        ))
    return patterns


def _piece_handling_issues(games: list[GameRecord]) -> list[PatternFinding]:
    """Checks if a particular piece type appears disproportionately in blunders."""
    piece_blunders: dict[str, int]  = defaultdict(int)
    piece_total:    dict[str, int]  = defaultdict(int)

    for game in games:
        for m in game.moves:
            if m.color != game.player_color:
                continue
            piece = _piece_from_san(m.san)
            piece_total[piece] += 1
            if m.is_blunder:
                piece_blunders[piece] += 1

    patterns = []
    total_moves = sum(piece_total.values()) or 1
    total_blunders = sum(piece_blunders.values()) or 1

    for piece, blunder_count in piece_blunders.items():
        if blunder_count < 3:
            continue
        move_share   = piece_total[piece] / total_moves
        blunder_share = blunder_count / total_blunders
        # Only flag if blunder share is at least 2x the move share
        if blunder_share >= move_share * 2.0 and blunder_share >= 0.20:
            piece_name = _piece_name(piece)
            patterns.append(PatternFinding(
                category="piece_handling",
                description=(
                    f"{piece_name} moves account for {int(blunder_share*100)}% of your blunders "
                    f"but only {int(move_share*100)}% of your moves"
                ),
                frequency=blunder_count,
                severity="moderate",
                example_game_ids=[],
                recommendation=(
                    f"Be more careful when moving your {piece_name.lower()}. "
                    f"Before each {piece_name.lower()} move, verify: can it be captured? "
                    f"Does it leave another piece hanging?"
                ),
            ))
    return patterns


def _worst_phase_pattern(report: AnalysisReport) -> list[PatternFinding]:
    rates = report.phase_error_rates
    if not rates:
        return []
    worst_phase = max(rates, key=rates.get)
    worst_rate  = rates[worst_phase]
    # Only flag if clearly worse than the best phase
    best_rate = min(rates.values())
    if worst_rate < 2.0 or worst_rate < best_rate * 1.5:
        return []
    return [PatternFinding(
        category="phase_weakness",
        description=(
            f"Your {worst_phase} is your weakest phase: "
            f"{worst_rate:.1f} serious errors per 10 moves "
            f"(vs {best_rate:.1f} in your best phase)"
        ),
        frequency=int(worst_rate * 10),
        severity="moderate",
        example_game_ids=[],
        recommendation=_phase_recommendation(worst_phase),
    )]


# ----------------------------------------------
# Strength detectors
# ----------------------------------------------

def _opening_strengths(report: AnalysisReport) -> list[PatternFinding]:
    patterns = []
    for family, s in report.opening_stats.items():
        if s.games_played < MIN_GAMES_FOR_OPENING:
            continue
        if s.win_rate >= 0.58 and s.avg_blunders <= 1.2:
            desc = (
                f"{family}: {s.wins}W-{s.draws}D-{s.losses}L "
                f"({int(s.win_rate*100)}% win rate, {s.avg_blunders:.1f} blunders/game)"
            )
            patterns.append(PatternFinding(
                category="opening_strength",
                description=desc,
                frequency=s.games_played,
                severity="minor",
                example_game_ids=[],
                recommendation=f"Keep playing the {family} -- it's working well for you.",
            ))
    return patterns


def _equal_position_accuracy(games: list[GameRecord]) -> list[PatternFinding]:
    """Checks how well the player plays from near-equal positions (eval between -0.5 and +0.5)."""
    total_equal_moves = 0
    errors_in_equal   = 0

    for game in games:
        for m in game.moves:
            if m.color != game.player_color or m.eval_before is None:
                continue
            player_eval = m.eval_before if game.player_color == chess.WHITE else -m.eval_before
            if -0.5 <= player_eval <= 0.5:
                total_equal_moves += 1
                if m.is_blunder or m.is_mistake:
                    errors_in_equal += 1

    if total_equal_moves < 20:
        return []

    error_rate = errors_in_equal / total_equal_moves
    if error_rate <= 0.04:   # < 4% error rate in equal positions = strength
        return [PatternFinding(
            category="equal_position_accuracy",
            description=(
                f"Good accuracy in equal positions: only {int(error_rate*100)}% serious error rate "
                f"across {total_equal_moves} moves from balanced positions"
            ),
            frequency=total_equal_moves,
            severity="minor",
            example_game_ids=[],
            recommendation="You handle equal positions well -- keep playing solidly and look to outplay opponents slowly.",
        )]
    return []


# ----------------------------------------------
# Recommendations
# ----------------------------------------------

def _build_recommendations(report: AnalysisReport, games: list[GameRecord]) -> list[str]:
    recs = []

    # Priority 1: biggest weakness patterns
    for p in report.weaknesses:
        if p.severity == "critical":
            recs.append(p.recommendation)

    # Priority 2: moderate weaknesses
    for p in report.weaknesses:
        if p.severity == "moderate" and p.recommendation not in recs:
            recs.append(p.recommendation)

    # Priority 3: general advice based on stats
    if report.blunders_per_game >= 2.5:
        recs.append(
            "Before every move, use the 'blunder check': scan for your opponent's threats "
            "and verify your piece isn't hanging after you move."
        )

    if report.games_with_evals < report.games_analyzed * 0.4:
        recs.append(
            f"Only {report.games_with_evals}/{report.games_analyzed} games had eval data. "
            "After games, request computer analysis on Lichess to get more eval data for future runs."
        )

    return recs[:8]  # cap at 8 recommendations


# ----------------------------------------------
# New weakness detectors (Phase 2)
# ----------------------------------------------

def _loss_type_pattern(report: AnalysisReport) -> list[PatternFinding]:
    """Flags if a large share of losses came from time forfeit or tactical collapse."""
    if report.losses < 3:
        return []

    results = []
    time_pct     = report.losses_by_time / report.losses
    collapse_pct = report.losses_by_collapse / report.losses

    if time_pct >= 0.40:
        results.append(PatternFinding(
            category="loss_by_time_forfeit",
            description=(
                f"{report.losses_by_time} of your {report.losses} losses "
                f"({int(time_pct * 100)}%) were time forfeits"
            ),
            frequency=report.losses_by_time,
            severity="critical" if time_pct >= 0.60 else "moderate",
            example_game_ids=[],
            recommendation=(
                "Most of your losses are on the clock, not the board. "
                "Practise making 'good enough' moves quickly: in 3+2, aim to keep at least "
                "20s per move through move 30. Pre-move on forced recaptures to bank extra time."
            ),
        ))

    if collapse_pct >= 0.50:
        results.append(PatternFinding(
            category="loss_by_tactical_collapse",
            description=(
                f"{report.losses_by_collapse} of your {report.losses} losses "
                f"({int(collapse_pct * 100)}%) involved 2+ blunders — "
                f"tactical collapse rather than being outplayed positionally"
            ),
            frequency=report.losses_by_collapse,
            severity="critical" if collapse_pct >= 0.70 else "moderate",
            example_game_ids=[],
            recommendation=(
                "You're losing games you could hold — tactical collapses with multiple blunders "
                "per game. Before every move, ask: 'What can my opponent do?' Solve 10 defensive "
                "tactics puzzles daily (Lichess Puzzles, filter by Fork, Pin, Skewer)."
            ),
        ))

    return results


def _blunder_move_range_pattern(
    games: list[GameRecord],
    report: AnalysisReport,
) -> list[PatternFinding]:
    """
    Finds the 5-move window with the highest blunder concentration.
    Only fires if the worst bucket is OUTSIDE moves 16-25
    (those are already covered by _early_middlegame_collapse).
    Requires >= 10 total blunders for a reliable signal.
    """
    bucket_counts: dict[tuple[int, int], int] = {b: 0 for b in MOVE_BUCKETS}

    for game in games:
        for m in game.moves:
            if m.color != game.player_color or not m.is_blunder:
                continue
            for lo, hi in MOVE_BUCKETS:
                if lo <= m.move_number <= hi:
                    bucket_counts[(lo, hi)] += 1
                    break

    total_blunders = sum(bucket_counts.values())
    if total_blunders < 10:
        return []

    worst_bucket = max(bucket_counts, key=bucket_counts.get)
    worst_count  = bucket_counts[worst_bucket]
    worst_pct    = worst_count / total_blunders

    lo, hi = worst_bucket
    # Skip if already covered by _early_middlegame_collapse
    if (lo, hi) in {(16, 20), (21, 25)}:
        return []

    if worst_pct < 0.30:
        return []

    # Write back to report for potential future display use
    hi_label = hi if hi != 999 else "+"
    report.blunder_spike_range = f"moves {lo}-{hi_label}"
    report.blunder_spike_count = worst_count
    report.blunder_spike_pct   = worst_pct

    return [PatternFinding(
        category="blunder_spike_range",
        description=(
            f"{worst_count} blunders ({int(worst_pct * 100)}% of all your blunders) "
            f"cluster at moves {lo}-{hi_label} — a {_phase_hint_for_range(lo)} transition"
        ),
        frequency=worst_count,
        severity="critical" if worst_pct >= 0.45 else "moderate",
        example_game_ids=[],
        recommendation=_range_recommendation(lo, hi),
    )]


def _lookup_opening_themes(family: str) -> list[str]:
    """Exact match then prefix match against _OPENING_TACTICAL_THEMES."""
    if family in _OPENING_TACTICAL_THEMES:
        return _OPENING_TACTICAL_THEMES[family]
    for key, themes in _OPENING_TACTICAL_THEMES.items():
        if family.startswith(key):
            return themes
    return []


def _phase_hint_for_range(move_start: int) -> str:
    if move_start <= 10:
        return "late-opening"
    if move_start <= 15:
        return "opening-to-middlegame"
    if move_start <= 25:
        return "early-middlegame"
    if move_start <= 35:
        return "middlegame-to-endgame"
    return "deep endgame"


def _range_recommendation(lo: int, hi: int) -> str:
    hi_label = hi if hi != 999 else "+"
    if lo <= 10:
        return (
            f"You're blundering most at moves {lo}-{hi_label}, still in the opening. "
            "Review your opening preparation to move 12 in your main lines and ensure "
            "you know the key threats in each position before leaving theory."
        )
    if lo <= 15:
        return (
            f"Moves {lo}-{hi_label} are your danger zone — the opening-to-middlegame transition. "
            "Pause after your last known theory move and ask: 'What is the plan from here?' "
            "before committing to a move."
        )
    if lo <= 30:
        return (
            f"You're struggling at moves {lo}-{hi_label}, likely a middlegame-to-endgame "
            "transition. Practise recognising when to trade pieces and simplify, "
            "and solve tactical puzzles from complex middlegame positions."
        )
    return (
        f"Your blunders concentrate at moves {lo}-{hi_label} — deep endgame errors. "
        "Study rook endgames and pawn endgame technique on Lichess Endgame Practice."
    )


# ----------------------------------------------
# Helpers
# ----------------------------------------------

def _unique_game_ids(games: list[GameRecord], limit: int = 3) -> list[str]:
    seen = set()
    result = []
    for g in games:
        if g.game_id not in seen:
            seen.add(g.game_id)
            result.append(g.game_id)
        if len(result) >= limit:
            break
    return result


def _piece_from_san(san: str) -> str:
    """Returns the piece letter from SAN ('N', 'B', 'R', 'Q', 'K', or 'P' for pawns)."""
    if not san or san[0] not in "NBRQK":
        return "P"
    return san[0]


def _piece_name(letter: str) -> str:
    return {"N": "Knight", "B": "Bishop", "R": "Rook", "Q": "Queen", "K": "King", "P": "Pawn"}.get(letter, letter)


def _severity_order(severity: str) -> int:
    return {"critical": 0, "moderate": 1, "minor": 2}.get(severity, 3)


def _phase_recommendation(phase: str) -> str:
    if phase == "endgame":
        return (
            "Study endgame fundamentals: king activity, pawn promotion, rook endgames. "
            "Do 10 endgame practice sessions on Lichess."
        )
    if phase == "middlegame":
        return (
            "Improve your middlegame by solving 10-15 tactical puzzles daily on Lichess. "
            "Also study basic positional concepts: piece activity, pawn structure, open files."
        )
    return (
        "Review your opening repertoire. Learn the key ideas of your chosen openings "
        "to move 12-15, not just the first few moves."
    )
