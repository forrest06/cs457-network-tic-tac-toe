"""Localhost integration test for two clients and a complete game."""

from __future__ import annotations

import socket
import subprocess
import sys
import time
import unittest
from collections import deque
from pathlib import Path
from typing import Any

from src.protocol import NDJSONBuffer, ProtocolViolation, encode_message, unix_time

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class WireClient:
    def __init__(self, port: int, alias: str) -> None:
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(3)
        self.sock.connect(("127.0.0.1", port))
        self.framer = NDJSONBuffer()
        self.pending: deque[dict[str, Any]] = deque()
        self.alias = alias
        self.send(
            {
                "version": 1,
                "msg_type": "CONNECT",
                "alias": alias,
                "timestamp": unix_time(),
            }
        )

    def send(self, message: dict[str, Any]) -> None:
        self.sock.sendall(encode_message(message))

    def receive(self) -> dict[str, Any]:
        if self.pending:
            return self.pending.popleft()
        while True:
            data = self.sock.recv(4096)
            if not data:
                raise AssertionError("server closed before sending expected message")
            for item in self.framer.feed(data):
                if isinstance(item, ProtocolViolation):
                    raise AssertionError(item.message)
                self.pending.append(item)
            if self.pending:
                return self.pending.popleft()

    def move(self, game_id: str, player_id: str, cell: int) -> None:
        self.send(
            {
                "version": 1,
                "msg_type": "MOVE",
                "game_id": game_id,
                "player_id": player_id,
                "payload": {"cell": cell},
                "timestamp": unix_time(),
            }
        )

    def close(self) -> None:
        self.sock.close()


def unused_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class MultiplayerIntegrationTests(unittest.TestCase):
    def test_two_clients_complete_five_turn_game(self) -> None:
        port = unused_port()
        process = subprocess.Popen(
            [sys.executable, "server.py", "-p", str(port)],
            cwd=PROJECT_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        first = None
        second = None
        try:
            self._wait_for_server(process)
            first = WireClient(port, "Alice")
            self.assertEqual(first.receive()["msg_type"], "LOBBY_WAIT")
            second = WireClient(port, "Bob")

            start_one = first.receive()
            start_two = second.receive()
            self.assertEqual(start_one["msg_type"], "GAME_START")
            self.assertEqual(start_one, start_two)
            game_id = start_one["game_id"]

            # Player 2 cannot move before Player 1, and the game stays usable.
            second.move(game_id, "Player_2", 4)
            wrong_turn = second.receive()
            self.assertEqual(wrong_turn["msg_type"], "ERROR")
            self.assertEqual(wrong_turn["payload"]["code"], "WRONG_TURN")

            moves = (
                (first, "Player_1", 1),
                (second, "Player_2", 4),
                (first, "Player_1", 2),
                (second, "Player_2", 5),
            )
            for sequence, (player, player_id, cell) in enumerate(moves, start=1):
                player.move(game_id, player_id, cell)
                update_one = first.receive()
                update_two = second.receive()
                self.assertEqual(update_one, update_two)
                self.assertEqual(update_one["msg_type"], "STATE_UPDATE")
                self.assertEqual(update_one["sequence"], sequence)

            first.move(game_id, "Player_1", 3)
            final_one = first.receive()
            final_two = second.receive()
            self.assertEqual(final_one, final_two)
            self.assertEqual(final_one["msg_type"], "GAME_OVER")
            self.assertEqual(final_one["sequence"], 5)
            self.assertEqual(final_one["payload"]["winner"], "Player_1")
            self.assertEqual(len(final_one["payload"]["leaderboard"]), 2)
        finally:
            if first is not None:
                first.close()
            if second is not None:
                second.close()
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
            if process.stdout is not None:
                process.stdout.close()

    @staticmethod
    def _wait_for_server(process: subprocess.Popen[str]) -> None:
        if process.stdout is None:
            raise AssertionError("server output pipe is unavailable")
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            line = process.stdout.readline()
            if "Listening on 0.0.0.0" in line:
                return
            if process.poll() is not None:
                raise AssertionError(f"server exited early: {line}")
        raise AssertionError("server did not start in time")


if __name__ == "__main__":
    unittest.main()
