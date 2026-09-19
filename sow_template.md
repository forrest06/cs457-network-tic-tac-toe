# CS 457 Project Statement of Work (SOW) & Protocol Specification Template

**Student Name:** Forrest Fisher

**Date:** 2026-09-19

**Course:** CS 457 - Computer Networks

**Target Server Domain:** `server.fisher.edu`

---

## 1. Game Selection & Scope (Sprint 0)

> Planning is an iterative process. Sections for later sprints describe the current design direction and may be refined as implementation and testing reveal new requirements.

### 1.1 Game Overview

- **Chosen Game:** Network Tic-Tac-Toe
- **Player Capacity:** Exactly 2 players, simulated by two CML client nodes
- **Game Summary:** Two clients connect to a central, server-authoritative game over TCP. The game uses a 3-by-3 board whose cells are numbered 1 through 9 from left to right and top to bottom. Player X and Player O alternate choosing one unoccupied cell. The server validates every request, updates the canonical board, and sends the same resulting state to both clients. The game ends with a win or a draw; spectators, computer players, chat, persistent accounts, and matchmaking across multiple simultaneous games are outside the initial project scope.

### 1.2 Core Game Rules & Win/Draw Conditions

- **Role assignment:** The first accepted client connection is `Player_1` and receives mark X. The second accepted connection is `Player_2` and receives mark O. The server rejects additional players once the two-player lobby is full.
- **Turn mechanics:** X always moves first. On a turn, the active client sends one cell number from 1 through 9. The server accepts the move only when it comes from the active player, the value is an integer in range, and the selected cell is empty. Invalid or out-of-turn requests produce an `ERROR` response and do not consume the turn. After an accepted move, the server broadcasts the new board and changes the active player.
- **Victory condition:** Immediately after each accepted move, the server checks all eight possible winning lines: three rows, three columns, and two diagonals. A player wins when three of that player's marks occupy one complete line. The server broadcasts `GAME_OVER` with the winner and final board.
- **Draw/tie condition:** If all nine cells are occupied and no winning line exists, the server declares a draw and broadcasts `GAME_OVER` with result `DRAW` and the final board.
- **Disconnect rule:** A disconnect before normal game completion ends the session. The remaining player receives `GAME_OVER` with result `FORFEIT`; the server then cleans up the game state.

---

## 2. Application-Layer Messaging Protocol Blueprint (Sprint 1 Deliverable)

The following is the preliminary protocol plan and will be finalized in Sprint 1.

### 2.1 Message Transport & Serialization Format

- **Transport Protocol:** TCP over IPv4
- **Default Server Port:** `45700`
- **Serialization Format:** UTF-8 JSON objects
- **Framing Mechanism:** Newline-delimited JSON (NDJSON); every complete message ends with one `\n`. Receivers buffer partial TCP data until a newline is present and may process multiple frames received in one TCP read.
- **Common fields:** Every message contains `version`, `msg_type`, and `game_id`. Messages associated with a player also contain `player_id`. Server state messages contain a monotonically increasing `sequence` number so clients can detect stale or duplicate state.

### 2.2 Message Schema Definitions

#### Message Types

1. `CONNECT` (Client -> Server): Requests entry to the two-player lobby and declares protocol version.
2. `LOBBY_WAIT` (Server -> Client): Confirms the assigned identity/mark and reports that the server is waiting for the second player.
3. `GAME_START` (Server -> Clients): Assigns X/O roles, supplies the initial empty board, and identifies the first active player.
4. `MOVE` (Client -> Server): Requests placement of the sender's mark in a cell numbered 1 through 9.
5. `STATE_UPDATE` (Server -> Clients): Broadcasts the canonical board, last accepted move, and next active player.
6. `GAME_OVER` (Server -> Clients): Reports `WIN`, `DRAW`, or `FORFEIT`, along with the winner when applicable and the final board.
7. `ERROR` (Server -> Client): Rejects an invalid, malformed, unexpected, or out-of-turn request without changing the game state.

#### Example `MOVE` Message

```json
{
  "version": 1,
  "msg_type": "MOVE",
  "game_id": "game-001",
  "player_id": "Player_1",
  "payload": {
    "cell": 3
  }
}
```

#### Example `STATE_UPDATE` Message

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
  }
}
```

The server will cap a single frame at 4 KiB, reject unknown message types or extra-large frames, and return stable error codes such as `INVALID_JSON`, `WRONG_TURN`, `CELL_OCCUPIED`, and `OUT_OF_RANGE`.

### 2.3 Game State Machine (FSM) Design (Sprint 1 Deliverable)

The planned server state flow is:

`INIT` -> `WAITING_FOR_PLAYERS` -> `GAME_START` -> `PLAYER_TURN` -> `EVALUATE_MOVE` -> `CHECK_WIN_DRAW`

- An invalid move returns from `EVALUATE_MOVE` to the same `PLAYER_TURN` without changing state.
- A valid nonterminal move returns from `CHECK_WIN_DRAW` to `PLAYER_TURN` with the other player active.
- A win, draw, or disconnect moves to `GAME_OVER` -> `CLEANUP` -> `WAITING_FOR_PLAYERS`.

---

## 3. Game Behavior & Server Concurrency Architecture (Sprint 2 Deliverable)

The following is the preliminary concurrency design and will be finalized in Sprint 2.

### 3.1 Server Concurrency Strategy

- **Architecture choice:** Non-blocking I/O multiplexing with Python's `selectors.DefaultSelector`.
- **Synchronization logic:** One event-loop thread owns and mutates the client registry and game state. Because state transitions are serialized in that thread, no two moves can update the board concurrently and a `threading.Lock` is unnecessary in the initial architecture. Per-client receive buffers handle partial frames; per-client send queues handle partial writes without blocking the event loop.
- **Connection limits:** The server accepts two active players for one game. Later connections receive a `SERVER_FULL` error and are closed cleanly.

### 3.2 State & Score Synchronization Across Clients

- **Turn enforcement:** The server associates each socket with its assigned `player_id`. It compares that identity to `active_player` before validating the requested cell. A client-provided identity is never trusted as the source of authorization.
- **Board synchronization:** The server is the only authority allowed to modify the board. It broadcasts one complete board snapshot and sequence number to both clients after every accepted move so neither client must reconstruct canonical state from local guesses.
- **Terminal state synchronization:** `GAME_OVER` includes the result, winner if any, final board, and final sequence number. Clients stop accepting moves after receiving it.
- **Scoring scope:** Sprint 0 defines one game per server session; there is no cross-session leaderboard. Within the session, the result is one win, one loss, one draw, or a forfeit.

---

## 4. Coding & AI Implementation Plan (Sprint 3)

- **Language and standard library:** Python 3, using `socket`, `selectors`, `json`, `logging`, and `argparse`. Third-party runtime dependencies are not planned.
- **Permitted AI tools:** OpenAI Codex/ChatGPT, only to the extent allowed by the course academic-integrity policy. All AI-assisted work will be reviewed, understood, tested, and committed by the student.
- **AI prompting and constraint strategy:** Prompts will include the finalized message schemas, framing rules, finite-state machine, input limits, and acceptance tests. Requested code must preserve the server-authoritative design, use NDJSON framing correctly across partial TCP reads, avoid hidden third-party dependencies, and remain compatible with the Python version available on the CML nodes.
- **Implementation risk management:** Development will proceed in small milestones: pure game-rule functions, protocol encode/decode functions, single-client socket loop, two-client turn enforcement, disconnect handling, then CML deployment. Unit tests will cover all winning lines, draw detection, invalid cells, wrong-turn moves, split frames, and multiple frames in one read. End-to-end tests will use two local client processes before CML deployment. Each completed milestone will receive a separate Git commit.

### Planned Repository Layout

```text
src/
  client.py
  server.py
  game.py
  protocol.py
tests/
  test_game.py
  test_protocol.py
docs/
  toolchain-verification.md
sow_template.md
README.md
```

---

## 5. CML Multi-Subnet Topology & Wireshark Deployment Plan (Sprint 4 & 5 Deliverable)

The topology below is the current plan and may be updated when subnet requirements are finalized.

### 5.1 Subnet & Router Design

- **Subnet A (Client 1):** `192.168.10.0/24` (interface `Gi0/1` on Router R1)
- **Subnet B (Client 2):** `192.168.11.0/24` (interface `Gi0/2` on Router R1)
- **Subnet C (Game Server):** `192.168.20.0/24` (interface `Gi0/1` on Router R2)
- **Router backbone:** `10.0.0.0/30` (interface `Gi0/0` on R1 <-> `Gi0/0` on R2)
- **Server address:** `192.168.20.100/24`, default gateway `192.168.20.1`

### 5.2 DHCP Pools & DNS Configuration Plan

- **Router R1 DHCP Pool 1 (`CLIENT1_POOL`):** Leases `192.168.10.10` through `192.168.10.50`, gateway `192.168.10.1`, DNS `10.0.0.2`.
- **Router R1 DHCP Pool 2 (`CLIENT2_POOL`):** Leases `192.168.11.10` through `192.168.11.50`, gateway `192.168.11.1`, DNS `10.0.0.2`.
- **Router R2 authoritative DNS:** Static host mapping `server.fisher.edu` -> `192.168.20.100` with DNS service enabled.
- **Required name-resolution test:** From both client nodes, `nslookup server.fisher.edu` must return `192.168.20.100` before the game clients are launched.

### 5.3 Deployment Strategy & Wireshark Trace Capture

- **CML deployment:** Place `server.py` on the Subnet C node at `192.168.20.100`. Place `client.py` on the separate Subnet A and Subnet B nodes. Both clients connect to `server.fisher.edu:45700` rather than a hard-coded IP address.
- **Cisco infrastructure configuration:** Configure Router R1 DHCP pools (`CLIENT1_POOL` and `CLIENT2_POOL`), routed connectivity over `10.0.0.0/30`, a static route to the server subnet, and Router R2 DNS mapping `ip host server.fisher.edu 192.168.20.100`.
- **Connectivity checks:** Verify leases and gateways, ping each router hop, resolve the server domain from both clients, and establish TCP connections from both clients to port `45700`.
- **Wireshark traces:** Capture DHCP DORA as `dhcp_negotiation.pcap`, the DNS query/response for `server.fisher.edu` as `dns_lookup.pcap`, and a complete two-client game session as `game_session.pcap`.
- **Acceptance evidence:** Retain terminal output showing client addresses, DNS resolution, successful TCP connections, alternating moves, an invalid-move rejection, and one normal `GAME_OVER` result.

---

## Sprint 0 Acceptance Checklist

- [x] Python 3 and Git verified on the development computer.
- [x] Editor-neutral project settings and VS Code Python settings added to the repository.
- [x] Public-repository-ready `.gitignore` added.
- [x] Two-player CLI game selected with role assignment, turn order, win conditions, draw conditions, and disconnect behavior defined.
- [x] Target authoritative DNS name set to `server.fisher.edu`.
- [x] Protocol, architecture, implementation, and CML deployment roadmap documented.
- [ ] Public Git repository URL added after publication.
- [ ] CML runtime verified on a supported x86_64 host; the current Apple Silicon Mac cannot run the course's required local image.

## Public Git Repository

**Repository URL:** To be added immediately after the repository is published.
