#!/usr/bin/env python3
"""Non-blocking two-player Network Tic-Tac-Toe server."""

from __future__ import annotations

import argparse
import selectors
import socket
import sys
from dataclasses import dataclass, field
from types import TracebackType
from typing import Any

from src.game import GameState, MoveError, MoveResult
from src.protocol import (
    NDJSONBuffer,
    MessageValidationError,
    ProtocolViolation,
    encode_message,
    make_error,
    unix_time,
    validate_connect,
    validate_disconnect,
    validate_envelope,
    validate_move,
)

MIN_PORT = 1024
MAX_PORT = 65535
READ_SIZE = 4096
MAX_SEND_BUFFER = 65536


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
        description="Run the Network Tic-Tac-Toe game server.",
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
class ClientSession:
    """Per-socket buffers and the identity assigned by the server."""

    sock: socket.socket
    address: tuple[str, int]
    framer: NDJSONBuffer = field(default_factory=NDJSONBuffer)
    send_buffer: bytearray = field(default_factory=bytearray)
    alias: str | None = None
    player_id: str | None = None
    closing_after_flush: bool = False


class GameServer:
    """Selector-based server that owns one game at a time."""

    def __init__(self, port: int) -> None:
        self.port = port
        self.selector = selectors.DefaultSelector()
        self.listener: socket.socket | None = None
        self.sessions: dict[socket.socket, ClientSession] = {}
        self.players: dict[str, ClientSession] = {}
        self.leaderboard: dict[str, dict[str, int]] = {}
        self.game_number = 1
        self.game: GameState | None = None
        self.running = False

    @property
    def current_game_id(self) -> str:
        return f"game-{self.game_number:03d}"

    def run(self) -> None:
        """Bind to all IPv4 interfaces and service ready sockets."""

        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listener.bind(("0.0.0.0", self.port))
        self.listener.listen()
        self.listener.setblocking(False)
        self.selector.register(self.listener, selectors.EVENT_READ, data=None)
        self.running = True
        self._log(f"Listening on 0.0.0.0:{self.port}")
        self._log(f"Waiting for Player 1 ({self.current_game_id})")

        try:
            while self.running:
                for key, mask in self.selector.select(timeout=1.0):
                    if key.data is None:
                        self._accept_connections()
                    else:
                        self._service_client(key.data, mask)
        except KeyboardInterrupt:
            self._log("Shutdown requested")
        finally:
            self.close()

    def close(self) -> None:
        """Close every socket without creating extra game results."""

        self.running = False
        for session in list(self.sessions.values()):
            self._close_session(session, reset_when_empty=False)
        if self.listener is not None:
            try:
                self.selector.unregister(self.listener)
            except (KeyError, ValueError):
                pass
            self.listener.close()
            self.listener = None
        self.selector.close()
        self._log("Server stopped")

    def _accept_connections(self) -> None:
        if self.listener is None:
            return
        while True:
            try:
                client_socket, address = self.listener.accept()
            except BlockingIOError:
                return
            except OSError as exc:
                self._log(f"Accept failed: {exc}")
                return
            client_socket.setblocking(False)
            session = ClientSession(client_socket, address)
            self.sessions[client_socket] = session
            self.selector.register(client_socket, selectors.EVENT_READ, session)
            self._log(f"TCP connection from {address[0]}:{address[1]}")

    def _service_client(self, session: ClientSession, mask: int) -> None:
        if session.sock not in self.sessions:
            return
        if mask & selectors.EVENT_READ and not session.closing_after_flush:
            self._read_client(session)
        if session.sock not in self.sessions:
            return
        if mask & selectors.EVENT_WRITE:
            self._write_client(session)

    def _read_client(self, session: ClientSession) -> None:
        while session.sock in self.sessions and not session.closing_after_flush:
            try:
                data = session.sock.recv(READ_SIZE)
            except BlockingIOError:
                return
            except (
                ConnectionResetError,
                ConnectionAbortedError,
                BrokenPipeError,
                TimeoutError,
                OSError,
            ):
                self._handle_disconnect(session, "CONNECTION_LOST")
                return

            if not data:
                self._handle_disconnect(session, "CONNECTION_LOST")
                return

            for item in session.framer.feed(data):
                if isinstance(item, ProtocolViolation):
                    self._send_error(
                        session,
                        item.code,
                        item.message,
                        item.recoverable,
                    )
                    if not item.recoverable:
                        return
                else:
                    self._dispatch(session, item)
                    if session.sock not in self.sessions or session.closing_after_flush:
                        return

    def _write_client(self, session: ClientSession) -> None:
        if not session.send_buffer:
            if session.closing_after_flush:
                self._close_session(session)
            else:
                self._update_interest(session)
            return
        try:
            sent = session.sock.send(session.send_buffer)
        except BlockingIOError:
            return
        except (
            ConnectionResetError,
            ConnectionAbortedError,
            BrokenPipeError,
            TimeoutError,
            OSError,
        ):
            self._handle_disconnect(session, "CONNECTION_LOST")
            return
        if sent == 0:
            self._handle_disconnect(session, "CONNECTION_LOST")
            return
        del session.send_buffer[:sent]
        if not session.send_buffer and session.closing_after_flush:
            self._close_session(session)
        elif session.sock in self.sessions:
            self._update_interest(session)

    def _dispatch(self, session: ClientSession, message: dict[str, Any]) -> None:
        try:
            msg_type = validate_envelope(message)
        except MessageValidationError as exc:
            self._send_error(
                session,
                exc.code,
                exc.message,
                exc.recoverable,
            )
            return

        if session.player_id is None:
            if msg_type != "CONNECT":
                self._send_error(
                    session,
                    "UNEXPECTED_MESSAGE",
                    "CONNECT is required before any other message",
                )
                return
            self._handle_connect(session, message)
            return

        if msg_type == "MOVE":
            self._handle_move(session, message)
        elif msg_type == "DISCONNECT":
            self._handle_disconnect_message(session, message)
        else:
            self._send_error(
                session,
                "UNEXPECTED_MESSAGE",
                f"{msg_type} is not a valid client message now",
            )

    def _handle_connect(
        self,
        session: ClientSession,
        message: dict[str, Any],
    ) -> None:
        try:
            alias = validate_connect(message)
        except MessageValidationError as exc:
            self._send_error(session, exc.code, exc.message, exc.recoverable)
            return

        if len(self.players) >= 2:
            self._send_error(
                session,
                "SERVER_FULL",
                "Two players are already connected",
                recoverable=False,
            )
            return
        if any(player.alias == alias for player in self.players.values()):
            self._send_error(
                session,
                "INVALID_PAYLOAD",
                "That alias is already in use",
            )
            return

        player_id = "Player_1" if "Player_1" not in self.players else "Player_2"
        session.alias = alias
        session.player_id = player_id
        self.players[player_id] = session
        self._ensure_score_row(alias)
        self._log(f"{player_id} joined as {alias}")

        if player_id == "Player_1":
            self._queue_message(
                session,
                {
                    "version": 1,
                    "msg_type": "LOBBY_WAIT",
                    "game_id": self.current_game_id,
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

        self.game = GameState(self.current_game_id)
        start_message = {
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
        self._broadcast(start_message)
        self._log(f"{self.game.game_id} started; Player_1 moves first")

    def _handle_move(
        self,
        session: ClientSession,
        message: dict[str, Any],
    ) -> None:
        try:
            cell = validate_move(message)
        except MessageValidationError as exc:
            self._send_error(session, exc.code, exc.message, exc.recoverable)
            return

        if self.game is None:
            self._send_error(
                session,
                "UNEXPECTED_MESSAGE",
                "The game has not started",
            )
            return
        if message["game_id"] != self.game.game_id:
            self._send_error(
                session,
                "INVALID_PAYLOAD",
                "game_id does not match this game",
            )
            return
        if message["player_id"] != session.player_id:
            self._send_error(
                session,
                "INVALID_PAYLOAD",
                "player_id does not match this socket",
            )
            return

        try:
            result = self.game.apply_move(session.player_id, cell)
        except MoveError as exc:
            self._send_error(session, exc.code, exc.message)
            self._log(f"Rejected {session.player_id} move: {exc.code}")
            return

        self._log(
            f"Accepted move {self.game.sequence}: "
            f"{session.player_id} chose cell {cell}"
        )
        if result.terminal:
            self._finish_game(result)
        else:
            update = {
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
            self._broadcast(update)
            self._log(
                f"Broadcast STATE_UPDATE sequence {self.game.sequence}; "
                f"next turn {self.game.active_player}"
            )

    def _handle_disconnect_message(
        self,
        session: ClientSession,
        message: dict[str, Any],
    ) -> None:
        try:
            validate_disconnect(message)
        except MessageValidationError as exc:
            self._send_error(session, exc.code, exc.message, exc.recoverable)
            return
        if self.game is not None and message["game_id"] != self.game.game_id:
            self._send_error(
                session,
                "INVALID_PAYLOAD",
                "game_id does not match this game",
            )
            return
        if message["player_id"] != session.player_id:
            self._send_error(
                session,
                "INVALID_PAYLOAD",
                "player_id does not match this socket",
            )
            return
        self._handle_disconnect(session, "PLAYER_QUIT")

    def _finish_game(self, result: MoveResult) -> None:
        if self.game is None:
            return
        self._record_scores(result.result, result.winner)
        message = self._game_over_message(
            result=result.result or "DRAW",
            winner=result.winner,
            reason=result.reason or "BOARD_FULL",
        )
        self._broadcast(message)
        self._log(
            f"GAME_OVER {message['payload']['result']}; "
            f"winner={message['payload']['winner']}"
        )
        self._close_players_after_flush()

    def _handle_disconnect(self, session: ClientSession, reason: str) -> None:
        if session.sock not in self.sessions:
            return
        player_id = session.player_id
        alias = session.alias
        self._log(f"Disconnected {player_id or session.address}: {reason}")

        opponent_id = None
        if player_id == "Player_1":
            opponent_id = "Player_2"
        elif player_id == "Player_2":
            opponent_id = "Player_1"
        opponent = self.players.get(opponent_id) if opponent_id else None

        if (
            self.game is not None
            and self.game.state == "PLAYER_TURN"
            and opponent is not None
        ):
            self.game.state = "GAME_OVER"
            self.game.active_player = None
            self._record_scores("FORFEIT", opponent_id)
            final_message = self._game_over_message(
                result="FORFEIT",
                winner=opponent_id,
                reason=reason,
            )
            self._queue_message(opponent, final_message)
            opponent.closing_after_flush = True
            self._update_interest(opponent)
            self._log(
                f"GAME_OVER FORFEIT; winner={opponent_id}; "
                f"departed={alias or player_id}"
            )

        self._close_session(session)

    def _send_error(
        self,
        session: ClientSession,
        code: str,
        message: str,
        recoverable: bool = True,
    ) -> None:
        game_id = (
            self.game.game_id
            if self.game is not None and session.player_id is not None
            else None
        )
        self._queue_message(
            session,
            make_error(
                code,
                message,
                game_id,
                session.player_id,
                recoverable,
            ),
        )
        if not recoverable and session.sock in self.sessions:
            session.closing_after_flush = True
            self._update_interest(session)

    def _broadcast(self, message: dict[str, Any]) -> None:
        """Queue exactly the same serialized frame for both player sockets."""

        frame = encode_message(message)
        for player_id in ("Player_1", "Player_2"):
            session = self.players.get(player_id)
            if session is not None:
                self._queue_frame(session, frame)

    def _queue_message(
        self,
        session: ClientSession,
        message: dict[str, Any],
    ) -> None:
        self._queue_frame(session, encode_message(message))

    def _queue_frame(self, session: ClientSession, frame: bytes) -> None:
        if session.sock not in self.sessions:
            return
        if len(session.send_buffer) + len(frame) > MAX_SEND_BUFFER:
            self._handle_disconnect(session, "CONNECTION_LOST")
            return
        session.send_buffer.extend(frame)
        self._update_interest(session)

    def _update_interest(self, session: ClientSession) -> None:
        if session.sock not in self.sessions:
            return
        events = 0 if session.closing_after_flush else selectors.EVENT_READ
        if session.send_buffer:
            events |= selectors.EVENT_WRITE
        if events == 0:
            self._close_session(session)
            return
        try:
            self.selector.modify(session.sock, events, session)
        except (KeyError, ValueError, OSError):
            self._close_session(session)

    def _close_players_after_flush(self) -> None:
        for session in list(self.players.values()):
            if session.sock in self.sessions:
                session.closing_after_flush = True
                self._update_interest(session)

    def _close_session(
        self,
        session: ClientSession,
        reset_when_empty: bool = True,
    ) -> None:
        if session.sock not in self.sessions:
            return
        try:
            self.selector.unregister(session.sock)
        except (KeyError, ValueError, OSError):
            pass
        self.sessions.pop(session.sock, None)
        if session.player_id is not None:
            self.players.pop(session.player_id, None)
        try:
            session.sock.close()
        except OSError:
            pass
        session.send_buffer.clear()
        session.framer.buffer.clear()
        if reset_when_empty and session.player_id is not None and not self.players:
            self._reset_game()

    def _reset_game(self) -> None:
        self.game = None
        self.game_number += 1
        self._log(f"Waiting for Player 1 ({self.current_game_id})")

    def _record_scores(self, result: str | None, winner: str | None) -> None:
        if self.game is None or self.game.scores_recorded:
            return
        first = self.players.get("Player_1")
        second = self.players.get("Player_2")
        if (
            first is None
            or second is None
            or first.alias is None
            or second.alias is None
        ):
            return
        first_score = self._ensure_score_row(first.alias)
        second_score = self._ensure_score_row(second.alias)
        first_score["games_played"] += 1
        second_score["games_played"] += 1
        if result == "DRAW":
            first_score["draws"] += 1
            second_score["draws"] += 1
        else:
            winner_session = self.players.get(winner or "")
            loser_session = second if winner == "Player_1" else first
            if winner_session is not None and winner_session.alias is not None:
                self.leaderboard[winner_session.alias]["wins"] += 1
            if loser_session.alias is not None:
                self.leaderboard[loser_session.alias]["losses"] += 1
                if result == "FORFEIT":
                    self.leaderboard[loser_session.alias]["forfeits"] += 1
        self.game.scores_recorded = True

    def _ensure_score_row(self, alias: str) -> dict[str, int]:
        return self.leaderboard.setdefault(
            alias,
            {
                "wins": 0,
                "losses": 0,
                "draws": 0,
                "forfeits": 0,
                "games_played": 0,
            },
        )

    def _leaderboard_rows(self) -> list[dict[str, Any]]:
        sorted_rows = sorted(
            self.leaderboard.items(),
            key=lambda item: (
                -item[1]["wins"],
                item[1]["losses"],
                item[0].lower(),
            ),
        )
        return [
            {"rank": rank, "alias": alias, **scores}
            for rank, (alias, scores) in enumerate(sorted_rows, start=1)
        ]

    def _game_over_message(
        self,
        result: str,
        winner: str | None,
        reason: str,
    ) -> dict[str, Any]:
        if self.game is None:
            raise RuntimeError("cannot create GAME_OVER without a game")
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
                "leaderboard": self._leaderboard_rows(),
            },
            "timestamp": unix_time(),
        }

    @staticmethod
    def _log(message: str) -> None:
        print(f"[SERVER] {message}", flush=True)

    def __enter__(self) -> "GameServer":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    server = GameServer(args.port)
    try:
        server.run()
    except OSError as exc:
        print(
            f"[ERROR] Unable to bind server to 0.0.0.0:{args.port}: {exc}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
