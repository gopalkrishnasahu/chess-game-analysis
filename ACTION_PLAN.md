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

## Phase 3.5 — Multi-Platform & Custom Input (Future Web Features)

### 3.5.1 Chess.com Support
**Why:** Chess.com is the largest chess platform — many users are there, not Lichess.

**How:**
- New `chess_analyzer/fetcher_chesscom.py` using Chess.com public API:
  `GET https://api.chess.com/pub/player/{username}/games/{YYYY}/{MM}` (returns JSON with `pgn` field)
- PGN format is compatible with `python-chess` — parser and analyzer unchanged
- Add "Platform" dropdown to the web form (Lichess / Chess.com)
- **Caveat:** Chess.com PGNs don't include `[%eval]` annotations, so blunder detection requires Stockfish

### 3.5.2 Custom PGN Upload / Paste
**Why:** Some players export games from other platforms or have tournament PGN files.

**How:**
- Add a second tab on the web form: "Paste PGN" (textarea) + "Upload .pgn file" (file input)
- File input reads the file client-side (FileReader API) and populates the textarea
- In `app.py`: detect username-based vs PGN-based request; for PGN, skip fetch step
- Username field still needed to identify which player in the PGN to analyse
- Split PGN into blocks using existing `_split_pgn_blocks()` from `fetcher.py`

---

## Phase 3.6 — AI Coach Layer (High Impact for ELO Growth)

**Mission:** Bridge the gap between diagnosis (what the app already does) and improvement (what players actually need). The app currently says *what* is wrong. This phase makes it say *why* and *exactly what to do about it*.

### 3.6.1 LLM-Powered Personalised Coach Report
**Why:** Numbers alone don't change behaviour. A personalised narrative from an AI coach — written in plain English, using the player's actual game data — is far more actionable than template strings.

**How:**
- Add a "Generate AI Coach Report" button on the report page
- On click: POST to `/coach-report/<token>` — server serialises `AnalysisReport` to JSON and sends to LLM API
- Prompt includes: blunder rates, worst phase, loss types, struggling openings, blunder move range, W/D/L
- LLM returns: 400–500 word personalised report with specific study advice tied to the player's actual weaknesses
- Render result in a new card below the recommendations section
- Use Claude API (claude-haiku-4-5-20251001 for speed/cost, or claude-sonnet-4-6 for depth) or OpenAI GPT-4o
- API key stored in `.env` / Render environment variable — not committed

**Files:** `app.py` (new `/coach-report/<token>` route), `templates/report.html` (button + result card), `chess_analyzer/coach.py` (prompt builder + LLM call)

**Cost estimate:** ~$0.002–0.005 per report with Haiku. Negligible for a small public tool.

### 3.6.2 In-App Study Plan (Action Plan Tab)
**Why:** The report shows what to fix. The study plan shows *when* and *how* — turning analysis into a week-by-week improvement programme the player can actually follow inside the app.

**How:**
- Second tab on the report page: "Study Plan"
- LLM generates a 2–4 week plan based on the top 3 weaknesses: specific puzzle categories, opening lines to study, endgame drills
- Each task links to a Lichess resource: puzzle categories (`lichess.org/training/<theme>`), studies, opening explorer
- Player can check off tasks (localStorage persistence — no login needed)
- "Re-analyse in 2 weeks" reminder prompt shown at the top

**Files:** `templates/report.html` (tab UI + task checklist with localStorage), `chess_analyzer/coach.py` (extended prompt for study plan)

### 3.6.3 Progress Tracking (Return Visitor Flow)
**Why:** Without a feedback loop, players can't tell if they're improving on their specific weaknesses. This closes the loop.

**How:**
- After analysis, offer "Save this report" — generates a shareable/bookmarkable URL with the token persisted to disk (not just in-memory)
- On re-analysis of the same username: compare current report vs saved baseline — show deltas (blunders/game ↓ 0.4, win rate ↑ 6%)
- "You've improved your endgame error rate by 23% since your last analysis" type messaging
- No account/login needed — reports stored server-side keyed by username+date, or exported as JSON for the player to upload next time

**Files:** `app.py` (disk persistence for reports), `templates/report.html` (delta display), `chess_analyzer/diff.py` (report comparison logic)

### 3.6.4 Lichess Resource Deep-Links
**Why:** The recommendations currently say "study X" — this makes every recommendation a direct link the player can act on immediately.

**How:**
- Map each detected weakness to a Lichess resource URL:
  - Tactical themes → `https://lichess.org/training/<theme>` (fork, pin, skewer, etc.)
  - Opening family → `https://lichess.org/opening/<ECO-name>`
  - Endgame drill → `https://lichess.org/practice`
- These are static mappings in a `chess_analyzer/resources.py` dict — no LLM needed
- Render as clickable buttons next to each recommendation in the report

**Files:** `chess_analyzer/resources.py` (new, static mapping), `templates/report.html` (link buttons in recommendations)

---

## Phase 3.7 — UI/UX Design Overhaul (Professional Look & Feel)

**Goal:** Make the app look like it was designed by a real product team — not AI-generated or hobbyist. Reference: tools like Notion, Linear, Vercel dashboard — clean, opinionated, high-trust.

**Action:** Work session with Claude (design mode) to review and redesign the interface.

### What to bring to that session
- Screenshots of the current app (index, loading, report pages)
- Reference apps / design inspiration (e.g. chess24, lichess new UI, Sigma Chess, chessigma.com)
- Specific pain points: anything that "looks off", feels crowded, or feels generic

### Areas to audit and potentially redesign
1. **Typography** — font pairing, sizing scale, weight contrast; Playfair Display + Inter is decent but may not be distinctive enough
2. **Colour palette** — current green/dark feels chess-generic; a more considered accent colour + neutral system could feel premium
3. **Hero / report header** — W/D/L layout, username display, date range — could be a more impactful dashboard header
4. **Card hierarchy** — all cards look the same weight; a visual hierarchy (primary / secondary / tertiary) would guide the eye
5. **Opening table** — currently functional but plain; could use subtle row banding, sticky header, better column proportions
6. **Findings cards** (weaknesses/strengths) — the left-border treatment is good; badge, category label and tip box spacing could be tighter
7. **Mobile layout** — test on actual phone; 2-col grid stacking behaviour
8. **Loading page** — the animated knight + fact box is good; step indicator could be more polished (stepper component style)
9. **Empty/no-eval states** — currently a dashed box; could be a more intentional "no data" illustration or pattern
10. **Micro-details** — hover states, focus rings, link styles, divider lines, button radius consistency

### Outcome
A redesign spec or direct CSS/template changes that make the app feel production-grade, building trust with first-time visitors who don't know the tool yet.

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

1. **Deploy web app to Render.com** (Phase 3.2 — DONE in code, needs hosting setup)
   - Push to GitHub, connect repo to Render.com, deploy
   - Share URL with others

2. **Download Stockfish** when ready for full eval coverage
   - Windows: download from https://stockfishchess.org/download/
   - Add path to `.env` as `STOCKFISH_PATH=C:/path/to/stockfish.exe`
   - Unlocks blunder detection for 100% of games (currently ~60%)

---

## Notes on Making It Public
- All Lichess game data is public (Creative Commons license) — no legal issues
- Stockfish is open source (GPLv3) — freely distributable
- No Lichess API key needed for read-only game export
- Rate limits to respect: max 20 req/min to Lichess API (our tool already handles this)
- Consider adding a `--delay` flag so hosted versions can be polite to Lichess servers
