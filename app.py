"""
Flask web application for chess game analysis.
Run locally:  flask run  or  python app.py
Production:   gunicorn --workers 1 --threads 4 --timeout 120 app:app
"""
import json
import time
import uuid
from pathlib import Path

from flask import (
    Flask,
    Response,
    redirect,
    render_template,
    request,
    stream_with_context,
    url_for,
)

app = Flask(__name__)

# ECO code -> opening name lookup (sourced from lichess-org/chess-openings, CC0)
_ECO_FILE = Path(__file__).parent / "chess_analyzer" / "eco_names.json"
ECO_NAMES: dict[str, str] = json.loads(_ECO_FILE.read_text(encoding="utf-8"))

# In-memory report cache: token -> (AnalysisReport, created_at)
_cache: dict[str, tuple] = {}
_CACHE_TTL = 1800  # 30 minutes

# Temporary PGN store for upload flow: token -> pgn_text
_pgn_store: dict[str, str] = {}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/analyse", methods=["POST"])
def analyse():
    source = request.form.get("source", "lichess")  # lichess | chesscom | pgn

    if source == "pgn":
        # PGN upload / paste
        pgn_text = request.form.get("pgn_text", "").strip()
        if not pgn_text:
            uploaded = request.files.get("pgn_file")
            if uploaded and uploaded.filename:
                pgn_text = uploaded.read().decode("utf-8", errors="replace").strip()
        if not pgn_text:
            return redirect(url_for("index"))
        username = request.form.get("username_pgn", "").strip() or "Player"
        # Stash PGN so the SSE stream can read it
        pgn_token = uuid.uuid4().hex[:12]
        _pgn_store[pgn_token] = pgn_text
        return redirect(url_for("loading",
                                source="pgn",
                                pgn_token=pgn_token,
                                username=username,
                                games="",
                                perf=""))

    # Lichess or Chess.com
    username = request.form.get("username", "").strip()
    if not username:
        return redirect(url_for("index"))
    games = _clamp(request.form.get("games", 50), 10, 200)
    perf  = request.form.get("perf", "rapid")
    return redirect(url_for("loading",
                            source=source,
                            username=username,
                            games=games,
                            perf=perf))


@app.route("/loading")
def loading():
    return render_template(
        "loading.html",
        source=request.args.get("source", "lichess"),
        username=request.args.get("username", ""),
        games=request.args.get("games", 50),
        perf=request.args.get("perf", "rapid"),
        pgn_token=request.args.get("pgn_token", ""),
    )


@app.route("/stream")
def stream():
    source   = request.args.get("source", "lichess")
    username = request.args.get("username", "").strip()
    games    = _clamp(request.args.get("games", 50), 10, 200)
    perf     = request.args.get("perf", "rapid")
    pgn_token = request.args.get("pgn_token", "")

    def generate():
        from chess_analyzer.parser   import parse_game
        from chess_analyzer.analyzer import compute_eval_deltas, aggregate_games
        from chess_analyzer.patterns import detect_patterns

        try:
            # ── Fetch PGN blocks ─────────────────────────────────────────────
            if source == "pgn":
                pgn_text = _pgn_store.pop(pgn_token, "")
                if not pgn_text:
                    yield _err("PGN data not found. Please paste or upload your PGN again.")
                    return
                from chess_analyzer.fetcher import _split_pgn_blocks
                pgn_blocks = _split_pgn_blocks(pgn_text)
                yield _msg(f"Reading {len(pgn_blocks)} games from uploaded PGN...")

            elif source == "chesscom":
                yield _msg(f"Fetching up to {games} {perf} games for '{username}' from Chess.com...")
                from chess_analyzer.fetcher_chesscom import fetch_games_chesscom
                pgn_blocks = fetch_games_chesscom(username, games, perf)

            else:  # lichess (default)
                yield _msg(f"Fetching up to {games} {perf} games for '{username}' from Lichess...")
                from chess_analyzer.fetcher import fetch_games
                pgn_blocks = fetch_games(username, games, perf, use_cache=False)

            if not pgn_blocks:
                platform_label = {"chesscom": "Chess.com", "pgn": "the uploaded PGN"}.get(source, "Lichess")
                yield _err(f"No {perf} games found in {platform_label}. "
                           "Check the username or try a different time control.")
                return

            # ── Parse ────────────────────────────────────────────────────────
            yield _msg(f"Parsing {len(pgn_blocks)} games...")
            game_records = []
            for pgn in pgn_blocks:
                record = parse_game(pgn, username)
                if record is not None:
                    game_records.append(record)

            if not game_records:
                yield _err("Could not parse any games. The PGN data may be malformed.")
                return

            # ── Stockfish enrichment (optional) ──────────────────────────────
            from chess_analyzer.stockfish_eval import get_stockfish_path, enrich_games_with_stockfish
            if get_stockfish_path():
                needs_eval = sum(1 for g in game_records if not g.has_evals)
                if needs_eval:
                    yield _msg(
                        f"Running Stockfish on {needs_eval} games without eval data "
                        f"(depth 12) — takes ~{needs_eval * 3}s..."
                    )
                    game_records = enrich_games_with_stockfish(game_records, pgn_blocks, depth=12)

            # ── Analyse ──────────────────────────────────────────────────────
            yield _msg("Computing move evaluations...")
            game_records = [compute_eval_deltas(g) for g in game_records]

            yield _msg("Detecting patterns and building report...")
            report = aggregate_games(game_records, username)
            report = detect_patterns(report, game_records)
            report.source = source

            token = uuid.uuid4().hex[:10]
            _cache[token] = (report, time.time(), source)
            _evict_old()

            yield f"event: done\ndata: {token}\n\n"

        except ValueError as exc:
            yield _err(str(exc))
        except Exception as exc:
            yield _err(f"Unexpected error: {exc}")

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/report/<token>")
def report(token: str):
    entry = _cache.get(token)
    if not entry:
        return render_template(
            "error.html",
            msg="Report not found or expired (reports are kept for 30 minutes). "
                "Please run the analysis again.",
        ), 404
    r, _, source = entry
    return render_template("report.html", r=r, source=source, eco_names=ECO_NAMES)


@app.route("/error")
def error():
    return render_template("error.html", msg=request.args.get("msg", "An unknown error occurred.")), 400


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _msg(text: str) -> str:
    return f"data: {text}\n\n"


def _err(text: str) -> str:
    return f"event: error\ndata: {text}\n\n"


def _clamp(value, lo: int, hi: int) -> int:
    try:
        return max(lo, min(int(value), hi))
    except (TypeError, ValueError):
        return lo


def _evict_old() -> None:
    cutoff = time.time() - _CACHE_TTL
    for k in list(_cache):
        if _cache[k][1] < cutoff:  # index 1 is timestamp in (report, ts, source)
            del _cache[k]


if __name__ == "__main__":
    app.run(debug=True)
