from dataclasses import dataclass, field
from typing import Optional


@dataclass
class MoveRecord:
    move_number: int          # full-move number (1, 2, 3...)
    color: bool               # chess.WHITE (True) or chess.BLACK (False)
    san: str                  # e.g. "Nf3"
    uci: str                  # e.g. "g1f3"
    eval_before: Optional[float]   # eval in pawns before this move (White's perspective)
    eval_after: Optional[float]    # eval in pawns after this move (White's perspective)
    eval_delta: Optional[float]    # centipawn loss for the player who moved (always >= 0)
    clock_remaining: Optional[float]  # seconds remaining after this move
    time_spent: Optional[float]       # seconds spent on this move
    phase: str                # "opening" | "middlegame" | "endgame"
    is_blunder: bool = False      # eval_delta >= 3.00
    is_mistake: bool = False      # eval_delta >= 1.00
    is_inaccuracy: bool = False   # eval_delta >= 0.50


@dataclass
class OpeningStats:
    family: str
    games_played: int
    wins: int
    draws: int
    losses: int
    total_blunders: int
    total_mistakes: int
    games_with_evals: int
    eval_sum_at_move10: float   # sum for averaging (White's perspective, adjusted for color)
    as_white: int
    as_black: int

    @property
    def win_rate(self) -> float:
        return self.wins / self.games_played if self.games_played else 0.0

    @property
    def avg_blunders(self) -> float:
        return self.total_blunders / self.games_played if self.games_played else 0.0

    @property
    def avg_mistakes(self) -> float:
        return self.total_mistakes / self.games_played if self.games_played else 0.0

    @property
    def avg_eval_at_move10(self) -> Optional[float]:
        if self.games_with_evals == 0:
            return None
        return self.eval_sum_at_move10 / self.games_with_evals


@dataclass
class PatternFinding:
    category: str          # e.g. "time_pressure", "endgame_conversion", "opening_struggle"
    description: str
    frequency: int         # how many times this pattern appeared
    severity: str          # "critical" | "moderate" | "minor"
    example_game_ids: list[str]
    recommendation: str


@dataclass
class AnalysisReport:
    username: str
    games_analyzed: int
    games_with_evals: int
    date_range: tuple[str, str]

    # overall performance
    wins: int
    draws: int
    losses: int

    # error rates
    total_blunders: int
    total_mistakes: int
    total_inaccuracies: int
    blunders_per_game: float
    mistakes_per_game: float

    # phase breakdown: errors per 10 moves by phase
    phase_error_rates: dict[str, float]   # {"opening": X, "middlegame": X, "endgame": X}

    # opening analysis
    opening_stats: dict[str, OpeningStats]   # keyed by opening family name

    # time management
    time_pressure_games: int     # games where player had <15s with blunders
    time_pressure_blunders: int
    avg_time_opening: Optional[float]    # seconds per move
    avg_time_middlegame: Optional[float]
    avg_time_endgame: Optional[float]

    # pattern findings
    weaknesses: list[PatternFinding]
    strengths: list[PatternFinding]
    recommendations: list[str]

    # loss type breakdown (defaulted — populated by analyzer.py)
    losses_by_time: int = 0               # termination == "Time forfeit"
    losses_by_collapse: int = 0           # not time, has evals, >= 2 blunders in game
    losses_by_resignation_clean: int = 0  # residual (outplayed or no eval data)

    # blunder spike (defaulted — set by patterns.py)
    blunder_spike_range: Optional[str] = None   # e.g. "moves 6-10"
    blunder_spike_count: int = 0
    blunder_spike_pct: float = 0.0

    # data source (defaulted — set by app.py after analysis)
    source: str = "lichess"   # "lichess" | "chesscom" | "pgn"


@dataclass
class GameRecord:
    game_id: str
    white: str
    black: str
    result: str                  # "1-0" | "0-1" | "1/2-1/2" | "*"
    player_color: bool           # chess.WHITE or chess.BLACK
    player_won: bool
    player_drew: bool
    termination: str             # "Normal" | "Time forfeit" | "Abandoned"
    eco: str                     # "B13"
    opening_name: str            # full opening string from PGN header
    opening_family: str          # part before ":" or full name if no ":"
    time_control: str            # "180+2"
    date: str
    moves: list[MoveRecord] = field(default_factory=list)
    has_evals: bool = False
    lost_by_time: bool = False
