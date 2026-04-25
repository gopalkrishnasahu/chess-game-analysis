"""
Optional Stockfish eval enrichment.
Only runs when STOCKFISH_PATH is set in the environment.
Adds [%eval] data to games that don't already have it (e.g. Chess.com games).
"""
import os
from typing import Optional

import chess
import chess.engine


def get_stockfish_path() -> Optional[str]:
    """Returns STOCKFISH_PATH from env if set and file exists, else None."""
    path = os.getenv("STOCKFISH_PATH", "").strip()
    if path and os.path.isfile(path):
        return path
    return None


def enrich_games_with_stockfish(
    game_records,
    pgn_blocks: list[str],
    depth: int = 12,
) -> list:
    """
    For each game without eval data, run Stockfish and fill in eval_after
    on each MoveRecord. Returns the updated game_records list.

    progress_cb: optional callable(message: str) for SSE progress updates.
    depth: Stockfish analysis depth (12 = fast+accurate enough for pattern detection).
    """
    from .models import GameRecord

    path = get_stockfish_path()
    if not path:
        return game_records

    needs_eval = [(i, g) for i, g in enumerate(game_records) if not g.has_evals]
    if not needs_eval:
        return game_records

    try:
        engine = chess.engine.SimpleEngine.popen_uci(path)
        engine.configure({"Threads": 1, "Hash": 32})  # conservative for shared hosting

        for _, game in needs_eval:
            _eval_game(game, engine, depth)

        engine.quit()

    except Exception:
        return game_records

    return game_records


def _eval_game(game, engine: chess.engine.SimpleEngine, depth: int) -> None:
    """Run Stockfish on a single GameRecord, filling eval_after on each move."""
    import chess.pgn
    board = chess.Board()

    for move_rec in game.moves:
        try:
            uci_move = chess.Move.from_uci(move_rec.uci)
            board.push(uci_move)
        except Exception:
            break

        try:
            info = engine.analyse(board, chess.engine.Limit(depth=depth))
            score = info["score"].white()
            if score.is_mate():
                # Use sentinel values matching parser.py convention
                move_rec.eval_after = 100.0 if score.mate() > 0 else -100.0
            else:
                move_rec.eval_after = score.score() / 100.0  # centipawns → pawns
        except Exception:
            break

    # Mark game as having evals if we got at least half the moves evaluated
    evaluated = sum(1 for m in game.moves if m.eval_after is not None)
    if evaluated >= len(game.moves) // 2:
        game.has_evals = True


def _game_id_from_pgn(pgn: str) -> str:
    import re
    m = re.search(r'\[Site "([^"]+)"\]', pgn)
    if m:
        return m.group(1).rsplit("/", 1)[-1]
    return ""
