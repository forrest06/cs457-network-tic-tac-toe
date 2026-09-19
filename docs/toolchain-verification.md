# Sprint 0 Toolchain Verification

**Verified:** 2026-09-19

**Student:** Forrest Fisher

## Local Tools

| Requirement | Result | Evidence |
|---|---|---|
| Python 3.x | Verified | `Python 3.9.6` |
| Git | Verified | `git version 2.50.1 (Apple Git-155)` |
| Editor configuration | Ready | `.editorconfig` and `.vscode/settings.json` are committed |
| Public Git repository | Pending publication | Local repository and initial commit are ready |
| Cisco Modeling Labs | Blocked on this host | Host is `arm64`; the course CML install page requires x86_64 and states that Mac M-series systems will not work |

## CML Resolution Needed

The course CML instructions require at least four virtualization-capable x86_64 vCPUs, 8 GB RAM, 30 GB disk, Ubuntu 24.04 as the CML base system, and UEFI firmware. The current development computer is an Apple Silicon Mac (`arm64`). UTM is installed, but it contains no CML virtual machine and cannot satisfy the course image's x86_64 requirement.

Before Sprint 4, run CML on an instructor-provided remote instance or another supported x86_64 Windows/Linux/Intel Mac host. Verification is complete when the student can sign into the normal CML portal, create a lab, and start the required nodes.

## Reproduction Commands

```bash
python3 --version
git --version
uname -m
```
