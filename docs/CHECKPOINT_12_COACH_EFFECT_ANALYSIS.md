# Checkpoint Twelve — Final Coach Effect Equation Research

## Decision

**Production decision: NO-GO.** The evidence supports continued exploratory research, especially
for verified play callers, but it does not support a final production Coach Effect equation,
production weights, a 0–100 score, or coach rankings. All estimates are observational associations,
not proof of causation.

Research data version: `c12-8cd15ae6015e900b`.

## Frozen inputs and boundaries

- Production publication lineage: `22680407-d503-5290-bda2-18f4cbcb622a`.
- PAE data/model: `c5-8fd5d1aba2598c59` /
  `expected-performance-8fd5d1aba2598c59`.
- PCAE data/model: `c11b-bbf7d43d0e4c4c05` /
  `pcae-expanding-prior-seasons-v1`.
- PCAE play eligibility: `pcae-play-eligibility-v2`.
- PAE remains `actual EPA/dropback - expected EPA/dropback` and is joined on the complete
  `(load_id, player_id, team_id, season)` key.
- PCAE is attached only to verified, explicitly sourced, week-bounded play-caller assignments.
  Missing PCAE remains null; no attributed plays is not converted to zero PCAE.
- Every validation fold fits through season `S-1` and evaluates season `S`. Preprocessing and
  residualization are fitted on training rows only.
- Same-season environment measures are descriptive only. Leakage-safe preseason context is used
  only in robustness comparisons and never contributes score points.
- This checkpoint changes no production model, data, database, API, frontend, deployment, or
  publication pointer.

## Research table and exact samples

The joined research table contains 3,900 assignment/QB interval rows. Counts below are assignment
intervals rather than collapsed team-seasons, so in-season changes remain distinct.

| Role | Joined rows | Assignment intervals | Coaches | QBs | Teams | Seasons | Exposure dropbacks | 200+ DB facts | Q rows | PCAE rows |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Head coach | 1,225 | 540 | 120 | 263 | 32 | 16 | 317,885 | 581 | 797 | 0 |
| Offensive coordinator | 1,159 | 513 | 154 | 261 | 32 | 16 | 302,973 | 554 | 776 | 0 |
| Quarterbacks coach | 1,144 | 497 | 151 | 262 | 32 | 16 | 306,806 | 564 | 753 | 0 |
| Play caller | 372 | 175 | 93 | 152 | 32 | 12 | 81,805 | 170 | 295 | 173 |

The 173 PCAE intervals cover 134,150 attributed plays. PCAE is unavailable for the other roles
because play-level decision attribution is specific to verified play callers.

## Q: QB development beyond normal progression

Q is the interval-weighted PAE movement remaining after a Ridge model predicts normal QB
progression using strictly prior-season information. It is not raw PAE and is not a causal coach
effect. Repeatability is weak for head coaches, offensive coordinators, and quarterbacks coaches,
and stronger but still uncertain for verified play callers.

| Role | Coach-seasons | Consecutive pairs | Pearson | Spearman | One-season reliability | Bootstrap Pearson interval |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Head coach | 442 | 309 | 0.070 | 0.034 | 0.016 | [-0.021, 0.167] |
| Offensive coordinator | 430 | 238 | 0.014 | 0.004 | 0.055 | [-0.071, 0.102] |
| Quarterbacks coach | 419 | 230 | 0.046 | 0.054 | 0.000 | [-0.077, 0.157] |
| Play caller | 160 | 49 | 0.416 | 0.323 | 0.388 | [0.103, 0.615] |

## PCAE repeatability and reliability

Verified play callers produced 171 coach-seasons, 48 repeat coaches, and 56 consecutive-season
pairs. PCAE repeatability was Pearson `0.383`, Spearman `0.312`, and same-direction `0.571`; the
bootstrap Pearson interval was `[0.061, 0.588]`. Reliability estimates were `0.326` for one season,
`0.491` for two seasons, and `0.559` for the observed multi-season mix. These results pass the
research repeatability gate inside the verified subset, but incomplete historical play-caller
coverage prevents production use.

## Portability

Different-QB Q portability was near zero for head coach (`0.004`), offensive coordinator (`0.010`),
and quarterbacks coach (`0.059`), and modest for play caller (`0.203`). The play-caller bootstrap
interval was `[0.069, 0.341]`; this is encouraging but not role-complete evidence.

Different-team Q portability was head coach `0.033`, offensive coordinator `0.047`, quarterbacks
coach `-0.038`, and play caller `0.517`. Verified play-caller PCAE different-team portability was
`0.429`. Samples were sparse: the play-caller analyses used 51 Q pairs and 57 PCAE pairs. Results
therefore remain exploratory and are not interpreted causally.

## Rolling-origin model comparison

The common Q/P evaluation covers only the 2024 and 2025 target folds and 50 observations. That is
too little history to select stable learned weights.

| Candidate | Pearson | Spearman | RMSE | MAE | Direction accuracy |
| --- | ---: | ---: | ---: | ---: | ---: |
| Model 1 — Q only | -0.005 | -0.051 | 0.762 | 0.643 | 0.640 |
| Model 2 — PCAE only | 0.264 | 0.221 | 0.757 | 0.625 | 0.660 |
| Model 3 — equal Q + PCAE | 0.197 | 0.202 | 0.800 | 0.623 | 0.760 |
| Model 4 — learned joint | 0.175 | 0.162 | 0.731 | 0.611 | 0.740 |
| Model 5 — overlap decomposition | 0.173 | 0.155 | 0.728 | 0.607 | 0.740 |
| Model 6 — core plus Scheme | excluded | excluded | excluded | excluded | excluded |

The prior-season-offense baseline had Pearson `0.033`, RMSE `0.789`, and MAE `0.667`. Current-season
raw EPA, offensive rank, and record are explicitly marked descriptive and are not selectable
baselines. Model 5 has the best error metrics in this narrow comparison, but neither it nor Model 4
is selected because only two future folds support weight learning.

The learned Model 4 weights moved from Q/P `0.142/0.120` in 2024 to `0.165/0.123` in 2025. Model 5
unique-Q/unique-P/shared weights moved from `0.108/0.083/0.090` to
`0.127/0.078/0.112`. This short series is not adequate evidence of stable production weights.

## Q/P overlap

Across 160 common play-caller coach-season observations, Q and PCAE correlated at Pearson `0.109`
and Spearman `0.037`; linear shared variance was `1.19%`, and signs agreed in `48.1%` of rows. The
signals are not interchangeable. Overlap decomposition remains a candidate research
specification, not a selected formula.

## Deterministic placebo tests

Each applicable test uses 1,000 seeded, within-season/role label permutations. Most head coach,
offensive coordinator, and quarterbacks coach tests did not separate from placebo. Play-caller Q
did separate for future prediction (`p=0.004`), repeatability (`p=0.004`), different-QB portability
(`p=0.014`), and different-team portability (`p=0.001`), but not between-coach variance (`p=0.121`).
Play-caller PCAE separated for future prediction (`p=0.001`), repeatability (`p=0.003`), and
different-team portability (`p=0.001`), but not between-coach variance (`p=0.196`). This pattern is
promising within the verified subset but does not overcome coverage and identification limits.

## Environment robustness

Adding leakage-safe preseason environment features did not improve held-out error for any role.
For play callers, history-only Pearson/RMSE were `0.235/0.212`, versus `0.160/0.215` with preseason
environment. The environment gate therefore fails. Context remains a robustness adjustment, never
a set of additive Coach Effect points.

## Scheme portability gate

Only three of ten required scheme measures are directly available: shotgun rate, no-huddle rate,
and early-down pass rate. Personnel groupings, motion, play action, screens, and RPO rates remain
explicitly unavailable rather than inferred from staff descriptions. The partial study includes 43
OC moves, only six coaches with multiple moves, 20 persistence observations, 42 future-PAE
observations, and 14 future-PCAE observations.

Euclidean, Manhattan, cosine, and correlation distances were compared against 1,000 deterministic
placebos. Several partial metrics showed directional movement toward the incoming coordinator's
prior offense, but results varied by distance and the required feature/coverage gates fail. Scheme
is excluded from Model 6 and cannot enter a production score.

## Shrinkage, confidence, suppression, and presentation

Method-of-moments between-coach variance reaches the zero boundary for every role/signal. The
empirical-Bayes posterior therefore centers estimates at the prior rather than manufacturing
separation. At that boundary, intervals use a documented sampling-variance fallback so uncertainty
does not collapse to zero width. Exposure sensitivity is reported at Q constants 200/400/600 and
PCAE constants 500/1,000/2,000, but no production shrinkage constant is selected.

Confidence is represented as a separate evidence grade plus an interval; it never multiplies the
score. The candidate research suppression rule requires at least three seasons, two quarterbacks
where applicable, and 600 exposure dropbacks for eligibility; two seasons and 200 dropbacks are
provisional, and smaller samples are suppressed. Every row remains
`research_only_not_publishable`.

Percentile, reliability-adjusted percentile, and bounded-z 0–100 presentations are exported only
to examine behavior. Because the variance component is at its boundary and no core equation has
passed, no 0–100 mapping is approved.

## Role readiness and decision gates

| Role | Readiness | Reason |
| --- | --- | --- |
| Head coach | EXPLORATORY ONLY | Very low Q reliability and no portability separation. |
| Offensive coordinator | EXPLORATORY ONLY | Weak Q validation; PCAE unavailable; Scheme incomplete. |
| Quarterbacks coach | EXPLORATORY ONLY | Zero estimated Q reliability and weak portability. |
| Play caller | EXPLORATORY ONLY | Promising Q/PCAE signals, but incomplete verified coverage, only two common future folds, zero-boundary variance, and failed Scheme gate. |

Gate outcomes:

- QB development: **MIXED**.
- PAE reliability by role: **MIXED**.
- PCAE repeatability: **PASS within the verified play-caller subset**.
- PCAE future portability: **PASS within the verified play-caller subset**.
- Different-QB portability: **MIXED**.
- Different-team portability: **MIXED**.
- Placebo separation: **MIXED**.
- Environment robustness: **FAIL**.
- Scheme portability: **MIXED and partial**.
- Scheme component: **FAIL**.
- Core production equation: **NOT READY**.
- Learned weights: **NOT JUSTIFIED / UNSTABLE**.
- Production shrinkage: **NOT READY**.
- Confidence representation: **READY as grade plus interval only**.
- Suppression policy: **READY for research use only**.
- Production 0–100 score: **NOT READY**.

## Reproducibility and artifacts

The content-addressed identity hashes every source file, every manual coaching CSV, all 2010–2025
play-by-play inputs, relevant research code, parameters, and NumPy, Polars, scikit-learn, and SciPy
versions. Deterministic CSVs use stable total ordering and normalized floating-point output. Two
independent empty-directory builds must have the same research version, file list, checksums, and
bytes. Execution-specific timing or cache information is not written into analytical artifacts.

Generated outputs are ignored under
`research/coach_effect/outputs/checkpoint_12/c12-8cd15ae6015e900b/`. The tracked research files are:

- `research/coach_effect/checkpoint_twelve.py`
- `scripts/run_checkpoint_twelve.py`
- `tests/test_checkpoint_twelve_coach_effect.py`
- this report and the research README/Makefile entry

No production score, ranking, equation, or publication was created. Nothing in this research phase
is committed, pushed, deployed, or loaded into the application.
