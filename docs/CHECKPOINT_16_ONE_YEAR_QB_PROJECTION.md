# Checkpoint 16 — One-year QB projection: Player State baseline

Status: **COMPLETE — historical research evaluation; no live projection approval**.

Data version: `c16-c7cee27a36eb0445`. Model version: `qb-projection-c7cee27a36eb0445`.

The approved roster audit was committed and fast-forwarded/pushed to main as
`0bd54cffdaa61ed76677cbf675a6deb9338697f5`. This implementation starts from that commit on
`codex/phase2-checkpoint-16-qb-projection`. The checkpoint branch is for review only; it is not
merged, pushed, or deployed.

## Decision and scope correction

A team-independent quarterback projection does **not** require knowing his future team.
Checkpoint 15's 130-row target-team cohort is therefore not reused. Checkpoint 16 joins the full
frozen Player State population to independently materialized outcomes. It neither requests nor
constructs target-team assignments. Scheme, coaching assignments, PCAE, Coach Effect, interactions,
rankings, and 0–100 grades are absent from model predictors.

**Checkpoint 15's data limitation still blocks validated Player × Scheme Fit.
Checkpoint 16 does not solve that problem.** The weekly-roster source remains CONDITIONAL and is
not ingested. Earlier C15 and roster-audit statements that C16 was entirely blocked are historical:
the approved, narrower Player-State-only experiment is now completed without relaxing timing.

EPA's development-selected model is **B2**, the frozen preseason-expectation baseline. M1 is a
promising challenger, but its development-window gain did not clear the predeclared uncertainty
screen. PAE selects M1. Both selected targets receive **NOT SUPPORTED** under the declared full
acceptance checklist: B2's validation calibration intercept narrowly fails, and M1 PAE's slope
fails. This is a refusal to approve a projection product, **not** a claim that QB history contains
no predictive signal. No thresholds or selection rule were relaxed after inspecting results.

Checkpoint 17 readiness: **NOT READY**. A calibrated, accepted projection foundation, an approved
forward Player State snapshot, and defensible target-environment/scenario contracts remain needed.
No Checkpoint 17+ system is implemented.

## Exact cohort and outcome grain

Pinned source artifacts:

- C14 `c14-43283062e788e686`: 8,457 Player State headers, registered feature records, registry,
  and retrospective evaluation links. State values and the state universe are never rebuilt.
- Canonical enhancements `enh-04254065cafd92ba`: QB-team-season EPA totals/dropbacks and the
  frozen canonical C5 PAE/preseason expectations.
- C13 `c13-5e3d7a34ea4d1af5`: frozen foundation identity and the existing registry/timing/lineage
  validator contract. No Scheme records are consumed.

Every captured input is hashed and checked against its source manifest/checksum file before
parsing those same bytes. Predictor construction receives only Player State, state records, and
the registry. Outcomes and retrospective subgroup labels enter a separate join afterward.

| Reconciliation | Rows |
|---|---:|
| Original canonical QB-team-season evaluation rows | 1,187 |
| C14 state-matched stints | 1,146 |
| Explicit C14 `NOT_IN_ASOF_STATE_UNIVERSE` exclusions | 41 |
| Unique QB-seasons after aggregating 13 additional team stints | 1,174 |
| State-matched unique QB-seasons | 1,133 |
| Matched QB-seasons below 50 combined dropbacks | 320 |
| **Eligible QB-seasons, 2010–2025** | **813** |

The analytical grain is **`(player_id, target_season)`**, not QB-team-season. All team stints
aggregate from `sum(total_qb_epa) / sum(dropbacks)` before applying the 50-dropback evaluation
threshold. Player State appears once, regardless of the number of teams. No team-stint rate is
averaged unweighted, and no outcome may add a missing Player State. The 50-dropback threshold is
evaluation eligibility, not a roster prediction or a QB ranking rule.

Primary target: full regular-season QB EPA/dropback. Secondary target: actual EPA/dropback minus
the existing preseason expectation. PAE joins each original stint on the complete player/team/
season key, reconciles actual EPA and dropbacks, and requires the same expectation across teams.
Contradictory expectations fail; missing PAE remains null and never excludes an otherwise valid
primary EPA observation. The observed data have complete PAE for this cohort.

## Predictors and baselines

M1 uses a predeclared, limited set of 19 input columns:

- C14 preseason ability estimate, recent EPA, success rate, CPOE, sack rate, scramble rate,
  average air yards, short/intermediate/deep target rates, and shotgun tendency;
- age, seasons since rookie year (an explicitly labeled experience proxy), seasons with QB
  activity, `log1p` prior/career starts and dropbacks, and preseason-ability standard error.

All 11 selected performance/style features must be C14 PREDICTIVE_CORE. These are predeclared
unconditioned candidates, not situation features promoted after seeing C16 outcomes. Conditional
trend/PAE/location features and descriptive volatility/rushing are not inserted into M1. Prior
PAE is read only for the separate B1 PAE baseline. No latent or combined QB grade is created.
Ability, recent observed performance, and original prediction uncertainty stay distinct.

The full selected input lineage retains C14 classification, qualification, missingness,
sample sizes, shrinkage, reliability, standard error, and intervals. Missing state estimates
remain null in artifacts. Only within a training fold may a feature with at least 10 finite,
varying values receive a training-median fill plus an explicit missing indicator; otherwise the
feature is dropped for that fold. Means/scales are fit on that same training history.
No feature reliability multiplier is applied to a final prediction.

Across 813 eligible QB-seasons, missing inputs are: ability estimate/standard error 135 each;
prior starts/dropbacks 151 each; recent EPA/success/scramble/shotgun 237 each; sack rate 239;
air yards and each depth rate 287; CPOE 289. Age, career usage, seasons since entry, and seasons
with QB activity have no missing values. These are recorded missing values, not zero performance;
per-season counts are in `missingness_coverage.csv`.

| Model | EPA prediction | PAE prediction |
|---|---|---|
| B0 | Prior eligible player-season dropback-weighted league EPA | Prior eligible player-season dropback-weighted PAE |
| B1 | Qualified prior-season raw observed EPA | Qualified prior-season raw observed PAE |
| B2 | Frozen C5 career-performance preseason expectation | Zero: exactly at that expectation |
| M1 | Ridge on the 19 Player State inputs and missing indicators | Separate Ridge on the same inputs |

B1 uses B0 when its prior observation is unavailable, with `b1_used_league_fallback=true`.
The raw observation is distinguished from the shrunk Player State feature. B2 is a comparison
baseline, **never** an M1 predictor or a condition for generating Player State. It is the
published `career_performance` model (`expected-performance-8fd5d1aba2598c59`), which shrinks
career EPA toward prior league EPA using 500 pseudo-dropbacks and falls back for no-history QBs.
Its per-row OOS flag/training cutoff and invariant multi-team expectation are validated. Its
published participant-dependent row universe is not used to restrict M1. The original C5 family
was selected on historical data; B2 is an inherited benchmark, not an independently untouched
model-discovery holdout.

No nonlinear challenger was added: one interpretable regularized candidate is sufficient for
this first comparison, and model proliferation is not justified by the sample size.

## Rolling validation and model selection

Each outer target trains on earlier eligible seasons only. A fold requires 120 training rows,
three earlier seasons, and 20 target rows. Ridge uses an intercept and deterministic SVD solver,
with equal weight per eligible QB-season. This differs intentionally from B0's league-average
dropback weighting. Standardization reuses the existing train-only fold preprocessor; C13's
feature validator enforces source season, as-of date, normalization timing, and provenance.

Inner rolling folds require 100 training rows, two prior seasons, and 20 validation rows. Alpha
is chosen by mean inner-fold MAE from `{0.1, 1, 10, 100, 1000}`; ties prefer stronger regularization.
Default alpha 100 is declared for an absence of valid inner folds. Both preprocessing and alpha
selection are refit strictly inside outer history. No random split or full-dataset scaling occurs.

| Outer target | Training rows | Target/OOS rows | Historical calibration rows |
|---|---:|---:|---:|
| 2013 | 150 | 45 | 0 |
| 2014 | 195 | 49 | 45 |
| 2015 | 244 | 50 | 94 |
| 2016 | 294 | 48 | 144 |
| 2017 | 342 | 49 | 192 |
| 2018 | 391 | 49 | 241 |
| 2019 | 440 | 51 | 245 |
| 2020 | 491 | 48 | 247 |
| 2021 | 539 | 53 | 245 |
| 2022 | 592 | 59 | 250 |
| 2023 | 651 | 54 | 260 |
| 2024 | 705 | 53 | 265 |
| 2025 | 758 | 55 | 267 |

There are **13 outer folds and 663 OOS predictions per model/target**, or 5,304 long-form rows
across four models and two targets. The first 150 eligible rows (2010–2012) initialize training;
they are not falsely labeled OOS. Development uses 2013–2018 (290 OOS rows), and the family choice
is frozen for 2019–2025 (373 OOS rows). Later validation seasons can use earlier validation seasons
as training/calibration history, as in a genuine rolling forecast; they never affect an earlier
prediction or the frozen model-family choice.

Before inspecting C16 performance, a replacement for B2 was required to have at least three
development folds, positive correlation, mean fold MAE gain greater than both one standard error
and 2% of B2 MAE, improvement in at least 60% of folds, and mean fold RMSE no worse than 1.01× B2.
The winning qualifying candidate is chosen by development MAE; otherwise B2 is retained.
EPA M1 gained 0.00219 on average per development fold, below its 0.00311 standard error: **B2 stays**.
PAE M1 gained 0.00330, exceeded the screen, and was selected. Validation results cannot switch
EPA to M1 after the fact.

## Results

Primary final assessment uses the 373-row 2019–2025 rolling validation segment:

| Target | Model | RMSE | MAE | Pearson | Spearman | Direction accuracy | Calibration slope | Intercept |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| EPA | B0 | 0.18694 | 0.13876 | -0.05275 | -0.05089 | 0.56300 | -4.94862 | 0.31477 |
| EPA | B1 | 0.18694 | 0.14087 | 0.31331 | 0.31716 | 0.59249 | 0.49714 | -0.02154 |
| EPA | **B2 selected** | **0.17276** | **0.12704** | **0.37746** | **0.38692** | **0.60054** | **1.05741** | **-0.05110** |
| EPA | M1 challenger | 0.15653 | 0.11721 | 0.49193 | 0.50749 | 0.69437 | 1.09892 | -0.01141 |
| PAE | B0 | 0.17242 | 0.12689 | -0.02149 | -0.00205 | 0.52547 | -1.21797 | -0.04974 |
| PAE | B1 | 0.18817 | 0.14497 | 0.13717 | 0.12434 | 0.55764 | 0.21983 | -0.04674 |
| PAE | B2 zero | 0.17276 | 0.12704 | unavailable | unavailable | 0.41555 | unavailable | unavailable |
| PAE | **M1 selected** | **0.16011** | **0.11957** | **0.31531** | **0.26744** | **0.58445** | **1.91741** | **0.01744** |

Direction is agreement of `actual >= 0` and `prediction >= 0`, explicitly including equality.
For a constant zero PAE prediction this is the nonnegative-outcome frequency, not demonstrated
directional skill. Correlations and calibration coefficients are null where not identifiable.

EPA M1 improves validation MAE by 0.00983 (7.74%) and RMSE by 0.01623 (9.39%) versus B2, but is
not retroactively selected. The selected EPA baseline's improvement over B2 is exactly zero.
Selected PAE M1 improves MAE by 0.00747 (5.88%) and RMSE by 0.01265 (7.32%).

Across all 663 rolling observations, EPA MAE/RMSE are B0 0.13667/0.18352,
B1 0.13777/0.18164, B2 0.12209/0.16660, and M1 0.11564/0.15611. These combined development/validation
figures are supplementary, not an untouched selection score.

M1 minus B2 error improvements by validation fold (positive means M1 improves MAE):

| Year | EPA MAE gain | PAE MAE gain |
|---|---:|---:|
| 2019 | 0.00252 | 0.00540 |
| 2020 | 0.00430 | 0.00570 |
| 2021 | 0.00766 | 0.00836 |
| 2022 | 0.01788 | 0.01178 |
| 2023 | 0.01135 | 0.00885 |
| 2024 | 0.01269 | 0.00541 |
| 2025 | 0.01064 | 0.00609 |

Both improve validation MAE in seven of seven seasons, including the recent era. A fixed-prediction
bootstrap resampling 119 QB clusters with replacement (1,000 deterministic draws) gives MAE-gain
95% intervals of [0.00415, 0.01540] for EPA M1 and [0.00317, 0.01196] for PAE M1. These describe
paired OOS error differences, **not** QB prediction intervals or full model-refit uncertainty.
Shared season shocks and prior feature-development choices remain limitations.

## Subgroups and uncertainty

Subgroups are diagnostic only; none changes training membership or generates target-team evidence.
Returning veterans have prior QB activity and are not rookies. Developing/experienced labels use
seasons since rookie year, not an unvalidated exact NFL-experience field. Team changers compare
adjacent retrospective primary outcome teams (most dropbacks, stable team tie-break), including
2010 history where available; the label is never a predictor. It is not guaranteed to represent
a preseason-known move and does not identify a scheme effect.

| Validation EPA subgroup | n | B2 MAE | M1 MAE |
|---|---:|---:|---:|
| Returning veterans | 304 | 0.11581 | 0.10894 |
| Developing, 0–3 years | 154 | 0.13980 | 0.12772 |
| Experienced, 4+ years | 219 | 0.11808 | 0.10982 |
| 50–199 outcome dropbacks | 118 | 0.19648 | 0.17616 |
| 200–399 outcome dropbacks | 77 | 0.10780 | 0.08990 |
| 400+ outcome dropbacks | 178 | 0.08934 | 0.08995 |
| Retrospective team changers | 93 | 0.14677 | 0.13566 |
| High C14 ability reliability | 207 | 0.10783 | 0.10216 |

Prediction intervals use the previous five seasons' **OOS absolute residuals for the same model
and target**. With `n` prior residuals, the radius for nominal level `p` is ordered residual
`ceil((n+1)*p)`; at least 100 residuals and a valid finite order statistic are required. All
current-year predictions are frozen before adding current residuals. The first 144 OOS rows
(2013–2015) per model/target have unavailable intervals, explicitly recorded rather than filled
from in-sample residuals. This is rolling residual/conformal-style calibration, not a coefficient
confidence interval and not an exchangeability-based guarantee. All later intervals have valid
historical calibration; widths vary by forecast year/model, not by every individual player.

| Validation model/target | Interval n | 50% coverage | 80% coverage | 95% coverage |
|---|---:|---:|---:|---:|
| Selected B2 EPA | 373 | 47.45% | 78.55% | 95.17% |
| Challenger M1 EPA | 373 | 50.67% | 79.89% | 95.44% |
| Selected M1 PAE | 373 | 49.06% | 78.28% | 94.37% |

Coverage is marginal among eligible observed QB-seasons, not guaranteed for an individual QB,
rookie, injury state, team, or an unobserved environment. Outcomes conditional on reaching 50
dropbacks do not model playing time, survival, or active-roster probability.

## Acceptance and forward readiness

The predeclared checklist requires at least 200 validation rows, five folds, Pearson ≥0.10,
positive Spearman, lower MAE than B0, calibration slope within [0.5, 1.5], absolute intercept
≤0.05 EPA units, recent MAE no worse than 1.01× B2, and coverage within six percentage points
of each nominal level. Both selected models meet interval coverage checks. B2 EPA fails the
intercept limit at **−0.051098**; selected M1 PAE fails the slope limit at **1.917407**. Thresholds
are research guardrails rather than scientific constants. B2's near-boundary failure warrants
future calibration work, not a claim that its positive association is absent. No recalibration
has been fitted to validation outcomes here.

The request's assertion about C14's 2026 snapshot does not match the artifacts: its manifest,
all 8,457 state rows, and all existing C14 version directories stop at **2025**. The forward-ready
2026 snapshot documented in Checkpoint 13 is a **Scheme** snapshot, not a Player State snapshot.
The implementation records `NOT_READY_MISSING_APPROVED_2026_PLAYER_STATE`, with **zero 2026 QBs
projected**. It does not infer 2026 membership from outcomes, season rosters, current status, or
scheme data. A separately approved forward C14-compatible state artifact is required first.

## Artifacts, reproduction, and validation

Run with project dependencies from the isolated worktree:

```sh
PYTHONPATH=src OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python scripts/run_checkpoint_sixteen.py
```

`--project-root` can reference existing frozen inputs; use `--output-root` to keep outputs in
an independent empty directory. No network or database is needed. The full offline regression
uses isolated mutable artifact pointers, with existing versioned inputs read from their frozen
locations; regression rebuilds remain test outputs, not replacements for approved C14 states.

The content identity includes exact input/manifest hashes, C13/C14 provenance, selected features,
all modeling/selection/calibration/acceptance/bootstrap rules, relevant source modules, Python,
NumPy, Polars, SciPy, scikit-learn, and serialization settings. Outputs are staged, checksummed,
atomically renamed, then `LATEST` is atomically updated. Reuse checks every output digest; a
changed parameter produces a different version, and a partial failure preserves the old pointer.

Deterministic artifacts under `data/processed/qb_projection/<version>/`:

- `projection_feature_registry.csv`, `state_predictors.parquet`, `state_input_lineage.parquet`
- `projection_cohort.parquet`, `cohort_coverage.csv`, `missingness_coverage.csv`
- `fold_assignments.csv`, `baseline_comparison.csv`, `model_comparison.csv`
- `oos_predictions.parquet`, `selected_oos_projections.parquet`
- `subgroup_diagnostics.csv`, `interval_coverage.csv`, `bootstrap_comparison.csv`
- `selected_model_parameters.json`, `leakage_audit.csv`, `checkpoint_decision.csv`
- `forward_readiness.csv`, `MANIFEST.json`, and family-level atomic `LATEST`

Selected OOS rows explicitly carry model/data/state versions, target/as-of dates, calibration
window/sample, intervals, acceptance status, and `HISTORICAL_OOS_RESEARCH_NOT_LIVE_FORECAST`.
EPA and PAE are separate fitted targets, not a guaranteed coherent joint distribution.
No unsupported forward projection file is fabricated. Tests enforce chronology, no target-team
requirement, no state backfill, restricted predictors, raw-baseline/missingness handling,
multi-team formulas, train-only fitting/tuning, interval ordering, outcome mutation invariance,
selection cutoff, absent forward-state handling, content versioning, checksum rejection,
atomic rollback, and independent byte-identical rebuilds.

### Final validation

- Focused C16: **24 passed** (`pytest -q tests/test_checkpoint_sixteen_qb_projection.py`).
  This includes actual independent empty-directory builds of all 18 deterministic outputs plus
  their manifest, version equality, checksum validation, reuse, and failed-publication rollback.
- Full offline regression and final targeted reruns: **306 distinct tests passed, 51 skipped**.
  The first full invocation collected 355 tests and returned 303 passed, 51 skipped, and one
  pre-existing C12 test failure: its participation loader attempted a network request without a
  populated cache. The unchanged failing test then passed using the hash-verified approved C12
  participation/FTN source files seeded into nflreadpy's in-memory cache, without downloading.
  The final 24-test C16 rerun includes two tests added after the full invocation collected its
  tests; all 357 currently collected tests are therefore accounted for. These totals describe
  the full run plus targeted reruns, not a claimed single 357-test invocation.
- The **51 intentional skips are 46 PostgreSQL/API tests and five opt-in network tests**.
  Database URLs and the network opt-in were unset for offline testing; these tests were not run
  and are not claimed as passes. No production database or service was contacted.
- Ruff: **PASS**; `ruff format --check src scripts tests`: **PASS, 73 files**.
- Python compilation (`python -m compileall -q src scripts tests`): **PASS**.
- `git diff --check` and equivalent checks for new files: **PASS**.
- Current C16 source/input identity and all published output checksums: **PASS**.
- One existing Starlette/httpx deprecation warning occurred during offline collection; no
  API dependency or production code was changed to silence it.

The C12 cache inputs match their approved source manifest: participation
`f7685093665ff052304ca9358ba85c9734b9cdbf41e6ba8f304730d49712dfe0` and FTN
`03105dfc45803bdd3bcfdaf74b282bb0911a3c15d68b509958b291eb608f5f4f`. They are used solely for the
unchanged historical regression; neither is a C16 predictor or new ingestion. All source model
artifacts, production surfaces, and the roster-audit scientific conclusion remain unchanged.

## Method references

- [scikit-learn: avoiding preprocessing leakage](https://scikit-learn.org/stable/common_pitfalls.html).
  Transformations must be learned on training observations, not the held-out target.
- [scikit-learn Ridge](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.Ridge.html).
  L2 regularization controls the correlated feature/missing-indicator design; SVD is deterministic.
- [Barber et al., Conformal Prediction Beyond Exchangeability](https://www.stat.berkeley.edu/~ryantibs/papers/nexcp.pdf).
  Temporal drift and dependence limit standard conformal guarantees. This checkpoint reports
  observed rolling coverage and does not assert unconditional finite-sample validity.
