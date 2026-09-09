# Checkpoint 12 final Coach Effect research

Date: 2026-09-09
Research version: `c12-final-0c746df0290c836c`
Status: research complete; production Coach Effect **NO-GO**

## Executive decision

The final architecture decision is **E — NO COMPOSITE COACH EFFECT APPROVED**. Preserve Q and
PCAE as different research measurements. Do not combine them, publish fixed weights, transform
them to 0–100, or rank coaches.

PCAE contains a repeatable, directly attributed play-calling decision-value association in the
modern verified sample. Q does not contain a stable repeatable signal for any role. More
importantly, no coach-history model improves future Play Caller Q meaningfully over the no-coach
baseline. The best candidate reduces pooled RMSE by only 0.12%, has negative Pearson correlation,
and does not improve direction accuracy. Learned Q and PCAE coefficients change sign across
chronological folds and every cluster-bootstrap interval includes zero.

This is an observational result. It neither proves that coaches cause QB outcomes nor proves that
all coaches are identical.

## Frozen inputs and grains

The run consumes Prompt 10 `c12-pc-final-cac923f086757e5b` and Prompt 11
`c12-gate-38dc6c52c7f74b88`. It reproduces the independent gate counts before modeling: 180/192
fully verified 2020–2025 cells, 206 recent and 269 historical common Q/P coach-seasons, 165 future
rows, 136 credible target rows, five credible folds, 96 different-QB pairs, and 19 different-team
pairs.

| Object | Grain |
|---|---|
| PAE | `load_id, player_id, team_id, season` |
| Q | verified `assignment_key, player_id, team_id, season` exposure with at least 25 effective dropbacks |
| PCAE | verified, non-shared `coach_id, team_id, season, start_week, end_week` interval |
| Coach-season | exposure-weighted `coach_id, team_id, season` |
| Future target | current verified Play Caller coach-team-season Q with earlier common Q/P history |
| Repeatability pair | same coach in consecutive seasons; never across a missing season |
| Different-QB pair | repeatability pair whose canonical QB-ID set changes |
| Different-team pair | repeatability pair whose canonical team changes |

The final interval-aware snapshot contains 4,159 assignment-QB-team-season rows, 300 coaches, 263
QBs, 32 teams, 16 seasons, and 1,065,725 effective exposure dropbacks. PCAE has 287 verified,
non-shared intervals, 105 callers, 14 seasons, and 226,266 attributed plays. Provisional,
unresolved, season-designation-only, and shared play-caller duties receive no individual PCAE.

The primary common Q/P sample has 206 coach-seasons, 81 callers, 107 canonical QBs, all 32 teams,
and 187,291 attributable plays. The broader primary PCAE audit has 212 coach-seasons and 189,353
plays; the difference consists of verified PCAE rows without a common Q observation.

PAE remains `actual EPA/dropback - preseason expected EPA/dropback`. Q remains observed
coach-interval change from prior PAE minus the expanding-window estimate of normal QB
progression. PCAE remains `CoachAverage(CallValue) - LeagueAverage(CallValue)`, and CallValue
uses expected chosen-play EPA minus expected alternative-play EPA—not the realized EPA of the
play.

## Exact future target and chronology

For caller `c`, team `t`, and target season `s`, the prediction target is:

`Y(c,t,s) = Q(c,t,s)`

where Q is the verified Play Caller coach-season QB-development residual. A model may use only
the caller's Q/PCAE observations from seasons earlier than `s`. Every center, scale,
residualization, coefficient, intercept, and Ridge fit is learned inside the training portion.
The target and future seasons never enter training.

The independently declared primary folds are:

| Target | Prior training rows | Target rows |
|---:|---:|---:|
| 2021 | 29 | 27 |
| 2022 | 56 | 23 |
| 2023 | 79 | 27 |
| 2024 | 106 | 30 |
| 2025 | 136 | 29 |

Models 0–5 use exactly these same 136 target rows. The rejected 2020 fold remains outside primary
evaluation because it had only 18 targets and 11 prior rows.

## Role-specific Q audit

Primary results use 2020–2025. Intervals are coach-cluster bootstraps with 500 successful draws.

| Role | Coach-seasons | Coaches | QBs | Teams | Exposure DB | Repeat r | Different-QB r | Different-team r | Decision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Head coach | 195 | 68 | 99 | 32 | 103,890 | 0.064 | 0.047 | not estimable (1 pair) | Not identifiable |
| OC | 185 | 82 | 98 | 32 | 99,296 | 0.010 | -0.033 | 0.074 (10 pairs) | Insufficient signal |
| QB coach | 182 | 82 | 99 | 32 | 100,270 | -0.005 | -0.042 | 0.151 (16 pairs) | Insufficient signal |
| Play Caller | 202 | 80 | 99 | 32 | 98,166 | 0.010 | -0.013 | 0.241 (15 pairs) | Insufficient signal |

All primary Q repeatability and different-QB bootstrap intervals include zero. Head-coach Q is
not independently identified from the franchise, staff, and team-season environment. The other
Q role results are weak, inconsistent, and exploratory. Historically offensive versus
non-offensive head coaches were not compared because the repository has no independently
versioned, source-backed orientation contract; inventing labels would violate the evidence
standard.

## Final PCAE audit

In the primary window, PCAE has 212 coach-seasons, 82 callers, 112 consecutive pairs, 92
different-QB pairs, 20 different-team pairs, and 189,353 attributed plays.

- Repeatability: Pearson 0.354, Spearman 0.276, direction agreement 58.9%, coach-bootstrap 95%
  interval [0.119, 0.517].
- Different-QB portability: Pearson 0.370, bootstrap interval [0.146, 0.542].
- Different-team portability: Pearson 0.299, bootstrap interval [-0.276, 0.669]. This is a thin,
  selected 20-pair sensitivity and is not established portability.
- One-season reliability: 0.293.
- Two-season reliability: 0.453.
- Multi-season reliability at the observed mean 3.41 repeated seasons: 0.585.

The full verified historical sensitivity has 278 coach-seasons, 105 callers, 120 consecutive
pairs, and 226,266 plays. Its repeatability is 0.333; one-, two-, and observed multi-season
reliabilities are 0.264, 0.418, and 0.555. Expanded verification therefore supports a moderate
PCAE research signal, but at lower reliability than the earlier sparse Prompt 6 estimates of
approximately 0.437 and 0.608.

PCAE is **RESEARCH-READY** as a separate, observational play-calling decision-value metric. It
does not establish future QB-development Q and is not a production Coach Effect.

## Q/P relationship

In the primary 206-row common sample, Q/P Pearson is 0.096, Spearman is 0.043, shared linear
variance is 0.0092, and sign agreement is 51.9%. Full-history values are 0.069, 0.027, 0.0048,
and 49.8%.

The low overlap is consistent with different mechanisms and substantial Q noise. It does not by
itself demonstrate that Q and PCAE are complementary, and it supplies no reason to combine them.

## Rolling-origin model comparison

| Model | n | Pearson | Spearman | RMSE | MAE | Direction |
|---|---:|---:|---:|---:|---:|---:|
| 0 — no coach history | 136 | -0.155 | -0.033 | 0.25484 | 0.13003 | 49.3% |
| 1 — Q only | 136 | -0.186 | -0.064 | 0.25558 | 0.13019 | 50.0% |
| 2 — PCAE only | 136 | -0.117 | -0.005 | 0.25522 | 0.13082 | 47.1% |
| 3 — equal Q/P | 136 | -0.119 | -0.011 | 0.25452 | 0.12980 | 49.3% |
| 4 — learned Q/P | 136 | -0.142 | -0.032 | 0.25587 | 0.13089 | 48.5% |
| 5 — overlap decomposition | 136 | -0.140 | -0.032 | 0.25583 | 0.13087 | 48.5% |
| 6 — role-aware | 0 | — | — | — | — | — |

Model 3 has the lowest RMSE among Models 0–5, improving on Model 0 by just 0.00032, or 0.12%; its
MAE improvement is 0.00023 and direction accuracy is unchanged. Model 2 has the least-negative
Pearson correlation among Models 0–5. No candidate has positive pooled Pearson or Spearman
correlation. These changes are not practically meaningful.

Model 6 is not fit because team-season roles co-occur too consistently to identify separate HC,
OC, QB-coach, and Play Caller effects from this sample. It is not assigned a more favorable
evaluation population.

## Coefficient stability

The learned standardized `(Q, PCAE)` coefficients by target fold are:

- 2021: `(0.0154, -0.0034)`
- 2022: `(-0.0034, 0.0314)`
- 2023: `(-0.0050, 0.0193)`
- 2024: `(-0.0008, 0.0232)`
- 2025: `(-0.0055, 0.0211)`

Coach-cluster bootstrap intervals are Q [-0.0277, 0.0115] and PCAE [-0.0035, 0.0554]. Team,
QB-set, and season resampling also include zero. Leave-one-season-out and leave-one-coach-out
refits are retained in `weight_stability.csv`. Signs are unstable and magnitudes are small, so no
fixed Q/P weights are approved.

## Shrinkage and uncertainty

Method-of-moments and REML diagnostics are role-specific. Primary between-coach variance
estimates `(MOM, REML)` are approximately:

- HC Q: `(0.000674, 0.000379)`
- OC Q: `(0.000322, 0.000006)`
- QB-coach Q: `(0, 0.000006)`
- Play Caller Q: `(0.005394, 0.000483)`
- PCAE: `(0.000086, 0.000060)`

Normal-normal empirical-Bayes shrinkage improves RMSE versus raw history for PCAE and for noisy Q
histories largely by pulling them toward the league center. That error reduction is not evidence
of a coach effect: Q correlations remain near zero or negative, and variance methods disagree
materially for several roles. No universal or production shrinkage method is selected. REML
normal-normal estimates and 95% research intervals are retained as diagnostics; MOM remains a
boundary/sensitivity comparison.

Low-evidence estimates shrink more than high-evidence estimates. The structured eligibility
file reports the raw estimate, exposure, seasons, QBs, teams, shrinkage weight, interval, evidence
grade, and suppression status for each coach. Confidence never multiplies the estimate.

Evidence grades are descriptive rather than opaque points:

- HIGH: at least four seasons, at least two QBs, and at least 1,500 exposure units.
- MODERATE: at least three seasons, at least two QBs, and at least 600 exposure
  units.
- LOW: anything narrower.

Research inclusion uses the MODERATE boundary, while all production rows remain suppressed.
Intervals are approximate normal-normal empirical-Bayes research intervals. They are not causal
intervals or future-performance prediction intervals.

## Environment, missingness, placebos, and Scheme

Preseason environment residualization is learned inside each chronological target fold. Raw and
context-adjusted coach aggregates remain highly similar: Pearson 0.951–0.982, rank correlation
0.937–0.984, and sign agreement 83.3%–93.2% across roles. Environment remains a control and
sensitivity, not score points. These high similarities do not identify causal coach effects.

Prompt 11's missing-not-at-random finding is preserved. Modern-primary PCAE repeatability is
0.354 versus 0.333 full history; leave-old-era-out is about 0.399 in the 206 common Q/P subset.
Clipped verification-propensity weighting moves the historical PCAE repeatability diagnostic
from 0.380 to 0.363, with effective n only 61.2 and poor overlap. It is a sensitivity—not a
missing-data solution.

Each applicable placebo uses 1,000 deterministic within-season permutations, preserving role,
season, rows, and exposure structure. Modern PCAE repeatability and different-QB results have
empirical two-sided p=0.001. The different-team result has p=0.170. Every primary Q placebo is
non-significant. Statistical significance does not make the moderate PCAE effect causal or
production-ready.

The Scheme challenger uses only prior-season shotgun, no-huddle, and early-down pass rates. It
uses the same 136 target rows, has RMSE 0.25848 and Pearson -0.114, and is worse than the no-coach
baseline on error. Scheme does not enter Coach Effect and remains explanatory/Phase II input.

## Eligibility, readiness, and production gate

Role/signal classifications are:

- Head-coach Q: **NOT IDENTIFIABLE**.
- OC Q: **EXPLORATORY ONLY**.
- QB-coach Q: **EXPLORATORY ONLY**.
- Play Caller Q: **EXPLORATORY ONLY**.
- PCAE: **RESEARCH-READY** as a separate metric.
- Combined Play Caller signal: **EXPLORATORY ONLY**; no combination approved.

No 0–100 mapping is statistically ready. Coaches without sufficient evidence are marked
`SUPPRESSED`, not assigned precise average-looking public scores.

Production remains **NO-GO** because:

- recent full-cell coverage is 93.75%, below 95%;
- recent attributable-play coverage is 94.65%, below 95%;
- there is no stable OOS Coach Effect architecture;
- OC, QB-coach, and Play Caller verification is not comprehensively production-complete;
- role-specific uncertainty and production eligibility are not validated.

Additional broad historical caller research is not recommended. Targeted verification of the 12
recent non-full cells remains useful only if production is pursued.

## Closeout

Checkpoint 12 research is **COMPLETE**. It answers which signals repeat, which fail, why a
composite is not defensible, how uncertainty and suppression must be represented, and what would
be needed for production. Phase II Checkpoint 13 readiness is **READY**, but Phase II was not
implemented.

## Phase II handoff

Phase II begins at **Checkpoint 13 — Predictive Data Foundation + Scheme Engine**. It may use
historical PAE, QB histories, Coach/QB relationships, verified coaching assignments, PCAE as a
research feature where appropriate, Scheme artifacts, and uncertainty/verification metadata.
It must not treat a finalized composite Coach Effect as an available production feature.

The generated outputs are deterministic, ignored, research-only artifacts under
`research/coach_effect/outputs/checkpoint_12_final_research/`. No production code, database,
API, frontend, Neon, Render, ranking, unsupported attribution, Phase II feature, or Ask Anything
feature changed.
