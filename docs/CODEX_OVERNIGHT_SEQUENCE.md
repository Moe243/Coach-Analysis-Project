# Approved Overnight Codex Sequence

This file defines the worktree and dependency order for the current four-task overnight run. The complete human-approved prompt text for each task remains authoritative.

## Required order

1. Prompt 1 — Close Checkpoint 11B
2. Prompt 2 — Relationship Explorer Final Structural UX Refinement
3. Prompt 3 — Complete Coach Verification: Broad Search + Archival Pass
4. Prompt 4 — Independent Adversarial Verification Review

Do not reorder, skip, or invent tasks.

## Prompt 1 — Close Checkpoint 11B

Run against the current local Checkpoint 11B worktree, which is intentionally dirty.

Known pre-11B baseline:

`180264e674c40e6c1618ace9e4d573863984b98a`

Prompt 1 may perform its focused evidence review/corrections and, only when its own acceptance conditions pass, create the approved commit:

`data: expand verified coaching evidence`

Prompt 1 is explicitly authorized to push that commit to `origin/main`.

If Prompt 1 cannot close cleanly, stop the entire sequence. Prompts 2–4 must not begin.

Record the resulting clean post-11B `origin/main` commit as `POST_11B_MAIN`.

## Prompt 2 — Relationship Explorer Final Structural UX Refinement

Only after Prompt 1 closes successfully.

Create/use an isolated worktree based on `POST_11B_MAIN`.

This worktree belongs only to Prompt 2.

Follow Prompt 2 exactly.

Its final state must remain:

- uncommitted
- unpushed
- undeployed
- preserved for human review

Do not allow Prompt 3 or Prompt 4 to inherit Prompt 2 frontend changes.

## Prompt 3 — Complete Coach Verification

Only after Prompt 1 closes successfully. Prompt 2 does not need to be committed because Prompt 3 must not use Prompt 2's worktree.

Create/use a second isolated worktree based on the clean `POST_11B_MAIN` commit.

This worktree belongs to the coaching-verification sequence (Prompts 3 and 4).

Prompt 3 performs the broad/simple-search-first plus archival verification pass for unresolved Offensive Coordinator, QB Coach, and Play Caller cells from 2010–2025, followed by the specified research-only PCAE attribution rebuild.

Follow the complete human-approved Prompt 3 exactly.

Its final state must remain:

- uncommitted
- unpushed
- undeployed
- preserved intact for Prompt 4

Do not clean, reset, stash away, or replace Prompt 3's dirty verification result before Prompt 4.

## Prompt 4 — Independent Adversarial Verification Review

Prompt 4 is dependent on completion of Prompt 3.

Use the EXACT SAME dirty verification worktree left by Prompt 3.

Do not create a clean worktree for Prompt 4.

Prompt 4's purpose is to independently challenge Prompt 3 for both:

- false negatives: qualifying evidence was missed and a cell remains unresolved unnecessarily
- false positives: a row was promoted to VERIFIED without evidence meeting the project standard

Prompt 4 may correct only defects it independently verifies, according to its complete human-approved prompt.

After Prompt 4, the coaching-verification worktree must still remain:

- uncommitted
- unpushed
- undeployed
- ready for human review

Do not begin Coach Effect equation/model-selection research after Prompt 4.

## Cross-task isolation

At the end of the sequence there may intentionally be two separate dirty worktrees:

1. Relationship Explorer UX worktree from Prompt 2
2. Coaching verification + adversarial review worktree from Prompts 3–4

They must not be combined automatically.

`main` should contain only the approved Prompt 1 Checkpoint 11B closeout unless a human later approves additional work.

## Global stop conditions

Stop rather than weaken project integrity if any task requires:

- fabricated coaching evidence
- lowering role-verification standards to reach 100%
- inferring Play Caller from OC/HC/QB Coach title alone
- changing PAE or PCAE definitions
- implementing Coach Effect weights/rankings/production score
- PFR scraping/ingestion
- production Neon writes
- manual deployment
- destructive or unrelated architecture changes
- overwriting another task's dirty worktree

100% coaching verification is a target, not permission to overstate evidence.

## Morning cutoff

Use `RUN_UNTIL` from `docs/CODEX_QUEUE.md` in `America/Chicago`.

At or after the cutoff, do not start a new task. Leave current worktree state understandable and report completed/incomplete task status.
