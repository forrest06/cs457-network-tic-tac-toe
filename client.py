#!/usr/bin/env python3
"""Command-line client for the network Tic-Tac-Toe game."""

import argparse
import socket

from src.protocol import (
    NDJSONBuffer,
    ProtocolViolation,
    encode_message,
    unix_time,
)


def valid_port(value):
    try:
        port = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("port must be an integer") from error
    if not 1024 <= port <= 65535:
        raise argparse.ArgumentTypeError("port must be between 1024 and 65535")
    return port


def build_parser():
    parser = argparse.ArgumentParser(
        description="Connect to a Network Tic-Tac-Toe server.",
        epilog="Example: python3 client.py -i server.fisher.edu -p 45700",
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
    parser.add_argument("-n", "--name", dest="alias", help="player name")
    return parser


class GameClient:
    def __init__(self, server_ip, port, alias):
        self.server_ip = server_ip
        self.port = port
        self.alias = alias
        self.sock = None
        self.reader = NDJSONBuffer()
        self.pending = []
        self.game_id = None
        self.player_id = None
        self.board = [None] * 9
        self.active_player = None
        self.sequence = -1
        self.done = False

    def connect(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((self.server_ip, self.port))
        self.send(
            {
                "version": 1,
                "msg_type": "CONNECT",
                "alias": self.alias,
                "timestamp": unix_time(),
            }
        )
        print(f"Connected to {self.server_ip}:{self.port} as {self.alias}")

    def play(self):
        while not self.done:
            message = self.receive()
            kind = message.get("msg_type")

            if kind == "LOBBY_WAIT":
                self.game_id = message["game_id"]
                self.player_id = "Player_1"
                print("Assigned Player 1 (X)")
                print("Waiting for Player 2...")

            elif kind == "GAME_START":
                self.game_id = message["game_id"]
                if self.player_id is None:
                    # Only Player 1 gets LOBBY_WAIT, so this client is Player 2.
                    self.player_id = "Player_2"
                self.sequence = 0
                data = message["payload"]
                self.board = data["board"]
                self.active_player = data["active_player"]
                mark = data["roles"][self.player_id]
                print(f"\nGame started: {self.player_id} ({mark})")
                self.show_board()
                self.check_turn()

            elif kind == "STATE_UPDATE":
                if message["sequence"] <= self.sequence:
                    continue
                self.sequence = message["sequence"]
                data = message["payload"]
                self.board = data["board"]
                self.active_player = data["active_player"]
                last = data["last_move"]
                print(
                    f"\nMove {self.sequence}: {last['player_id']} "
                    f"played cell {last['cell']}"
                )
                self.show_board()
                self.check_turn()

            elif kind == "ERROR":
                data = message["payload"]
                print(f"[ERROR] {data['code']}: {data['message']}")
                if not data["recoverable"]:
                    self.done = True
                elif self.active_player == self.player_id:
                    self.ask_for_move()

            elif kind == "GAME_OVER":
                self.show_game_over(message)
                self.done = True

            else:
                raise ConnectionError(f"unexpected server message: {kind}")

    def receive(self):
        if self.pending:
            return self.pending.pop(0)
        while True:
            data = self.sock.recv(4096)
            if not data:
                raise ConnectionError("server closed the connection")
            for item in self.reader.feed(data):
                if isinstance(item, ProtocolViolation):
                    raise ConnectionError(item.message)
                self.pending.append(item)
            if self.pending:
                return self.pending.pop(0)

    def send(self, message):
        self.sock.sendall(encode_message(message))

    def check_turn(self):
        if self.active_player == self.player_id:
            print("Your Turn")
            self.ask_for_move()
        else:
            print(f"Waiting for {self.active_player}...")

    def ask_for_move(self):
        while not self.done:
            try:
                answer = input(
                    "Choose an empty cell (1-9), or q to quit: "
                ).strip()
            except EOFError:
                answer = "q"
            if answer.lower() in ("q", "quit"):
                self.disconnect()
                self.done = True
                return
            try:
                cell = int(answer)
            except ValueError:
                print("Please enter a number from 1 to 9.")
                continue
            if not 1 <= cell <= 9:
                print("Please enter a number from 1 to 9.")
                continue
            if self.board[cell - 1] is not None:
                print("That cell is already occupied.")
                continue
            self.send(
                {
                    "version": 1,
                    "msg_type": "MOVE",
                    "game_id": self.game_id,
                    "player_id": self.player_id,
                    "payload": {"cell": cell},
                    "timestamp": unix_time(),
                }
            )
            return

    def disconnect(self):
        if self.sock is None or self.game_id is None or self.player_id is None:
            return
        try:
            self.send(
                {
                    "version": 1,
                    "msg_type": "DISCONNECT",
                    "game_id": self.game_id,
                    "player_id": self.player_id,
                    "payload": {"reason": "QUIT"},
                    "timestamp": unix_time(),
                }
            )
        except OSError:
            pass

    def show_board(self):
        cells = [mark or str(index + 1) for index, mark in enumerate(self.board)]
        print(f" {cells[0]} | {cells[1]} | {cells[2]} ")
        print("---+---+---")
        print(f" {cells[3]} | {cells[4]} | {cells[5]} ")
        print("---+---+---")
        print(f" {cells[6]} | {cells[7]} | {cells[8]} ")

    def show_game_over(self, message):
        data = message["payload"]
        self.board = data["final_board"]
        print("\nFinal board:")
        self.show_board()
        if data["result"] == "DRAW":
            print("Game over: Draw")
        elif data["winner"] == self.player_id:
            print(f"Game over: You win ({data['reason']})")
        else:
            print(f"Game over: {data['winner']} wins ({data['reason']})")

        print("\nScore summary:")
        print("Rank  Player               W  L  D  F  Games")
        for row in data.get("leaderboard", []):
            print(
                f"{row['rank']:>4}  {row['alias']:<20} "
                f"{row['wins']:>2} {row['losses']:>2} "
                f"{row['draws']:>2} {row['forfeits']:>2} "
                f"{row['games_played']:>6}"
            )

    def close(self):
        if self.sock is not None:
            self.sock.close()


def get_alias(value):
    while True:
        if value is None:
            value = input("Player name (1-20 characters): ")
        alias = value.strip()
        if 1 <= len(alias) <= 20 and all(c.isprintable() for c in alias):
            return alias
        print("[ERROR] Name must contain 1-20 visible characters.")
        value = None


def main(argv=None):
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
        client.play()
    except KeyboardInterrupt:
        print("\nLeaving the game...")
        client.disconnect()
    except (ConnectionError, OSError, TimeoutError) as error:
        print(f"[ERROR] Network connection failed: {error}")
        return 1
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
