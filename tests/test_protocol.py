"""Tests for deterministic NDJSON framing and schema validation."""

import unittest

from src.protocol import (
    NDJSONBuffer,
    MessageValidationError,
    ProtocolViolation,
    encode_message,
    validate_connect,
)


class ProtocolTests(unittest.TestCase):
    def test_fragmented_message_waits_for_delimiter(self) -> None:
        framer = NDJSONBuffer()
        message = {
            "version": 1,
            "msg_type": "CONNECT",
            "alias": "Alice",
            "timestamp": 1,
        }
        frame = encode_message(message)

        self.assertEqual(framer.feed(frame[:10]), [])
        self.assertEqual(framer.feed(frame[10:]), [message])

    def test_coalesced_messages_are_both_extracted(self) -> None:
        framer = NDJSONBuffer()
        first = {
            "version": 1,
            "msg_type": "CONNECT",
            "alias": "Alice",
            "timestamp": 1,
        }
        second = {
            "version": 1,
            "msg_type": "CONNECT",
            "alias": "Bob",
            "timestamp": 2,
        }

        self.assertEqual(
            framer.feed(encode_message(first) + encode_message(second)),
            [first, second],
        )

    def test_invalid_json_becomes_protocol_violation(self) -> None:
        result = NDJSONBuffer().feed(b"not-json\n")

        self.assertEqual(len(result), 1)
        self.assertIsInstance(result[0], ProtocolViolation)
        self.assertEqual(result[0].code, "MALFORMED_JSON")

    def test_unknown_connect_field_is_rejected(self) -> None:
        message = {
            "version": 1,
            "msg_type": "CONNECT",
            "alias": "Alice",
            "timestamp": 1,
            "extra": True,
        }

        with self.assertRaises(MessageValidationError) as context:
            validate_connect(message)
        self.assertEqual(context.exception.code, "INVALID_PAYLOAD")


if __name__ == "__main__":
    unittest.main()
