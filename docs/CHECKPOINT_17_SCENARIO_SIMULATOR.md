# Checkpoint 17 — conditional one-year QB scenario research

Baseline: `da75c03563db4b6e033b140783767d00fc7149e7`. C16 was fast-forwarded and
pushed before this isolated checkpoint began. No production publication is involved.

## Scientific gate and estimand (declared before model results)

Historical destination identity is admissible **only as a supplied condition** for
estimating the observational conditional distribution of QB-team-season EPA/DB given
frozen Player State and the destination's prior-season scheme. It is not evidence the
team was known on August 31. The model does not predict assignment. C15's unconditional
preseason-target-team contract and NOT ESTIMABLE / DATA-LIMITED conclusion are unchanged.

This distinction permits a conditional predictive experiment, not identification of
the outcome of moving a particular QB to an arbitrary team. Assignment, playing time,
injury, roster quality, and survivorship are selected, potentially outcome-dependent
processes. We condition on a recorded stint with >=50 dropbacks. Retrospective team
membership and usage must never enter the frozen player representation or numerical
predictors. All target-year stints are kept separately; no hindsight selection of the
largest stint. Predictions across a player's stints share one C16 baseline and state.

Statistical background: [Shalizi's optimal-prediction notes](https://www.stat.cmu.edu/~cshalizi/2010-06-15-2-CSSS.pdf)
distinguish predictive conditional structure from counterfactual guarantees;
[Correa, Lee and Bareinboim](https://proceedings.mlr.press/v162/correa22a.html) formalize
the additional identification requirements for counterfactual transport. Their
results do not establish those requirements for this NFL dataset. This gate is our
scoped methodological judgment, not a claim those sources validate this application.

## Frozen experiment

- Modeling grain: `(player_id, team_id, target_season)`; state grain remains
  `(player_id, target_season)`. EPA numerator/dropback denominator remain stint-specific.
- M0: exact approved C16 B2 + chronological rolling bias point prediction. No PAE,
  Coach Effect, coach identities, or target-season scheme is used.
- M1: M0 plus centered prior-destination scheme main effects, Ridge without an intercept.
  Centering makes the training-reference scheme adjustment zero rather than silently
  changing the approved baseline intercept.
- M2: M1 plus the eight predeclared C15 interaction families. Centered player-style ×
  scheme products are orthogonalized against training player/scheme main effects and
  intercept, then standardized inside each fold. This avoids attributing omitted
  player main-effect corrections to a fit interaction. Missing products are explicitly
  masked; their observation indicators accompany them. No split-performance features.
  Numerical SVD rank tolerance 1e-8 handles rounded, nearly dependent compositional
  depth rates. A regression caught unstable default-rank inversion; this numerical
  correction changes no feature family, sample definition or acceptance threshold.
- C13 AsOfFeatureStore validates the request and lineage. Its recorded raw measures
  are used so the same football units have the same meaning across target years; C15
  train-only preprocessing supplies imputation and standardization. Source season is
  strictly prior and availability/standardization dates obey the August 31 boundary.
- Ten primary scheme features: shotgun, no-huddle, pass, early-down pass, neutral-pass,
  short/intermediate/deep target rates, average air yards, scramble rate. PROE,
  personnel and FTN are not searched as extra challengers in this small experiment.
- Missing raw values remain null in artifacts. Train-only median imputation and missing
  indicators are model preprocessing, never a fabricated zero observation. C14 feature
  reliability/uncertainty and C13 samples/missingness remain in lineage outputs.
- Outer expanding folds require >=120 earlier stint rows, three earlier seasons and
  >=20 test rows. Inner chronological folds require >=80 earlier rows/two seasons,
  >=15 validation rows. Alpha grid 0.1/1/10/100/1000, default 100 before an inner fold;
  minimize mean inner-fold MAE, larger-alpha tie break. Residual training targets use
  previously issued C16 baseline predictions, not in-sample fitted residuals.
- Equal stint weighting estimates conditional stint-level error. Repeated QBs and
  shared team-season environments are addressed by separate QB-cluster and team-season
  cluster paired bootstraps, not by pretending every row is independent. A single-team
  evaluation subset removes duplicated player-years; a >=200-dropback evaluation subset
  checks usage. These reuse issued predictions, not newly tuned/refitted subgroup models.
- Development ends 2018; 2019–2025 is fixed validation. Both this archive and the C16
  family/calibration choices have been viewed in earlier work, so validation is
  retrospective and cannot support a pristine prospective label.

## Advancement gates

Before seeing results: M1 must beat M0; M2 must additionally beat M1 and may advance only
if M1 advances. Development requires three folds, mean fold MAE gain greater than both
one standard error and 2% of comparator MAE, >=60% positive folds, and RMSE <=1.01 times
comparator. Final validation requires >=200 rows/five folds, >=2% MAE improvement,
non-worsening RMSE, >=60% improving folds, positive 95% lower bound of MAE gain in both
QB and team-season cluster bootstraps, and positive gain in single-team/high-volume
sensitivities. Real changers require >=50 rows/30 QBs/five seasons, improved MAE/RMSE,
and >=60% improving seasons. Calibration requires slope [0.5,1.5], |intercept| <=0.05
and 50/80/95% coverage within six percentage points. Insufficient evidence is not a pass.

Intervals use each model's own previously issued stint-level OOS absolute residuals,
trailing five seasons, >=100 observations, ordered `ceil((n+1)*coverage)` quantile.
They are empirical prediction intervals, not confidence intervals for an individual
environment effect; they have no conditional or exchangeability guarantee under
selection, repeated QBs, team dependence or distribution shift. See
[Tibshirani et al.](https://papers.neurips.cc/paper_files/paper/2019/hash/8fb21ee7a2207526da55a679f0332de2-Abstract.html)
for assumptions needed to extend conformal coverage under covariate shift; this
checkpoint does not estimate shift weights or claim those guarantees.

Paired QB-cluster sign-flip placebos are descriptive diagnostics conditional on fixed
OOS predictions, not an exact randomized assignment test or a model-refit permutation.
No choice is made from placebo results. All thresholds, randomness and serialization
are content-versioned. A negative result is successful research completion and produces
zero hypothetical 2026 scenarios, not disguised baseline-only simulations.

## Results

Research data `c17-9f582e4ac18d8cd6`; model `qb-scenario-9f582e4ac18d8cd6`.
**SCENARIO MODEL: NOT SUPPORTED. CHECKPOINT 17: COMPLETE research.
CHECKPOINT 18: NOT READY.** Zero hypothetical 2026 scenarios. The original C16
57 team-independent EPA projections remain intact; no PAE projection is added.

### Cohort and chronology

There are 1,187 canonical analysis QB-team-season records in 2010–2025. Exclusions
are assigned in explicit precedence order (a row can fail multiple conditions):

| First exclusion reason | Rows |
|---|---:|
| No as-of Player State | 41 |
| No frozen C16 OOS baseline (includes early years and unqualified participant rows) | 472 |
| Stint below 50 dropbacks, after the preceding checks | 7 |
| Eligible | 667 |

Eligible data span **2013–2025, 167 QBs, 662 player-seasons and 415 team-seasons**.
The first three seasons provide residual training history. There are **521 OOS stints
per model, 142 QBs, ten folds (2016–2025)**; development has 146 stints/three folds,
validation has **375 stints, 119 QBs, seven folds (2019–2025)**.
The latter differs from C16's 373 observations because C16 aggregates whole player-seasons;
C17 preserves stint outcomes, filters each stint and duplicates the baseline across them.
This difference is intentional and never changes the C16 point predictions themselves.

Baker Mayfield (`00-0034855`) in 2022 has two retained conditions: Carolina
(234 dropbacks, actual EPA/DB −0.161333) and Los Angeles (152, −0.067317).
Both share the exact same frozen state and **0.0176033193** baseline, while each uses
its own destination's 2021 scheme. No largest-stint substitution or cross-team outcome
join occurs. The Player State remains independent of both team conditions.

### Main comparison

All validation metrics below use the same 375 held-out stints. Positive direction means
correctly classifying above/below zero EPA/DB, not predicting a causal benefit from a move.

| Model | RMSE | MAE | Pearson | Spearman | Direction accuracy | Calibration slope | Intercept |
|---|---:|---:|---:|---:|---:|---:|---:|
| M0 C16 anchor | 0.166303 | 0.125335 | 0.373130 | 0.377449 | 63.73% | 1.041749 | −0.002892 |
| M1 + destination main effects | 0.167243 | 0.125714 | 0.361356 | 0.373725 | 63.47% | 0.978690 | −0.006520 |
| M2 + interactions | 0.167470 | 0.126041 | 0.358289 | 0.363078 | 62.13% | 0.971410 | −0.006672 |

- M1 versus M0: MAE **worsens 0.000379 (0.30%)**, RMSE worsens 0.000940 (0.57%).
- M2 versus M1: MAE **worsens 0.000327 (0.26%)**, RMSE worsens 0.000228 (0.14%).
- Development mean-fold MAE gains were only 0.000244 and 0.000337 against required
  thresholds 0.002414 and 0.002409. Neither model qualified before validation.
- Both win MAE in only **3/7** validation folds. No post-result challenger search or
  replacement of C16 with its previously unselected M1 family is performed.

For completeness, combined development + validation OOS results (521 stints, ten folds)
are below. They are **not** substituted for the fixed validation gate.

| Model | RMSE | MAE | Pearson | Spearman | Direction | Slope | Intercept |
|---|---:|---:|---:|---:|---:|---:|---:|
| M0 | 0.166339 | 0.124053 | 0.396238 | 0.398479 | 63.53% | 1.108055 | −0.008944 |
| M1 | 0.166745 | 0.124258 | 0.392381 | 0.399216 | 63.92% | 1.067393 | −0.012130 |
| M2 | 0.166877 | 0.124397 | 0.390991 | 0.393312 | 63.15% | 1.060974 | −0.012571 |

| Validation year | M1 minus M0 MAE improvement | M2 minus M1 MAE improvement |
|---|---:|---:|
| 2019 | −0.001841 | 0.000745 |
| 2020 | −0.000539 | 0.000129 |
| 2021 | −0.000656 | 0.000377 |
| 2022 | −0.001196 | −0.000649 |
| 2023 | 0.000441 | −0.000069 |
| 2024 | 0.000966 | −0.001242 |
| 2025 | 0.000174 | −0.001419 |

### Real destination changes and sensitivity

Change means the conditioned team is absent from the player's >=50-dropback prior-season
team set; no prior qualified team leaves the flag null, not "changed." This includes
recorded in-season destination changes and does not claim they occurred before August 31.
Validation contains **72 changed-team stints, 43 QBs, seven seasons, 64 team-seasons**.

| Model | Changer MAE | Changer RMSE | Pearson | Spearman | Direction |
|---|---:|---:|---:|---:|---:|
| M0 | 0.119440 | 0.146311 | 0.218732 | 0.057288 | 50.00% |
| M1 | 0.120560 | 0.147817 | 0.190917 | 0.031127 | 50.00% |
| M2 | 0.122580 | 0.149329 | 0.166264 | 0.011383 | 48.61% |

M1 improves changer MAE in **2/7** years; M2 versus M1 in **1/7**. M2's changer
calibration slope is 0.435, a further limitation even though pooled calibration passes.
This does not establish transferable environment response.

Single-team validation (368 stints) also worsens with both additions. Among >=200-dropback
stints (255 rows), M1 improves MAE from 0.098237 to 0.097943 and RMSE from 0.121445 to
0.120991; this small subset gain cannot override failed primary and changer results.
M2 worsens that subset. Medium/high C14 ability-reliability rows (282 stints) show a tiny
M1 MAE gain, but RMSE worsens; M2 worsens both. These are declared evaluation diagnostics,
not a new approval cohort or claims about staff changes. No coach-assignment data is used.

### Interaction interpretation

The six player style inputs are prior shrunk scramble rate, shotgun rate, average air
yards and short/intermediate/deep target rates. All eight C15 interaction definitions
are retained: six same-trait alignments plus mobility × pass rate and depth × neutral
pass rate. No PAE, conditioned split EPA, ability/fit score or Coach Effect enters.

| Interaction | Positive validation-fold coefficients | Standardized coefficient range (EPA/DB) |
|---|---:|---:|
| Scramble alignment | 5/7 | −0.000363 to 0.001356 |
| Shotgun alignment | 0/7 | −0.004097 to −0.002161 |
| Short-depth alignment | 7/7 | 0.002394 to 0.003551 |
| Intermediate-depth alignment | 7/7 | 0.001754 to 0.003321 |
| Deep-depth alignment | 5/7 | −0.000480 to 0.001879 |
| Air-yard alignment | 7/7 | 0.001895 to 0.002918 |
| Mobility × pass-heavy environment | 5/7 | −0.000287 to 0.001316 |
| Depth × neutral-pass environment | 7/7 | 0.001439 to 0.004515 |

These are coefficients per training-standard-deviation of the residualized product,
not EPA/DB benefits for raw changes in a trait. Signs alone do not pass the incremental
prediction test. All interaction families remain unapproved for scenario use.

### Bootstrap, placebo and intervals

Each reported paired bootstrap has 1,000 successful draws. QB clusters retain all
seasons/stints; the separate team-season bootstrap retains all QBs sharing that environment.
Neither combines all dependence structures, nor refits models, so uncertainty is conditional
on the issued OOS predictions. Positive MAE gain means the candidate improves the comparator.

| Comparison / subset | QB-cluster 95% MAE-gain interval | Team-season-cluster interval |
|---|---:|---:|
| M1−M0 / all | [−0.001441, 0.000631] | [−0.001403, 0.000613] |
| M2−M1 / all | [−0.001323, 0.000739] | [−0.001095, 0.000526] |
| M1−M0 / changers | [−0.002982, 0.000522] | [−0.002999, 0.000855] |
| M2−M1 / changers | [−0.003822, −0.000300] | [−0.003645, −0.000277] |

The 1,000-draw descriptive QB sign-flip tail fractions are 0.768 (M1−M0 all), 0.701
(M2−M1 all), 0.902 and 0.977 for changers. No positive placebo evidence; these are not
exact permutation-test p-values for randomized QB placement, and no model-refit
permutation or causal estimate is claimed.

| Model | 50% coverage | 80% coverage | 95% coverage |
|---|---:|---:|---:|
| M0 | 45.33% | 77.87% | 95.47% |
| M1 | 47.73% | 78.40% | 95.47% |
| M2 | 46.67% | 77.60% | 95.73% |

All 375 validation stints have intervals; the first 146 OOS stints per model do not.
Coverage and calibration pass pooled thresholds, but never compensate for worsened
accuracy, unstable year-specific gains and unsupported transport to changed environments.

### Missingness and forward gate

All ten scheme features are available for all 667 eligible stints. Prior air yards and
each depth-rate estimate are missing in **234/667 (35.08%)**; prior scramble and shotgun
rates in **192/667 (28.79%)**. Raw nulls, qualification/reliability and historical source
records remain separate from fitted median/indicator preprocessing. Main and interaction
models use the same sample; no hidden complete-case selection creates an apparent gain.

There is enough historical information for 57 C16 candidate QBs and 32 prior-team schemes
to describe 1,824 *potential* pairings. **None is issued as a scenario projection.** Both
response candidates failed the predeclared gate. The typed forward artifact is empty;
it does not silently return the baseline with a fabricated zero adjustment. An approved
future response model would also require observed-context support checks, separate
player/scenario metadata and explicit noncausal labels. No 2026 roster is inferred.

## Artifacts and validation

The 19 deterministic outputs plus `MANIFEST.json` are under ignored
`data/processed/qb_scenario/c17-9f582e4ac18d8cd6/`, with atomic family `LATEST`.
See the root data dictionary for each grain. They include registry/interaction definitions,
cohort, player/scheme lineage, destination matrix, fold/tuning audits, OOS predictions,
comparison/subgroup/fold metrics, coefficients, bootstrap/placebos, interval coverage,
missingness, leakage gates, decisions and the empty 2026 scenario table.

```bash
PYTHONPATH=src:. OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  python scripts/run_checkpoint_seventeen.py
PYTHONPATH=src:. OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  python -m pytest -q tests/test_checkpoint_seventeen_scenario.py
```

Focused tests: **18 passed**, including actual fitted Ridge designs with equal stint weights,
chronological inner/outer windows, forbidden fields, multi-team and real changer records,
nulls, outcome mutation invariance, negative forward gate, version changes, and two
independent empty-directory byte-identical builds of all outputs/manifest/LATEST.
Six output leakage gates pass with zero failures. Original C16 artifacts are untouched.
Ruff, formatting (157 Python files), compilation and diff checks pass.
Full offline regression: **340 passed, 51 intentionally skipped, one warning**, in
1,108.58 seconds. The skips are 37 checkpoint-seven PostgreSQL/API tests plus nine
PostgreSQL behavior tests (no disposable `TEST_DATABASE_URL` configured), and five
opt-in network tests. They were not run separately and are not claimed as passes.
The warning is an existing Starlette/httpx test-client deprecation. The unchanged legacy
C12 tests used hash-verified approved participation/FTN inputs seeded into nflreadpy's
in-memory cache; no download, altered assertion or production connection was involved.

Two additional independent CLI builds into empty directories also matched byte-for-byte
for all 19 outputs, `MANIFEST.json` and `LATEST`. No timestamps, local paths, cache status
or execution logs enter the content identity or deterministic outputs.

## Closeout and next gate

C16 integration: both approved commits fast-forwarded into main and pushed; main/origin
baseline is `da75c03563db4b6e033b140783767d00fc7149e7`. C17 is isolated on
`codex/phase2-checkpoint-17-scenario-simulator`; this closeout creates one review commit only.
C17 is not merged, pushed or deployed. No DB/API/frontend, Neon/Render, PFR ingestion,
Coach Effect, PAE forward projection or arbitrary fit score is added.

**Checkpoint 18 NOT READY:** no validated one-year environment-response mechanism exists
to compose across years. A selected conditional sample can be analyzed, but these measured
prior schemes do not demonstrate useful incremental prediction or changed-team generalization.
This negative research finding does not prove scheme never matters. C16 can continue to
provide its separately approved team-independent EPA research baseline. No C18+ work is done.
