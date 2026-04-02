"""
Fetches games from the Lichess public API.
No authentication required for public game exports.
"""
import os
import re
import time
from pathlib import Path
from datetime import datetime, timezone

import requests

LICHESS_BASE = "https://lichess.org"
CACHE_DIR = Path(__file__).parent.parent / "cache"


def fetch_games(
    username: str,
    max_games: int = 150,
    perf_type: str = "blitz",
    use_cache: bool = False,
) -> list[str]:
    """
    Returns a list of raw PGN strings, one per game (newest first).
    Fetches up to max_games from the Lichess API with eval/clock/opening data.
    """
    cache_file = CACHE_DIR / f"{username}_{perf_type}.pgn"

    if use_cache and _cache_is_fresh(cache_file):
        print(f"  Using cached PGN from {cache_file}")
        raw = cache_file.read_text(encoding="utf-8")
        return _split_pgn_blocks(raw)

    pgn_blocks: list[str] = []
    fetched = 0
    until_ms: int | None = None

    while fetched < max_games:
        batch_size = min(100, max_games - fetched)
        batch = _fetch_batch(username, batch_size, perf_type, until_ms)
        if not batch:
            break

        pgn_blocks.extend(batch)
        fetched += len(batch)

        if len(batch) < batch_size:
            # No more games available
            break

        if fetched < max_games:
            # Get timestamp of oldest game to paginate
            until_ms = _extract_oldest_timestamp(batch[-1])
            if until_ms is None:
                break
            time.sleep(1.5)  # Respect Lichess rate limits

    if use_cache and pgn_blocks:
        CACHE_DIR.mkdir(exist_ok=True)
        cache_file.write_text("\n\n".join(pgn_blocks), encoding="utf-8")
        print(f"  Cached {len(pgn_blocks)} games to {cache_file}")

    return pgn_blocks


def _fetch_batch(
    username: str,
    max_games: int,
    perf_type: str,
    until_ms: int | None,
) -> list[str]:
    params: dict = {
        "max": max_games,
        "perfType": perf_type,
        "evals": "true",
        "clocks": "true",
        "opening": "true",
        "rated": "true",
    }
    if until_ms is not None:
        params["until"] = until_ms

    url = f"{LICHESS_BASE}/api/games/user/{username}"
    headers = {"Accept": "application/x-chess-pgn"}

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=60)
        resp.raise_for_status()
    except requests.exceptions.HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            raise ValueError(f"Lichess user '{username}' not found.") from e
        raise

    return _split_pgn_blocks(resp.text)


def _split_pgn_blocks(raw_text: str) -> list[str]:
    """Splits a multi-game PGN stream into individual game strings."""
    blocks = re.split(r'\n\n(?=\[Event)', raw_text.strip())
    return [b.strip() for b in blocks if b.strip() and b.strip().startswith("[")]


def _extract_oldest_timestamp(pgn_block: str) -> int | None:
    """Extracts the UTCDate+UTCTime from a PGN block and returns Unix ms."""
    date_m = re.search(r'\[UTCDate "(\d{4}\.\d{2}\.\d{2})"\]', pgn_block)
    time_m = re.search(r'\[UTCTime "(\d{2}:\d{2}:\d{2})"\]', pgn_block)
    if not date_m or not time_m:
        return None
    dt_str = f"{date_m.group(1).replace('.', '-')}T{time_m.group(1)}Z"
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return int(dt.timestamp() * 1000) - 1  # subtract 1ms so we don't re-fetch this game
    except ValueError:
        return None


def _cache_is_fresh(cache_file: Path, max_age_hours: int = 24) -> bool:
    if not cache_file.exists():
        return False
    age_seconds = time.time() - cache_file.stat().st_mtime
    return age_seconds < max_age_hours * 3600
