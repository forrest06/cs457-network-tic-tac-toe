# CS 457 Network Tic-Tac-Toe

Sprint 0 through Sprint 2 design repository for Forrest Fisher's CS 457 final project.

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

## Planned Milestones

1. Implement and test the finalized NDJSON codec.
2. Implement pure game-state and win/draw logic from the FSM.
3. Implement the selector-based server and two CLI clients.
4. Add unit and end-to-end tests, including TCP framing edge cases.
5. Deploy the three application nodes and two routers in CML.
6. Configure DHCP, routing, and authoritative DNS for `server.fisher.edu`.
7. Capture and document DHCP, DNS, and gameplay traffic in Wireshark.

## Development Setup

```bash
python3 --version
python3 -m venv .venv
source .venv/bin/activate
python3 -m unittest discover -s tests -v
```

No third-party runtime packages are planned for the initial implementation.
