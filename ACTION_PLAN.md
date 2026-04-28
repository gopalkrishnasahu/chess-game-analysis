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

### 3.2 Web Interface — DONE ✓
- Flask + SSE streaming backend deployed on Render.com
- Lichess, Chess.com, and PGN upload all work
- Live progress bar, chess facts carousel, step-by-step indicator
- Hosted at: https://chess-game-analysis.onrender.com

### 3.3 Docker Container
```bash
docker run -e LICHESS_USERNAME=yourname ghcr.io/you/chess-insight
```
- Dockerfile: Python 3.12 slim + Stockfish binary + pip install
- Makes it easy for others to self-host

### 3.4 GitHub Repository — DONE ✓
- Public repo: https://github.com/gopalkrishnasahu/chess-game-analysis
- README with description and features

---

## Phase 3.5 — Multi-Platform & Custom Input (DONE ✓)

### 3.5.1 Chess.com Support — DONE ✓
- `chess_analyzer/fetcher_chesscom.py` using Chess.com public API
- PGN format compatible with python-chess
- Cloud eval removed for Chess.com (Lichess DB doesn't cover Chess.com positions)
- Report shows opening win rates, W/D/L, strengths/struggles by win rate alone

### 3.5.2 Custom PGN Upload / Paste — DONE ✓
- Tab on landing page: paste PGN text or upload .pgn file
- Cloud eval runs for PGN source (Lichess positions covered)
- Username field identifies which player to analyse

---

## Phase 3.6 — AI Coach Layer (High Impact for ELO Growth)

**Mission:** Bridge diagnosis (what the app already does) and improvement (what players need). Currently says *what* is wrong. This phase makes it say *why* and *exactly what to do*.

### 3.6.1 LLM-Powered Personalised Coach Report
**Why:** Numbers alone don't change behaviour. A personalised narrative from an AI coach is far more actionable.

**How:**
- Add "Generate AI Coach Report" button on the report page
- POST to `/coach-report/<token>` — server serialises `AnalysisReport` to JSON and sends to LLM API
- Prompt includes: blunder rates, worst phase, loss types, struggling openings, W/D/L
- LLM returns: 400–500 word personalised report with specific study advice
- Render result in a new card below recommendations section
- Use Claude API (`claude-haiku-4-5-20251001` for speed/cost, or `claude-sonnet-4-6` for depth)
- API key stored in `.env` / Render environment variable

**Files:** `app.py` (new `/coach-report/<token>` route), `templates/report.html` (button + result card), `chess_analyzer/coach.py` (prompt builder + LLM call)

**Cost estimate:** ~$0.002–0.005 per report with Haiku.

### 3.6.2 In-App Study Plan (Action Plan Tab)
- Second tab on report page: "Study Plan"
- LLM generates a 2–4 week plan: puzzle categories, opening lines, endgame drills
- Each task links to Lichess resource: `lichess.org/training/<theme>`, studies, opening explorer
- Player can check off tasks (localStorage persistence — no login needed)

### 3.6.3 Progress Tracking (Return Visitor Flow)
- After analysis, offer "Save this report" — persistent URL keyed by username+date
- On re-analysis: compare current vs saved baseline — show deltas
- "You've improved your endgame error rate by 23% since your last analysis"

### 3.6.4 Lichess Resource Deep-Links — QUICK WIN
- Map each weakness to a Lichess resource URL:
  - Tactical themes → `https://lichess.org/training/<theme>`
  - Opening family → `https://lichess.org/opening/<ECO-name>`
  - Endgame drill → `https://lichess.org/practice`
- Static mappings in `chess_analyzer/resources.py` — no LLM needed
- Render as clickable buttons next to each recommendation

**Files:** `chess_analyzer/resources.py` (new, static mapping), `templates/report.html` (link buttons)

---

## Phase 3.7 — UI/UX Design Overhaul — DONE ✓

**Completed session: 2026-04-26**

### What was implemented

Full design system applied across all four templates (`base.html`, `report.html`, `index.html`, `loading.html`):

**Design tokens (base.html):**
- Gold accent (#e6c17a) replacing chess-generic green
- Deep background hierarchy: `--bg #0d0f14`, `--surface-1 #14171f`, `--surface-2 #1a1e28`, `--surface-3 #232834`
- Foreground hierarchy: `--fg-1 #f3f4f7`, `--fg-2 #b8bdc9`, `--fg-3 #7a8290`, `--fg-4 #4a5160`
- Semantic colours: `--positive #4ade80`, `--negative #f87171`, `--warning #f5b860`
- Fonts: Fraunces (display/numbers), Inter (UI), JetBrains Mono (data)
- 4px spacing grid, radius scale (4/6/10/16px), line hierarchy tokens

**Navbar:** Frosted-glass sticky nav (`backdrop-filter: blur(12px)`) with knight SVG logo on all pages

**Brand mark:** Knight SVG silhouette replaces pawn unicode on all pages

**report.html — biggest changes:**
- Hero: Fraunces 3rem display numbers for win%, blunders/game, mistakes/game
- W/D/L shown as coloured chips (green/amber/red) in a secondary row
- Opening table: animated gauge bars for win% (colour-coded green/amber/red)
- Blunders/g column uses JetBrains Mono
- Finding tip boxes: gold left-border accent (`border-left: 2px solid var(--accent)`)
- Weakness finding cards: clean border style (no coloured left border, cleaner card)
- Recommendation numbers: gold badge pill (`badge-accent` style)

**index.html:**
- Knight SVG replaces pawn in brand mark
- Tab bar: gold active state with `accent-soft` background
- "Notice" boxes: gold left-border style
- PGN textarea uses JetBrains Mono

**loading.html:**
- Knight SVG with gold glow animation (replaces pawn unicode)
- Step items: numbered badge pills (gold=active, green=done, grey=pending)
- Elapsed/remaining time in JetBrains Mono
- Chess fact box: gold left-border style

**Buttons:** Gold gradient background (`#e6c17a → #b8965a`) with dark text (`#0d0f14`) — high contrast, premium feel

**Commit:** `7e42b22` — pushed to main → auto-deploys on Render

---

## Previously Completed (earlier sessions)

### Bugs Fixed
- **Cloud eval 0/N for Chess.com**: Dropped cloud eval for Chess.com entirely (Lichess DB doesn't cover Chess.com positions). Chess.com reports now complete in ~15s instead of 90s.
- **ECO codes in weakness text** (e.g. "struggling in B50"): Added `_opening_display_name()` in `patterns.py` that looks up `eco_names.json` — readable names shown everywhere.
- **Duplicate opening rows** (A02 and A03 both = "Bird Opening"): Fixed by normalising ECO codes to family names at aggregation stage in `analyzer.py::_normalise_family()`.
- **"MODERATE" badge unclear**: Changed to human-readable "Fix first", "Work on this", "Minor".
- **"0/N with eval" shown when 0**: Hero now hides this when zero, shows green check when 100%.
- **Chess.com blunders/g showing 0.0**: Opening table now shows `—` instead of misleading 0.0 when no eval.
- **Opening struggles without eval**: `patterns.py` now detects struggles/strengths using win-rate alone (<38% / ≥60%) when no eval data available.
- **White vs Black color imbalance insight**: New recommendation when win rate differs by ≥20% between colours.

---

## Immediate Next Steps (for next session)

1. **Full deploy on Linode** (Phase 2.1 — IN PROGRESS) — Stockfish installed, app deployment next
   - Stockfish already installed on Linode server ✓
   - Deploy script: `scripts/deploy_linode.sh` — clone repo, set up gunicorn + nginx
   - **TODO:** Run `deploy_linode.sh` on the Linode server, app will be live at server IP
   - Render.com can be left running or shut down after confirming Linode works

2. **Lichess resource deep-links** (Phase 3.6.4) — quick win, high player value
   - Create `chess_analyzer/resources.py` with static weakness→URL mappings
   - Add clickable buttons in `templates/report.html` next to each recommendation

3. **AI Coach Report** (Phase 3.6.1) — high impact
   - Add Claude API key to `.env`
   - Create `chess_analyzer/coach.py` with prompt builder
   - Add "Generate AI Coach Report" button to report page

---

## Notes on Making It Public
- All Lichess game data is public (Creative Commons license) — no legal issues
- Stockfish is open source (GPLv3) — freely distributable
- No Lichess API key needed for read-only game export
- Rate limits to respect: max 20 req/min to Lichess API (our tool already handles this)
- Consider adding a `--delay` flag so hosted versions can be polite to Lichess servers
