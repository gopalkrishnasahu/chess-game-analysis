# Chess Analysis Tool — Action Plan

## Current State (Phase 1 — DONE)
- Fetches blitz games from Lichess public API (no auth needed)
- Parses PGN with eval/clock annotations (python-chess)
- Identifies blunders/mistakes by phase, opening win rates, time pressure patterns
- Rich terminal output + Markdown report
- Secrets in `.env`, git-ignored

**Limitation:** Only games already analyzed on Lichess have eval data.
**Fix:** Add local Stockfish support (Phase 2, first priority).

---

## Phase 2 — Make the Tool Reliable (Next Session)

### 2.1 Add Local Stockfish Analysis (HIGHEST PRIORITY)
**Why:** Lichess only has eval data for ~5% of blitz games (ones you manually analyzed).
Local Stockfish gives eval for 100% of games, offline, no rate limits.

**How:**
- Download Stockfish from https://stockfishchess.org/download/ (free, ~10MB binary)
- Add `--stockfish PATH` flag to `main.py`
- In `analyzer.py`: if `--stockfish` provided and game lacks evals, run Stockfish on each position
- Use `chess.engine.SimpleEngine.popen_uci(stockfish_path)` (built into python-chess, no extra dep)
- Use depth=15 for speed (accurate enough for pattern detection at 1600 level)
- Show a progress bar with `rich.progress` while analyzing

**Files to change:** `main.py`, `analyzer.py` (add `run_stockfish_analysis(game, engine)`)

### 2.2 Better Recommendation Engine
- Cross-reference opening struggles with specific tactical themes
- Add "game phase transition" detection (when eval swings happen most)
- Identify if losses are from time forfeit vs. positional/tactical collapse

### 2.3 Fix Minor Display Issues
- Recommendation text wrapping in terminal (currently breaks mid-sentence)
- Opening table border rendering on Windows

---

## Phase 3 — Share With Others

### 3.1 Package as a pip-installable CLI tool
```bash
pip install chess-insight
chess-insight --username lichess_user --games 150 --output both
```
- Create `pyproject.toml` with entry point `chess-insight = chess_analyzer.main:main`
- Publish to PyPI
- Users need to download Stockfish separately (OS-specific binary, can't bundle)
- Add clear README with setup instructions

### 3.2 Web Interface (Flask + HTMX)
- Simple one-page web app: enter Lichess username → click Analyze → see report
- No login needed (all public Lichess data)
- Run Stockfish analysis server-side (single shared Stockfish instance)
- Show live progress bar while fetching + analyzing
- Report rendered as a nice HTML page (not just markdown)
- Host on: Render.com / Railway.app / Fly.io (free tiers available)

### 3.3 Docker Container
```bash
docker run -e LICHESS_USERNAME=yourname ghcr.io/you/chess-insight
```
- Dockerfile: Python 3.12 slim + Stockfish binary + pip install
- Makes it easy for others to self-host

### 3.4 GitHub Repository
- Clean public repo with:
  - README: what it does, screenshot of terminal output, quick start
  - CONTRIBUTING.md
  - GitHub Actions: run tests on PR
  - Releases with pre-built Docker image

---

## Phase 4 — Advanced Analysis Features

### 4.1 Tactical Pattern Classification (with Stockfish)
After identifying a blunder with Stockfish, classify *why* it was a blunder:
- Fork missed / fell for a fork
- Hanging piece (undefended piece captured)
- Back-rank weakness
- Pin / discovered attack
- This requires checking the winning move type after the blunder

### 4.2 Opening Repertoire Builder
- Given your struggling openings, suggest specific variations to study
- Link to Lichess study pages for those variations
- Show move-by-move where you deviate from theory

### 4.3 Historical Trend
- Track rating-correlated metrics over time (blunders/game improving?)
- "Your accuracy has improved 8% over the last 3 months"

### 4.4 Position Similarity Clustering
- Group similar blunder positions to identify recurring blind spots
- More advanced: use FEN similarity or piece configuration matching

---

## Immediate Next Steps (for next session)

1. **Download Stockfish** from https://stockfishchess.org/download/
   - Windows: download the `.exe`, note the path
   - Add path to `.env` as `STOCKFISH_PATH=C:/path/to/stockfish.exe`

2. **Run Stockfish integration first** — this unlocks full analysis for all 50+ games

3. Then decide: CLI-only package OR web app first?

---

## Notes on Making It Public
- All Lichess game data is public (Creative Commons license) — no legal issues
- Stockfish is open source (GPLv3) — freely distributable
- No Lichess API key needed for read-only game export
- Rate limits to respect: max 20 req/min to Lichess API (our tool already handles this)
- Consider adding a `--delay` flag so hosted versions can be polite to Lichess servers
