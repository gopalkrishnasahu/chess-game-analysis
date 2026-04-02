"""
Generates the analysis report.
- Terminal output: uses the `rich` library for colour and formatting.
- Markdown output: writes chess_report.md.
"""
import sys
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box
from rich.text import Text

from .models import AnalysisReport, OpeningStats, PatternFinding

LICHESS_GAME_URL = "https://lichess.org/"

console = Console(force_terminal=True, highlight=False)

_TABLE_BOX = box.SIMPLE_HEAD if sys.platform == "win32" else box.SIMPLE


# --------------------------------------------
# Terminal report
# --------------------------------------------

def print_terminal_report(report: AnalysisReport) -> None:
    console.print()
    _print_header(report)
    _print_performance(report)
    _print_phase_breakdown(report)
    _print_openings(report)
    _print_weaknesses(report)
    _print_strengths(report)
    _print_time_management(report)
    _print_recommendations(report)
    console.print()


def _print_header(report: AnalysisReport) -> None:
    start, end = report.date_range
    subtitle = f"{report.games_analyzed} games  |  {end} to {start}"
    if report.games_with_evals < report.games_analyzed:
        subtitle += f"  |  [yellow]{report.games_with_evals} with eval data[/yellow]"
    console.print(Panel(
        f"[bold cyan]CHESS ANALYSIS REPORT: {report.username.upper()}[/bold cyan]\n"
        f"[dim]{subtitle}[/dim]",
        box=box.DOUBLE_EDGE,
        expand=False,
    ))


def _print_performance(report: AnalysisReport) -> None:
    total = report.wins + report.draws + report.losses or 1
    win_pct  = int(report.wins   / total * 100)
    draw_pct = int(report.draws  / total * 100)
    loss_pct = int(report.losses / total * 100)

    console.print("\n[bold]OVERALL PERFORMANCE[/bold]")
    console.print(
        f"  Win/Draw/Loss:    [green]{report.wins}W[/green] / "
        f"[yellow]{report.draws}D[/yellow] / "
        f"[red]{report.losses}L[/red]  "
        f"([green]{win_pct}%[/green] / {draw_pct}% / [red]{loss_pct}%[/red])"
    )
    if report.losses > 0:
        parts = []
        if report.losses_by_time > 0:
            parts.append(f"[red]{report.losses_by_time} on time[/red]")
        if report.losses_by_collapse > 0:
            parts.append(f"[yellow]{report.losses_by_collapse} tactical collapse[/yellow]")
        if report.losses_by_resignation_clean > 0:
            parts.append(f"{report.losses_by_resignation_clean} outplayed")
        if parts:
            console.print(f"  Loss breakdown:  {' / '.join(parts)}")
    if report.games_with_evals > 0:
        console.print(
            f"  Blunders/game:   [red]{report.blunders_per_game:.1f}[/red]   "
            f"Mistakes/game: [yellow]{report.mistakes_per_game:.1f}[/yellow]   "
            f"Inaccuracies/game: "
            f"{report.total_inaccuracies / max(1, report.games_with_evals):.1f}"
        )


def _print_phase_breakdown(report: AnalysisReport) -> None:
    rates = report.phase_error_rates
    if not rates:
        return
    console.print("\n[bold]PHASE BREAKDOWN[/bold]  [dim](serious errors per 10 moves)[/dim]")
    phases = ["opening", "middlegame", "endgame"]
    worst  = max(rates, key=rates.get) if rates else None
    for phase in phases:
        rate = rates.get(phase, 0.0)
        bar  = "#" * max(1, int(rate * 3))
        tag  = " [bold red]<-- WORST[/bold red]" if phase == worst else ""
        colour = "red" if rate >= 3.0 else ("yellow" if rate >= 1.5 else "green")
        console.print(f"  {phase.capitalize():<12} [{colour}]{rate:.1f}  {bar}[/{colour}]{tag}")


def _print_openings(report: AnalysisReport) -> None:
    MIN_GAMES = 4
    qualifying = {k: v for k, v in report.opening_stats.items() if v.games_played >= MIN_GAMES}
    if not qualifying:
        return

    console.print("\n[bold]OPENING BREAKDOWN[/bold]  [dim](>=4 games)[/dim]")

    table = Table(box=_TABLE_BOX, show_header=True, header_style="bold")
    table.add_column("Opening",          style="cyan",   min_width=28)
    table.add_column("Games",            justify="right")
    table.add_column("W/D/L",            justify="center")
    table.add_column("Win%",             justify="right")
    table.add_column("Blunders/game",    justify="right")
    table.add_column("As",               justify="center")

    sorted_openings = sorted(qualifying.values(), key=lambda s: -s.games_played)
    for s in sorted_openings:
        win_pct = int(s.win_rate * 100)
        win_col = (
            f"[green]{win_pct}%[/green]" if win_pct >= 55
            else f"[red]{win_pct}%[/red]" if win_pct < 40
            else f"{win_pct}%"
        )
        blunder_col = (
            f"[red]{s.avg_blunders:.1f}[/red]" if s.avg_blunders >= 2.0
            else f"[green]{s.avg_blunders:.1f}[/green]" if s.avg_blunders < 1.0
            else f"{s.avg_blunders:.1f}"
        )
        sides = []
        if s.as_white: sides.append(f"W:{s.as_white}")
        if s.as_black: sides.append(f"B:{s.as_black}")
        table.add_row(
            s.family[:30],
            str(s.games_played),
            f"{s.wins}/{s.draws}/{s.losses}",
            win_col,
            blunder_col,
            " ".join(sides),
        )
    console.print(table)


def _print_weaknesses(report: AnalysisReport) -> None:
    if not report.weaknesses:
        return
    console.print("\n[bold red]WEAKNESSES[/bold red]  [dim](address these first)[/dim]")
    for i, p in enumerate(report.weaknesses, 1):
        sev_colour = {"critical": "red", "moderate": "yellow", "minor": "dim"}.get(p.severity, "white")
        console.print(f"\n  [bold]{i}. [{sev_colour}]{p.category.upper().replace('_', ' ')}[/{sev_colour}][/bold]")
        console.print(f"     {p.description}")
        if p.example_game_ids:
            links = "  ".join(f"{LICHESS_GAME_URL}{gid}" for gid in p.example_game_ids)
            console.print(f"     [dim]Examples: {links}[/dim]")


def _print_strengths(report: AnalysisReport) -> None:
    if not report.strengths:
        return
    console.print("\n[bold green]STRENGTHS[/bold green]  [dim](keep doing these)[/dim]")
    for p in report.strengths:
        console.print(f"  + {p.description}")


def _print_time_management(report: AnalysisReport) -> None:
    has_time_data = any([
        report.avg_time_opening,
        report.avg_time_middlegame,
        report.avg_time_endgame,
    ])
    if not has_time_data:
        return
    console.print("\n[bold]TIME MANAGEMENT[/bold]")
    if report.avg_time_opening:
        console.print(f"  Avg seconds/move:  Opening {report.avg_time_opening:.1f}s  |  "
                      f"Middlegame {report.avg_time_middlegame:.1f}s  |  "
                      f"Endgame {report.avg_time_endgame:.1f}s")
    if report.time_pressure_blunders > 0:
        console.print(
            f"  Time-pressure blunders: [red]{report.time_pressure_blunders}[/red] "
            f"across {report.time_pressure_games} games"
        )


def _print_recommendations(report: AnalysisReport) -> None:
    if not report.recommendations:
        return
    console.print("\n[bold]RECOMMENDATIONS[/bold]  [dim](ordered by impact)[/dim]")
    for i, rec in enumerate(report.recommendations, 1):
        label = Text(f"\n  {i}. ", style="bold cyan")
        body  = Text(rec)
        console.print(label + body)


# --------------------------------------------
# Markdown report
# --------------------------------------------

def write_markdown_report(report: AnalysisReport, output_path: str) -> None:
    lines: list[str] = []
    start, end = report.date_range

    lines += [
        f"# Chess Analysis Report: {report.username}",
        f"",
        f"**Games analyzed:** {report.games_analyzed}  "
        f"| **With eval data:** {report.games_with_evals}  "
        f"| **Period:** {end} to {start}",
        f"",
        f"---",
        f"",
        f"## Overall Performance",
        f"",
        f"| Metric | Value |",
        f"|--------|-------|",
    ]
    total = report.wins + report.draws + report.losses or 1
    lines += [
        f"| Win / Draw / Loss | {report.wins}W / {report.draws}D / {report.losses}L ({int(report.wins/total*100)}% win rate) |",
    ]
    if report.losses > 0:
        loss_parts = []
        if report.losses_by_time > 0:
            loss_parts.append(f"{report.losses_by_time} on time")
        if report.losses_by_collapse > 0:
            loss_parts.append(f"{report.losses_by_collapse} tactical collapse")
        if report.losses_by_resignation_clean > 0:
            loss_parts.append(f"{report.losses_by_resignation_clean} outplayed cleanly")
        if loss_parts:
            lines.append(f"| Loss breakdown | {' / '.join(loss_parts)} |")
    lines += [
        f"| Blunders per game | {report.blunders_per_game:.2f} |",
        f"| Mistakes per game | {report.mistakes_per_game:.2f} |",
        f"| Inaccuracies per game | {report.total_inaccuracies / max(1, report.games_with_evals):.2f} |",
        f"",
    ]

    # Phase breakdown
    if report.phase_error_rates:
        lines += ["## Phase Breakdown (serious errors per 10 moves)", ""]
        worst = max(report.phase_error_rates, key=report.phase_error_rates.get)
        for phase in ("opening", "middlegame", "endgame"):
            rate = report.phase_error_rates.get(phase, 0.0)
            tag  = " <-- **WORST**" if phase == worst else ""
            lines.append(f"- **{phase.capitalize()}**: {rate:.1f}{tag}")
        lines.append("")

    # Openings
    qualifying = {k: v for k, v in report.opening_stats.items() if v.games_played >= 4}
    if qualifying:
        lines += [
            "## Opening Breakdown",
            "",
            "| Opening | Games | W/D/L | Win% | Blunders/game | As W/B |",
            "|---------|-------|-------|------|---------------|--------|",
        ]
        for s in sorted(qualifying.values(), key=lambda x: -x.games_played):
            sides = f"W:{s.as_white}/B:{s.as_black}"
            lines.append(
                f"| {s.family} | {s.games_played} | {s.wins}/{s.draws}/{s.losses} "
                f"| {int(s.win_rate*100)}% | {s.avg_blunders:.1f} | {sides} |"
            )
        lines.append("")

    # Weaknesses
    if report.weaknesses:
        lines += ["## Weaknesses", ""]
        for i, p in enumerate(report.weaknesses, 1):
            lines += [
                f"### {i}. {p.category.replace('_', ' ').title()} ({p.severity})",
                f"",
                f"{p.description}",
            ]
            if p.example_game_ids:
                links = ", ".join(f"[{gid}]({LICHESS_GAME_URL}{gid})" for gid in p.example_game_ids)
                lines.append(f"\n**Examples:** {links}")
            lines += [f"", f"> **Tip:** {p.recommendation}", f""]

    # Strengths
    if report.strengths:
        lines += ["## Strengths", ""]
        for p in report.strengths:
            lines.append(f"- {p.description}")
        lines.append("")

    # Recommendations
    if report.recommendations:
        lines += ["## Recommendations (ordered by impact)", ""]
        for i, rec in enumerate(report.recommendations, 1):
            lines.append(f"{i}. {rec}")
        lines.append("")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
