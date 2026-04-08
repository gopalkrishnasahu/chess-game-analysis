"""
Fetches games from the Chess.com public API.
No authentication required.

Chess.com PGNs do NOT include [%eval] annotations, so blunder detection
will show 0 eval-based stats. Phase/opening/W-D-L stats still work.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

CHESSCOM_BASE = "https://api.chess.com/pub"
HEADERS = {"User-Agent": "chess-game-analyser/1.0"}
_PARALLEL_WORKERS = 4   # fetch up to 4 monthly archives at once


def fetch_games_chesscom(
    username: str,
    max_games: int = 50,
    perf_type: str = "rapid",
) -> list[str]:
    """
    Returns a list of raw PGN strings (newest first, up to max_games) from Chess.com.
    perf_type: rapid | blitz | bullet | classical | daily
    """
    time_class = _perf_to_time_class(perf_type)

    # Get list of monthly archives (API returns oldest-first; we want newest-first)
    try:
        archives_resp = requests.get(
            f"{CHESSCOM_BASE}/player/{username}/games/archives",
            headers=HEADERS, timeout=15,
        )
        if archives_resp.status_code == 404:
            raise ValueError(f"Chess.com user '{username}' not found.")
        archives_resp.raise_for_status()
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else "?"
        if status == 404:
            raise ValueError(f"Chess.com user '{username}' not found.") from e
        raise

    archives = list(reversed(archives_resp.json().get("archives", [])))
    if not archives:
        return []

    pgn_blocks: list[str] = []

    # Process months in batches, newest first, stop when we have enough
    for batch_start in range(0, len(archives), _PARALLEL_WORKERS):
        if len(pgn_blocks) >= max_games:
            break

        batch = archives[batch_start: batch_start + _PARALLEL_WORKERS]

        # Fetch this batch of months in parallel
        month_games: dict[str, list[dict]] = {}
        with ThreadPoolExecutor(max_workers=_PARALLEL_WORKERS) as pool:
            future_to_url = {
                pool.submit(_fetch_month, url): url for url in batch
            }
            for future in as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    month_games[url] = future.result()
                except Exception:
                    month_games[url] = []

        # Collect games in order (newest month first within batch)
        for url in batch:
            if len(pgn_blocks) >= max_games:
                break
            games = month_games.get(url, [])
            # Chess.com returns games oldest-first within a month — reverse for newest first
            for game in reversed(games):
                if len(pgn_blocks) >= max_games:
                    break
                if game.get("time_class") != time_class:
                    continue
                pgn = game.get("pgn", "").strip()
                if pgn:
                    pgn_blocks.append(pgn)

    return pgn_blocks


def _fetch_month(url: str) -> list[dict]:
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json().get("games", [])


def _perf_to_time_class(perf_type: str) -> str:
    return {
        "rapid": "rapid",
        "blitz": "blitz",
        "bullet": "bullet",
        "classical": "daily",
        "daily": "daily",
    }.get(perf_type.lower(), "rapid")
