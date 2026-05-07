# Chess Game Analyser — Project Context for Claude

## What this project is

A web app that analyses a chess player's recent games (Lichess, Chess.com, or uploaded PGN) and produces a personalised report: blunders/game, mistakes/game, opening win rates, phase breakdown, weaknesses, strengths, and study recommendations.

**Live URL:** http://172.105.63.146 (Linode server — friend's server)
**GitHub:** https://github.com/gopalkrishnasahu/chess-game-analysis
**Old hosting:** https://chess-game-analysis.onrender.com (Render.com — still live but being replaced by Linode)

---

## Architecture

```
Browser → nginx (port 80) → gunicorn (port 5000) → Flask app (app.py)
                                                          │
                                              Stockfish (local binary)
                                              /usr/games/stockfish
```

- **Flask + SSE streaming** — analysis results streamed live to browser via Server-Sent Events
- **Stockfish** — installed on Linode via `apt install stockfish`, path set in `.env` as `STOCKFISH_PATH=/usr/games/stockfish`
- **Parallel analysis** — 4 Stockfish instances run in parallel (ThreadPoolExecutor, 4 workers)
- **gunicorn** — 1 worker, 4 threads, 300s timeout (SSE requires single worker)
- **nginx** — reverse proxy with `proxy_buffering off` (required for SSE streaming)

---

## Server (Linode)

- **IP:** 172.105.63.146
- **RAM:** 4GB
- **OS:** Ubuntu (Debian-based)
- **App directory:** `/root/chess-game-analysis`
- **Service:** `chess-app.service` (systemd)
- **Auto-deploy:** crontab polls GitHub every 5 minutes, restarts service if changes found

### Key server commands

```bash
sudo systemctl status chess-app          # check app status
sudo journalctl -u chess-app -f          # live logs
sudo systemctl restart chess-app         # manual restart

# Manual deploy
git -C ~/chess-game-analysis pull && sudo systemctl restart chess-app
```

### .env on the server

```
STOCKFISH_PATH=/usr/games/stockfish
```

### Auto-deploy crontab (runs on server)

```
*/5 * * * * cd /root/chess-game-analysis && git fetch origin -q && git diff --quiet HEAD origin/main || (git pull -q && systemctl restart chess-app)
```

---

## Project structure

```
chess-game-analysis/
├── app.py                        # Flask web server, SSE stream, all routes
├── main.py                       # CLI entry point (not used on server)
├── requirements.txt
├── Procfile                      # Render.com config (legacy)
├── runtime.txt                   # Python 3.11.9
├── ACTION_PLAN.md                # Full roadmap with phase status
├── CLAUDE.md                     # ← this file
├── scripts/
│   ├── deploy_linode.sh          # Full deploy script (clone + venv + systemd + nginx)
│   └── linode_setup_stockfish.sh # Phase 1: just install + verify Stockfish
├── chess_analyzer/
│   ├── models.py                 # Data classes: MoveRecord, GameRecord, AnalysisReport
│   ├── fetcher.py                # Lichess API game export
│   ├── fetcher_chesscom.py       # Chess.com API game export
│   ├── parser.py                 # PGN parsing, eval/clock extraction
│   ├── analyzer.py               # Eval delta computation, error classification
│   ├── patterns.py               # Weakness/strength detection (615 LOC)
│   ├── report.py                 # Terminal + Markdown report output (CLI only)
│   ├── cloud_eval.py             # Lichess cloud eval API (PGN uploads only)
│   ├── stockfish_eval.py         # Local Stockfish analysis
│   ├── logger.py                 # Run history logging
│   └── eco_names.json            # ECO code → opening name lookup
└── templates/
    ├── base.html                 # Design tokens, navbar, shared CSS
    ├── index.html                # Landing page (3 tabs: Lichess, Chess.com, PGN)
    ├── loading.html              # SSE progress page with step indicators
    └── report.html               # Analysis report rendering
```

---

## Key design decisions

- **gunicorn single worker** — SSE uses in-memory state; multiple workers break the stream
- **nginx `proxy_buffering off`** — required for SSE live progress bar to work
- **Stockfish depth=12** — fast enough (~3s/game), accurate enough for 1600-level pattern detection
- **4 parallel Stockfish workers** — safe on 4GB RAM (~64MB each = 256MB total)
- **Chess.com: no cloud eval** — Lichess cloud eval DB doesn't cover Chess.com positions, skipped
- **Eval enrichment priority:** local Stockfish → Lichess cloud (PGN only) → skip

---

## Analysis pipeline (app.py /stream route)

1. Fetch PGN blocks (Lichess API / Chess.com API / uploaded PGN)
2. Parse each PGN into `GameRecord` objects
3. Enrich with evals:
   - If `STOCKFISH_PATH` set → run parallel Stockfish (4 workers, depth 12)
   - Else if PGN source → Lichess cloud eval
   - Else (Chess.com without Stockfish) → skip, show no-eval report
4. `compute_eval_deltas()` — classify blunders (≥3.0), mistakes (1.0-3.0), inaccuracies (0.5-1.0)
5. `aggregate_games()` — build `AnalysisReport` with opening stats, phase breakdown
6. `detect_patterns()` — find weaknesses/strengths/recommendations
7. Cache report with UUID token (30-min TTL), stream `done` event to browser

---

## Error thresholds (analyzer.py)

| Error type | Eval swing | Notes |
|------------|-----------|-------|
| Blunder | ≥ 3.00 pawns | |
| Mistake | 1.00 – 3.00 pawns | |
| Inaccuracy | 0.50 – 1.00 pawns | |
| Already losing | position ≥ 3.00 pawns down | errors in losing positions not counted |

---

## Design system (base.html)

- **Background:** `#0d0f14` (deep dark), surface hierarchy `#14171f → #1a1e28 → #232834`
- **Accent:** `#e6c17a` (gold)
- **Fonts:** Fraunces (display/numbers), Inter (UI), JetBrains Mono (data/code)
- **Positive:** `#4ade80`, **Negative:** `#f87171`, **Warning:** `#f5b860`

---

## Current state (as of 2026-05-07)

### Done ✓
- Full web app with Lichess, Chess.com, PGN upload support
- Stockfish running on Linode with parallel analysis (4 workers)
- Per-game progress in loading screen ("Stockfish: analysed game X/Y")
- Step indicator in loading screen advances correctly during Stockfish phase
- Empty state messages in report (Openings, Weaknesses, Strengths, Recommendations)
- Auto-deploy via crontab on Linode server
- UI design overhaul (gold theme, knight SVG brand, Fraunces font)

### Next up (from ACTION_PLAN.md)
1. **Lichess resource deep-links** (Phase 3.6.4) — quick win
   - `chess_analyzer/resources.py` — static weakness → Lichess URL mapping
   - Add clickable buttons in `templates/report.html` next to each recommendation
2. **AI Coach Report** (Phase 3.6.1) — high impact
   - `chess_analyzer/coach.py` — Claude API prompt builder
   - New route `/coach-report/<token>` in `app.py`
   - "Generate AI Coach Report" button in `report.html`
   - Needs `ANTHROPIC_API_KEY` in `.env` on server
3. **Study Plan** (Phase 3.6.2) — LLM-generated 2–4 week plan with Lichess links

---

## Environment variables

| Variable | Where | Purpose |
|----------|-------|---------|
| `STOCKFISH_PATH` | Linode `.env` | Path to Stockfish binary |
| `ANTHROPIC_API_KEY` | Linode `.env` (future) | For AI coach report feature |
| `LICHESS_USERNAME` | CLI `.env` only | Default username for `main.py` CLI — NOT used by web app |

---

## Running locally (development)

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py                   # starts Flask on http://127.0.0.1:5000
```

Stockfish is optional locally — without it, Lichess PGN uploads still get cloud eval.

---

## Deploying changes

```bash
# Local: push to GitHub
git add -A && git commit -m "your message" && git push origin main

# Linode picks up automatically within 5 minutes via crontab
# Or manually on the server:
git -C ~/chess-game-analysis pull && sudo systemctl restart chess-app
```
