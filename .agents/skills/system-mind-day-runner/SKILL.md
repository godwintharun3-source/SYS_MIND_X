---
name: system-mind-day-runner
description: Executes one bounded SYSTEM MIND development day with repository-state recovery, tests, security checks, documentation and a human-reviewed handoff.
---
# SYSTEM MIND Daily Development Skill

1. Read `AGENTS.md`, `PROJECT_CHARTER.md`, `docs/PROJECT_STATE.md`, `docs/ROADMAP_365_DAYS.md`, `docs/DECISION_LOG.md`, `docs/BLOCKERS.md`, `docs/DAILY_LOG.md`, `docs/ACCEPTANCE_GATES.md` and `.project-state/current_day.json`.
2. Inspect Git status, current branch, recent commits and the relevant implementation before editing.
3. Confirm the requested day equals `current_day` and is not already reviewed complete. If not, stop and report the mismatch.
4. Implement only the objective in that day's prompt. Do not broaden scope or skip ahead.
5. Prefer read-only and mock implementations first. Do not perform privileged host operations without exact user approval.
6. Add tests and run the relevant checks. Record failures honestly.
7. Update `docs/PROJECT_STATE.md`, `docs/DAILY_LOG.md`, `docs/BLOCKERS.md` and `docs/DECISION_LOG.md` as required.
8. Set state to `awaiting_review`; do not increment `current_day`.
9. Provide changed files, test commands and results, risks, manual review actions and the next day number.
