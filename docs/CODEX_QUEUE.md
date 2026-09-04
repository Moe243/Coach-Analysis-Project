# Codex Automation Queue

This file is the source of truth for unattended Codex task order and execution state. The complete human-approved prompt text supplied for each task remains authoritative for task-specific requirements.

## Automation state

`PAUSED`

Codex must not start engineering/research work while this value is `PAUSED`.

Change it to `ENABLED` only when the Codex Automation is configured to use the approved prompt set and the local Checkpoint 11B worktree is available to Prompt 1.

## Overnight window

Default timezone: `America/Chicago`

Default morning cutoff: `08:00`

When the overnight run is enabled, replace the value below with an explicit ISO timestamp. Codex must not begin a new task after that cutoff.

`RUN_UNTIL: NOT_SET`

## Current repository/worktree warning

Prompt 1 is intentionally defined against the current local dirty Checkpoint 11B worktree. A remote environment that can see only GitHub `main` cannot perform Prompt 1 correctly.

Do not enable this queue unless Codex has access to that intended local project/worktree state.

## Queue rules

1. Execute only tasks listed under **Approved tasks** with status `READY`.
2. Work on at most one task per automation run.
3. Process tasks in the dependency order below.
4. Never invent tasks, expand scope, or silently reinterpret acceptance criteria.
5. Follow task-specific branch/worktree and delivery instructions exactly.
6. Never merge automatically.
7. If methodology, data grain, source evidence, licensing, secrets, deployment access, or repository conflicts require judgment outside the approved prompt, mark/report the task `BLOCKED` and stop.
8. A task is not complete until required validation passes. Report skipped tests separately.
9. Preserve every invariant in `docs/CODEX_AUTOMATION.md`.
10. Follow the worktree handoff rules in `docs/CODEX_OVERNIGHT_SEQUENCE.md`.
11. Do not begin a new task after `RUN_UNTIL`.
12. If the queue is empty, paused, expired, or blocked, stop without inventing work.
13. Never clean/reset/overwrite an intentionally dirty worktree belonging to another queued task.
14. Prompt 4 must review the exact dirty verification worktree produced by Prompt 3.

## Status values

- `READY` — approved for unattended execution when dependencies and automation state permit
- `IN_PROGRESS` — currently being worked
- `BLOCKED` — requires human decision or unavailable dependency
- `REVIEW` — implementation/research finished and ready for human review
- `DONE` — human-approved and merged/closed where applicable

## Approved tasks

### TASK CAX-001 — Close Checkpoint 11B

- Status: READY
- Priority: P1
- Dependency: none
- Objective: Perform the final evidence-integrity review of the completed local Checkpoint 11B work, correct only genuine defects, reproduce required counts/boundaries, and close 11B.
- Worktree: current local dirty Checkpoint 11B worktree
- Known pre-11B baseline: `180264e674c40e6c1618ace9e4d573863984b98a`
- Delivery: if and only if the complete Prompt 1 requirements pass, commit as `data: expand verified coaching evidence` and push to `origin/main`.
- Stop condition: if 11B cannot close cleanly, block the entire remaining sequence.
- Complete instructions: human-approved **PROMPT 1 — CLOSE CHECKPOINT 11B**.

### TASK CAX-002 — Relationship Explorer Final Structural UX Refinement

- Status: READY
- Priority: P2
- Dependency: CAX-001 must complete successfully
- Objective: Implement the approved final Journey/Team History/Full Network structural UX refinement without analytics/model changes.
- Worktree: isolated worktree created from clean post-11B `origin/main`
- Delivery: leave uncommitted, unpushed, undeployed, and preserved for human review.
- Isolation: do not pass this dirty frontend worktree into CAX-003 or CAX-004.
- Complete instructions: human-approved **PROMPT 2 — RELATIONSHIP EXPLORER FINAL UX**.

### TASK CAX-003 — Complete Coach Verification

- Status: READY
- Priority: P3
- Dependency: CAX-001 must complete successfully
- Objective: Perform the broad simple-search-first plus archival pass for every unresolved OC, QB Coach, and Play Caller team-season cell from 2010–2025, preserving strict evidence standards and rebuilding research-only PCAE attribution as specified.
- Worktree: second isolated worktree created from clean post-11B `origin/main`
- Delivery: leave uncommitted, unpushed, undeployed, and preserved intact for CAX-004.
- Critical rule: 100% is a target, never a reason to lower verification standards.
- Complete instructions: human-approved **PROMPT 3 — COMPLETE COACH VERIFICATION**.

### TASK CAX-004 — Independent Adversarial Verification Review

- Status: READY
- Priority: P4
- Dependency: CAX-003 must complete
- Objective: Independently challenge CAX-003 for both false negatives and false positives, audit intervals/identity/source diversity/PCAE attribution, and correct only independently verified defects.
- Worktree: EXACT SAME dirty coaching-verification worktree produced by CAX-003
- Delivery: leave uncommitted, unpushed, undeployed, ready for human review.
- Critical rule: do not start from clean main and do not discard CAX-003 changes before reviewing them.
- Complete instructions: human-approved **PROMPT 4 — INDEPENDENT VERIFICATION REVIEW**.

## Completion boundary

After CAX-004, stop.

Do NOT automatically start Coach Effect equation/model-selection research, production scoring, rankings, deployment, or any additional checkpoint.

Expected intentional end state:

- `main`: contains only the approved Prompt 1 / Checkpoint 11B closeout from this sequence
- one dirty isolated Relationship Explorer UX worktree from Prompt 2
- one dirty isolated coaching-verification worktree containing Prompt 3 plus Prompt 4 review/corrections

Both dirty worktrees remain for human review.

## Completed tasks

Move human-approved tasks here only after they are merged/closed or otherwise explicitly accepted.
