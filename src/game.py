"""Pure server-authoritative Tic-Tac-Toe state and move rules."""

from __future__ import annotations

from dataclasses import dataclass, field

WINNING_LINES = (
    (0, 1, 2),
    (3, 4, 5),
    (6, 7, 8),
    (0, 3, 6),
    (1, 4, 7),
    (2, 5, 8),
    (0, 4, 8),
    (2, 4, 6),
)


class MoveError(ValueError):
    """A rejected move with its protocol ERROR code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class MoveResult:
    """State produced by one accepted move."""

    player_id: str
    cell: int
    terminal: bool
    result: str | None = None
    winner: str | None = None
    reason: str | None = None


@dataclass
class GameState:
    """The canonical state for one two-player game."""

    game_id: str
    board: list[str | None] = field(default_factory=lambda: [None] * 9)
    active_player: str | None = "Player_1"
    sequence: int = 0
    state: str = "PLAYER_TURN"
    scores_recorded: bool = False

    def apply_move(self, player_id: str, cell: int) -> MoveResult:
        """Validate and apply one move without allowing partial mutation."""

        if self.state != "PLAYER_TURN":
            raise MoveError("GAME_ALREADY_OVER", "The game is already over")
        if player_id != self.active_player:
            raise MoveError(
                "WRONG_TURN",
                f"{self.active_player} must move next",
            )
        if type(cell) is not int or not 1 <= cell <= 9:
            raise MoveError("OUT_OF_RANGE", "cell must be an integer from 1 to 9")
        index = cell - 1
        if self.board[index] is not None:
            raise MoveError("CELL_OCCUPIED", f"cell {cell} is already occupied")

        mark = "X" if player_id == "Player_1" else "O"
        self.board[index] = mark
        self.sequence += 1

        if self._has_winner(mark):
            self.state = "GAME_OVER"
            self.active_player = None
            return MoveResult(
                player_id=player_id,
                cell=cell,
                terminal=True,
                result="WIN",
                winner=player_id,
                reason="THREE_IN_A_ROW",
            )

        if all(value is not None for value in self.board):
            self.state = "GAME_OVER"
            self.active_player = None
            return MoveResult(
                player_id=player_id,
                cell=cell,
                terminal=True,
                result="DRAW",
                winner=None,
                reason="BOARD_FULL",
            )

        self.active_player = "Player_2" if player_id == "Player_1" else "Player_1"
        return MoveResult(player_id=player_id, cell=cell, terminal=False)

    def _has_winner(self, mark: str) -> bool:
        return any(
            all(self.board[index] == mark for index in line)
            for line in WINNING_LINES
        )
