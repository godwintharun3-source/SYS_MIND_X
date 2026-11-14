# SYSTEM MIND X - Antigravity 365-Day Development Pack

This pack contains a bounded 365-working-day plan for a solo developer building a cross-platform AI computer-operation platform and a Linux-based SYSTEM MIND OS prototype.

## Important scope boundary

The target is a feature-complete first release for a defined compatibility matrix, not support for every computer, every OS release, every firmware vendor or every possible file type. Universal hardware coverage and security maintenance remain ongoing work after v1.0.

## Start here

1. Open this folder as the Antigravity workspace (or copy its contents into the root of your new SYSTEM-MIND repository).
2. Read `START_HERE.md`.
3. Paste `prompts/00_BOOTSTRAP_MASTER_PROMPT.md` into Antigravity once.
4. Review generated architecture and safety decisions before allowing implementation.
5. Begin Day 001 using `daily-prompts/DAY-001.md`.
6. After the agent finishes, inspect code changes and test results. Advance the tracker only after your review.

## Daily continuity

Antigravity must read `docs/PROJECT_STATE.md`, `docs/DAILY_LOG.md`, `docs/DECISION_LOG.md`, `docs/BLOCKERS.md`, `docs/ROADMAP_365_DAYS.md`, and `.project-state/current_day.json` at the start of every daily session.

The next day is not marked complete automatically. The agent writes `awaiting_review`; you review the diff and evidence, then run:

```bash
python3 tools/day_tracker.py status
python3 tools/day_tracker.py start --day 1
# After implementation and your review:
python3 tools/day_tracker.py complete --day 1 --summary "..." --tests "..." --reviewed
```

Replace `1` with the current day number. Do not skip unfinished days.

## Antigravity features

- Workspace instructions are in `AGENTS.md` and `.agents/rules/`.
- Reusable project skills are in `.agents/skills/`.
- The daily prompts are individual Markdown files in `daily-prompts/`.
- Use the Antigravity App's `/automation` only for reminders or carefully scoped recurring checks. Recurring automations start fresh conversations, so they must read the repository state files.
- Use `/goal` only for one bounded daily task with the project safety rules loaded. Do not set it to perform unrestricted privileged changes.
- Antigravity's legacy Workflows are deprecated in current documentation in favour of Skills; this pack uses Skills.

## Development assumptions

- One developer, focused full-time, approximately 6-8 hours per workday.
- Development host: Apple Silicon MacBook Air M1 running macOS.
- First implementation: macOS companion agent and local digital twin.
- Cross-platform targets: defined macOS, Windows and Ubuntu/NixOS test configurations.
- SYSTEM MIND OS: NixOS-based x86_64 and ARM64 virtual-machine alpha, not a new kernel.
- User-installed apps and user project dependencies are excluded from automatic system updates.
- Untrusted or unknown files are not granted unrestricted execution. They are inspected and, where appropriate, tested in isolation.

See `PROJECT_CHARTER.md` and `ROADMAP_365_DAYS.md` before coding.
