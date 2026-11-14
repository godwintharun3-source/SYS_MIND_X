# Start Here - Operating Procedure

## A. Create the workspace

Create a folder named `SYSTEM-MIND` on your Mac. Extract this pack into that folder. Open that folder as the Antigravity workspace. Initialise Git before implementation and make an initial commit containing only the planning files.

## B. One-time bootstrap prompt

Paste `prompts/00_BOOTSTRAP_MASTER_PROMPT.md` into Antigravity. Ask it to inspect the workspace and produce the architecture/implementation plan, but do not allow it to run privileged host operations. Review the proposed structure and update `docs/DECISION_LOG.md`.

## C. Start each day

1. Run `python3 tools/day_tracker.py status` in the workspace terminal.
2. Start the matching day: `python3 tools/day_tracker.py start --day N`.
3. Open `daily-prompts/DAY-NNN.md` and paste the entire prompt into Antigravity. Replace NNN with zero-padded day number; use the numeric N in the command.
4. The agent must read the continuity files, inspect Git state, implement only that day's bounded objective, run tests and write a handoff.
5. Review all diffs and test evidence. Do not accept a day just because the agent says it is complete.
6. Run `python3 tools/day_tracker.py complete --day N --summary "reviewed result" --tests "test commands and results" --reviewed` only after you have verified the work.
7. Start the next numbered day.

## D. If a day is not completed

Do not advance the tracker. Keep the current day active. Add blockers to `docs/BLOCKERS.md`. The next session repeats the same day's prompt, and the agent must continue from existing code rather than recreating it.

## E. Suggested Antigravity settings

- Use Request Review / default execution mode for terminal commands.
- Keep terminal sandboxing enabled when available.
- Restrict file access to the workspace.
- Keep artifact review enabled.
- Do not enable unrestricted command execution for this project.
- Never provide broad administrator credentials to the AI.

## F. Daily reminder

If you use the Antigravity App, you can create a reminder automation with a prompt like:

`/automation every weekday at 9:00 AM Asia/Kolkata, read SYSTEM-MIND/.project-state/current_day.json and SYSTEM-MIND/docs/PROJECT_STATE.md, identify the next incomplete development day, and remind me of the exact daily prompt file. Do not edit code, update the operating system, install software, or run privileged commands.`

Automations start fresh conversations, so the prompt deliberately reads the state files rather than relying on chat memory. The schedule is a reminder, not permission for unattended implementation.

## G. Daily completion rule

A day is complete only when:
- the requested implementation exists;
- tests relevant to the task pass or a blocker is documented;
- the code is reviewed;
- documentation is updated;
- Git changes are understandable;
- no safety boundary was bypassed;
- the handoff identifies the next day's task.
