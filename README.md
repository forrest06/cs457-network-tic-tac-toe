# CS 457 Network Tic-Tac-Toe

Sprint 0 proposal repository for Forrest Fisher's CS 457 final project.

## Project Summary

Network Tic-Tac-Toe is a two-player command-line game with one authoritative Python server and two TCP clients. The first client is Player X, the second is Player O, and the server validates turns, stores the canonical 3-by-3 board, detects wins or draws, and broadcasts synchronized state to both players.

- **Authoritative DNS name:** `server.fisher.edu`
- **Planned transport:** TCP on port `45700`
- **Planned application format:** Newline-delimited JSON
- **Language:** Python 3
- **Sprint 0 SOW:** [`sow_template.md`](sow_template.md)
- **Local setup record:** [`docs/toolchain-verification.md`](docs/toolchain-verification.md)

## Sprint 0 Status

- Python 3 and Git are installed and verified.
- A Python-focused `.gitignore`, EditorConfig file, and VS Code project settings are committed.
- Game scope, rules, victory conditions, draw handling, DNS name, protocol direction, concurrency strategy, implementation plan, and CML deployment plan are documented in the SOW.
- CML validation remains dependent on access to a supported x86_64 host. The course instructions state that the required local CML image does not run on Apple Silicon, and the current development computer is `arm64`.

## Planned Milestones

1. Finalize and test the NDJSON application-layer protocol.
2. Implement pure game-state and win/draw logic.
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
