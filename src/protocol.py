"""NDJSON framing and strict client-message validation for the game protocol."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

PROTOCOL_VERSION = 1
MAX_PAYLOAD_BYTES = 4096
FRAME_DELIMITER = b"\n"


@dataclass(frozen=True)
class ProtocolViolation:
    """A bad wire frame that the server can convert to an ERROR message."""

    code: str
    message: str
    recoverable: bool = True


class MessageValidationError(ValueError):
    """A structured message that does not match its required schema."""

    def __init__(
        self,
        code: str,
        message: str,
        recoverable: bool = True,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.recoverable = recoverable


def unix_time() -> int:
    """Return an integer timestamp for protocol messages."""

    return int(time.time())


def encode_message(message: dict[str, Any]) -> bytes:
    """Serialize one compact JSON object and append the NDJSON delimiter."""

    if not isinstance(message, dict):
        raise TypeError("protocol messages must be JSON objects")
    payload = json.dumps(
        message,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    if len(payload) > MAX_PAYLOAD_BYTES:
        raise ValueError("frame exceeds 4096-byte protocol limit")
    return payload + FRAME_DELIMITER


class NDJSONBuffer:
    """Accumulate TCP chunks and extract every complete NDJSON frame."""

    def __init__(self) -> None:
        self.buffer = bytearray()

    def feed(
        self,
        data: bytes,
    ) -> list[dict[str, Any] | ProtocolViolation]:
        """Add one TCP chunk and return complete messages or frame errors."""

        self.buffer.extend(data)
        results: list[dict[str, Any] | ProtocolViolation] = []

        while FRAME_DELIMITER in self.buffer:
            delimiter_index = self.buffer.index(FRAME_DELIMITER)
            frame = bytes(self.buffer[:delimiter_index])
            del self.buffer[: delimiter_index + 1]
            results.append(self._decode_frame(frame))

        if len(self.buffer) > MAX_PAYLOAD_BYTES:
            self.buffer.clear()
            results.append(
                ProtocolViolation(
                    "FRAME_TOO_LARGE",
                    "Frame exceeded the 4096-byte protocol limit",
                    recoverable=False,
                )
            )
        return results

    @staticmethod
    def _decode_frame(
        frame: bytes,
    ) -> dict[str, Any] | ProtocolViolation:
        if not frame:
            return ProtocolViolation("MALFORMED_JSON", "Empty JSON frame")
        if len(frame) > MAX_PAYLOAD_BYTES:
            return ProtocolViolation(
                "FRAME_TOO_LARGE",
                "Frame exceeded the 4096-byte protocol limit",
                recoverable=False,
            )
        try:
            text = frame.decode("utf-8")
        except UnicodeDecodeError:
            return ProtocolViolation("MALFORMED_JSON", "Frame is not valid UTF-8")
        try:
            message = json.loads(text)
        except json.JSONDecodeError:
            return ProtocolViolation("MALFORMED_JSON", "Frame is not valid JSON")
        if not isinstance(message, dict):
            return ProtocolViolation(
                "MALFORMED_JSON",
                "Top-level JSON value must be an object",
            )
        return message


def validate_envelope(message: dict[str, Any]) -> str:
    """Validate fields common to every client message and return its type."""

    version = message.get("version")
    if type(version) is not int or version != PROTOCOL_VERSION:
        raise MessageValidationError(
            "UNSUPPORTED_VERSION",
            f"Protocol version must be {PROTOCOL_VERSION}",
            recoverable=False,
        )
    msg_type = message.get("msg_type")
    if not isinstance(msg_type, str):
        raise MessageValidationError(
            "INVALID_PAYLOAD",
            "msg_type must be a string",
        )
    return msg_type


def validate_connect(message: dict[str, Any]) -> str:
    """Validate CONNECT and return its trimmed alias."""

    _require_exact_keys(
        message,
        {"version", "msg_type", "alias", "timestamp"},
    )
    if message.get("msg_type") != "CONNECT":
        raise MessageValidationError("UNEXPECTED_MESSAGE", "Expected CONNECT")
    alias_value = message.get("alias")
    if not isinstance(alias_value, str):
        raise MessageValidationError("INVALID_PAYLOAD", "alias must be a string")
    alias = alias_value.strip()
    if not 1 <= len(alias) <= 20 or not all(char.isprintable() for char in alias):
        raise MessageValidationError(
            "INVALID_PAYLOAD",
            "alias must contain 1-20 visible characters",
        )
    _validate_timestamp(message.get("timestamp"))
    return alias


def validate_move(message: dict[str, Any]) -> int:
    """Validate the MOVE shape and return its requested cell."""

    _require_exact_keys(
        message,
        {"version", "msg_type", "game_id", "player_id", "payload", "timestamp"},
    )
    if message.get("msg_type") != "MOVE":
        raise MessageValidationError("UNEXPECTED_MESSAGE", "Expected MOVE")
    _validate_session_fields(message)
    payload = message.get("payload")
    if not isinstance(payload, dict):
        raise MessageValidationError("INVALID_PAYLOAD", "payload must be an object")
    _require_exact_keys(payload, {"cell"})
    cell = payload.get("cell")
    if type(cell) is not int:
        raise MessageValidationError(
            "OUT_OF_RANGE",
            "cell must be an integer from 1 to 9",
        )
    _validate_timestamp(message.get("timestamp"))
    return cell


def validate_disconnect(message: dict[str, Any]) -> None:
    """Validate the exact DISCONNECT schema."""

    _require_exact_keys(
        message,
        {"version", "msg_type", "game_id", "player_id", "payload", "timestamp"},
    )
    if message.get("msg_type") != "DISCONNECT":
        raise MessageValidationError("UNEXPECTED_MESSAGE", "Expected DISCONNECT")
    _validate_session_fields(message)
    payload = message.get("payload")
    if not isinstance(payload, dict):
        raise MessageValidationError("INVALID_PAYLOAD", "payload must be an object")
    _require_exact_keys(payload, {"reason"})
    if payload.get("reason") != "QUIT":
        raise MessageValidationError(
            "INVALID_PAYLOAD",
            "DISCONNECT reason must be QUIT",
        )
    _validate_timestamp(message.get("timestamp"))


def make_error(
    code: str,
    message: str,
    game_id: str | None,
    player_id: str | None,
    recoverable: bool = True,
) -> dict[str, Any]:
    """Create an ERROR message matching the Sprint 1 schema."""

    return {
        "version": PROTOCOL_VERSION,
        "msg_type": "ERROR",
        "game_id": game_id,
        "player_id": player_id,
        "payload": {
            "code": code,
            "message": message,
            "recoverable": recoverable,
        },
        "timestamp": unix_time(),
    }


def _validate_session_fields(message: dict[str, Any]) -> None:
    game_id = message.get("game_id")
    player_id = message.get("player_id")
    if not isinstance(game_id, str):
        raise MessageValidationError("INVALID_PAYLOAD", "game_id must be a string")
    if player_id not in {"Player_1", "Player_2"}:
        raise MessageValidationError(
            "INVALID_PAYLOAD",
            "player_id must be Player_1 or Player_2",
        )


def _validate_timestamp(value: Any) -> None:
    if type(value) is not int or value < 0:
        raise MessageValidationError(
            "INVALID_PAYLOAD",
            "timestamp must be a nonnegative integer",
        )


def _require_exact_keys(message: dict[str, Any], expected: set[str]) -> None:
    actual = set(message)
    if actual != expected:
        missing = sorted(expected - actual)
        unknown = sorted(actual - expected)
        details = []
        if missing:
            details.append(f"missing fields: {', '.join(missing)}")
        if unknown:
            details.append(f"unknown fields: {', '.join(unknown)}")
        raise MessageValidationError(
            "INVALID_PAYLOAD",
            "; ".join(details) or "invalid fields",
        )
