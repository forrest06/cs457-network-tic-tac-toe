"""The Tic-Tac-Toe rules kept separate from the socket code."""

from dataclasses import dataclass, field

WIN_LINES = (
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
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class MoveResult:
    player_id: str
    cell: int
    terminal: bool
    result: str | None = None
    winner: str | None = None
    reason: str | None = None


@dataclass
class GameState:
    game_id: str
    board: list = field(default_factory=lambda: [None] * 9)
    active_player: str | None = "Player_1"
    sequence: int = 0
    state: str = "PLAYER_TURN"
    scores_recorded: bool = False

    def apply_move(self, player_id, cell):
        if self.state != "PLAYER_TURN":
            raise MoveError("GAME_ALREADY_OVER", "The game is already over")
        if player_id != self.active_player:
            raise MoveError("WRONG_TURN", f"{self.active_player} must move next")
        if type(cell) is not int or not 1 <= cell <= 9:
            raise MoveError("OUT_OF_RANGE", "cell must be from 1 to 9")
        if self.board[cell - 1] is not None:
            raise MoveError("CELL_OCCUPIED", f"cell {cell} is already occupied")

        mark = "X" if player_id == "Player_1" else "O"
        self.board[cell - 1] = mark
        self.sequence += 1

        if self.has_won(mark):
            self.state = "GAME_OVER"
            self.active_player = None
            return MoveResult(
                player_id,
                cell,
                True,
                "WIN",
                player_id,
                "THREE_IN_A_ROW",
            )

        if None not in self.board:
            self.state = "GAME_OVER"
            self.active_player = None
            return MoveResult(player_id, cell, True, "DRAW", None, "BOARD_FULL")

        if player_id == "Player_1":
            self.active_player = "Player_2"
        else:
            self.active_player = "Player_1"
        return MoveResult(player_id, cell, False)

    def has_won(self, mark):
        for line in WIN_LINES:
            if all(self.board[index] == mark for index in line):
                return True
        return False
