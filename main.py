"""
Chess game analysis tool for Lichess players.

Usage:
    python main.py                          # uses LICHESS_USERNAME from .env
    python main.py --games 150              # fetch 150 games (default: 100)
    python main.py --output both            # terminal + chess_report.md
    python main.py --cache                  # cache PGN to avoid re-fetching
    python main.py --username someuser      # override username from .env
"""
import argparse
import os
import sys

from dotenv import load_dotenv

load_dotenv()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyse your Lichess games to find patterns, weaknesses and strengths.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--username", "-u",
        default=os.getenv("LICHESS_USERNAME", ""),
        help="Lichess username (default: LICHESS_USERNAME from .env)",
    )
    parser.add_argument(
        "--games", "-n",
        type=int,
        default=100,
        help="Number of recent blitz games to fetch (default: 100, max: 200)",
    )
    parser.add_argument(
        "--perf",
        default="rapid",
        choices=["bullet", "blitz", "rapid", "classical"],
        help="Game variant to analyse (default: rapid)",
    )
    parser.add_argument(
        "--output",
        default="terminal",
        choices=["terminal", "markdown", "both"],
        help="Report format (default: terminal)",
    )
    parser.add_argument(
        "--output-file",
        default="chess_report.md",
        help="Markdown output file path (default: chess_report.md)",
    )
    parser.add_argument(
        "--cache",
        action="store_true",
        help="Cache fetched PGN and reuse if <24h old (useful when iterating)",
    )
    args = parser.parse_args()

    if not args.username:
        print(
            "ERROR: No Lichess username provided.\n"
            "Set LICHESS_USERNAME in .env or pass --username <name>",
            file=sys.stderr,
        )
        sys.exit(1)

    args.games = min(max(args.games, 1), 200)

    # ── Imports here so errors surface cleanly before work begins ──
    from chess_analyzer.fetcher   import fetch_games
    from chess_analyzer.parser    import parse_game
    from chess_analyzer.analyzer  import compute_eval_deltas, aggregate_games
    from chess_analyzer.patterns  import detect_patterns
    from chess_analyzer.report    import print_terminal_report, write_markdown_report
    from chess_analyzer.logger    import update_log

    # 1. Fetch
    print(f"\nFetching up to {args.games} {args.perf} games for '{args.username}'...")
    try:
        pgn_blocks = fetch_games(
            username=args.username,
            max_games=args.games,
            perf_type=args.perf,
            use_cache=args.cache,
        )
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    if not pgn_blocks:
        print(f"No {args.perf} games found for '{args.username}'. "
              "Check the username or try a different --perf type.")
        sys.exit(0)

    print(f"Fetched {len(pgn_blocks)} games. Parsing...")

    # 2. Parse
    games = []
    for pgn in pgn_blocks:
        record = parse_game(pgn, args.username)
        if record is not None:
            games.append(record)

    print(f"Parsed {len(games)} valid games. Running analysis...")

    # 3. Compute eval deltas
    games = [compute_eval_deltas(g) for g in games]

    games_with_evals = sum(1 for g in games if g.has_evals)
    if games_with_evals == 0:
        print(
            "\nWARNING: None of your fetched games have computer analysis data.\n"
            "Error-rate analysis will be skipped.\n"
            "To get eval data, request computer analysis on Lichess after your games,\n"
            "or play analysed games (Lichess sometimes auto-analyses games).\n"
            "Opening win rates and time stats will still be shown.\n"
        )
    elif games_with_evals < 20:
        print(
            f"\nWARNING: Only {games_with_evals}/{len(games)} games have eval data. "
            "Pattern analysis may be limited.\n"
        )

    # 4. Aggregate + detect patterns
    report = aggregate_games(games, args.username)
    report = detect_patterns(report, games)

    # 5. Output
    if args.output in ("terminal", "both"):
        print_terminal_report(report)

    if args.output in ("markdown", "both"):
        write_markdown_report(report, args.output_file)
        print(f"\nMarkdown report saved to: {args.output_file}")

    update_log(report)

    print(f"\nDone. Analysed {len(games)} games ({games_with_evals} with eval data).\n")


if __name__ == "__main__":
    main()
