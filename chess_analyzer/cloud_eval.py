"""
Lichess Cloud Eval enrichment — zero installation required.

Uses the Lichess public cloud-eval API (free, no auth):
  GET https://lichess.org/api/cloud-eval?fen=<FEN>

Coverage: positions that have been analysed on Lichess (Stockfish depth 20-30).
Common openings + mainline middlegames: ~70-80% hit rate.
Very unusual positions: may return nothing (gracefully skipped).

Rate limit: ~1 req/s is safe. We batch with a small delay between requests.
"""
import time
from typing import Optional

import chess
import chess.pgn
import requests

CLOUD_EVAL_URL = "https://lichess.org/api/cloud-eval"
HEADERS = {"Accept": "application/json"}
REQUEST_DELAY = 0.12   # ~8 req/s — well within Lichess limits
MATE_SENTINEL  = 100.0


def enrich_games_with_cloud_eval(
    game_records: list,
    depth: int = 20,
    max_moves_per_game: int = 30,
):
    """
    Generator — yields progress strings, modifies game_records in-place.

    Usage in a Flask SSE generator:
        for msg in enrich_games_with_cloud_eval(game_records):
            yield _msg(msg)

    max_moves_per_game: only evaluate first N moves per game (opening +
    early middlegame have the best cloud coverage; endgame less so).
    """
    needs_eval = [(i, g) for i, g in enumerate(game_records) if not g.has_evals]
    total = len(needs_eval)
    if not needs_eval:
        return

    for idx, (_, game) in enumerate(needs_eval):
        yield f"Cloud eval: game {idx + 1}/{total} — fetching positions..."

        board = chess.Board()
        hits = 0

        for move_idx, move_rec in enumerate(game.moves):
            if move_idx >= max_moves_per_game * 2:   # *2 = both colours' plies
                break
            try:
                uci_move = chess.Move.from_uci(move_rec.uci)
                board.push(uci_move)
            except Exception:
                break

            eval_val = _fetch_cloud_eval(board.fen(), depth)
            if eval_val is not None:
                move_rec.eval_after = eval_val
                hits += 1

            time.sleep(REQUEST_DELAY)

        if hits >= 8:
            game.has_evals = True


def _fetch_cloud_eval(fen: str, depth: int) -> Optional[float]:
    """Returns eval in pawns (White's perspective), or None on miss/error."""
    try:
        resp = requests.get(
            CLOUD_EVAL_URL,
            params={"fen": fen, "multiPv": 1},
            headers=HEADERS,
            timeout=5,
        )
        if resp.status_code == 404:
            return None   # position not in cloud DB — normal, not an error
        resp.raise_for_status()

        data = resp.json()
        pvs = data.get("pvs", [])
        if not pvs:
            return None

        pv = pvs[0]
        if "mate" in pv:
            return MATE_SENTINEL if pv["mate"] > 0 else -MATE_SENTINEL
        if "cp" in pv:
            return pv["cp"] / 100.0   # centipawns → pawns

    except Exception:
        pass

    return None
