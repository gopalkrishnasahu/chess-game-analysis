"""
Fetches games from the Chess.com public API.
No authentication required.

Chess.com PGNs do NOT include [%eval] annotations, so blunder detection
will show 0 eval-based stats. Phase/opening/W-D-L stats still work.
"""
import re
import time
from datetime import datetime, timezone

import requests

CHESSCOM_BASE = "https://api.chess.com/pub"
HEADERS = {"User-Agent": "chess-game-analyser/1.0"}


def fetch_games_chesscom(
    username: str,
    max_games: int = 50,
    perf_type: str = "rapid",
) -> list[str]:
    """
    Returns a list of raw PGN strings (newest first) from Chess.com.
    perf_type must be one of: rapid, blitz, bullet, classical, daily.
    """
    time_class = _perf_to_time_class(perf_type)

    # Verify user exists
    try:
        resp = requests.get(f"{CHESSCOM_BASE}/player/{username}", headers=HEADERS, timeout=15)
        if resp.status_code == 404:
            raise ValueError(f"Chess.com user '{username}' not found.")
        resp.raise_for_status()
    except requests.exceptions.HTTPError as e:
        raise ValueError(f"Chess.com user '{username}' not found.") from e

    # Get list of available monthly archives (newest first)
    archives_resp = requests.get(
        f"{CHESSCOM_BASE}/player/{username}/games/archives",
        headers=HEADERS, timeout=15,
    )
    archives_resp.raise_for_status()
    archives = list(reversed(archives_resp.json().get("archives", [])))

    pgn_blocks: list[str] = []

    for archive_url in archives:
        if len(pgn_blocks) >= max_games:
            break

        try:
            month_resp = requests.get(archive_url, headers=HEADERS, timeout=30)
            month_resp.raise_for_status()
        except requests.exceptions.RequestException:
            continue

        games = month_resp.json().get("games", [])
        # Newest games last in each month — reverse to get newest first
        for game in reversed(games):
            if len(pgn_blocks) >= max_games:
                break
            if game.get("time_class") != time_class:
                continue
            pgn = game.get("pgn", "").strip()
            if pgn:
                pgn_blocks.append(pgn)

        time.sleep(0.5)  # be polite to Chess.com API

    return pgn_blocks


def _perf_to_time_class(perf_type: str) -> str:
    mapping = {
        "rapid": "rapid",
        "blitz": "blitz",
        "bullet": "bullet",
        "classical": "daily",
        "daily": "daily",
    }
    return mapping.get(perf_type.lower(), "rapid")
