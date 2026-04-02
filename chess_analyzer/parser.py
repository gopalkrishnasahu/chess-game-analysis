"""
Parses individual PGN strings into GameRecord objects.
Extracts Lichess eval ([%eval]) and clock ([%clk]) annotations from move comments.
"""
import io
import re
from typing import Optional

import chess
import chess.pgn

from .models import GameRecord, MoveRecord

EVAL_RE = re.compile(r'\[%eval\s+([+-]?(?:\d+\.?\d*|#[+-]?\d+))\]')
CLK_RE  = re.compile(r'\[%clk\s+(\d+):(\d+):(\d+)\]')

MATE_SENTINEL = 100.0   # ±100 pawns used for mate scores


def parse_game(pgn_string: str, username: str) -> Optional[GameRecord]:
    """
    Parses one PGN string into a GameRecord.
    Returns None if the PGN is malformed or has no moves.
    """
    game = chess.pgn.read_game(io.StringIO(pgn_string))
    if game is None or game.next() is None:
        return None

    headers = game.headers
    white = headers.get("White", "")
    black = headers.get("Black", "")
    result = headers.get("Result", "*")
    termination = headers.get("Termination", "Normal")

    player_color = _determine_color(white, black, username)
    opening_name = headers.get("Opening", "")
    opening_family = opening_name.split(":")[0].strip() if opening_name else headers.get("ECO", "Unknown")

    moves = _extract_moves(game, player_color)
    has_evals = any(m.eval_after is not None for m in moves)

    player_won = (
        (player_color == chess.WHITE and result == "1-0") or
        (player_color == chess.BLACK and result == "0-1")
    )
    player_drew = result == "1/2-1/2"

    return GameRecord(
        game_id=_extract_game_id(headers),
        white=white,
        black=black,
        result=result,
        player_color=player_color,
        player_won=player_won,
        player_drew=player_drew,
        termination=termination,
        eco=headers.get("ECO", ""),
        opening_name=opening_name,
        opening_family=opening_family,
        time_control=headers.get("TimeControl", ""),
        date=headers.get("UTCDate", headers.get("Date", "")),
        moves=moves,
        has_evals=has_evals,
        lost_by_time=(not player_won and not player_drew and "Time forfeit" in termination),
    )


def _determine_color(white: str, black: str, username: str) -> bool:
    """Returns chess.WHITE (True) or chess.BLACK (False). Case-insensitive match."""
    username_lower = username.lower()
    if white.lower() == username_lower:
        return chess.WHITE
    if black.lower() == username_lower:
        return chess.BLACK
    # Fallback: should never happen for games fetched for this username
    import warnings
    warnings.warn(
        f"Could not match username '{username}' to either player "
        f"(White='{white}', Black='{black}'). Defaulting to White — results for this game may be wrong."
    )
    return chess.WHITE


def _extract_game_id(headers: chess.pgn.Headers) -> str:
    site = headers.get("Site", "")
    return site.rsplit("/", 1)[-1] if "/" in site else site


def _extract_moves(game: chess.pgn.Game, player_color: bool) -> list[MoveRecord]:
    records: list[MoveRecord] = []
    board = game.board()
    node = game
    prev_clock: Optional[float] = None

    while node.next() is not None:
        node = node.next()
        comment = node.comment or ""
        color_to_move = board.turn  # color that just played this move

        eval_after = _parse_eval(comment)
        clock_remaining = _parse_clock(comment)
        time_spent = None
        if prev_clock is not None and clock_remaining is not None:
            time_spent = max(0.0, prev_clock - clock_remaining)

        # ply // 2 + 1 gives full-move number (ply 0=White move 1, ply 1=Black move 1, ...)
        move_number = (node.ply() - 1) // 2 + 1
        phase = _determine_phase(board, node.ply())

        records.append(MoveRecord(
            move_number=move_number,
            color=color_to_move,
            san=node.san(),
            uci=node.move.uci(),
            eval_before=None,       # filled in analyzer.py
            eval_after=eval_after,
            eval_delta=None,        # filled in analyzer.py
            clock_remaining=clock_remaining,
            time_spent=time_spent,
            phase=phase,
        ))

        board.push(node.move)
        prev_clock = clock_remaining

    return records


def _parse_eval(comment: str) -> Optional[float]:
    m = EVAL_RE.search(comment)
    if not m:
        return None
    raw = m.group(1)
    if "#" in raw:
        return MATE_SENTINEL if not raw.startswith("#-") else -MATE_SENTINEL
    return float(raw)


def _parse_clock(comment: str) -> Optional[float]:
    m = CLK_RE.search(comment)
    if not m:
        return None
    h, mn, s = int(m.group(1)), int(m.group(2)), int(m.group(3))
    return h * 3600 + mn * 60 + s


def _determine_phase(board: chess.Board, ply: int) -> str:
    """
    Opening: first 20 plies (moves 1-10 for each side).
    Endgame: total non-pawn, non-king pieces <= 6.
    Middlegame: everything else.
    """
    if ply <= 20:
        return "opening"
    total_minors = sum(
        len(board.pieces(pt, c))
        for pt in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN)
        for c in (chess.WHITE, chess.BLACK)
    )
    if total_minors <= 6:
        return "endgame"
    return "middlegame"
