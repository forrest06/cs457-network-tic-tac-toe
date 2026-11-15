"""Tests for server-authoritative Tic-Tac-Toe rules."""

import unittest

from src.game import GameState, MoveError


class GameStateTests(unittest.TestCase):
    def test_out_of_turn_move_does_not_change_state(self) -> None:
        game = GameState("game-001")

        with self.assertRaises(MoveError) as context:
            game.apply_move("Player_2", 1)

        self.assertEqual(context.exception.code, "WRONG_TURN")
        self.assertEqual(game.board, [None] * 9)
        self.assertEqual(game.sequence, 0)
        self.assertEqual(game.active_player, "Player_1")

    def test_occupied_cell_does_not_consume_turn(self) -> None:
        game = GameState("game-001")
        game.apply_move("Player_1", 1)

        with self.assertRaises(MoveError) as context:
            game.apply_move("Player_2", 1)

        self.assertEqual(context.exception.code, "CELL_OCCUPIED")
        self.assertEqual(game.sequence, 1)
        self.assertEqual(game.active_player, "Player_2")

    def test_five_moves_produce_player_one_win(self) -> None:
        game = GameState("game-001")
        moves = (
            ("Player_1", 1),
            ("Player_2", 4),
            ("Player_1", 2),
            ("Player_2", 5),
            ("Player_1", 3),
        )

        result = None
        for player_id, cell in moves:
            result = game.apply_move(player_id, cell)

        self.assertIsNotNone(result)
        self.assertTrue(result.terminal)
        self.assertEqual(result.result, "WIN")
        self.assertEqual(result.winner, "Player_1")
        self.assertEqual(game.sequence, 5)
        self.assertEqual(game.state, "GAME_OVER")

    def test_nine_moves_can_produce_draw(self) -> None:
        game = GameState("game-001")
        cells = (1, 2, 3, 5, 4, 6, 8, 7, 9)

        result = None
        for index, cell in enumerate(cells):
            player_id = "Player_1" if index % 2 == 0 else "Player_2"
            result = game.apply_move(player_id, cell)

        self.assertIsNotNone(result)
        self.assertEqual(result.result, "DRAW")
        self.assertIsNone(result.winner)


if __name__ == "__main__":
    unittest.main()
