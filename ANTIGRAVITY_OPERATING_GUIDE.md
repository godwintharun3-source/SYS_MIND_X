# Antigravity Operating Guide for 365 Daily Sessions

## Recommended setup
- Open the extracted project root as one Antigravity workspace.
- Keep `AGENTS.md` at the root.
- Keep workspace rules in `.agents/rules/`.
- Keep reusable skills in `.agents/skills/`.
- Use Request Review/default command execution mode, terminal sandboxing where available, workspace-only file access and artifact review.

Antigravity's current documentation describes Agent Skills as reusable folders containing `SKILL.md`; the workspace default is `.agents/skills`. Workspace rules can be placed in `AGENTS.md` or `.agents/rules/*.md`. The old workflow system is deprecated in current docs in favour of skills.

## One-time first message
Paste `prompts/00_BOOTSTRAP_MASTER_PROMPT.md`. Ask Antigravity to inspect the workspace, validate the plan, and begin only Day 001. Do not allow it to perform privileged host changes.

## Daily process
For Day N:
1. `python3 tools/day_tracker.py status`
2. `python3 tools/day_tracker.py start --day N`
3. Paste all contents of `daily-prompts/DAY-NNN.md` into the agent.
4. Let the agent implement only that day's objective.
5. Inspect the diff and test evidence yourself.
6. If accepted: `python3 tools/day_tracker.py complete --day N --summary "..." --tests "..." --reviewed`
7. If not accepted: do not advance. Re-run the same day's prompt with the unresolved failure details.

## Use of /goal
For one bounded day, prefix or invoke `/goal` if supported by your Antigravity surface. It is intended to run the task autonomously until completion. Keep the workspace safety rules active and review the final diff. Do not use it to authorise high-impact operating-system changes.

## Daily reminder automation (Antigravity App)
The current `/automation` feature is documented for the Antigravity App. It runs a fresh conversation each time; it does not carry prior conversation memory. Use it only as a reminder/state-check unless you have separately reviewed scoped permissions.

Suggested prompt:

`/automation every weekday at 9:00 AM Asia/Kolkata, open the SYSTEM MIND project state files, read .project-state/current_day.json and docs/PROJECT_STATE.md, identify the next incomplete daily prompt, and remind me of the exact DAY-NNN.md path and the start command. Do not edit source code, install software, update the operating system, access personal files or run privileged commands.`

If you use only Antigravity IDE and not the App, do not assume `/automation` is available there. Use the day tracker and open the next daily prompt manually. `/schedule` belongs to a conversation and is not a substitute for persistent project state.

## Conversation recovery
If Antigravity starts a fresh conversation, tell it: `Read AGENTS.md and the project state files, inspect Git, and continue the current day only.` The repository state files are authoritative.
