# Checkpoint 14 — QB Style Profile and Player State

Status: **COMPLETE**

Data version: `c14-43283062e788e686`

Baseline: `ac53008f05e6771d68a0e00b01a37a2b57224aaf`

Checkpoint 14 creates a deterministic, file-only quarterback representation for future Phase II
research. It does not fit a Player State transition, projection, fit, simulation, Coach Effect, or
production model and changes no database, API, frontend, or deployment behavior.

## State universe and evaluation cohort

The 8,457 state headers cover 2010–2025 and are generated independently of target-season
outcomes. Membership is based only on prior resolved QB history, immutable draft/QB facts, or a
dated QB depth-chart record observed by August 31. Undated target-season rosters and week-one
depth charts cannot add a player. Retired players can remain because the checkpoint does not infer
active-roster status.

The separate retrospective evaluation table contains 1,187 canonical QB-team-season outcomes.
Of those, 1,146 join to an as-of state and 41 remain explicitly marked
`NOT_IN_ASOF_STATE_UNIVERSE`. Evaluation outcomes never backfill state membership.

## Profiles and state

The build creates 52,572 QB-team-season profile rows and 53,382 canonical QB-season profile rows.
Multi-team stints remain separate; player-season rates are rebuilt from additive numerators and
denominators. Prior PAE requires an invariant preseason expectation across a player's team rows
and remains distinct from the preseason ability estimate.

The 50,787 state feature rows use sources strictly before their target season. The preseason
ability estimate is an empirical-Bayes estimate of cumulative historical EPA/dropback. It is not
a latent or composite QB score. Prior-season observed EPA, prior PAE, career observation, trend,
style, and uncertainty remain separate fields.

Low-volume values are suppressed or shrunk using as-of empirical Beta-binomial or normal-normal
priors. Every estimate records exposure, prior parameters, shrinkage weight, standard error, 95%
interval, reliability, qualification, lineage, and missingness. The complete availability table
also represents absent player-feature combinations rather than silently treating them as zero.

## Stability and portability

The predeclared stability rule uses 100 adjacent qualified seasons, Spearman correlation of at
least 0.25, 80% coverage, positive early/late-era and medium/high-volume direction, and nearby
sensitivity thresholds. Core admission additionally requires at least two of the stricter
125-pair, 0.30-correlation, and 85%-coverage checks.

Scheme/situation-conditioned performance also requires a portability audit across at least 50
material environment changes, team-changer correlation of at least 0.20, a positive 80% bootstrap
lower bound, and the same correlation direction among team changers and team stayers. Features
failing either gate remain conditional or descriptive.

The final registry contains 31 features: 13 core, 13 conditional, and five descriptive. These
labels are research admission statuses, not claims that team and scheme effects have been removed.

## Artifacts and determinism

Ignored artifacts are published beneath
`data/processed/qb_player_state/c14-43283062e788e686/`. The manifest binds every input, the final
registry, all thresholds and shrinkage rules, dependency versions, and the source-code hash.
Sorted Parquet/CSV outputs and canonical JSON are atomically published with checksums and `LATEST`.

Checkpoint 15 remains deferred. No future projection, state transition, target-team selection,
scenario simulation, database load, API, frontend, or deployment was added.
