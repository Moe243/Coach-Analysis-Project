# Expected-quarterback-performance model card

Status: checkpoint five implemented; pending approval.

## Version and intended use

- Data version: `c5-0ebaff47c63c6910`
- Source historical version: `c3-f6c1aa118ff43b90`
- Model version: `expected-performance-0ebaff47c63c6910`
- Feature version: `qb-preseason-v2`
- Evaluation seasons: 2010-2025
- Training warm-up: 1999-2009 for the first published season, expanding through 2024

The model estimates preseason EPA/dropback for one NFL QB-team-season. PAE is actual minus expected EPA/dropback. It supports later analysis of performance relative to expectation; it is not a final quarterback ranking, a coach-effect estimate, or causal evidence.

## Population and outputs

The build contains 2,899 feature rows across 1999-2025 and publishes 1,689 analysis-season PAE rows. All analysis rows receive out-of-sample predictions. The 582 rows with at least 200 dropbacks are evaluation-eligible; 1,107 smaller samples remain stored with low reliability. Reliability is high for 417 eligible rows with at least 600 prior career dropbacks and medium for the other 165 eligible rows.

Outputs include actual and expected EPA/dropback, PAE, dropbacks, starts, complete prior/career features, target and as-of seasons, model/data/feature versions, prediction intervals, eligibility, reliability, experience group, team-change flag, and missingness indicators. Warm-up rows never appear in `qb_pae.parquet`.

## Features and timing

Every performance feature for season `S` is available by `S-1`. Roster `years_exp`, `entry_year`, and `rookie_year` establish NFL experience and rookie status independently of QB history. A unique Week 1 depth-chart team establishes the opening team-change feature and is shared by every observed stint for that player-season; later destinations are never fitted. Other inputs are age, exact prior-season starts/usage and EPA/CPOE/success/sack/interception/touchdown rates, career starts/usage and the same career rates, `no_prior_qb_performance`, prior QB-season count, and prior injury-report/out weeks. Career fields aggregate only seasons earlier than the target.

There is no validated college-production, draft, or combine dataset in the repository. The roster profile college name is not used as performance data. College production, draft position, and draft round are null with missing indicators. Coaching assignments, coach identities, current-season team results, records, rankings, and future data are prohibited features.

## Candidate models and selection

| Candidate | OOS MAE | RMSE | R² | Correlation | Calibration intercept | Calibration slope | 95% interval coverage | Selection score |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Career performance (selected) | 0.09172 | 0.11752 | 0.18925 | 0.44673 | 0.00707 | 0.82192 | 0.94502 | 0.09705 |
| Ridge | 0.09398 | 0.12104 | 0.13985 | 0.43562 | 0.02288 | 0.66433 | 0.94674 | 0.10642 |
| Recent performance | 0.09519 | 0.12135 | 0.13541 | 0.41666 | 0.01580 | 0.68326 | 0.95189 | 0.10547 |
| League average | 0.10565 | 0.13273 | -0.03435 | -0.01722 | 0.06944 | -0.31157 | 0.93471 | 0.14924 |

Career performance shrinks prior-career EPA toward the expanding league average with 500 pseudo-dropbacks. It was selected because it achieved the best eligible OOS MAE and best declared composite of MAE and calibration penalties. Ridge uses training-only median imputation, scaling, explicit missing indicators, capped dropback weights, and time-ordered alpha tuning. A mixed-effects expectation model was not added: the four reliable candidates satisfied this checkpoint without introducing an additional fragile dependency or hierarchy.

## Small samples and uncertainty

Recent performance shrinks with 200 pseudo-dropbacks; career performance uses 500. Rookies and veterans with no prior QB performance fall back to the expanding league average in those baselines while remaining distinct Ridge inputs. Exact small prior seasons remain available and are shrunk rather than erased. The 200 current-season dropback threshold affects evaluation eligibility and reliability, never the PAE arithmetic.

Prediction intervals are expected EPA plus/minus 1.96 times an expanding residual RMSE calculated only from earlier OOS seasons. Before 20 eligible residuals exist, the model uses prior-training outcome dispersion. This gives 94.50% eligible coverage, but it is not a player-specific probabilistic interval.

## Subgroup and threshold diagnostics

Eligible results are weaker for true rookies (63 rows; MAE 0.12066; R² -0.27044; coverage 84.13%) and one-prior-NFL-season players (75 rows; MAE 0.10593; R² 0.00441; coverage 90.67%) than veterans (444 rows; MAE 0.08522; R² 0.21702; coverage 96.62%). Selected-model MAE declines from 0.12234 at 50 dropbacks to 0.08346 at 400, demonstrating why small samples remain visible but receive lower reliability.

## Validation and release gate

Regression tests enforce strict feature timing, a target-metric leakage adversary, Trent Edwards' 2010 midseason destination invariance, true-rookie versus veteran-no-history cases, missing prior/college fields, duplicate grains and outputs, finite predictions, exact PAE arithmetic, dropback reconciliation, warm-up exclusion, forbidden coaching/current-result features, complete parameter/source versioning, byte-identical clean rebuilds, and atomic failure. PostgreSQL behavior tests cover timing, roster/performance-history fields, interval bounds, uncertainty fields, reliability, and PAE arithmetic when a database is available.

The version identity includes all declared model parameters, every feature source, relevant source-code hashes, and modeling-library versions. Changing career shrinkage or any other output-affecting specification creates a new immutable data/model version.

## Known risks and prohibited uses

PAE is performance relative to a limited expectation, not player or coach quality. It can absorb supporting cast, scheme, injuries, schedule, measurement error, and luck. Model-family selection uses the reported backtest rather than an untouched deployment holdout. Do not use PAE alone for employment, contract, wagering, causal, or medical decisions. See `LIMITATIONS.md`.
