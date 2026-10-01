# Sprint 1 AI Prompting and Constraint Strategy

Forrest Fisher | CS 457 - Computer Networks | October 1, 2026

## Limited AI role

The protocol fields, framing rule, game rules, and state transitions are already decided in [`protocol_blueprint.md`](protocol_blueprint.md) and [`fsm_specification.md`](fsm_specification.md). AI assistance will be limited to implementing or checking small protocol functions after those designs are complete. It will not be asked to choose an architecture, invent message types, or generate a general socket server.

## Constrained implementation prompt

The following prompt will be used when the protocol parser is implemented:

```text
Implement only the protocol codec described in docs/protocol_blueprint.md for this Network Tic-Tac-Toe project.

Treat that Markdown file as the only source of truth. Support exactly protocol version 1 and exactly these messages: CONNECT, LOBBY_WAIT, GAME_START, MOVE, STATE_UPDATE, ERROR, DISCONNECT, and GAME_OVER.

Use UTF-8 compact JSON followed by one newline byte. The JSON payload limit is 4096 bytes. The decoder must keep incomplete bytes between reads, extract every complete frame in order, and handle both fragmented and coalesced TCP data. Reject unknown keys, wrong types, invalid ranges, non-object JSON, invalid UTF-8, and unsupported versions. Do not assume one recv() call equals one message.

Implement only encode_message(), feed_data(), and validate_message() in src/protocol.py. Do not create socket loops, game rules, alternate schemas, extra message types, dependencies, or fallback formats. If the blueprint is unclear, stop and identify the exact ambiguity instead of making a design decision.
```

## Conformance-check prompt

After implementation, one short review prompt will be used:

```text
Compare src/protocol.py and tests/test_protocol.py against docs/protocol_blueprint.md. List only concrete mismatches with a file and line number. Check the eight exact schemas, 4096-byte limit, newline framing, partial frames, multiple frames per read, unknown fields, and error codes. Do not rewrite the design or suggest new features.
```

## Checks required before accepting generated code

- The implementation uses the exact field names and allowed values in the blueprint.
- No ninth message type or alternate framing format is introduced.
- A split frame is buffered until its newline arrives.
- Two frames in one input chunk are returned as two messages in order.
- A frame over 4096 bytes is rejected.
- Invalid or out-of-turn requests cannot mutate the board or consume a turn.
- The standard library is sufficient; no package is added.
- I can explain and test every accepted line before committing it.

Any generated code that changes the protocol instead of following it will be discarded.
