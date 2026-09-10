# Checkpoint 16 — calibration refinement and 2026 candidate-state audit

Status: **COMPLETE, research only**. EPA: **RESEARCH-READY WITH LIMITATIONS**.
PAE: **NOT SUPPORTED**. Checkpoint 17: **NOT READY**.

Follow-up version: `c16r-8c8063c5954e2a22`.
Model version: `qb-calibrated-8c8063c5954e2a22`.
Original commit: `ace3618748a8ccb82439c8520d82fff8be23d910`.
Original C16 `c16-c7cee27a36eb0445` and its artifacts remain unchanged. Work continues on
`codex/phase2-checkpoint-16-qb-projection`, without merging, pushing, or deploying.

## 1. Why B2 was correctly selected

The frozen family-selection experiment uses development OOS folds **2013–2018**, followed by
validation **2019–2025**. Each underlying prediction and hyperparameter fit is chronological.
There are 290 development and 373 validation observations per model/outcome, from the same
813 eligible player-seasons; no target-team requirement is introduced.

A challenger must have at least three development folds, positive development correlation,
mean fold MAE gain greater than both one standard error and 2% of B2 mean fold MAE, at least
60% positive-gain folds, and mean fold RMSE no worse than 1.01 times B2. The lowest eligible
mean fold MAE wins; if no challenger qualifies, retain B2. Final validation cannot change this.

EPA M1's development mean fold MAE gain was **0.00219286**, below its standard error
**0.00311025**. It won four of six development folds, but did not clear the gain criterion.
Thus B2 was correctly retained. M1's later validation RMSE/MAE of 0.15653/0.11721 versus B2's
0.17276/0.12704 do not authorize retrospective reselection. The original function and thresholds
are preserved; adversarial tests mutate validation outcomes and recover the same choice.

## 2. Small, predeclared calibration experiment

Apply exactly the same three-method protocol to selected **B2 EPA** and selected **M1 PAE**:

1. `NONE`: preserve original predictions and interval procedure exactly.
2. `BIAS`: add mean historical OOS residual (`actual − prediction`), fixing slope at one.
3. `LINEAR`: ordinary least squares of actual on original OOS prediction, with intercept.

For target year Y, fit only on the selected base family's OOS rows in Y−5 through Y−1.
Bias and linear fits require **100 observations and three distinct prior seasons**; linear
also requires nonconstant predictions. Before qualification, use explicit identity calibration
with `INSUFFICIENT_OOS_HISTORY`, never an in-sample or target-year substitute.

Calibrator choice uses **only qualified 2016–2018 development folds**. Require three folds,
mean MAE improvement greater than both one standard error and 2% of uncalibrated mean MAE,
at least 60% improving folds, and mean RMSE no worse than 1.01 times uncalibrated RMSE.
Among qualifying methods, choose lowest development MAE, with simpler-method tie-break.
Otherwise select NONE. This decision is frozen before reviewing 2019–2025 metrics.

| Outcome | Method | Development MAE gain | Required gain | Improving folds | Selected |
|---|---|---:|---:|---:|---|
| EPA | BIAS | 0.00272322 | 0.00246908 | 2/3 | Yes |
| EPA | LINEAR | 0.00230572 | 0.00246908 | 2/3 | No |
| PAE | BIAS | −0.00038473 | 0.00234778 | 1/3 | No |
| PAE | LINEAR | −0.00114540 | 0.00234778 | 0/3 | No |

The layer uses ordinary, equally weighted QB-season calibration observations. It does not
create a new score, mix EPA with PAE, change the original Ridge fit, or multiply predictions
by an arbitrary confidence number. Calibration is a predictive adjustment, not a causal effect.

### Predictive intervals

Each method recalibrates interval radii from **its own prior calibrated OOS errors**, as actually
predicted in those earlier folds. It never applies the latest calibrator retrospectively to the
same outcomes used to fit it. Preserve the original five-year interval window, minimum 100
residuals, and ordered absolute-residual radius `ceil((n+1)*p)` for p = 50%, 80%, and 95%.
All predictions for one year are formed before those residuals can enter future calibration.
The first 144 OOS observations per method/outcome still have unavailable intervals.

## 3. Before/after validation results

Every row below has **373 observations, 2019–2025**. NONE is the original selected family, not
the original unselected EPA M1 challenger. Correlations compare predictions with observations.

| Outcome | Calibration | RMSE | MAE | Pearson | Spearman | Slope | Intercept |
|---|---|---:|---:|---:|---:|---:|---:|
| EPA | NONE | 0.172763 | 0.127044 | 0.377456 | 0.386922 | 1.057413 | −0.051098 |
| EPA | **BIAS selected** | **0.166105** | **0.125074** | **0.376088** | **0.381955** | **1.045820** | **−0.002447** |
| EPA | LINEAR | 0.166637 | 0.125934 | 0.372528 | 0.385619 | 0.869757 | −0.000532 |
| PAE | **NONE selected** | **0.160113** | **0.119572** | **0.315312** | **0.267441** | **1.917407** | **0.017438** |
| PAE | BIAS | 0.159626 | 0.120922 | 0.313474 | 0.273383 | 1.900416 | 0.051978 |
| PAE | LINEAR | 0.159492 | 0.121798 | 0.286181 | 0.266936 | 0.894777 | 0.004122 |

Selected EPA bias correction improves RMSE by **3.85%** and MAE by **1.55%**. Rank correlation
does not improve, and year-specific errors remain mixed. PAE linear calibration improves the
slope but **worsens MAE by 1.86%**; bias correction worsens MAE by 1.13%. Neither may be approved
just because one calibration statistic looks better, and neither won development selection.

| Outcome | Method | 50% coverage | 80% coverage | 95% coverage |
|---|---|---:|---:|---:|
| EPA | NONE | 47.45% | 78.55% | 95.17% |
| EPA | **BIAS selected** | **45.04%** | **78.02%** | **95.17%** |
| EPA | LINEAR | 45.31% | 78.02% | 94.91% |
| PAE | **NONE selected** | **49.06%** | **78.28%** | **94.37%** |
| PAE | BIAS | 49.87% | 78.55% | 95.17% |
| PAE | LINEAR | 47.45% | 79.09% | 95.71% |

Intervals are available for all 373 validation rows. EPA's 50% interval undercovers by 4.96
percentage points, within the unchanged six-point tolerance but a genuine limitation.
No finite-sample unconditional guarantee follows under repeated-QB dependence or temporal drift.

### Fold stability

Positive numbers are MAE improvements against the corresponding uncalibrated selected family.

| Year | EPA bias gain | EPA linear gain | PAE bias gain | PAE linear gain |
|---|---:|---:|---:|---:|
| 2019 | 0.004987 | 0.004983 | 0.000311 | 0.000214 |
| 2020 | −0.003053 | −0.000930 | −0.003864 | −0.003284 |
| 2021 | 0.002900 | 0.002625 | −0.003289 | −0.013833 |
| 2022 | 0.010550 | 0.005484 | 0.002620 | 0.004614 |
| 2023 | 0.003555 | 0.002982 | −0.001169 | −0.002312 |
| 2024 | −0.003237 | −0.003663 | −0.003605 | −0.002280 |
| 2025 | −0.003083 | −0.004090 | −0.001091 | 0.000421 |

EPA bias improves MAE in **4/7** validation seasons and RMSE in **5/7**. It is not uniformly
better. The recent-period aggregate remains within the original B2 robustness guard.
PAE NONE means its final predictions and metrics remain exactly unchanged.

### Acceptance and interpretation

Reuse all original point and interval gates: at least 200 validation observations/five folds,
Pearson ≥0.10, positive Spearman, MAE better than B0, slope in [0.5, 1.5], absolute intercept
≤0.05, recent mean-fold MAE ≤1.01 times B2, and interval coverage within six points of nominal.
An additional guard prevents approval if either validation MAE or RMSE is more than 1% worse
than the corresponding uncalibrated selected family. No original threshold is weakened.

- **B2 + BIAS EPA: RESEARCH-READY WITH LIMITATIONS.** Selected using development OOS data;
  every unchanged acceptance check and the extra accuracy guard passes.
- **M1 + NONE PAE: NOT SUPPORTED.** Its slope remains 1.917407. The unselected PAE linear
  challenger passes the slope/intercept checks but fails the accuracy guard and cannot be swapped
  in after validation.

This is a **retrospective refinement prompted by the original validation results**, not a fresh
untouched holdout or prospective external validation. The parameter fits and method selection
are chronological, but the overall research process reused the archive. This is why the stronger
`VALIDATED FOR RESEARCH PROJECTION` label is not used.

## 4. Root cause of the 2026 state contradiction

Classification: **A — documentation/reporting error only**, specifically the claim that an
existing 2026 QB Player State snapshot was already present.

- C13's `predictive_asof_snapshot_summary.csv` has a 2026 row: **32 team entities, 18 features,
  576 records**, all sourced from 2025. It is not a quarterback Player State snapshot.
- C14's `TARGET_SEASONS = tuple(range(2010, 2026))` deliberately ends at 2025. Both its universe
  builder and feature-prior loop use that range. Its manifest and 8,457 state headers agree.
- The C14 report explicitly says 2010–2025. Its tests enforce historical chronology and universe
  independence, not a 2026 forward state. “Entering season” describes its grain/cutoff, not a
  promise that every future year has been materialized.
- C14's history/draft/dated-evidence universe permits retired QBs and does not require an active
  roster. Lack of a 2026 roster therefore was not the cause of the historical target limit.

No original C13/C14 data is overwritten. The only C14 code extension is an optional declared
`target_seasons` argument in the existing feature estimator, preserving its historical default
and formulas. A default-versus-explicit-target regression confirms unchanged historical values.

## 5. Valid new 2026 candidate-state contract

The newly authorized universe is **57 canonical QBs with at least 50 observed dropbacks in 2025**,
aggregated across teams in the frozen C14 profiles. It means only:

> QB with sufficient historical information to generate a team-independent entering-2026 projection.

It is **not** an active-roster list, a claim of continued participation, or a 2026 team assignment.
Retirements and roster moves are deliberately not inferred. It excludes 2026 rookies, QBs inactive
in 2025, and 2025 samples below 50; it is not the complete C14 historical/drafted universe.

Reuse C14's frozen canonical player-season profiles, qualified registry, as-of empirical priors,
shrinkage, uncertainty, demographic facts, and usage aggregation to construct only target 2026.
The historical sources end at 2025; as-of date is **2026-08-31**. Birth date, draft year, and
rookie-season facts come from the exact C14-hashed player file, with any future-valued year
suppressed. Mutable current-team/status fields are never selected. No 2026 outcome, Scheme,
coach association, or team field is used to define membership or the predictor matrix.

The output has **57 state headers, 1,767 feature records, and 57 predictor rows**. CPOE, air yards,
and depth-rate estimates remain missing for 12 candidates below their feature-specific covered
sample thresholds. Other primary input columns are available. These nulls are not zeroes.
The new data/state identity is distinct from the historical C14 identity and records it as lineage.

## 6. Team-independent 2026 research projections

Both required gates now pass for EPA: a research-approved calibrated EPA model and valid candidate
states. Generate **57 EPA projections, zero PAE projections** with the exact label:

**TEAM-INDEPENDENT RESEARCH PROJECTIONS**

B2 is extended using its existing C5 career-performance formula, 500 pseudo-dropbacks, and exact
frozen C5 historical outcomes through 2025. This does not substitute C14's differently shrunk
ability estimate for B2. A regression reconstructs B2 in 2013, 2018, and 2025 to numerical identity
with the original predictions before permitting the forward extension.

The 2026 bias adjustment and intervals use **274 historical OOS rows, 2021–2025**. The bias is
−0.05089588 EPA/dropback. Outputs contain canonical player ID, target/as-of date, point projection,
50/80/95 predictive intervals, original/calibrated model identity, candidate-state identity,
calibration history, research status, and `active_roster_claim=false`. They contain **no team,
coach, Scheme assignment, ranking, or composite score**. PAE is not generated because its model
is unapproved; a calibrated EPA projection is not relabeled as a PAE forecast.

These are conditional performance forecasts, not playing-time, injury, survival, active-roster,
or role projections. Validation still conditions on eventual target-season volume ≥50, whereas
forward candidates are chosen from prior-season volume. That prospective selection difference
and absence of actual 2026 outcomes limit validation claims for this candidate population.

## 7. Checkpoint 17 and scope

**NOT READY.** A team-independent baseline is not a validated response to changes in teammates,
teams, coaches, or scheme. Checkpoint 15 remains **COMPLETE / NOT ESTIMABLE / DATA-LIMITED**.
Historically dated target-environment evidence and out-of-sample scenario/environment validation
are still absent. No scenario simulator, historical assignment backfill, Coach Effect, production
database/API/frontend change, Neon/Render operation, merge, push, or deployment is included.

## 8. Artifacts and reproducibility

Run `PYTHONPATH=src python scripts/refine_checkpoint_sixteen.py` from the isolated worktree.
Use `--output-root` for independent empty-directory builds. No network or database is required.

Outputs are under ignored `data/processed/qb_projection_refinement/c16r-8c8063c5954e2a22/`:

- `original_selection_audit.csv`, `calibration_selection_audit.csv`
- `calibration_parameters.csv`, `calibrated_oos_predictions.parquet`
- `model_comparison.csv`, `interval_coverage.csv`, `fold_metrics.csv`, `outcome_decisions.csv`
- `candidate_universe_2026.parquet`, `candidate_player_states_2026.parquet`
- `candidate_feature_records_2026.parquet`, `candidate_predictors_2026.parquet`
- `projections_2026.parquet`, `forward_model_parameters.json`, `forward_state_audit.json`
- `leakage_audit.csv`, `MANIFEST.json`; family-level atomic `LATEST`

The identity includes all captured input hashes, original C16 manifest, source modules (including
C14 and C5 reusable formulas), dependencies, exact feature lists, calibration/selection rules,
unchanged acceptance thresholds, candidate contract, and serialization settings. All inputs are
hashed and parsed from the same bytes. Publication is staged/atomic; checksums guard reuse.
The original C16 manifest/output hashes are verified before and after clean rebuild tests.

Focused validation: **40 tests passed** (24 original C16 plus 16 refinement tests), including
target/future mutation, selection chronology, historical interval-only calibration, candidate
source cutoffs, canonical uniqueness, forbidden context, B2 reproduction, both projection gates,
changed-input/dependency identity, and two independent byte-identical builds. Full regression
and final lint/format/compilation results are recorded at closeout below.

### Final closeout validation

- Full offline regression: **322 passed, 51 skipped**, in one 373-test invocation.
  The unchanged older C12 tests used the existing manifest-verified participation/FTN files in
  nflreadpy's in-memory cache; no download, fresh ingestion, or test-assertion bypass was needed.
- The 51 skips are **46 PostgreSQL/API tests and five opt-in network tests**. Database URLs and
  network opt-ins were unset for this offline task. Skipped tests were not run or claimed as passes.
- Final focused C16 rerun: **40 passed**, including original C16 and refinement regressions.
- Ruff: **PASS**; formatting: **PASS, 76 Python files**; compilation: **PASS**.
- `git diff --check` and new-file whitespace checks: **PASS**.
- Two independent empty-directory refinement builds: **byte-identical** across all 16 outputs,
  `MANIFEST.json`, and `LATEST`; same version. Original C16 output hashes remain unchanged.
- Final input/output identity and checksum verification: **PASS**. All five leakage audit gates
  have zero failures. The 57 EPA projections are finite, unique, and explicitly non-roster claims.
- One existing Starlette/httpx deprecation warning occurred. No production dependencies were
  changed to suppress it. Production DB/API/frontend and deployment configuration are untouched.

## Method references

- [scikit-learn LinearRegression](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.LinearRegression.html):
  ordinary least squares with an intercept; this is regression recalibration, not probability calibration.
- [Barber et al., Conformal Prediction Beyond Exchangeability](https://www.stat.berkeley.edu/~ryantibs/papers/nexcp.pdf):
  dependence and temporal drift limit standard conformal guarantees; report empirical rolling coverage.
