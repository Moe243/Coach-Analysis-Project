# Expected-quarterback-performance model card

## Checkpoint 16 team-independent projection research

Data version: `c16-c7cee27a36eb0445`; model version: `qb-projection-c7cee27a36eb0445`.
This is a separate historical experiment, not a replacement for the production C5 model below.
Frozen C14 states yield 813 eligible player-seasons in 2010–2025; 13 rolling folds produce
663 predictions per model/target. No preseason target-team assignment is required.

B0 is a historical league baseline, B1 is qualified raw prior QB performance with an explicit
B0 fallback, B2 is the existing career-performance expectation (zero for PAE), and M1 is a
19-predictor Ridge model with training-only imputation, scaling, and chronological alpha tuning.
2013–2018 development folds select **B2 EPA** and **M1 PAE** before 2019–2025 validation.
The latter contains 373 QB-seasons. Selected EPA MAE/RMSE are 0.12704/0.17276; selected PAE
MAE/RMSE are 0.11957/0.16011. EPA M1 is a promising challenger, but its later gains do not
retroactively change model selection.

Both selected outcomes are **NOT SUPPORTED for projection approval under the declared checklist**:
B2 EPA narrowly fails the absolute calibration-intercept limit (−0.051098 versus 0.05), while
M1 PAE fails the calibration-slope limit (1.917407 versus 1.5). Rolling OOS residual intervals
have 50/80/95% validation coverage of 47.45/78.55/95.17% for EPA and 49.06/78.28/94.37% for PAE.
These are predictive intervals with empirical coverage, not coefficient confidence intervals or
unconditional guarantees. Source uncertainty remains separately visible, not an arbitrary score.

The historical experiment is complete; Checkpoint 17 is not ready. There is no approved 2026
Player State in the frozen source (which ends in 2025), and no forward predictions are generated.
No Scheme, coach variable, Coach Effect, ranking, or production behavior was added. Full methods,
selection rules, cohort accounting, limitations, and artifacts are in
[the Checkpoint 16 report](docs/CHECKPOINT_16_ONE_YEAR_QB_PROJECTION.md).

## Checkpoint 15 Player × Scheme fit research

Corrected version `c15-c4d7c86f56238a49` compares rolling-origin Ridge models: core Player State
(M0), core
Player State plus prior Scheme main effects (M1), and predeclared Player × Scheme interactions
(M2). Conditional Checkpoint 13/14 features are challengers, not promoted into the primary
specifications. Preprocessing and hyperparameter selection are fit inside each training window.

The final status is `NOT ESTIMABLE / DATA-LIMITED`. M2 has zero estimable historical folds because
safely dated
preseason veteran target-team evidence begins in 2025, while prior years' immutable draft-team rows
do not have prior NFL style histories. No standalone fit quantity, M2 coefficient, bootstrap
interval, permutation result, or fit score is released. M0/M1 metrics are narrow-cohort research
diagnostics and not a projection product. Their negative out-of-sample correlation and calibration
evidence did not support a scheme-conditioned projection baseline. This is the historical C15
readiness conclusion, not a target-team requirement for C16's independent Player State experiment.
Projection work is still explicitly forbidden from consuming interactions from this checkpoint.
Original run `c15-2ac7553234223553` and its original
label remain preserved as historical output rather than being overwritten.

## Checkpoint 14 research representation

Checkpoint 14 adds no production prediction or transition model. Its empirical-Bayes operations
shrink individual historical QB feature estimates toward as-of league priors and expose the raw
values, shrinkage weights, standard errors, and intervals. The preseason ability estimate is only
a cumulative EPA/dropback baseline and must not be interpreted as a latent or composite QB grade.

Status: checkpoint six implemented; pending approval.

## Version and intended use

- Data version: `c5-8fd5d1aba2598c59`
- Source historical version: `c3-f6c1aa118ff43b90`
- Model version: `expected-performance-8fd5d1aba2598c59`
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

Regression tests enforce strict feature timing, a target-metric leakage adversary, Trent Edwards' 2010 midseason destination invariance, true-rookie versus veteran-no-history cases, missing prior/college fields, duplicate grains and outputs, finite predictions, exact PAE arithmetic, dropback reconciliation, warm-up exclusion, forbidden coaching/current-result features, complete parameter/source/dependency versioning, byte-identical clean rebuilds, and atomic failure. A dedicated dependency regression changes the recorded SciPy version and proves that a new immutable output is built instead of reusing the prior directory. PostgreSQL behavior tests cover timing, roster/performance-history fields, interval bounds, uncertainty fields, reliability, and PAE arithmetic when a database is available.

The version identity includes all declared model parameters, every feature source, relevant source-code hashes, and NumPy, Polars, SciPy, and scikit-learn versions. Changing career shrinkage, the recorded SciPy version, or any other output-affecting specification creates a new immutable data/model version.

## Known risks and prohibited uses

PAE is performance relative to a limited expectation, not player or coach quality. It can absorb supporting cast, scheme, injuries, schedule, measurement error, and luck. Model-family selection uses the reported backtest rather than an untouched deployment holdout. Do not use PAE alone for employment, contract, wagering, causal, or medical decisions. See `LIMITATIONS.md`.

## Coach-impact extension

- Coach-impact data version: `c6-400a5b474aa37a35`
- Coach-impact model version: `coach-impact-400a5b474aa37a35`
- Outcome: interval actual EPA/dropback minus the checkpoint-five preseason expectation
- Primary assignment scope: verified only
- Selected exploratory estimator: role-specific empirical-Bayes partial pooling of adjusted interval residuals, with weighted Ridge hat-matrix effective degrees of freedom
- Uncertainty: 200 QB-season block-bootstrap attempts; conditional coach-specific percentiles require at least 160 successful appearances
- Ranking status: suppressed because coach and team environment are not independently identified

The coach model uses one QB-coach-assignment interval after joining actual game weeks to supported coaching boundaries. The no-coach baseline and regularized coach fixed-effects candidate are retained for comparison. Primary controls include timing-safe QB profile/history/injury fields plus repeated-QB and season indicators. Team-season indicators are excluded because they nearly encode full-season coach assignments; they appear only in a nonidentified contextual sensitivity. Same-season offensive EPA, final records, honors, external rankings, and provisional assignments are absent from the primary model.

Verified usable samples are 983 head-coach, 23 offensive-coordinator, 12 play-caller, and one quarterbacks-coach interval after applying the 25-dropback rule to fractional exposure. The two Houston shared-duty rows each have 20 effective dropbacks and are excluded. The QB-coach role is structurally unidentified, and all other role rankings are also suppressed because the available data cannot separate coaches from team environment. Of the estimated effects, supported conditional intervals exist for 107 head coaches, six OCs, and two play-callers; every row reports successful and attempted draws.

Checkpoint seven changes no feature, expectation, PAE, exposure, estimator, interval, or ranking definition. PostgreSQL and FastAPI preserve the exact checkpoint-five and checkpoint-six model/data versions and all eligibility, reliability, identification, provisional, exploratory, and suppression fields.
