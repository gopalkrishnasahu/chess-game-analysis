# Chess Mistake Log -- gopal_krishna_sahu

> Auto-updated by the analysis tool. Manual Notes section is preserved across runs.

---

## Run History

| Date | Games | W% | Blunders/game | Mistakes/game | Worst Phase | Eval Games |
|------|-------|----|---------------|---------------|-------------|------------|
| 2026-04-01 | 43 | 58% | 1.24 | 2.16 | middlegame | 25 |

## Active Weaknesses (latest run)

### 1. Early Middlegame [CRITICAL]

8 blunders on moves 15-25 (the transition out of the opening)

**Fix:** You're struggling in the early middlegame transition (moves 15-25). After leaving your opening preparation, pause and ask: 'What is my opponent threatening?' before each move. Tactical puzzles focused on move 15-25 positions will help.
**Examples:** https://lichess.org/kwYPjDnA  https://lichess.org/WJCnWkyZ  https://lichess.org/tXqTZsFl

### 2. Piece Handling [MODERATE]

King moves account for 25% of your blunders but only 8% of your moves

**Fix:** Be more careful when moving your king. Before each king move, verify: can it be captured? Does it leave another piece hanging?

## Active Strengths (latest run)

- Sicilian Defense: 8W-0D-4L (66% win rate, 0.6 blunders/game)

## Opening Snapshot (latest run)

| Opening | Games | Win% | Blunders/game | Verdict |
|---------|-------|------|---------------|---------|
| Sicilian Defense | 12 | 66% | 0.6 | Strength |
| Queen's Gambit Declined | 10 | 50% | 0.2 | Neutral |
| Slav Defense | 5 | 60% | 1.6 | Neutral |

## Core Patterns

_Dashboard: occurrences per review session. Trend = last 2 sessions._

| Pattern | Status | Total | 2026-04-01 | Trend |
|---------|--------|-------|------------|-------|
| Pre-move Check Failure | ACTIVE | 3 | 3 | new |

### Details

#### Pre-move Check Failure [ACTIVE]
**What:** Moving without asking 'what can my opponent do next?' -- leads to missing opponent's tactical threats
**First seen:** 2026-04-01  |  **Total occurrences:** 3

| Date | Game | Move | What happened |
|------|------|------|---------------|
| 2026-04-01 | [kwYPjDnA](https://lichess.org/kwYPjDnA) | 18 | Played Rb8 without checking opponent replies. White responded Nc6! forking queen and rook. Had a winning position, lost in one move. |
| 2026-04-01 | [WJCnWkyZ](https://lichess.org/WJCnWkyZ) | 16 | Auto-recaptured Bxe5 without scanning board. Missed fxe4 winning a free knight (Black still had Ne4 attacked by f-pawn). |
| 2026-04-01 | [WJCnWkyZ](https://lichess.org/WJCnWkyZ) | 20 | Played aggressive Rc7 without verifying it works. Black replied Qxd5 winning a pawn, rook stranded. Position collapsed in 3 moves. |


## Manual Notes

- **2026-04-01:** Game WJCnWkyZ (White vs vpstudio05, Slav): Move 20 -- played aggressive Rc7 without calculating Qxd5 response. Position collapsed in 3 moves (Qe2, Be4 both blunders trying to rescue stranded rook). Pattern: launched attack without verifying it works tactically.
- **2026-04-01:** Game WJCnWkyZ (White vs vpstudio05, Slav): Move 16 -- after 15...Nxe5, played automatic Bxe5 recapture. Missed 16.fxe4! winning a free knight (Black still had Ne4 on the board attacked by f3 pawn). Pattern: auto-recapture without scanning the board first.
- **2026-04-01:** Game kwYPjDnA (Black vs brimgels, QGD Exchange): Had winning advantage as Black throughout. Played 18...Rb8 without asking what opponent can do. White responded 19.Nc6! -- knight fork hitting queen on e7 and threatening rook. Lost immediately. Pattern: move made without pre-move check.
