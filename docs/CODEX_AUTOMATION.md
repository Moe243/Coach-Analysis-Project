# Codex Automation Operating Contract

This document defines the guardrails for unattended Codex work on this repository.

## Purpose

Allow the project owner to approve a set of engineering tasks before going offline, then let a Codex Automation process those tasks on its schedule until the configured morning cutoff or until the queue becomes empty or blocked.

The automation is an executor, not a product manager or research lead.

## Source of truth

Read these before every run:

1. `docs/CODEX_QUEUE.md`
2. `docs/PROJECT_PLAN.md`
3. `METHODOLOGY.md`
4. `LIMITATIONS.md`
5. `DATA_DICTIONARY.md`
6. relevant checkpoint reports and architecture documentation

Only tasks marked `READY` in `docs/CODEX_QUEUE.md` are authorized.

## Project invariants

Never violate these without explicit human approval in the queue task itself:

- Do not fabricate coaching assignments, QB facts, source evidence, analytical values, or citations.
- Preserve canonical coach identities and canonical GSIS QB identities.
- Preserve assignment interval grain and `assignment_key` semantics.
- Preserve QB analytical grain `(player_id, team_id, season)` and load/version lineage where applicable.
- PAE remains `Actual EPA/dropback - Expected EPA/dropback`.
- Never join PAE by player-season alone.
- Missing analytical values remain unavailable/null; never silently replace them with zero.
- Preserve eligibility, reliability, verification, confidence, provisional, interim, shared-duty, retained, uncertainty, and suppression semantics.
- Team-season context must not be described as exact weekly coach-QB exposure unless the underlying evidence establishes the overlap.
- Do not imply mentorship, causal influence, or definitive coach impact where the model/evidence does not support it.
- PFR remains `PERMISSION REQUIRED BEFORE INGESTION`; do not scrape, bulk collect, ingest, redistribute, or add PFR-derived model features.
- Do not weaken source-lineage, deterministic-build, reproducibility, bounded-network, accessibility, or API integrity requirements to make a task pass.
- Do not silently resolve unresolved coaching evidence.
- Do not begin future checkpoint work unless that work appears as an approved queue task.

## Repository safety

Before every run:

1. Fetch the latest remote state.
2. Confirm the automation's expected starting branch/ref still exists.
3. Confirm there is no unexpected remote divergence relevant to the task.
4. Never assume local-only workstation changes are visible remotely.
5. Never force-push `main`.
6. Never push task work directly to `main`.
7. Never merge automatically.

If the task's assumptions no longer match the repository, mark/report it `BLOCKED` rather than improvising.

## Run algorithm

Each scheduled run must:

1. Read `docs/CODEX_QUEUE.md`.
2. If `Automation state` is not `ENABLED`, stop.
3. Resolve `RUN_UNTIL` in `America/Chicago`.
4. If the cutoff has passed, stop without starting a new task.
5. Find the highest-priority task marked `READY`.
6. If none exists, stop.
7. Re-read the task's allowed scope, forbidden scope, acceptance tests, validation, and stop conditions.
8. Inspect current repository state before editing.
9. Create/use the authorized `codex-auto/...` task branch.
10. Implement only that one task.
11. Run targeted tests first, then the required regression suites listed by the task.
12. If validation fails, attempt only in-scope corrections. If resolution requires scope expansion or judgment, report `BLOCKED` and stop.
13. Inspect the final diff for unrelated changes, secrets, generated junk, data artifacts, and project invariant violations.
14. Commit the task branch only when the task's required validation passes.
15. Report the branch, commit, changed files, tests, skips, limitations, and review notes.
16. Leave the work for human review. Never merge it automatically.
17. Do not start a second task in the same automation run.

A later scheduled run may take the next `READY` task if the queue is still enabled and before the cutoff.

## Stop immediately when

Stop and require human review if any of these occur:

- methodological or statistical interpretation decision
- data-grain incompatibility
- source/licensing ambiguity
- need to fabricate or infer missing coaching evidence
- PFR ingestion requirement
- production credential or secret requirement not already safely configured
- migration that risks destructive data loss
- unexpected divergence from approved repository state
- acceptance criteria conflict with existing project contracts
- failing tests that can only be resolved by broadening scope
- security issue that changes the intended architecture materially
- morning cutoff reached

## Overnight completion behavior

The automation is considered finished for the night when any of these is true:

- all approved tasks are in `REVIEW`, `BLOCKED`, or `DONE`
- `RUN_UNTIL` has passed
- the queue is `PAUSED`
- a blocking decision is required

It must not invent additional work to fill remaining time.

## Morning review

The owner should receive/review for every attempted task:

- task ID and objective
- status
- branch and commit
- files changed
- validation results
- skipped tests and why
- blockers or limitations
- whether project invariants remained intact
- recommended next human action

Human review remains the release gate.
