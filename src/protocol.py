"""JSON message framing used by both the client and server."""

import json
import time
from dataclasses import dataclass

VERSION = 1
PROTOCOL_VERSION = VERSION
MAX_SIZE = 4096


@dataclass
class ProtocolViolation:
    code: str
    message: str
    recoverable: bool = True


class MessageValidationError(ValueError):
    def __init__(self, code, message, recoverable=True):
        super().__init__(message)
        self.code = code
        self.message = message
        self.recoverable = recoverable


def unix_time():
    return int(time.time())


def encode_message(message):
    """Turn one dictionary into compact newline-delimited JSON."""
    data = json.dumps(message, separators=(",", ":")).encode("utf-8")
    if len(data) > MAX_SIZE:
        raise ValueError("frame exceeds 4096-byte protocol limit")
    return data + b"\n"


class NDJSONBuffer:
    """Keeps unfinished TCP data until a complete line arrives."""

    def __init__(self):
        self.buffer = bytearray()

    def feed(self, data):
        self.buffer.extend(data)
        messages = []

        while b"\n" in self.buffer:
            end = self.buffer.index(b"\n")
            frame = bytes(self.buffer[:end])
            del self.buffer[: end + 1]
            messages.append(self._decode(frame))

        if len(self.buffer) > MAX_SIZE:
            self.buffer.clear()
            messages.append(
                ProtocolViolation(
                    "FRAME_TOO_LARGE",
                    "Frame exceeded the 4096-byte limit",
                    False,
                )
            )
        return messages

    @staticmethod
    def _decode(frame):
        if not frame:
            return ProtocolViolation("MALFORMED_JSON", "Empty JSON frame")
        if len(frame) > MAX_SIZE:
            return ProtocolViolation(
                "FRAME_TOO_LARGE",
                "Frame exceeded the 4096-byte limit",
                False,
            )
        try:
            message = json.loads(frame.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return ProtocolViolation("MALFORMED_JSON", "Invalid JSON frame")
        if not isinstance(message, dict):
            return ProtocolViolation("MALFORMED_JSON", "JSON must be an object")
        return message


def validate_envelope(message):
    if message.get("version") != VERSION or type(message.get("version")) is not int:
        raise MessageValidationError(
            "UNSUPPORTED_VERSION",
            "Protocol version must be 1",
            False,
        )
    if not isinstance(message.get("msg_type"), str):
        raise MessageValidationError("INVALID_PAYLOAD", "msg_type must be text")
    return message["msg_type"]


def validate_connect(message):
    exact_fields(message, {"version", "msg_type", "alias", "timestamp"})
    if message["msg_type"] != "CONNECT":
        raise MessageValidationError("UNEXPECTED_MESSAGE", "Expected CONNECT")
    alias = message.get("alias")
    if not isinstance(alias, str):
        raise MessageValidationError("INVALID_PAYLOAD", "alias must be text")
    alias = alias.strip()
    if not 1 <= len(alias) <= 20 or not all(c.isprintable() for c in alias):
        raise MessageValidationError(
            "INVALID_PAYLOAD",
            "alias must contain 1-20 visible characters",
        )
    valid_timestamp(message.get("timestamp"))
    return alias


def validate_move(message):
    exact_fields(
        message,
        {"version", "msg_type", "game_id", "player_id", "payload", "timestamp"},
    )
    valid_session_fields(message)
    payload = message.get("payload")
    if not isinstance(payload, dict):
        raise MessageValidationError("INVALID_PAYLOAD", "payload must be an object")
    exact_fields(payload, {"cell"})
    cell = payload.get("cell")
    if type(cell) is not int:
        raise MessageValidationError("OUT_OF_RANGE", "cell must be from 1 to 9")
    valid_timestamp(message.get("timestamp"))
    return cell


def validate_disconnect(message):
    exact_fields(
        message,
        {"version", "msg_type", "game_id", "player_id", "payload", "timestamp"},
    )
    valid_session_fields(message)
    payload = message.get("payload")
    if not isinstance(payload, dict):
        raise MessageValidationError("INVALID_PAYLOAD", "payload must be an object")
    exact_fields(payload, {"reason"})
    if payload.get("reason") != "QUIT":
        raise MessageValidationError("INVALID_PAYLOAD", "reason must be QUIT")
    valid_timestamp(message.get("timestamp"))


def make_error(code, text, game_id, player_id, recoverable=True):
    return {
        "version": VERSION,
        "msg_type": "ERROR",
        "game_id": game_id,
        "player_id": player_id,
        "payload": {
            "code": code,
            "message": text,
            "recoverable": recoverable,
        },
        "timestamp": unix_time(),
    }


def valid_session_fields(message):
    if not isinstance(message.get("game_id"), str):
        raise MessageValidationError("INVALID_PAYLOAD", "game_id must be text")
    if message.get("player_id") not in ("Player_1", "Player_2"):
        raise MessageValidationError("INVALID_PAYLOAD", "invalid player_id")


def valid_timestamp(value):
    if type(value) is not int or value < 0:
        raise MessageValidationError("INVALID_PAYLOAD", "invalid timestamp")


def exact_fields(message, expected):
    if set(message) != expected:
        raise MessageValidationError(
            "INVALID_PAYLOAD",
            "message fields do not match the protocol",
        )
