# Checkpoint 15 — Player × Scheme Fit

## Decision

- Corrected Checkpoint 15 version: `c15-c4d7c86f56238a49`
- Preserved original run: `c15-2ac7553234223553`
- Baseline: `505fd184bab5f1e0425cf68fba966d2c8652c1bb`
- Player × Scheme Fit status: **NOT ESTIMABLE / DATA-LIMITED**
- Standalone fit quantity: **not justified**
- Checkpoint 16 readiness: **NOT READY**
- Checkpoint 16 may consume Player × Scheme interactions: **no**

The original run and its checksums remain unchanged. Its `NOT SUPPORTED` label was too strong:
M2 produced no folds and therefore did not test Player × Scheme interactions. The corrected
scientific conclusion is a completed data-limited result, not evidence that fit does not exist.
The repository cannot establish
the target team by the August 31 boundary for historical veterans before 2025: the older roster
and depth-chart assets are not timestamped. Immutable draft-team facts provide historical
preseason-known team evidence, but those rows are rookies and therefore have no prior NFL style
profile. Dated preseason depth charts become usable in 2025. Consequently, no rolling-origin
training fold contains the qualified prior player-style interactions required for M2.

## Question, grain, and targets

The research question is whether measurable QB-style alignment with a measurable prior offensive
environment improves future QB prediction beyond Player State and Scheme main effects. It does
not model QB-name × coach-name effects, construct a Coach Effect, or create a fit score.

The entering-season grain is one row per `(player_id, target_season, cohort_version)`. Checkpoint
14 Player State remains team-independent. The current data attach the target team separately only
through:

1. the immutable draft-team fact in the player's draft season; or
2. the most recent dated QB depth-chart snapshot on or before August 31.

The corrected assignment contract retains `player_id`, `target_season`, `team_id`, evidence type,
evidence date and date precision, source, source hash, August 31 as-of date, and verification
status. Exact dated evidence supersedes the coarse immutable-draft bound; among dated records the
latest pre-cutoff date wins. Conflicting teams, or a team and release state, on the same latest
date are `AMBIGUOUS_PRESEASON_TEAM`. A verified release without a later assignment is
`PRESEASON_NO_TEAM_KNOWN`. Undated and post-cutoff records cannot establish a target team. Target
outcomes are joined only after the entering-season cohort is frozen, on the complete
`(player_id, target_team_id, target_season)` key. Multi-team outcomes therefore cannot
cross-attach or retroactively select a team.

The primary target is target-season EPA/dropback. The secondary target is target-season PAE,
retaining the existing definition `actual EPA/dropback - expected EPA/dropback`. Both require at
least 50 target-season dropbacks for this research evaluation. That outcome threshold affects
evaluation only; it never constructs Player State or target-team identity.

## Features and timing

All predictors are available by August 31 of the target season and have a maximum source season
strictly below the target. Checkpoint 14 supplies the player state and uncertainty. Checkpoint 13
supplies scheme records through `AsOfFeatureStore`; the Checkpoint 15 cohort retains player
reliability, missingness, shrinkage weight, standard error, interval, scheme sample size, scheme
status, and scheme predictive permission.

Primary player features are preseason ability EPA/dropback, recent EPA/dropback, success rate,
CPOE, sack rate, scramble rate, shotgun tendency, average air yards, target-depth tendencies,
age, seasons since rookie year, and prior/career starts and dropbacks. Preseason ability remains
distinct from recent observed performance. Conditional challengers add prior PAE and pass-location
tendencies; no descriptive or predictively forbidden Checkpoint 14 feature is used.

Primary scheme features are the target team's prior-season shotgun, no-huddle, pass, early-down
pass, neutral pass, short/intermediate/deep target, average air-yards, and scramble rates. Expected
pass rate and PROE are conditional challengers. For target season `Y`, every Scheme record has
`source_season = Y-1`, `target_season = Y`, and an August 31 as-of date. These are historical
Scheme Engine values, not target-season realized behavior and not causal coach characteristics.

The eight predeclared interactions are:

- player scramble rate × scheme scramble rate;
- player shotgun rate × scheme shotgun rate;
- player short, intermediate, and deep target rates × the corresponding scheme rates;
- player average air yards × scheme average air yards;
- player scramble rate × scheme pass rate; and
- player average air yards × scheme neutral-pass rate.

An interaction remains null unless both components exist. There is no blind cross-product search.
Conditional or environment-conditioned split-performance features are not promoted to inherent
player traits.

## Models and validation

- M0: core Player State main effects.
- M1: M0 plus core Scheme main effects.
- M2: M1 plus the eight predeclared interactions, only when a training fold contains at least 20
  finite, varying observations for an interaction.
- Conditional sensitivities: M0/M1 plus the permitted conditional features.
- M3: not fit. Checkpoint 13 contains no as-of Play Caller PCAE feature records and the target
  caller cannot be established at the preseason cutoff for this cohort.

Each outer fold trains only on earlier seasons. Median imputation, missingness indicators,
standardization, feature qualification, and Ridge fitting occur inside that training window.
Ridge alpha is selected by inner rolling-origin MAE using only the outer training data; if no
inner fold qualifies, the predeclared alpha is used. No random split or full-data tuning is used.

The 8,032-row Player State cohort has 265 state rows with a safe target-team assignment (3.30%):
157 from immutable draft-team evidence and 108 from dated 2025 depth charts. Of those, 165 match
a retrospective outcome team and 130 clear the 50-dropback evaluation threshold: 77 draft and 53
dated-depth rows. Exclusions remain 7,767
`TARGET_TEAM_NOT_ESTABLISHED`, 100 `TARGET_TEAM_NO_OUTCOME`, and 35
`BELOW_OUTCOME_DROPBACK_MINIMUM`. The eligible rows span 2011–2025. Rolling evaluation produces
100 predictions per outcome/model across nine folds (2017–2025).

The retrospective participant audit is evaluation-only and never constructs an assignment. Among
the 1,058 target-season participant states, safe evidence matches 35 of 533 returning veterans
(6.57%), 23 of 235 team changers (9.79%), 103 of 104 rookies (99.04%), and 4 of 186 other/new
entrants (2.15%). The respective 50-dropback eligible counts are 28, 16, 84, and 2. A further 37
retrospective participant player-seasons are outside the Checkpoint 14 state universe.

No newly audited source adds approved coverage. Pre-2025 depth charts and weekly/final rosters are
undated at the August 31 boundary; dated injury-report rows begin after it; contract records are
year-only or hindsight histories; and PBP/player statistics are outcomes. The nflverse trades
asset is PFR-derived and is rejected for model use under the approved
`PERMISSION REQUIRED BEFORE INGESTION` decision. An exact-dated official NFL/team transaction
contract is implemented and tested, but no approved historical input currently populates it.
Season-level and source-family coverage are in `target_team_coverage_by_season.csv` and
`target_team_source_audit.csv`.

| Outcome | Model | n | RMSE | MAE | Pearson | Spearman | Direction accuracy |
|---|---|---:|---:|---:|---:|---:|---:|
| EPA/dropback | M0 | 100 | 0.21597 | 0.18047 | -0.1487 | -0.2206 | 0.38 |
| EPA/dropback | M1 | 100 | 0.21779 | 0.18245 | -0.1251 | -0.1890 | 0.42 |
| PAE | M0 | 100 | 0.20246 | 0.16637 | -0.0955 | -0.1451 | 0.63 |
| PAE | M1 | 100 | 0.20274 | 0.16713 | -0.0669 | -0.0728 | 0.63 |

M1 did not improve the full evaluation sample over M0: EPA/dropback MAE worsened by 0.00198 and
PAE MAE worsened by 0.00076. Conditional challengers also did not improve the result. These
estimates describe a narrow, shifting evidence cohort and are not production projections.

## Interaction, portability, and uncertainty result

M2 has zero out-of-sample folds and zero predictions. Historical eligible rows through 2024 are
draft-season rows with zero qualified prior style interactions; 2025 has 36–37 usable rows per
interaction, but there is no earlier interaction training sample. Therefore:

- M2 versus M1 is not estimable;
- coefficient signs, fold stability, standardized effects, and interaction bootstrap intervals
  are not estimable;
- the deterministic permutation/placebo test is not run because no M2 out-of-sample predictions
  exist;
- the M2/M1 block bootstrap records zero successful draws rather than a fabricated interval; and
- the interaction contribution artifact is empty and no standalone fit delta is published.

The 16-row team-change prediction subset is concentrated in the dated 2025 cohort. All 16 also
meet the predeclared large Scheme-change diagnostic: at least one core, as-of Scheme feature differs
from the prior team's same-boundary value by at least one standardized unit. This small subset
cannot establish interaction portability. M1's EPA/dropback MAE is 0.21822 versus M0's 0.22908,
but Spearman correlations are negative and there is no M2 estimate. Verified coaching-change
membership is unavailable and is not inferred. Dropback-threshold sensitivities at 25, 50, and
100 yield 144, 130, and 110 rows, respectively, but none creates historical interaction training
data. Personnel-family features remain a later-window conditional challenger and FTN features do
not drive the conclusion.

## Missingness and limitations

All 130 eligible rows have prior-environment Scheme values. Only 44 have a preseason ability
estimate, 37 have recent EPA/success/PAE/scramble/shotgun values, and 36 have CPOE, sack,
air-yards, depth, and pass-location values. Missing predictors remain null in the cohort. A model
may use the training median only when the training fold has at least ten finite, varying values,
and always adds a missingness indicator; unsupported values are never replaced with zero.

The target-team evidence gap changes the composition of the evaluation cohort: pre-2025 rows are
primarily drafted rookies, while dated 2025 snapshots admit veterans. That makes even the M0/M1
numbers unsuitable as a general historical QB projection claim. Draft team is a source-known
assignment fact, not proof that the player remained with that team at the cutoff; exact-key outcome
joining prevents a changed destination from being substituted, and unmatched cases are excluded.
Scheme describes prior observed team behavior and cannot be attributed causally to a coach.

Checkpoint 16 is not ready. M0 and M1 have negative out-of-sample correlations and negative
calibration slopes in a narrow cohort dominated historically by rookies; neither is an honest
projection foundation. A licensed, source-hashed historical preseason player-team assignment
contract with evidence dated on or before August 31 and representative returning-veteran and
team-change coverage is required first. Checkpoint 16 must not consume M2 coefficients, an
interaction contribution, a standalone fit quantity, or a Fit Score.

## Deterministic outputs

Artifacts publish atomically beneath
`data/processed/player_scheme_fit/c15-c4d7c86f56238a49/` and remain ignored by Git. The original
`c15-2ac7553234223553` directory is preserved. The corrected identity hashes Checkpoints 13/14,
source facts, all dated depth-chart inputs, feature/model/cohort
specifications, interaction definitions, thresholds, Ridge grid, seeds, source code, and Python,
NumPy, Polars, SciPy, and scikit-learn versions.

The structured outputs add the target-team evidence contract, source audit, season coverage, and
retrospective evaluation-category coverage to the fit registry, modeling cohort, preseason team
assignments,
rolling-fold assignments and metrics, model comparison and predictions, interaction definitions,
coefficients and effects, fold diagnostics, team/environment-change validation,
portability/sensitivity results, bootstrap and permutation results, missingness/coverage,
approval decision, leakage audit, checkpoint summary, and `MANIFEST.json`. Two independent clean
builds produced the same version and byte-identical deterministic artifacts.

Checkpoint 15 changes no production database, migration, API, frontend, deployment, Coach Effect,
coach ranking, Player State grain, Checkpoint 13 chronology, or Checkpoint 14 state artifact.
