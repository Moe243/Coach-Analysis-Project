# Codex Automation Queue

This file is the only source of truth for unattended Codex engineering work.

## Automation state

`PAUSED`

Codex must not start engineering work while this value is `PAUSED`.

Change it to `ENABLED` only when the repository state and the next task are approved for unattended work.

## Overnight window

Default timezone: `America/Chicago`

Default morning cutoff: `08:00`

When an overnight run is enabled, add an explicit ISO timestamp below. Codex must not begin a new task after that cutoff.

`RUN_UNTIL: NOT_SET`

## Current repository warning

`docs/PROJECT_PLAN.md` currently describes Checkpoint Eleven as local work. Local or uncommitted workstation changes are not visible to remote Codex automation.

Keep this queue paused until those changes are committed/pushed or intentionally excluded from the unattended run.

## Queue rules

1. Execute only tasks listed under **Approved tasks** with status `READY`.
2. Work on at most one task per automation run.
3. Process tasks by priority, then numeric task ID.
4. Never invent tasks, expand scope, or silently reinterpret acceptance criteria.
5. Never push directly to `main`.
6. Use a task branch named `codex-auto/<task-id>-<short-slug>` unless the task explicitly specifies a safe existing branch.
7. Never merge automatically.
8. If methodology, data grain, source evidence, licensing, secrets, deployment access, or repository conflicts require judgment, mark/report the task `BLOCKED` and stop.
9. A task is not complete until required validation passes. Report skipped tests separately.
10. Preserve every invariant in `docs/CODEX_AUTOMATION.md`.
11. Do not begin a new task after `RUN_UNTIL`.
12. If the queue is empty, paused, expired, or blocked, stop without inventing work.

## Status values

- `READY` — approved for unattended execution
- `IN_PROGRESS` — currently being worked
- `BLOCKED` — requires human decision or unavailable dependency
- `REVIEW` — implementation finished and ready for human review
- `DONE` — human-approved and merged/closed

## Approved tasks

No unattended tasks are approved yet.

Use this template:

```md
### TASK CAX-001 — Short task name

- Status: READY
- Priority: P1
- Objective: One concrete outcome.
- Why now: Why this belongs next.
- Starting ref: main
- Allowed scope:
  - Exact files, systems, or feature area Codex may modify.
- Forbidden scope:
  - Anything explicitly out of bounds.
- Requirements:
  1. Requirement one.
  2. Requirement two.
- Acceptance tests:
  1. Observable proof one.
  2. Observable proof two.
- Required validation:
  - targeted tests
  - required regression suites
- Delivery:
  - Commit on the task branch.
  - Leave the result for human review.
  - Never merge automatically.
- Stop conditions:
  - Any condition requiring human review before proceeding.
```

## Completed tasks

Move human-approved tasks here only after they are merged or intentionally closed.
