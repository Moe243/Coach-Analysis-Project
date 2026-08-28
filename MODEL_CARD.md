# Expected-quarterback-performance model card

Status: checkpoint five implemented; pending approval.

## Version and intended use

- Data version: `c5-98c98cdcc8492333`
- Source historical version: `c3-f6c1aa118ff43b90`
- Model version: `expected-performance-98c98cdcc8492333`
- Feature version: `qb-preseason-v1`
- Evaluation seasons: 2010-2025
- Training warm-up: 1999-2009 for the first published season, expanding through 2024

The model estimates preseason EPA/dropback for one NFL QB-team-season. PAE is actual minus expected EPA/dropback. It supports later analysis of performance relative to expectation; it is not a final quarterback ranking, a coach-effect estimate, or causal evidence.

## Population and outputs

The build contains 2,899 feature rows across 1999-2025 and publishes 1,689 analysis-season PAE rows. All analysis rows receive out-of-sample predictions. The 582 rows with at least 200 dropbacks are evaluation-eligible; 1,107 smaller samples remain stored with low reliability. Reliability is high for 417 eligible rows with at least 600 prior career dropbacks and medium for the other 165 eligible rows.

Outputs include actual and expected EPA/dropback, PAE, dropbacks, starts, complete prior/career features, target and as-of seasons, model/data/feature versions, prediction intervals, eligibility, reliability, experience group, team-change flag, and missingness indicators. Warm-up rows never appear in `qb_pae.parquet`.

## Features and timing

Every feature for season `S` is available by `S-1`. Fitted inputs are age, observed NFL experience, exact prior-season starts/usage and EPA/CPOE/success/sack/interception/touchdown rates, career starts/usage and the same career rates, team change, and prior injury-report/out weeks. Career fields aggregate only seasons earlier than the target.

There is no validated college-production, draft, or combine dataset in the repository. The roster profile college name is not used as performance data. College production, draft position, and draft round are null with missing indicators. Coaching assignments, coach identities, current-season team results, records, rankings, and future data are prohibited features.

## Candidate models and selection

| Candidate | OOS MAE | RMSE | R² | Correlation | Calibration intercept | Calibration slope | 95% interval coverage | Selection score |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Career performance (selected) | 0.09172 | 0.11752 | 0.18925 | 0.44673 | 0.00707 | 0.82192 | 0.94502 | 0.09705 |
| Ridge | 0.09209 | 0.11907 | 0.16762 | 0.44447 | 0.01769 | 0.72057 | 0.94845 | 0.10210 |
| Recent performance | 0.09519 | 0.12135 | 0.13541 | 0.41666 | 0.01580 | 0.68326 | 0.95189 | 0.10547 |
| League average | 0.10565 | 0.13273 | -0.03435 | -0.01722 | 0.06944 | -0.31157 | 0.93471 | 0.14924 |

Career performance shrinks prior-career EPA toward the expanding league average with 500 pseudo-dropbacks. It was selected because it achieved the best eligible OOS MAE and best declared composite of MAE and calibration penalties. Ridge uses training-only median imputation, scaling, explicit missing indicators, capped dropback weights, and time-ordered alpha tuning. A mixed-effects expectation model was not added: the four reliable candidates satisfied this checkpoint without introducing an additional fragile dependency or hierarchy.

## Small samples and uncertainty

Recent performance shrinks with 200 pseudo-dropbacks; career performance uses 500. Rookies and players with no NFL history fall back to the expanding league average. Exact small prior seasons remain available and are shrunk rather than erased. The 200 current-season dropback threshold affects evaluation eligibility and reliability, never the PAE arithmetic.

Prediction intervals are expected EPA plus/minus 1.96 times an expanding residual RMSE calculated only from earlier OOS seasons. Before 20 eligible residuals exist, the model uses prior-training outcome dispersion. This gives 94.50% eligible coverage, but it is not a player-specific probabilistic interval.

## Subgroup and threshold diagnostics

Eligible results are weaker for rookies (71 rows; MAE 0.11789; R² -0.27535; coverage 85.92%) and one-prior-season QBs (75 rows; MAE 0.10752; R² 0.01669; coverage 90.67%) than veterans (436 rows; MAE 0.08475; R² 0.20782; coverage 96.56%). Selected-model MAE declines from 0.12234 at 50 dropbacks to 0.08346 at 400, demonstrating why small samples remain visible but receive lower reliability.

## Validation and release gate

Regression tests enforce strict feature timing, a target-metric leakage adversary, rookie fallback, team changes, missing prior/college fields, duplicate grains and outputs, finite predictions, exact PAE arithmetic, dropback reconciliation, warm-up exclusion, forbidden coaching/current-result features, deterministic features/model outputs/versioning, byte-identical clean rebuilds, and atomic failure. PostgreSQL behavior tests cover timing, interval bounds, uncertainty fields, reliability, and PAE arithmetic when a database is available.

## Known risks and prohibited uses

PAE is performance relative to a limited expectation, not player or coach quality. It can absorb supporting cast, scheme, injuries, schedule, measurement error, and luck. Model-family selection uses the reported backtest rather than an untouched deployment holdout. Do not use PAE alone for employment, contract, wagering, causal, or medical decisions. See `LIMITATIONS.md`.
