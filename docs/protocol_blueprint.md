# Sprint 1 Application Protocol Blueprint

Forrest Fisher | CS 457 - Computer Networks | October 1, 2026

## 1. Protocol overview

This project uses a server-authoritative protocol for a two-player command-line Tic-Tac-Toe game. The clients only request moves. The server assigns player roles, checks every move, owns the official board, and sends the resulting state to both clients.

| Setting | Value |
|---|---|
| Transport | TCP over IPv4 |
| Server port | `45700` |
| Character encoding | UTF-8 |
| Serialization | Compact JSON |
| Framing | Newline-delimited JSON (NDJSON) |
| Protocol version | `1` |
| Maximum JSON payload | 4096 bytes, not counting the final newline |
| Board representation | JSON array of 9 values: `"X"`, `"O"`, or `null` |

Board positions are numbered 1 through 9 from left to right and top to bottom. Position 1 is stored at array index 0, and position 9 is stored at array index 8.

## 2. TCP framing rule

TCP is a byte stream and does not preserve message boundaries. One call to `recv()` might contain part of one message, exactly one message, or several messages. The protocol therefore does not treat a `recv()` result as a complete message.

Every message is encoded as one compact JSON object followed by one line-feed byte:

```text
frame = UTF8(JSON_OBJECT) + 0x0A
```

The line-feed byte is written as `\n` in examples. Senders must not pretty-print JSON. Newlines inside JSON string values are escaped by the JSON serializer as `\n`, so they do not create an actual `0x0A` delimiter inside the payload.

### 2.1 Sender procedure

1. Build a dictionary that exactly matches one schema in this document.
2. Validate field names, types, ranges, and protocol version.
3. Serialize it with compact JSON separators and UTF-8 encoding.
4. Reject it locally if the encoded JSON is longer than 4096 bytes.
5. Append one `b"\n"` byte and call `sendall()`.

Equivalent Python behavior:

```python
payload = json.dumps(message, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
if len(payload) > 4096:
    raise ValueError("frame exceeds 4096-byte protocol limit")
sock.sendall(payload + b"\n")
```

### 2.2 Receiver procedure

Each socket has its own persistent `bytearray` receive buffer.

1. Append every nonempty `recv()` result to that socket's buffer.
2. While the buffer contains `0x0A`, remove bytes through the first delimiter.
3. Treat the bytes before the delimiter as one frame.
4. Reject an empty frame, invalid UTF-8, invalid JSON, a non-object JSON value, an unknown field, or a schema mismatch with an `ERROR` message.
5. Process all complete frames in order and leave any incomplete final bytes in the buffer for the next `recv()` call.
6. If a buffer grows beyond 4096 bytes without a delimiter, send `FRAME_TOO_LARGE` when possible and close that client connection.

### 2.3 Back-to-back wire example

The following is one continuous byte stream containing a `CONNECT` frame immediately followed by a `MOVE` frame. The visible `\n` tokens each represent one actual `0x0A` byte.

```text
{"version":1,"msg_type":"CONNECT","alias":"Forrest","timestamp":1790800000}\n{"version":1,"msg_type":"MOVE","game_id":"game-001","player_id":"Player_1","payload":{"cell":3},"timestamp":1790800005}\n
```

The receiver must extract two messages even if both arrive in one `recv()` call.

### 2.4 Fragmented stream example

The network may split the same stream at any byte position:

```text
recv #1: b'{"version":1,"msg_type":"MOVE","game_id":"game-001","player_id":"Play'
recv #2: b'er_1","payload":{"cell":3},"timestamp":1790800005}\n{"version":1,"msg_type":"DIS'
recv #3: b'CONNECT","game_id":"game-001","player_id":"Player_1","payload":{"reason":"QUIT"},"timestamp":1790800010}\n'
```

No message is parsed after `recv #1`. After `recv #2`, the complete `MOVE` is parsed and the partial `DISCONNECT` stays buffered. After `recv #3`, the complete `DISCONNECT` is parsed.

## 3. Shared data rules

| Name | Type and allowed values |
|---|---|
| `version` | Integer. Must equal `1`. |
| `msg_type` | String. Must be one of the eight message types defined below. |
| `game_id` | String matching `game-[0-9]{3,}`. Assigned by the server. |
| `player_id` | String. Either `Player_1` or `Player_2`. |
| `alias` | String, 1-20 visible characters. Leading and trailing spaces are removed. |
| `timestamp` | Integer Unix timestamp in seconds. Used for logs, not for turn authorization. |
| `sequence` | Nonnegative integer assigned by the server. It starts at 0 in `GAME_START` and increases after every accepted move. |
| `cell` | Integer from 1 through 9. JSON booleans are not accepted as integers. |
| `board` | Array of exactly 9 items. Each item is `"X"`, `"O"`, or `null`. |
| `active_player` | `Player_1`, `Player_2`, or `null` after the game ends. |

Unknown keys are rejected. A client may not select its own `player_id`, `game_id`, mark, sequence number, or turn. Those values come from the server.

## 4. Message summary

| Message | Direction | Purpose |
|---|---|---|
| `CONNECT` | Client -> Server | Request a place in the lobby. |
| `LOBBY_WAIT` | Server -> Client | Assign Player 1 and report that Player 2 is still needed. |
| `GAME_START` | Server -> Both clients | Announce the game, roles, empty board, and first turn. |
| `MOVE` | Client -> Server | Request placement of one mark in a numbered cell. |
| `STATE_UPDATE` | Server -> Both clients | Broadcast the board after an accepted nonterminal move. |
| `ERROR` | Server -> One client | Reject a bad or unexpected request without changing valid game state. |
| `DISCONNECT` | Client -> Server | Report an intentional departure. |
| `GAME_OVER` | Server -> Remaining connected clients | Announce a win, draw, or forfeit and the final board. |

## 5. Exact message schemas

### 5.1 `CONNECT`

Direction: Client -> Server

Purpose: Request entry into the one-game, two-player lobby. This is the only valid client message before a role is assigned.

| Field | Type | Required rule |
|---|---|---|
| `version` | integer | Must be `1`. |
| `msg_type` | string | Must be `"CONNECT"`. |
| `alias` | string | 1-20 visible characters. |
| `timestamp` | integer | Unix seconds. |

```json
{
  "version": 1,
  "msg_type": "CONNECT",
  "alias": "Forrest",
  "timestamp": 1790800000
}
```

The first accepted connection becomes `Player_1` with mark X. The second becomes `Player_2` with mark O. Later connections receive `ERROR` with code `SERVER_FULL` and are closed.

### 5.2 `LOBBY_WAIT`

Direction: Server -> Client

Purpose: Confirm Player 1's assignment while the server waits for Player 2.

| Field | Type | Required rule |
|---|---|---|
| `version` | integer | Must be `1`. |
| `msg_type` | string | Must be `"LOBBY_WAIT"`. |
| `game_id` | string | Server-generated game identifier. |
| `player_id` | string | Must be `"Player_1"`. |
| `payload.mark` | string | Must be `"X"`. |
| `payload.players_connected` | integer | Must be `1`. |
| `payload.message` | string | Human-readable CLI status. |
| `timestamp` | integer | Unix seconds. |

```json
{
  "version": 1,
  "msg_type": "LOBBY_WAIT",
  "game_id": "game-001",
  "player_id": "Player_1",
  "payload": {
    "mark": "X",
    "players_connected": 1,
    "message": "Waiting for Player 2"
  },
  "timestamp": 1790800001
}
```

### 5.3 `GAME_START`

Direction: Server -> Both clients

Purpose: Announce both role assignments and start the game with Player 1's turn.

| Field | Type | Required rule |
|---|---|---|
| `version` | integer | Must be `1`. |
| `msg_type` | string | Must be `"GAME_START"`. |
| `game_id` | string | Current game identifier. |
| `sequence` | integer | Must be `0`. |
| `payload.roles` | object | Exactly `Player_1: "X"` and `Player_2: "O"`. |
| `payload.board` | array | Exactly 9 `null` values. |
| `payload.active_player` | string | Must be `"Player_1"`. |
| `timestamp` | integer | Unix seconds. |

```json
{
  "version": 1,
  "msg_type": "GAME_START",
  "game_id": "game-001",
  "sequence": 0,
  "payload": {
    "roles": {"Player_1": "X", "Player_2": "O"},
    "board": [null, null, null, null, null, null, null, null, null],
    "active_player": "Player_1"
  },
  "timestamp": 1790800002
}
```

### 5.4 `MOVE`

Direction: Client -> Server

Purpose: Ask the server to place the sender's mark in one cell.

| Field | Type | Required rule |
|---|---|---|
| `version` | integer | Must be `1`. |
| `msg_type` | string | Must be `"MOVE"`. |
| `game_id` | string | Must match the client's assigned game. |
| `player_id` | string | Must match the identity bound to that TCP socket. |
| `payload.cell` | integer | From 1 through 9. |
| `timestamp` | integer | Unix seconds. |

```json
{
  "version": 1,
  "msg_type": "MOVE",
  "game_id": "game-001",
  "player_id": "Player_1",
  "payload": {"cell": 3},
  "timestamp": 1790800005
}
```

The server checks socket identity and turn order before checking the cell. A rejected move never changes the board, sequence number, or active player.

### 5.5 `STATE_UPDATE`

Direction: Server -> Both clients

Purpose: Broadcast the complete authoritative state after an accepted move that did not end the game.

| Field | Type | Required rule |
|---|---|---|
| `version` | integer | Must be `1`. |
| `msg_type` | string | Must be `"STATE_UPDATE"`. |
| `game_id` | string | Current game identifier. |
| `sequence` | integer | Previous sequence plus 1. |
| `payload.board` | array | Complete 9-item board. |
| `payload.last_move.player_id` | string | Player whose move was accepted. |
| `payload.last_move.cell` | integer | Accepted cell from 1 through 9. |
| `payload.active_player` | string | Player who moves next. |
| `timestamp` | integer | Unix seconds. |

```json
{
  "version": 1,
  "msg_type": "STATE_UPDATE",
  "game_id": "game-001",
  "sequence": 1,
  "payload": {
    "board": [null, null, "X", null, null, null, null, null, null],
    "last_move": {"player_id": "Player_1", "cell": 3},
    "active_player": "Player_2"
  },
  "timestamp": 1790800006
}
```

### 5.6 `ERROR`

Direction: Server -> One client

Purpose: Explain why one request was rejected. Recoverable errors keep the connection and current game state unchanged.

| Field | Type | Required rule |
|---|---|---|
| `version` | integer | Must be `1`. |
| `msg_type` | string | Must be `"ERROR"`. |
| `game_id` | string or null | `null` only when no game has been assigned. |
| `player_id` | string or null | Assigned player, or `null` before assignment. |
| `payload.code` | string | One code from the table below. |
| `payload.message` | string | Short human-readable explanation. |
| `payload.recoverable` | boolean | Whether the server will keep this socket open. |
| `timestamp` | integer | Unix seconds. |

```json
{
  "version": 1,
  "msg_type": "ERROR",
  "game_id": "game-001",
  "player_id": "Player_2",
  "payload": {
    "code": "WRONG_TURN",
    "message": "Player_1 must move next",
    "recoverable": true
  },
  "timestamp": 1790800007
}
```

| Error code | Meaning | Connection action |
|---|---|---|
| `MALFORMED_JSON` | Frame is not a JSON object. | Keep open unless repeated. |
| `INVALID_PAYLOAD` | Required field, type, or value is wrong. | Keep open. |
| `UNSUPPORTED_VERSION` | `version` is not `1`. | Send error, then close. |
| `UNEXPECTED_MESSAGE` | Message type is not allowed in the current state. | Keep open. |
| `WRONG_TURN` | A valid player sent a move out of turn. | Keep open. |
| `CELL_OCCUPIED` | The requested cell already has a mark. | Keep open. |
| `OUT_OF_RANGE` | Cell is not an integer from 1 through 9. | Keep open. |
| `SERVER_FULL` | Two players are already assigned. | Send error, then close. |
| `FRAME_TOO_LARGE` | Frame exceeds 4096 bytes. | Send error when possible, then close. |
| `GAME_ALREADY_OVER` | A move arrived after a terminal result. | Keep open until cleanup. |

### 5.7 `DISCONNECT`

Direction: Client -> Server

Purpose: Notify the server that a player is intentionally leaving.

| Field | Type | Required rule |
|---|---|---|
| `version` | integer | Must be `1`. |
| `msg_type` | string | Must be `"DISCONNECT"`. |
| `game_id` | string | Must match the assigned game. |
| `player_id` | string | Must match the identity bound to the socket. |
| `payload.reason` | string | Must be `"QUIT"`. |
| `timestamp` | integer | Unix seconds. |

```json
{
  "version": 1,
  "msg_type": "DISCONNECT",
  "game_id": "game-001",
  "player_id": "Player_1",
  "payload": {"reason": "QUIT"},
  "timestamp": 1790800010
}
```

If the game is active, the connected opponent wins by forfeit. If the game has not started, the server releases the waiting lobby slot. After sending this frame, the client calls `shutdown(SHUT_WR)` and closes its socket.

### 5.8 `GAME_OVER`

Direction: Server -> All clients that are still connected

Purpose: Report the terminal result and final authoritative board.

| Field | Type | Required rule |
|---|---|---|
| `version` | integer | Must be `1`. |
| `msg_type` | string | Must be `"GAME_OVER"`. |
| `game_id` | string | Current game identifier. |
| `sequence` | integer | Final server sequence. |
| `payload.result` | string | `"WIN"`, `"DRAW"`, or `"FORFEIT"`. |
| `payload.winner` | string or null | Player ID for a win/forfeit; `null` for a draw. |
| `payload.reason` | string | `THREE_IN_A_ROW`, `BOARD_FULL`, `PLAYER_QUIT`, or `CONNECTION_LOST`. |
| `payload.final_board` | array | Complete 9-item final board. |
| `payload.active_player` | null | Always `null`. |
| `timestamp` | integer | Unix seconds. |

```json
{
  "version": 1,
  "msg_type": "GAME_OVER",
  "game_id": "game-001",
  "sequence": 5,
  "payload": {
    "result": "WIN",
    "winner": "Player_1",
    "reason": "THREE_IN_A_ROW",
    "final_board": ["X", "O", null, "X", "O", null, "X", null, null],
    "active_player": null
  },
  "timestamp": 1790800020
}
```

## 6. Validation and dispatch order

For each complete frame, the server performs checks in this order:

1. Frame size, UTF-8 decoding, and JSON object parsing.
2. Exact field names and required fields.
3. Protocol version and `msg_type`.
4. Whether the message is legal in the current FSM state.
5. Whether `game_id` and `player_id` match the socket's server-side session.
6. Payload types and ranges.
7. Turn ownership.
8. Game rule checks such as empty cell, win, and draw.

Only a request that passes all checks may change game state. Client timestamps and client-supplied identifiers are never used as authorization.

## 7. Connection termination and socket lifecycle

### 7.1 Intentional application disconnect

A cooperative client sends `DISCONNECT`, then shuts down its write side and closes. The server handles the message once, declares a forfeit if the game is active, sends `GAME_OVER` to the remaining player, unregisters the socket from the selector, closes it, removes its receive/send buffers, and enters cleanup.

### 7.2 TCP FIN and the zero-byte EOF rule

If a peer closes normally without a `DISCONNECT` frame, `recv()` returns `b""`. This is EOF, not an empty message. The receive loop must stop immediately and create one internal `CLIENT_DISCONNECTED` event. Calling `recv()` again after EOF can cause a busy loop that consumes CPU.

```python
data = sock.recv(4096)
if not data:
    handle_client_disconnected(player_id, reason="EOF")
    unregister_and_close(sock)
    return
```

### 7.3 Abrupt failure

Crashes, killed processes, broken CML links, and forced socket closure may cause `ConnectionResetError`, `ConnectionAbortedError`, `BrokenPipeError`, or `TimeoutError`. Receive and send paths catch these exceptions and convert them into the same internal `CLIENT_DISCONNECTED` event. An active opponent wins by forfeit with reason `CONNECTION_LOST`. If no opponent is connected, the server only releases the slot.

```python
try:
    data = sock.recv(4096)
except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, TimeoutError):
    handle_client_disconnected(player_id, reason="CONNECTION_LOST")
    unregister_and_close(sock)
```

### 7.4 Cleanup rules

- A socket is unregistered and closed at most once.
- Pending output to a failed socket is discarded.
- The surviving player receives `GAME_OVER` when possible.
- Player identities, aliases, buffers, board cells, active player, and sequence number are cleared.
- The listening socket stays open so the server can return to `WAITING_FOR_PLAYERS` for a new game.
- Cleanup must still finish if sending the final message raises `BrokenPipeError`.

## 8. Protocol invariants

The implementation must always preserve these rules:

- Exactly one server owns and mutates the board.
- At most two players are assigned to one game.
- Player 1 is X and moves first; Player 2 is O.
- An invalid or out-of-turn move never consumes a turn or increments `sequence`.
- Every accepted move increments `sequence` exactly once.
- Both connected clients receive the same board and sequence after an accepted move.
- No moves are accepted after `GAME_OVER`.
- Every disconnect path reaches cleanup without crashing the server process.
