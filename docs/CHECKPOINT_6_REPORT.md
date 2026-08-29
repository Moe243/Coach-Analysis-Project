# Checkpoint Six Report

- **Date:** 2026-08-29
- **Data version:** `c6-633bf10b86381ce3`
- **Model version:** `coach-impact-633bf10b86381ce3`
**Pipeline version:** `checkpoint-6.1`

## Status

Checkpoint six is implemented and pending approval. It produces source-compatible coaching exposures, exploratory role-specific adjusted associations, identification diagnostics, uncertainty support diagnostics, and suppressed ranking contracts. No causal claim, API, frontend, network graph, production dashboard, or checkpoint-seven work was added.

## Exposure construction

PAE remains the outcome: game EPA/dropback minus the strictly preseason checkpoint-five expectation. Games join to the matching QB, canonical team, season, role, and supported week interval before aggregation to one QB-coach-assignment interval. Verified and provisional assignments remain distinct, and only verified rows enter the primary analysis.

Shared duties divide exposure before eligibility. Houston Week 4 contains 40 observed Deshaun Watson dropbacks; Tim Kelly and Bill O'Brien each receive 20 effective dropbacks. Both are excluded by the 25 fractional-exposure threshold. The complete output contains 4,308 exposure rows and 1,856 explicit exclusions.

Verified usable samples are:

| Role | Usable intervals |
|---|---:|
| Head coach | 983 |
| Offensive coordinator | 23 |
| Play-caller | 12 |
| Quarterbacks coach | 1 |

## Corrected empirical-Bayes estimator

Interval residuals are means. Residual variance is now calculated as `sum(exposure_dropbacks × residual²) / (independent intervals - 1)`, rather than normalizing by total dropbacks. That variance is used consistently in coach sampling variance, between-coach variance, shrinkage, analytic standard errors, effect estimates, and fallback intervals. A deterministic four-interval regression fixture verifies the exact variance, degrees of freedom, and shrinkage by hand.

## Identification decision

The primary baseline uses timing-safe preseason QB controls, season indicators, and repeated-QB indicators. It does not include team-season fixed effects, because 95% of verified head-coach team-seasons contain only one head coach and therefore nearly encode coach identity. The build publishes this diagnostic for every role. A team-season contextual model remains only as a sensitivity explicitly labeled nonidentified.

Removing the absorbing control does not solve unmeasured team-environment confounding. The repository lacks complete team-era, roster-quality, protection, receiver, defense, and opponent controls across the window. Therefore all coach effects are labeled `exploratory_team_environment_confounding`, `identified_effect` is false, and all rankings are suppressed. No head coach or other role is publishable at this checkpoint; this decision is based on identification, not rank attractiveness.

Descriptive in-sample comparisons under the corrected primary specification are:

| Role | Model | Observations | MAE | RMSE | R² |
|---|---|---:|---:|---:|---:|
| Head coach | No-coach baseline | 983 | 0.10078 | 0.14751 | 0.43125 |
| Head coach | Coach fixed effects | 983 | 0.09478 | 0.14065 | 0.48290 |
| Head coach | Partial pooling | 983 | 0.10078 | 0.14751 | 0.43125 |
| Offensive coordinator | No-coach baseline | 23 | 0.06449 | 0.10510 | 0.49167 |
| Offensive coordinator | Coach fixed effects | 23 | 0.04052 | 0.08889 | 0.63640 |
| Offensive coordinator | Partial pooling | 23 | 0.06449 | 0.10510 | 0.49167 |
| Play-caller | No-coach baseline | 12 | 0.00869 | 0.01456 | 0.99230 |
| Play-caller | Coach fixed effects | 12 | 0.01603 | 0.02705 | 0.97339 |
| Play-caller | Partial pooling | 12 | 0.00869 | 0.01456 | 0.99230 |

These are fit diagnostics, not out-of-sample validation or evidence of causal coach value.

## Bootstrap estimand and support

The build performs 200 deterministic QB-season cluster resamples. For each coach it reports successful and attempted draws. Percentiles are explicitly labeled conditional on that coach appearing in the resampled QB-season support; they are not described as unconditional confidence intervals. An interval requires at least 160 successful appearances, the greater of 50 draws or 80% of attempts. Missing support produces null bounds and `bootstrap_interval_available = false`, and ranking eligibility requires an available interval.

Supported conditional intervals exist for 107 of 120 estimated head coaches, six of 15 OCs, and two of eight play-callers. The other estimated coaches are suppressed for inadequate bootstrap support. The QB-coach role remains unestimated because only one verified coach identity is usable.

## Sensitivity and limitations

Sensitivity outputs include verified plus provisional assignments, exclusion of shared duties, equal weighting, removal of repeated-QB indicators, a contextual team-season specification labeled nonidentified, and 100/200 fractional-exposure thresholds. Provisional assignments never enter the verified primary estimates. Role overlap, coach-QB matching, roster construction, staff survival, missing team context, and selection remain unresolved. All results are exploratory adjusted associations rather than causal coach effects.

## Validation and reproducibility

Regression coverage now includes:

- exact hand-calculated interval-mean variance and shrinkage;
- near one-to-one coach/team-season confounding detection and ranking suppression;
- Houston shared-duty fractional exposure below the primary threshold;
- sparse coach bootstrap appearances, minimum-support suppression, estimand labeling, and reproducibility;
- independent-process byte-identical clean builds and content-addressed version changes.

Model identity includes every model, ranking, bootstrap, sensitivity, identification, and deterministic-output parameter; NumPy, Polars, SciPy, and scikit-learn versions; source input checksums; and relevant code hashes. Execution timestamps remain outside immutable artifacts.

The complete offline suite reports 74 passed and 11 skipped. Nine behavioral PostgreSQL tests are skipped because `TEST_DATABASE_URL` and a PostgreSQL client/server are unavailable; checkpoint six adds no PostgreSQL loading behavior, so this remains a checkpoint-seven integration risk. The two opt-in network tests were run separately and passed, including nflverse preflight and all coaching citation/content checks. Ruff lint, Ruff formatting, `git diff --check`, and the independent-process clean-rebuild tests pass.

## Files changed

- Modeling: `src/nfl_coaching_impact/coach_impact.py`
- Tests: `tests/test_checkpoint_six_coach_impact.py`
- Documentation: `README.md`, `METHODOLOGY.md`, `MODEL_CARD.md`, `DATA_DICTIONARY.md`, `LIMITATIONS.md`, and this report

Generated Parquet, JSON, checksums, and execution logs remain ignored and uncommitted.

## Exact next checkpoint

Checkpoint seven will create Alembic migrations and deterministic loaders for approved historical, PAE, coaching, and coach-impact outputs; populate the curated PostgreSQL schema and serving views; and build tested FastAPI search, filter, pagination, QB/coach/team detail, lineage, uncertainty, and methodology endpoints. It must not start until checkpoint six is explicitly approved. The frontend, network graph, production dashboard, deployment, and college enrichment remain out of scope.
