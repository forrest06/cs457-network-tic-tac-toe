# CS 457 Network Tic-Tac-Toe

Sprint 0 through Sprint 3 repository for Forrest Fisher's CS 457 final project.

## Project Summary

Network Tic-Tac-Toe is a two-player command-line game with one authoritative Python server and two TCP clients. The first client is Player X, the second is Player O, and the server validates turns, stores the canonical 3-by-3 board, detects wins or draws, and broadcasts synchronized state to both players.

- **Authoritative DNS name:** `server.fisher.edu`
- **Planned transport:** TCP on port `45700`
- **Planned application format:** Newline-delimited JSON
- **Language:** Python 3
- **Sprint 0 SOW:** [`sow_template.md`](sow_template.md)
- **Local setup record:** [`docs/toolchain-verification.md`](docs/toolchain-verification.md)
- **Sprint 1 protocol:** [`docs/protocol_blueprint.md`](docs/protocol_blueprint.md)
- **Sprint 1 state machine:** [`docs/fsm_specification.md`](docs/fsm_specification.md)
- **Sprint 1 AI constraints:** [`docs/ai_prompts.md`](docs/ai_prompts.md)
- **Sprint 2 concurrency design:** [`docs/concurrency_design.md`](docs/concurrency_design.md)
- **Sprint 3 execution log:** [`docs/sprint3_execution_log.txt`](docs/sprint3_execution_log.txt)

## Sprint 0 Status

- Python 3 and Git are installed and verified.
- A Python-focused `.gitignore`, EditorConfig file, and VS Code project settings are committed.
- Game scope, rules, victory conditions, draw handling, DNS name, protocol direction, concurrency strategy, implementation plan, and CML deployment plan are documented in the SOW.
- CML validation remains dependent on access to a supported x86_64 host. The course instructions state that the required local CML image does not run on Apple Silicon, and the current development computer is `arm64`.

## Sprint 1 Status

- Eight project-specific JSON message schemas are defined with exact fields, types, directions, and examples.
- TCP messages use UTF-8 newline-delimited JSON with a 4096-byte payload limit and persistent per-client receive buffers.
- Graceful disconnects, zero-byte TCP EOF, resets, broken pipes, and timeouts all lead to one cleanup path.
- The server game flow is defined in a GitHub-rendered Mermaid `stateDiagram-v2` diagram.
- AI use is limited to implementing and checking the exact codec described by the project protocol documents.

## Sprint 2 Status

- The server uses one non-blocking `selectors` event loop to service both clients without blocking.
- Mutable game state is isolated to the event-loop thread, with exact ownership rules for the board, turn, sequence, clients, buffers, and leaderboard.
- Valid updates are serialized once and queued to both player sockets before the next game event is processed.
- A Mermaid `sequenceDiagram` documents valid moves, invalid and out-of-turn moves, terminal score broadcasts, and disconnect handling.

## Sprint 3 Status

- `server.py` uses a non-blocking selector loop and binds to `0.0.0.0`.
- `client.py` resolves the supplied hostname and handles DNS failures without a traceback.
- Both programs use the Sprint 1 newline-delimited JSON protocol and exact message schemas.
- The server enforces turns, checks moves, broadcasts board state, handles disconnects, and updates scores.
- Unit and localhost integration tests cover framing, game rules, CLI validation, and a complete two-client game.

## Run the Game Locally

Start the server in one terminal:

```bash
python3 server.py -p 45700
```

Start one client in each of two other terminals:

```bash
python3 client.py -i localhost -p 45700
```

For the later CML deployment, replace `localhost` with `server.fisher.edu`.

## Remaining Milestones

1. Deploy the three application nodes and two routers in CML.
2. Configure DHCP, routing, and authoritative DNS for `server.fisher.edu`.
3. Capture and document DHCP, DNS, and gameplay traffic in Wireshark.

## Development Setup

```bash
python3 --version
python3 -m venv .venv
source .venv/bin/activate
python3 -m unittest discover -s tests -v
```

No third-party runtime packages are planned for the initial implementation.
