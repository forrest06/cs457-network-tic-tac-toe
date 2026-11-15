#!/usr/bin/env python3
"""Interactive command-line client for Network Tic-Tac-Toe."""

from __future__ import annotations

import argparse
import socket
import sys
from collections import deque
from typing import Any

from src.protocol import (
    NDJSONBuffer,
    PROTOCOL_VERSION,
    ProtocolViolation,
    encode_message,
    unix_time,
)

MIN_PORT = 1024
MAX_PORT = 65535
READ_SIZE = 4096


def valid_port(value: str) -> int:
    """Argparse type that accepts only non-privileged TCP ports."""

    try:
        port = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("port must be an integer") from exc
    if not MIN_PORT <= port <= MAX_PORT:
        raise argparse.ArgumentTypeError(
            f"port must be between {MIN_PORT} and {MAX_PORT}"
        )
    return port


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Connect to a Network Tic-Tac-Toe server.",
        epilog=(
            "Example: python3 client.py -i server.fisher.edu -p 45700"
        ),
    )
    parser.add_argument(
        "-i",
        "--host",
        dest="hostname",
        required=True,
        help="server DNS hostname or IP address",
    )
    parser.add_argument(
        "-p",
        "--port",
        required=True,
        type=valid_port,
        help="server TCP port (1024-65535)",
    )
    parser.add_argument(
        "-n",
        "--name",
        dest="alias",
        help="player alias (otherwise prompted)",
    )
    return parser


class GameClient:
    """Blocking CLI client with persistent NDJSON receive buffering."""

    def __init__(self, server_ip: str, port: int, alias: str) -> None:
        self.server_ip = server_ip
        self.port = port
        self.alias = alias
        self.sock: socket.socket | None = None
        self.framer = NDJSONBuffer()
        self.pending: deque[dict[str, Any]] = deque()
        self.game_id: str | None = None
        self.player_id: str | None = None
        self.board: list[str | None] = [None] * 9
        self.active_player: str | None = None
        self.sequence = -1
        self.game_finished = False

    def connect(self) -> None:
        """Create the required IPv4 TCP stream socket and connect."""

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((self.server_ip, self.port))
        self._send(
            {
                "version": PROTOCOL_VERSION,
                "msg_type": "CONNECT",
                "alias": self.alias,
                "timestamp": unix_time(),
            }
        )
        print(f"Connected to {self.server_ip}:{self.port} as {self.alias}")

    def run(self) -> None:
        """Receive server messages and prompt only when it is this player's turn."""

        while not self.game_finished:
            message = self._next_message()
            self._handle_message(message)

    def close(self) -> None:
        if self.sock is None:
            return
        try:
            self.sock.close()
        except OSError:
            pass
        self.sock = None

    def leave_game(self) -> None:
        """Send the graceful DISCONNECT message when a player quits."""

        if self.sock is None or self.game_id is None or self.player_id is None:
            return
        try:
            self._send(
                {
                    "version": PROTOCOL_VERSION,
                    "msg_type": "DISCONNECT",
                    "game_id": self.game_id,
                    "player_id": self.player_id,
                    "payload": {"reason": "QUIT"},
                    "timestamp": unix_time(),
                }
            )
            self.sock.shutdown(socket.SHUT_WR)
        except OSError:
            pass

    def _next_message(self) -> dict[str, Any]:
        if self.pending:
            return self.pending.popleft()
        if self.sock is None:
            raise ConnectionError("client socket is closed")

        while True:
            data = self.sock.recv(READ_SIZE)
            if not data:
                raise ConnectionError("server closed the connection")
            for item in self.framer.feed(data):
                if isinstance(item, ProtocolViolation):
                    raise ConnectionError(
                        f"server sent an invalid frame: {item.message}"
                    )
                self.pending.append(item)
            if self.pending:
                return self.pending.popleft()

    def _handle_message(self, message: dict[str, Any]) -> None:
        msg_type = message.get("msg_type")
        if msg_type == "LOBBY_WAIT":
            self.game_id = message["game_id"]
            self.player_id = message["player_id"]
            print("Assigned Player 1 (X)")
            print("Waiting for Player 2...")
        elif msg_type == "GAME_START":
            self._handle_game_start(message)
        elif msg_type == "STATE_UPDATE":
            self._handle_state_update(message)
        elif msg_type == "ERROR":
            self._handle_error(message)
        elif msg_type == "GAME_OVER":
            self._handle_game_over(message)
        else:
            raise ConnectionError(f"unexpected server message: {msg_type}")

    def _handle_game_start(self, message: dict[str, Any]) -> None:
        self.game_id = message["game_id"]
        if self.player_id is None:
            # Only Player 1 receives LOBBY_WAIT, so the other client is Player 2.
            self.player_id = "Player_2"
        self.sequence = message["sequence"]
        payload = message["payload"]
        self.board = payload["board"]
        self.active_player = payload["active_player"]
        mark = payload["roles"][self.player_id]
        print(f"\nGame started: {self.player_id} ({mark})")
        self._show_board()
        self._show_turn_and_maybe_move()

    def _handle_state_update(self, message: dict[str, Any]) -> None:
        sequence = message["sequence"]
        if sequence <= self.sequence:
            print(f"Ignored stale state update {sequence}")
            return
        self.sequence = sequence
        payload = message["payload"]
        self.board = payload["board"]
        self.active_player = payload["active_player"]
        last_move = payload["last_move"]
        print(
            f"\nMove {sequence}: {last_move['player_id']} "
            f"played cell {last_move['cell']}"
        )
        self._show_board()
        self._show_turn_and_maybe_move()

    def _handle_error(self, message: dict[str, Any]) -> None:
        payload = message["payload"]
        print(f"[ERROR] {payload['code']}: {payload['message']}")
        if not payload["recoverable"]:
            self.game_finished = True
            return
        if self.active_player == self.player_id:
            self._prompt_and_send_move()

    def _handle_game_over(self, message: dict[str, Any]) -> None:
        self.sequence = message["sequence"]
        payload = message["payload"]
        self.board = payload["final_board"]
        self.active_player = None
        print("\nFinal board:")
        self._show_board()
        if payload["result"] == "DRAW":
            print("Game over: Draw")
        elif payload["winner"] == self.player_id:
            print(f"Game over: You win ({payload['reason']})")
        else:
            print(
                f"Game over: {payload['winner']} wins "
                f"({payload['reason']})"
            )
        self._show_scores(payload.get("leaderboard", []))
        self.game_finished = True

    def _show_turn_and_maybe_move(self) -> None:
        if self.active_player == self.player_id:
            print("Your Turn")
            self._prompt_and_send_move()
        else:
            print(f"Waiting for {self.active_player}...")

    def _prompt_and_send_move(self) -> None:
        while True:
            try:
                raw_value = input("Choose an empty cell (1-9), or q to quit: ").strip()
            except EOFError:
                print("\nInput ended; leaving the game.")
                self.leave_game()
                self.game_finished = True
                return
            if raw_value.lower() in {"q", "quit"}:
                self.leave_game()
                self.game_finished = True
                return
            try:
                cell = int(raw_value)
            except ValueError:
                print("Please enter a number from 1 to 9.")
                continue
            if not 1 <= cell <= 9:
                print("Please enter a number from 1 to 9.")
                continue
            if self.board[cell - 1] is not None:
                print("That cell is already occupied.")
                continue
            self._send(
                {
                    "version": PROTOCOL_VERSION,
                    "msg_type": "MOVE",
                    "game_id": self.game_id,
                    "player_id": self.player_id,
                    "payload": {"cell": cell},
                    "timestamp": unix_time(),
                }
            )
            return

    def _send(self, message: dict[str, Any]) -> None:
        if self.sock is None:
            raise ConnectionError("client socket is closed")
        self.sock.sendall(encode_message(message))

    def _show_board(self) -> None:
        cells = [
            value if value is not None else str(index + 1)
            for index, value in enumerate(self.board)
        ]
        print(f" {cells[0]} | {cells[1]} | {cells[2]} ")
        print("---+---+---")
        print(f" {cells[3]} | {cells[4]} | {cells[5]} ")
        print("---+---+---")
        print(f" {cells[6]} | {cells[7]} | {cells[8]} ")

    @staticmethod
    def _show_scores(rows: list[dict[str, Any]]) -> None:
        print("\nScore summary:")
        if not rows:
            print("No scores available")
            return
        print("Rank  Player               W  L  D  F  Games")
        for row in rows:
            print(
                f"{row['rank']:>4}  {row['alias']:<20} "
                f"{row['wins']:>2} {row['losses']:>2} "
                f"{row['draws']:>2} {row['forfeits']:>2} "
                f"{row['games_played']:>6}"
            )


def normalize_alias(value: str) -> str:
    alias = value.strip()
    if not 1 <= len(alias) <= 20 or not all(char.isprintable() for char in alias):
        raise ValueError("alias must contain 1-20 visible characters")
    return alias


def get_alias(argument_value: str | None) -> str:
    if argument_value is not None:
        return normalize_alias(argument_value)
    while True:
        try:
            return normalize_alias(input("Player name (1-20 characters): "))
        except ValueError as exc:
            print(f"[ERROR] {exc}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        server_ip = socket.gethostbyname(args.hostname)
    except socket.gaierror:
        print(f"[ERROR] Unable to resolve DNS hostname '{args.hostname}'.")
        print(
            "Please check your Cisco router DNS configuration "
            "('ip dns server' / 'ip host') or verify domain spelling."
        )
        return 1

    try:
        alias = get_alias(args.alias)
    except (EOFError, KeyboardInterrupt):
        print("\nClient cancelled.")
        return 1

    client = GameClient(server_ip, args.port, alias)
    try:
        client.connect()
        client.run()
    except KeyboardInterrupt:
        print("\nLeaving the game...")
        client.leave_game()
    except (ConnectionError, ConnectionRefusedError, TimeoutError, OSError) as exc:
        print(f"[ERROR] Network connection failed: {exc}")
        return 1
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
