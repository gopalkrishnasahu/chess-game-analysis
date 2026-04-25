"""
Lichess Cloud Eval enrichment — zero installation required.

Uses the Lichess public cloud-eval API (free, no auth):
  GET https://lichess.org/api/cloud-eval?fen=<FEN>

Positions are fetched in parallel (8 workers) to keep analysis fast.
Coverage: ~70-80% of opening/early middlegame positions.
"""
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

import chess
import requests

CLOUD_EVAL_URL  = "https://lichess.org/api/cloud-eval"
REQUEST_TIMEOUT = 3      # seconds per request — fail fast on slow responses
MAX_WORKERS     = 8      # parallel requests to Lichess cloud eval
MAX_MOVES       = 15     # evaluate first N full moves per game (30 plies)
PROGRESS_EVERY  = 3      # yield a progress message every N games
MATE_SENTINEL   = 100.0

# Shared session for connection reuse
_session = requests.Session()
_session.headers.update({"Accept": "application/json"})


def enrich_games_with_cloud_eval(game_records: list):
    """
    Generator — yields progress strings, modifies game_records in-place.

    Usage:
        for msg in enrich_games_with_cloud_eval(game_records):
            yield _msg(msg)
    """
    needs_eval = [(i, g) for i, g in enumerate(game_records) if not g.has_evals]
    total = len(needs_eval)
    if not needs_eval:
        return

    for idx, (_, game) in enumerate(needs_eval):
        if idx % PROGRESS_EVERY == 0:
            yield f"Cloud eval: games {idx + 1}–{min(idx + PROGRESS_EVERY, total)}/{total}..."

        _eval_game_parallel(game)

    yield f"Cloud eval complete — eval data added to {total} games."


def _eval_game_parallel(game) -> None:
    """Fetch evals for all positions in a game using a thread pool."""
    # Build list of (move_idx, fen) for positions we want to evaluate
    board = chess.Board()
    positions: list[tuple[int, str]] = []   # (move_idx, fen)

    for move_idx, move_rec in enumerate(game.moves):
        if move_idx >= MAX_MOVES * 2:   # *2 = plies for both colours
            break
        try:
            board.push(chess.Move.from_uci(move_rec.uci))
        except Exception:
            break
        positions.append((move_idx, board.fen()))

    if not positions:
        return

    # Fetch all positions in parallel
    results: dict[int, Optional[float]] = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {
            pool.submit(_fetch_cloud_eval, fen): move_idx
            for move_idx, fen in positions
        }
        for future in as_completed(futures):
            move_idx = futures[future]
            try:
                results[move_idx] = future.result()
            except Exception:
                results[move_idx] = None

    # Write results back to move records
    hits = 0
    for move_idx, eval_val in results.items():
        if eval_val is not None:
            game.moves[move_idx].eval_after = eval_val
            hits += 1

    if hits >= 6:   # enough evals to be meaningful
        game.has_evals = True


def _fetch_cloud_eval(fen: str) -> Optional[float]:
    """Returns eval in pawns (White's perspective), or None on miss/error."""
    try:
        resp = _session.get(
            CLOUD_EVAL_URL,
            params={"fen": fen, "multiPv": 1},
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()

        pvs = resp.json().get("pvs", [])
        if not pvs:
            return None

        pv = pvs[0]
        if "mate" in pv:
            return MATE_SENTINEL if pv["mate"] > 0 else -MATE_SENTINEL
        if "cp" in pv:
            return pv["cp"] / 100.0

    except Exception:
        pass

    return None
