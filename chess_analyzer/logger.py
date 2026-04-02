"""
Maintains a persistent mistake log (mistake_log.md) that accumulates across runs.
- Auto section: updated by the tool after every run (stats, patterns, trends)
- Manual section: appended by Claude during game review sessions (preserved across runs)
"""
import json
import re
from datetime import datetime
from pathlib import Path

from .models import AnalysisReport

LOG_PATH = Path(__file__).parent.parent / "mistake_log.md"
HISTORY_PATH = Path(__file__).parent.parent / "run_history.json"
PATTERNS_PATH = Path(__file__).parent.parent / "core_patterns.json"


def update_log(report: AnalysisReport) -> None:
    """Called after every analysis run. Updates auto sections, preserves manual notes."""
    run_date = datetime.now().strftime("%Y-%m-%d")

    # Load run history — update today's entry if it exists, else append
    history = _load_history()
    today_entry = _run_to_dict(report, run_date)
    existing_dates = [r["date"] for r in history]
    if run_date in existing_dates:
        history[existing_dates.index(run_date)] = today_entry
    else:
        history.append(today_entry)
    _save_history(history)

    # Read existing manual notes (preserve them)
    manual_notes = _extract_manual_notes()

    # Rebuild the full log
    lines = _build_log(report, history, manual_notes, run_date)

    LOG_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"  Mistake log updated: {LOG_PATH.name}")


def upsert_core_pattern(
    name: str,
    description: str,
    game_id: str,
    move: str,
    instance_note: str,
) -> None:
    """
    Adds an occurrence to a named core pattern.
    Creates the pattern if it doesn't exist yet.
    Skips if the exact game_id + move combination already exists (deduplication).

    Args:
        name:          Short pattern name, e.g. "Pre-move Check Failure"
        description:   What this pattern means, e.g. "Moving without asking what opponent can do"
        game_id:       Lichess game ID, e.g. "kwYPjDnA"
        move:          Move number where it happened, e.g. "18"
        instance_note: What specifically happened, e.g. "Rb8 allowed Nc6 fork"
    """
    patterns = _load_patterns()
    today = datetime.now().strftime("%Y-%m-%d")

    # Find or create the pattern
    pattern = next((p for p in patterns if p["name"].lower() == name.lower()), None)
    if pattern is None:
        pattern = {
            "name": name,
            "description": description,
            "first_seen": today,
            "status": "active",
            "occurrences": [],
        }
        patterns.append(pattern)

    # Deduplicate by game_id + move
    already_exists = any(
        o["game_id"] == game_id and o["move"] == str(move)
        for o in pattern["occurrences"]
    )
    if not already_exists:
        pattern["occurrences"].append({
            "date": today,
            "game_id": game_id,
            "move": str(move),
            "note": instance_note,
        })

    _save_patterns(patterns)

    # Rebuild the log to reflect the update
    if LOG_PATH.exists():
        _rebuild_log_patterns_section(patterns)


def _rebuild_log_patterns_section(patterns: list[dict]) -> None:
    """Replaces just the Core Patterns section in the existing log."""
    if not LOG_PATH.exists():
        return
    content = LOG_PATH.read_text(encoding="utf-8")
    new_section = "\n".join(_build_core_patterns_section(patterns))

    if "## Core Patterns" in content:
        content = re.sub(
            r"## Core Patterns.*?(?=\n## |\Z)",
            new_section + "\n",
            content,
            flags=re.DOTALL,
        )
    else:
        # Insert before Manual Notes
        content = content.replace("## Manual Notes", new_section + "\n\n## Manual Notes")

    LOG_PATH.write_text(content, encoding="utf-8")


def append_manual_note(note: str) -> None:
    """
    Appends a timestamped manual observation to the manual notes section.
    Skips silently if an identical note already exists (deduplication).
    Called externally (e.g. by Claude during game review).
    """
    if not LOG_PATH.exists():
        print("No mistake_log.md found. Run the analysis tool first.")
        return

    content = LOG_PATH.read_text(encoding="utf-8")

    # Deduplicate: skip if the note text already exists in the log
    if note in content:
        return

    timestamp = datetime.now().strftime("%Y-%m-%d")
    new_entry = f"\n- **{timestamp}:** {note}"

    if "## Manual Notes" in content:
        content = content.replace(
            "## Manual Notes",
            f"## Manual Notes{new_entry}",
            1,
        )
    else:
        content += f"\n\n## Manual Notes{new_entry}\n"

    LOG_PATH.write_text(content, encoding="utf-8")


def _build_log(
    report: AnalysisReport,
    history: list[dict],
    manual_notes: str,
    run_date: str,
) -> list[str]:
    lines = [
        f"# Chess Mistake Log -- {report.username}",
        f"",
        f"> Auto-updated by the analysis tool. Manual Notes section is preserved across runs.",
        f"",
        f"---",
        f"",
    ]

    # ── Run history table ──
    lines += [
        "## Run History",
        "",
        "| Date | Games | W% | Blunders/game | Mistakes/game | Worst Phase | Eval Games |",
        "|------|-------|----|---------------|---------------|-------------|------------|",
    ]
    for r in history:
        lines.append(
            f"| {r['date']} | {r['games']} | {r['win_pct']}% "
            f"| {r['blunders_per_game']} | {r['mistakes_per_game']} "
            f"| {r['worst_phase']} | {r['eval_games']} |"
        )
    lines.append("")

    # ── Trend note ──
    if len(history) >= 2:
        prev = history[-2]
        curr = history[-1]
        delta = round(curr["blunders_per_game"] - prev["blunders_per_game"], 2)
        if delta < -0.1:
            trend = f"Blunders/game IMPROVED by {abs(delta)} since last run."
        elif delta > 0.1:
            trend = f"Blunders/game INCREASED by {delta} since last run -- review recent games."
        else:
            trend = "Blunders/game roughly stable since last run."
        lines += [f"> **Trend:** {trend}", ""]

    # ── Current weaknesses ──
    lines += ["## Active Weaknesses (latest run)", ""]
    if report.weaknesses:
        for i, p in enumerate(report.weaknesses, 1):
            lines += [
                f"### {i}. {p.category.replace('_', ' ').title()} [{p.severity.upper()}]",
                f"",
                f"{p.description}",
                f"",
                f"**Fix:** {p.recommendation}",
            ]
            if p.example_game_ids:
                links = "  ".join(
                    f"https://lichess.org/{gid}" for gid in p.example_game_ids
                )
                lines.append(f"**Examples:** {links}")
            lines.append("")
    else:
        lines += ["No significant weaknesses detected.", ""]

    # ── Current strengths ──
    lines += ["## Active Strengths (latest run)", ""]
    if report.strengths:
        for p in report.strengths:
            lines.append(f"- {p.description}")
        lines.append("")
    else:
        lines += ["Not enough data yet.", ""]

    # ── Opening breakdown snapshot ──
    qualifying = {k: v for k, v in report.opening_stats.items() if v.games_played >= 4}
    if qualifying:
        lines += [
            "## Opening Snapshot (latest run)",
            "",
            "| Opening | Games | Win% | Blunders/game | Verdict |",
            "|---------|-------|------|---------------|---------|",
        ]
        for s in sorted(qualifying.values(), key=lambda x: -x.games_played):
            if s.win_rate >= 0.58 and s.avg_blunders <= 1.2:
                verdict = "Strength"
            elif s.win_rate < 0.40 and s.avg_blunders >= 1.8:
                verdict = "Struggling"
            else:
                verdict = "Neutral"
            lines.append(
                f"| {s.family} | {s.games_played} | {int(s.win_rate*100)}% "
                f"| {s.avg_blunders:.1f} | {verdict} |"
            )
        lines.append("")

    # ── Core patterns (preserved, structured) ──
    patterns = _load_patterns()
    lines += _build_core_patterns_section(patterns)
    lines.append("")

    # ── Manual notes (preserved) ──
    lines += ["## Manual Notes", ""]
    if manual_notes.strip():
        # Strip the placeholder if it snuck in alongside real notes
        cleaned = manual_notes.replace(
            "_No manual notes yet. Claude will add observations here during game review sessions._", ""
        ).strip()
        lines.append(cleaned if cleaned else "_No manual notes yet._")
    else:
        lines.append("_No manual notes yet. Claude will add observations here during game review sessions._")
    lines.append("")

    return lines


def _build_core_patterns_section(patterns: list[dict]) -> list[str]:
    lines = ["## Core Patterns", ""]
    if not patterns:
        lines.append("_No patterns logged yet. Added by Claude during game review sessions._")
        return lines

    # ── Dashboard: one row per pattern, one column per session date ──
    all_dates = sorted({
        o["date"]
        for p in patterns
        for o in p["occurrences"]
    })

    if all_dates:
        header = "| Pattern | Status | Total | " + " | ".join(all_dates) + " | Trend |"
        sep    = "|---------|--------|-------|-" + "-|-".join("-" * len(d) for d in all_dates) + "-|-------|"
        lines += [
            "_Dashboard: occurrences per review session. Trend = last 2 sessions._",
            "",
            header,
            sep,
        ]
        for p in patterns:
            counts_by_date = {}
            for o in p["occurrences"]:
                counts_by_date[o["date"]] = counts_by_date.get(o["date"], 0) + 1
            total = sum(counts_by_date.values())
            cells = " | ".join(str(counts_by_date.get(d, 0)) for d in all_dates)
            # Trend: compare last two sessions that have data
            dated_counts = [(d, counts_by_date.get(d, 0)) for d in all_dates]
            non_zero = [(d, c) for d, c in dated_counts if c > 0]
            if len(non_zero) >= 2:
                trend = "improving" if non_zero[-1][1] < non_zero[-2][1] else (
                    "stable" if non_zero[-1][1] == non_zero[-2][1] else "worsening"
                )
            elif len(all_dates) >= 2 and non_zero and non_zero[-1][0] != all_dates[-1]:
                trend = "improving"  # had occurrences before but 0 in latest session
            else:
                trend = "new"
            status = p["status"].upper()
            lines.append(f"| {p['name']} | {status} | {total} | {cells} | {trend} |")
        lines.append("")

    # ── Detail: one subsection per pattern ──
    lines.append("### Details")
    lines.append("")
    for p in patterns:
        count = len(p["occurrences"])
        status_tag = "[ACTIVE]" if p["status"] == "active" else "[RESOLVED]"
        lines += [
            f"#### {p['name']} {status_tag}",
            f"**What:** {p['description']}",
            f"**First seen:** {p['first_seen']}  |  **Total occurrences:** {count}",
            f"",
            f"| Date | Game | Move | What happened |",
            f"|------|------|------|---------------|",
        ]
        for o in p["occurrences"]:
            lines.append(
                f"| {o['date']} | "
                f"[{o['game_id']}](https://lichess.org/{o['game_id']}) | "
                f"{o['move']} | {o['note']} |"
            )
        lines.append("")

    return lines


def _load_patterns() -> list[dict]:
    if not PATTERNS_PATH.exists():
        return []
    try:
        return json.loads(PATTERNS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _save_patterns(patterns: list[dict]) -> None:
    PATTERNS_PATH.write_text(json.dumps(patterns, indent=2), encoding="utf-8")


def _extract_manual_notes() -> str:
    """Reads and returns the Manual Notes section from the existing log."""
    if not LOG_PATH.exists():
        return ""
    content = LOG_PATH.read_text(encoding="utf-8")
    match = re.search(r"## Manual Notes\n(.*?)(?=\n## |\Z)", content, re.DOTALL)
    if not match:
        return ""
    return match.group(1).strip()


def _run_to_dict(report: AnalysisReport, run_date: str) -> dict:
    total = report.wins + report.draws + report.losses or 1
    worst_phase = (
        max(report.phase_error_rates, key=report.phase_error_rates.get)
        if report.phase_error_rates else "N/A"
    )
    return {
        "date": run_date,
        "games": report.games_analyzed,
        "win_pct": int(report.wins / total * 100),
        "blunders_per_game": round(report.blunders_per_game, 2),
        "mistakes_per_game": round(report.mistakes_per_game, 2),
        "worst_phase": worst_phase,
        "eval_games": report.games_with_evals,
    }


def _load_history() -> list[dict]:
    if not HISTORY_PATH.exists():
        return []
    try:
        return json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _save_history(history: list[dict]) -> None:
    HISTORY_PATH.write_text(
        json.dumps(history, indent=2), encoding="utf-8"
    )
