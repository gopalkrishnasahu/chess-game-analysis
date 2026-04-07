"""
Flask web application for chess game analysis.
Run locally:  flask run  or  python app.py
Production:   gunicorn --workers 1 --threads 4 --timeout 120 app:app
"""
import time
import uuid

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

# In-memory report cache: token -> (AnalysisReport, created_at)
_cache: dict[str, tuple] = {}
_CACHE_TTL = 1800  # 30 minutes


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/analyse", methods=["POST"])
def analyse():
    username = request.form.get("username", "").strip()
    if not username:
        return redirect(url_for("index"))
    games = _clamp(request.form.get("games", 50), 10, 200)
    perf  = request.form.get("perf", "rapid")
    return redirect(url_for("loading", username=username, games=games, perf=perf))


@app.route("/loading")
def loading():
    return render_template(
        "loading.html",
        username=request.args.get("username", ""),
        games=request.args.get("games", 50),
        perf=request.args.get("perf", "rapid"),
    )


@app.route("/stream")
def stream():
    username = request.args.get("username", "").strip()
    games    = _clamp(request.args.get("games", 50), 10, 200)
    perf     = request.args.get("perf", "rapid")

    def generate():
        from chess_analyzer.fetcher  import fetch_games
        from chess_analyzer.parser   import parse_game
        from chess_analyzer.analyzer import compute_eval_deltas, aggregate_games
        from chess_analyzer.patterns import detect_patterns

        try:
            yield _msg(f"Fetching up to {games} {perf} games for '{username}'...")

            pgn_blocks = fetch_games(username, games, perf, use_cache=False)

            if not pgn_blocks:
                yield _err(f"No {perf} games found for '{username}'. "
                           "Check the username or try a different time control.")
                return

            yield _msg(f"Parsing {len(pgn_blocks)} games...")
            game_records = []
            for pgn in pgn_blocks:
                record = parse_game(pgn, username)
                if record is not None:
                    game_records.append(record)

            if not game_records:
                yield _err("Could not parse any games. The PGN data may be malformed.")
                return

            yield _msg("Computing move evaluations...")
            game_records = [compute_eval_deltas(g) for g in game_records]

            yield _msg("Detecting patterns and building report...")
            report = aggregate_games(game_records, username)
            report = detect_patterns(report, game_records)

            token = uuid.uuid4().hex[:10]
            _cache[token] = (report, time.time())
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
    r, _ = entry
    return render_template("report.html", r=r)


@app.route("/error")
def error():
    return render_template("error.html", msg=request.args.get("msg", "An unknown error occurred.")), 400


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _msg(text: str) -> str:
    """Format a plain SSE data event."""
    return f"data: {text}\n\n"


def _err(text: str) -> str:
    """Format a named SSE error event."""
    return f"event: error\ndata: {text}\n\n"


def _clamp(value, lo: int, hi: int) -> int:
    try:
        return max(lo, min(int(value), hi))
    except (TypeError, ValueError):
        return lo


def _evict_old() -> None:
    """Remove cache entries older than _CACHE_TTL seconds."""
    cutoff = time.time() - _CACHE_TTL
    for k in list(_cache):
        if _cache[k][1] < cutoff:
            del _cache[k]


if __name__ == "__main__":
    app.run(debug=True)
