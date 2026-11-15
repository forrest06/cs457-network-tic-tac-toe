#!/usr/bin/env python3
"""Selector-based server for two-player network Tic-Tac-Toe."""

import argparse
import selectors
import socket
import sys
from dataclasses import dataclass, field

from src.game import GameState, MoveError
from src.protocol import (
    MessageValidationError,
    NDJSONBuffer,
    ProtocolViolation,
    encode_message,
    make_error,
    unix_time,
    validate_connect,
    validate_disconnect,
    validate_envelope,
    validate_move,
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
        description="Run the Network Tic-Tac-Toe server.",
        epilog="Example: python3 server.py -p 45700",
    )
    parser.add_argument(
        "-p",
        "--port",
        required=True,
        type=valid_port,
        help="TCP listening port (1024-65535)",
    )
    return parser


@dataclass
class Client:
    sock: socket.socket
    address: tuple
    reader: NDJSONBuffer = field(default_factory=NDJSONBuffer)
    output: bytearray = field(default_factory=bytearray)
    alias: str | None = None
    player_id: str | None = None
    closing: bool = False


class GameServer:
    def __init__(self, port):
        self.port = port
        self.selector = selectors.DefaultSelector()
        self.listener = None
        self.clients = {}
        self.players = {}
        self.scores = {}
        self.game_number = 1
        self.game = None
        self.running = True

    @property
    def game_id(self):
        return f"game-{self.game_number:03d}"

    def run(self):
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listener.bind(("0.0.0.0", self.port))
        self.listener.listen()
        self.listener.setblocking(False)
        self.selector.register(self.listener, selectors.EVENT_READ)

        self.log(f"Listening on 0.0.0.0:{self.port}")
        self.log(f"Waiting for Player 1 ({self.game_id})")
        try:
            while self.running:
                for key, mask in self.selector.select(timeout=1):
                    if key.fileobj is self.listener:
                        self.accept_clients()
                    else:
                        self.service_client(key.data, mask)
        except KeyboardInterrupt:
            self.log("Shutdown requested")
        finally:
            self.close()

    def accept_clients(self):
        while True:
            try:
                sock, address = self.listener.accept()
            except BlockingIOError:
                return
            sock.setblocking(False)
            client = Client(sock, address)
            self.clients[sock] = client
            self.selector.register(sock, selectors.EVENT_READ, client)
            self.log(f"TCP connection from {address[0]}:{address[1]}")

    def service_client(self, client, mask):
        if client.sock not in self.clients:
            return
        if mask & selectors.EVENT_READ and not client.closing:
            self.read_client(client)
        if client.sock in self.clients and mask & selectors.EVENT_WRITE:
            self.write_client(client)

    def read_client(self, client):
        while client.sock in self.clients and not client.closing:
            try:
                data = client.sock.recv(4096)
            except BlockingIOError:
                return
            except OSError:
                self.disconnect_client(client, "CONNECTION_LOST")
                return

            if not data:
                self.disconnect_client(client, "CONNECTION_LOST")
                return

            for item in client.reader.feed(data):
                if isinstance(item, ProtocolViolation):
                    self.send_error(
                        client,
                        item.code,
                        item.message,
                        item.recoverable,
                    )
                    if not item.recoverable:
                        return
                else:
                    self.handle_message(client, item)
                    if client.sock not in self.clients or client.closing:
                        return

    def write_client(self, client):
        if not client.output:
            self.update_events(client)
            return
        try:
            sent = client.sock.send(client.output)
        except BlockingIOError:
            return
        except OSError:
            self.disconnect_client(client, "CONNECTION_LOST")
            return
        if sent == 0:
            self.disconnect_client(client, "CONNECTION_LOST")
            return
        del client.output[:sent]
        self.update_events(client)

    def handle_message(self, client, message):
        try:
            kind = validate_envelope(message)
        except MessageValidationError as error:
            self.send_validation_error(client, error)
            return

        if client.player_id is None:
            if kind == "CONNECT":
                self.connect_player(client, message)
            else:
                self.send_error(
                    client,
                    "UNEXPECTED_MESSAGE",
                    "Send CONNECT first",
                )
            return

        if kind == "MOVE":
            self.play_move(client, message)
        elif kind == "DISCONNECT":
            self.handle_quit(client, message)
        else:
            self.send_error(
                client,
                "UNEXPECTED_MESSAGE",
                f"{kind} is not allowed here",
            )

    def connect_player(self, client, message):
        try:
            alias = validate_connect(message)
        except MessageValidationError as error:
            self.send_validation_error(client, error)
            return

        if len(self.players) == 2:
            self.send_error(
                client,
                "SERVER_FULL",
                "Two players are already connected",
                False,
            )
            return
        if any(player.alias == alias for player in self.players.values()):
            self.send_error(client, "INVALID_PAYLOAD", "That name is in use")
            return

        player_id = "Player_1" if not self.players else "Player_2"
        client.alias = alias
        client.player_id = player_id
        self.players[player_id] = client
        self.score_row(alias)
        self.log(f"{player_id} joined as {alias}")

        if player_id == "Player_1":
            self.queue(
                client,
                {
                    "version": 1,
                    "msg_type": "LOBBY_WAIT",
                    "game_id": self.game_id,
                    "player_id": "Player_1",
                    "payload": {
                        "mark": "X",
                        "players_connected": 1,
                        "message": "Waiting for Player 2",
                    },
                    "timestamp": unix_time(),
                },
            )
            return

        self.game = GameState(self.game_id)
        self.broadcast(
            {
                "version": 1,
                "msg_type": "GAME_START",
                "game_id": self.game.game_id,
                "sequence": 0,
                "payload": {
                    "roles": {"Player_1": "X", "Player_2": "O"},
                    "board": list(self.game.board),
                    "active_player": "Player_1",
                },
                "timestamp": unix_time(),
            }
        )
        self.log(f"{self.game.game_id} started; Player_1 moves first")

    def play_move(self, client, message):
        try:
            cell = validate_move(message)
        except MessageValidationError as error:
            self.send_validation_error(client, error)
            return

        if self.game is None:
            self.send_error(client, "UNEXPECTED_MESSAGE", "Game has not started")
            return
        if message["game_id"] != self.game.game_id:
            self.send_error(client, "INVALID_PAYLOAD", "Wrong game_id")
            return
        if message["player_id"] != client.player_id:
            self.send_error(client, "INVALID_PAYLOAD", "Wrong player_id")
            return

        try:
            result = self.game.apply_move(client.player_id, cell)
        except MoveError as error:
            self.send_error(client, error.code, error.message)
            self.log(f"Rejected {client.player_id} move: {error.code}")
            return

        self.log(
            f"Accepted move {self.game.sequence}: "
            f"{client.player_id} chose cell {cell}"
        )
        if result.terminal:
            self.finish_game(result.result, result.winner, result.reason)
            return

        self.broadcast(
            {
                "version": 1,
                "msg_type": "STATE_UPDATE",
                "game_id": self.game.game_id,
                "sequence": self.game.sequence,
                "payload": {
                    "board": list(self.game.board),
                    "last_move": {
                        "player_id": result.player_id,
                        "cell": result.cell,
                    },
                    "active_player": self.game.active_player,
                },
                "timestamp": unix_time(),
            }
        )
        self.log(
            f"Broadcast STATE_UPDATE sequence {self.game.sequence}; "
            f"next turn {self.game.active_player}"
        )

    def handle_quit(self, client, message):
        try:
            validate_disconnect(message)
        except MessageValidationError as error:
            self.send_validation_error(client, error)
            return
        if message["player_id"] != client.player_id:
            self.send_error(client, "INVALID_PAYLOAD", "Wrong player_id")
            return
        if self.game and message["game_id"] != self.game.game_id:
            self.send_error(client, "INVALID_PAYLOAD", "Wrong game_id")
            return
        self.disconnect_client(client, "PLAYER_QUIT")

    def finish_game(self, result, winner, reason):
        self.record_scores(result, winner)
        message = self.game_over_message(result, winner, reason)
        self.broadcast(message)
        self.log(f"GAME_OVER {result}; winner={winner}")
        for client in list(self.players.values()):
            client.closing = True
            self.update_events(client)

    def disconnect_client(self, client, reason):
        if client.sock not in self.clients:
            return
        player_id = client.player_id
        self.log(f"Disconnected {player_id or client.address}: {reason}")

        opponent_id = None
        if player_id == "Player_1":
            opponent_id = "Player_2"
        elif player_id == "Player_2":
            opponent_id = "Player_1"
        opponent = self.players.get(opponent_id)

        if self.game and self.game.state == "PLAYER_TURN" and opponent:
            self.game.state = "GAME_OVER"
            self.game.active_player = None
            self.record_scores("FORFEIT", opponent_id)
            self.queue(
                opponent,
                self.game_over_message("FORFEIT", opponent_id, reason),
            )
            opponent.closing = True
            self.update_events(opponent)
            self.log(f"GAME_OVER FORFEIT; winner={opponent_id}")

        self.close_client(client)

    def send_validation_error(self, client, error):
        self.send_error(client, error.code, error.message, error.recoverable)

    def send_error(self, client, code, text, recoverable=True):
        game_id = None
        if self.game is not None and client.player_id is not None:
            game_id = self.game.game_id
        self.queue(
            client,
            make_error(code, text, game_id, client.player_id, recoverable),
        )
        if not recoverable and client.sock in self.clients:
            client.closing = True
            self.update_events(client)

    def broadcast(self, message):
        """Serialize once, then give the same frame to both clients."""
        frame = encode_message(message)
        for player_id in ("Player_1", "Player_2"):
            client = self.players.get(player_id)
            if client:
                self.queue_frame(client, frame)

    def queue(self, client, message):
        self.queue_frame(client, encode_message(message))

    def queue_frame(self, client, frame):
        if client.sock not in self.clients:
            return
        if len(client.output) + len(frame) > 65536:
            self.disconnect_client(client, "CONNECTION_LOST")
            return
        client.output.extend(frame)
        self.update_events(client)

    def update_events(self, client):
        if client.sock not in self.clients:
            return
        events = 0 if client.closing else selectors.EVENT_READ
        if client.output:
            events |= selectors.EVENT_WRITE
        if events == 0:
            self.close_client(client)
            return
        try:
            self.selector.modify(client.sock, events, client)
        except (KeyError, OSError):
            self.close_client(client)

    def close_client(self, client, reset=True):
        if client.sock not in self.clients:
            return
        try:
            self.selector.unregister(client.sock)
        except (KeyError, OSError):
            pass
        self.clients.pop(client.sock, None)
        if client.player_id:
            self.players.pop(client.player_id, None)
        client.sock.close()
        if reset and client.player_id and not self.players:
            self.game = None
            self.game_number += 1
            self.log(f"Waiting for Player 1 ({self.game_id})")

    def record_scores(self, result, winner):
        if self.game is None or self.game.scores_recorded:
            return
        first = self.players.get("Player_1")
        second = self.players.get("Player_2")
        if not first or not second:
            return
        one = self.score_row(first.alias)
        two = self.score_row(second.alias)
        one["games_played"] += 1
        two["games_played"] += 1

        if result == "DRAW":
            one["draws"] += 1
            two["draws"] += 1
        else:
            winner_client = self.players[winner]
            loser_client = second if winner == "Player_1" else first
            self.scores[winner_client.alias]["wins"] += 1
            self.scores[loser_client.alias]["losses"] += 1
            if result == "FORFEIT":
                self.scores[loser_client.alias]["forfeits"] += 1
        self.game.scores_recorded = True

    def score_row(self, alias):
        if alias not in self.scores:
            self.scores[alias] = {
                "wins": 0,
                "losses": 0,
                "draws": 0,
                "forfeits": 0,
                "games_played": 0,
            }
        return self.scores[alias]

    def leaderboard(self):
        rows = sorted(
            self.scores.items(),
            key=lambda item: (
                -item[1]["wins"],
                item[1]["losses"],
                item[0].lower(),
            ),
        )
        return [
            {"rank": rank, "alias": alias, **score}
            for rank, (alias, score) in enumerate(rows, 1)
        ]

    def game_over_message(self, result, winner, reason):
        return {
            "version": 1,
            "msg_type": "GAME_OVER",
            "game_id": self.game.game_id,
            "sequence": self.game.sequence,
            "payload": {
                "result": result,
                "winner": winner,
                "reason": reason,
                "final_board": list(self.game.board),
                "active_player": None,
                "leaderboard": self.leaderboard(),
            },
            "timestamp": unix_time(),
        }

    def close(self):
        self.running = False
        for client in list(self.clients.values()):
            self.close_client(client, reset=False)
        if self.listener is not None:
            try:
                self.selector.unregister(self.listener)
            except (KeyError, OSError):
                pass
            self.listener.close()
        self.selector.close()
        self.log("Server stopped")

    @staticmethod
    def log(message):
        print(f"[SERVER] {message}", flush=True)


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        GameServer(args.port).run()
    except OSError as error:
        print(
            f"[ERROR] Unable to bind server to 0.0.0.0:{args.port}: {error}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
