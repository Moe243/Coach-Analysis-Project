# Checkpoint Twelve — Independent Adversarial Review

## Decision

**Prompt 6's production NO-GO is confirmed, but not every supporting interpretation is.** The
dominant constraint is insufficient verified historical play-caller evidence: the current common
Q/P design has only two eligible future folds and 50 target observations. There is also a secondary
methodology component: Candidate A pooled role-specific variance estimation, used nonchronological
all-time holdouts as portability evidence, and treated failure to improve prediction as failure of
environment robustness. Correcting those issues leaves an encouraging but exploratory verified
play-caller signal and does not justify a final equation, weights, score, or ranking.

Independent review version: `c12-review-7897e3d57dd8b22a`.

Candidate Research A remains unchanged at `c12-8cd15ae6015e900b`. Production remains unchanged at
repository baseline `3024ede03de9926a9fd96f98308e3cf9fd4d83c3` and load
`22680407-d503-5290-bda2-18f4cbcb622a`.

## Independent grain and attribution audit

The review rebuilt PAE, verified assignments, assignment/QB exposure, Q, and PCAE from frozen
repository sources rather than using Candidate A's intermediate research CSVs.

| Stage | Grain | Rows | Multiplication | Result |
| --- | --- | ---: | ---: | --- |
| PAE | `(load_id, player_id, team_id, season)` | 1,187 | 0 | Unique; arithmetic and preseason timing pass |
| Verified assignment | `assignment_key` plus bounded role interval | 1,725 | 0 | Play-caller season designations excluded |
| Assignment/QB exposure | `(assignment_key, player_id, team_id, season)` | 3,900 | 0 | Role duplication is intentional |
| PCAE | verified play-caller assignment interval | 173 | 0 | 134,150 eligible plays; no provisional/shared/unbounded rows |

One Q observation is a verified `assignment_key` × QB × team × season exposure interval with at
least 25 fractional exposure dropbacks. It is
`coach_interval_PAE - prior_PAE - expected_normal_QB_delta`, where the progression model and its
preprocessing use prior seasons only. A QB can appear once for each concurrently applicable role;
that is explicit role attribution, not silent row multiplication. In-season intervals remain
separate before coach-season aggregation.

PCAE maps eligible regular-season plays by game/week/team to an explicitly sourced, bounded,
verified play-caller assignment. Provisional and unresolved cells, shared intervals, OC
substitution, and unbounded season designations are excluded. Deterministic traces reproduced, for
example, Baltimore/Cam Cameron plays in 2010, 2011, and the bounded Weeks 1–14 interval in 2012.

## Q/P overlap reconciliation

The historical `0.5926` statistic came from an earlier 2025 paired coach-level exploratory table.
It is not the same estimand or evaluation population as Candidate A's transition-residual Q. It is
not reproducible from the current production PAE and verified interval PCAE at the current grains;
the current 2025 Q/P correlation is `0.252` over 34 coach-season rows.

| Subset | Grain | n | Pearson | Spearman |
| --- | --- | ---: | ---: | ---: |
| Full common history | QB-team-season PAE vs team PCAE | 342 | -0.026 | -0.049 |
| Full common history | team-season PAE vs PCAE | 144 | 0.005 | 0.014 |
| Full common history | verified-caller coach-season raw PAE vs PCAE | 160 | 0.111 | 0.053 |
| Full common history | Prompt 6 Q coach-season vs PCAE | 160 | **0.109** | **0.037** |
| 2023–2025 | QB-team-season PAE vs team PCAE | 235 | -0.068 | -0.057 |
| 2023–2025 | team-season PAE vs PCAE | 96 | -0.009 | 0.008 |
| 2023–2025 | verified-caller coach-season raw PAE vs PCAE | 101 | 0.135 | 0.072 |
| 2023–2025 | Prompt 6 Q coach-season vs PCAE | 101 | 0.108 | 0.030 |

The `0.109` result is correct for Candidate A's documented Q grain. The discrepancy is caused by
different source vintages, years, grains, verified-caller selection, transition residualization,
and aggregation—not by one team's PCAE being joined to another QB-team-season.

## Aggregation and variance audit

Q repeatability is materially aggregation-sensitive:

| Role | Raw PAE delta, DB-weighted | Transition Q, DB-weighted | Transition Q, unweighted | Q shrunk at 400 DB |
| --- | ---: | ---: | ---: | ---: |
| Head coach | -0.188 | 0.070 | 0.103 | 0.026 |
| Offensive coordinator | -0.167 | 0.014 | 0.081 | -0.007 |
| Play caller | -0.102 | 0.416 | 0.547 | 0.337 |
| Quarterbacks coach | -0.097 | 0.046 | 0.117 | 0.018 |

Candidate A's zero-boundary variance did not arise from a row-multiplication bug, but the
implementation pooled roles despite role-specific estimands. The independent audit estimates each
role separately with residual degrees of freedom `intervals - coaches` and compares weighted
method-of-moments, unweighted ANOVA, a group-mean REML-like likelihood, and 1,000 bootstrap draws.

| Signal / role | Intervals / coaches | Raw weighted MOM tau² | Truncated | REML-like tau² | ANOVA tau² | Bootstrap raw 95% interval |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| PCAE / play caller | 173 / 93 | -0.00000011 | 0 | 0.00002521 | 0.00002743 | [-0.00002059, 0.00001823] |
| Q / head coach | 663 / 108 | -0.004252 | 0 | 0.000242 | 0.000262 | [-0.006510, -0.002373] |
| Q / offensive coordinator | 647 / 140 | -0.003319 | 0 | 0.000084 | 0.001094 | [-0.005189, -0.001763] |
| Q / play caller | 249 / 89 | -0.001537 | 0 | 0.003961 | 0.009829 | [-0.005335, 0.001802] |
| Q / quarterbacks coach | 634 / 137 | -0.001494 | 0 | 0.0000039 | 0.000948 | [-0.002407, -0.000576] |

Zero is therefore an **estimator/sample limitation**, not proof of equal coaches and not a
production shrinkage estimate. Alternative estimators are positive and unstable; no method is
selected.

## Future folds and rolling validation

Individually verified partial seasons are already retained. League-complete play-caller coverage
was not required. The bottleneck is the intersection of a verified PCAE coach-season, a valid Q
transition, prior same-coach Q/P history, and at least ten prior training rows.

| Season | Q coach-seasons | PCAE coach-seasons | Common Q/P | Prior-history targets | Prior training | Target eligible | Main reason |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 2010 | 0 | 1 | 0 | 0 | 0 | No | no Q transition/history |
| 2011 | 0 | 1 | 0 | 0 | 0 | No | no Q transition/history |
| 2012 | 4 | 4 | 4 | 0 | 0 | No | no prior coach Q/P history |
| 2013 | 1 | 1 | 1 | 0 | 0 | No | no prior coach Q/P history |
| 2014 | 0 | 0 | 0 | 0 | 0 | No | no verified caller |
| 2015 | 3 | 3 | 3 | 0 | 0 | No | no prior coach Q/P history |
| 2016 | 8 | 8 | 8 | 0 | 0 | No | no prior coach Q/P history |
| 2017 | 36 | 36 | 36 | 6 | 0 | No | fewer than 10 training rows |
| 2018 | 6 | 8 | 6 | 3 | 6 | No | fewer than 10 training rows |
| 2019 | 0 | 0 | 0 | 0 | 9 | No | no verified caller |
| 2020 | 1 | 1 | 1 | 0 | 9 | No | fewer than two target rows |
| 2021 | 0 | 0 | 0 | 0 | 9 | No | provisional-only callers |
| 2022 | 0 | 0 | 0 | 0 | 9 | No | provisional-only callers |
| 2023 | 34 | 36 | 34 | 12 | 9 | No | nine prior rows, below ten |
| 2024 | 33 | 36 | 33 | 24 | 21 | **Yes** | eligible |
| 2025 | 34 | 36 | 34 | 26 | 45 | **Yes** | eligible |

The safe revised fold count remains two. Lowering verification or training standards merely to add
folds is not justified. Verifying existing partial/provisional/unresolved cells can add valid rows
without requiring 32/32 coverage.

All five models were independently refit with training through `S-1`, training-only centering,
scaling, and residualization, and identical target keys in each fold.

| Model | 2024 n / Pearson / RMSE / MAE | 2025 n / Pearson / RMSE / MAE | Pooled n / Pearson / Spearman / RMSE / MAE / direction |
| --- | --- | --- | --- |
| Q only | 24 / 0.094 / 0.661 / 0.540 | 26 / -0.024 / 0.844 / 0.738 | 50 / -0.005 / -0.051 / 0.762 / 0.643 / 0.640 |
| PCAE only | 24 / 0.166 / 0.657 / 0.524 | 26 / 0.367 / 0.838 / 0.719 | 50 / 0.264 / 0.221 / 0.757 / 0.625 / 0.660 |
| Equal Q/P | 24 / 0.175 / 0.767 / 0.611 | 26 / 0.216 / 0.830 / 0.633 | 50 / 0.197 / 0.202 / 0.800 / 0.623 / 0.760 |
| Learned joint | 24 / 0.174 / 0.622 / 0.491 | 26 / 0.173 / 0.819 / 0.722 | 50 / 0.175 / 0.162 / 0.731 / 0.611 / 0.740 |
| Overlap decomposition | 24 / 0.174 / 0.616 / 0.482 | 26 / 0.170 / 0.818 / 0.722 | 50 / 0.173 / 0.155 / 0.728 / 0.607 / 0.740 |

Model 5 improves pooled RMSE over Model 4 by only `0.00289`. A row bootstrap gives a small negative
interval, but only two temporal folds exist and the practical difference is negligible. It is not
weight-selection evidence.

## Weight stability

Candidate A's Model 4 coefficients reproduce independently with maximum absolute error
`3.8e-11`. The two fold means are Q `0.1533` and P `0.1210`; Q varies from `0.1417` to `0.1648`, and
P from `0.1195` to `0.1226`. On the 2025 training population, 1,000 row bootstraps produced Q mean
`0.1578` (5th–95th percentile `0.0435–0.2647`) and P mean `0.1128`
(`0.0021–0.2146`); 1.5% and 4.8% of draws, respectively, were negative. Coach, team, and QB
leave-group-out distributions stayed positive but do not create new time folds. Stable signs under
related holdouts cannot replace independent seasons. No weight is approved.

## Portability and placebos

Candidate A's all-time leave-one-group-out portability is nonchronological: future or return stints
can enter a row's history. The corrected primary audit uses only prior seasons from the same coach
and excludes the target QB or team.

| Role | Future different-QB n / Pearson / bootstrap interval | Future different-team n / Pearson / bootstrap interval |
| --- | --- | --- |
| Head coach Q | 432 / -0.023 / [-0.094, 0.073] | 67 / -0.097 / [-0.294, 0.318] |
| Offensive coordinator Q | 365 / 0.020 / [-0.057, 0.095] | 128 / 0.063 / [-0.088, 0.217] |
| Play caller Q | 110 / 0.292 / [0.114, 0.423] | 37 / 0.479 / [0.028, 0.750] |
| Quarterbacks coach Q | 357 / -0.035 / [-0.127, 0.097] | 125 / -0.159 / [-0.388, 0.103] |
| Play caller PCAE | — | 41 / 0.238 / [-0.108, 0.626] |
| Play caller equal Q/P | — | 37 / 0.470 / [0.034, 0.748] |

The different-QB audit also computed all-time leave-one-QB-out and leave-one-coach/QB-pair-out
diagnostics. The latter uses n `371/423/188/412` for HC/OC/play caller/QB coach and is explicitly
nonchronological. It does not duplicate the held-out coach-QB pair into training.

The 1,000 seeded within-role/season label permutations preserve rows, teams, and exposure but can
alter a coach's repeat-history structure. They are appropriate as a broad label-null and too loose
for a precise causal team-switch null. Corrected play-caller Q ranks at the 100th percentile for
both different-QB and different-team tests (`p=0.000999` each); PCAE team portability ranks at the
97.7th percentile (`p=0.024`). These are exploratory because clustering, selection into verified
cells, and small transition counts remain.

## Environment robustness reinterpretation

The correct question is signal stability, not whether context improves forecast error. Comparing
history-only estimates with estimates that add leakage-safe preseason context gives:

| Role | Pearson stability | Rank stability | Sign stability |
| --- | ---: | ---: | ---: |
| Head coach | 0.453 | 0.437 | 0.673 |
| Offensive coordinator | 0.444 | 0.404 | 0.666 |
| Play caller | **0.832** | **0.787** | **0.819** |
| Quarterbacks coach | 0.293 | 0.349 | 0.627 |

Candidate A's universal environment **FAIL** is corrected to **supportive but exploratory for play
callers; mixed/weak for other roles**. Context remains a sensitivity control and contributes no
score points.

## Expanded scheme audit

All ten intended traits can be built without text heuristics inside approved source windows:

| Traits | Source | Window | Observed non-null coverage |
| --- | --- | --- | ---: |
| 11 / 12 / 21 personnel | participation `offense_personnel` | 2016–2025 | 99.23% / 99.47% / 99.58% |
| Shotgun / no huddle | play-by-play flags | 2010–2025 | 100% / 100% |
| Early-down pass | play type plus down | 2010–2025 | 99.70% |
| Motion / play action / screen / RPO | explicit FTN flags | 2022–2025 | 99.93% each |

The seven Candidate A omissions were **available but not engineered and window-limited**, not
globally unavailable. They remain null outside their approved windows: personnel is unavailable
before 2016 and FTN traits before 2022.

The expanded all-qualifying-move sample is 10 HC, 43 OC, 13 verified play caller, 8 OC plus
verified-caller, and 0 HC plus verified-caller moves. Mean standardized-Euclidean adoption is
`1.383/0.390/0.743/0.158/null`, respectively. Results are directionally positive across Euclidean,
Manhattan, cosine, and correlation distance. The correctly aggregated, same-era random-team
specificity p-values under standardized Euclidean distance are `0.001/0.025/0.001/0.057`.
Head-coach, OC, and verified-caller movement separates from this broad placebo, while the combined
OC+caller result is borderline. This is evidence of scheme portability, but the role samples,
selection, multiple comparisons, and future-outcome samples remain too small for a production
component.

For verified callers, the strongest directional year-one trait movements are shotgun `0.064`, 11
personnel `0.058`, 12 personnel `0.035`, motion `0.022`, no huddle `0.020`, and play action `0.014`.
The move sample is too small and correlated to label any trait established. Year-two persistence
has only two retained caller moves; its 100% positive aggregate distance is therefore descriptive,
not evidence.

Every qualifying multiple-move coach is retained in the structured output: John Fox at HC; Brian
Daboll, Darrell Bevell, Dirk Koetter, Dowell Loggains, Kellen Moore, and Kyle Shanahan at OC; and
Kellen Moore among verified play callers. No OC+verified-caller or HC+verified-caller coach has two
qualifying moves in the current source windows.

Future performance uses move-season adoption and the destination team's following season only,
restricted to retained coaches. Verified play-caller associations have only two observations and
are suppressed. HC has 6–7 observations and OC 18–20 for future Q/PAE/offensive EPA; results are
mixed (OC: Q `0.259`, PAE `0.098`, offensive EPA `-0.193`). The OC/PCAE result has n=3 and is not
interpretable. Scheme cannot enter a final equation.

## Play-caller expansion and power

Current serving classification is exactly 119 verified, 1 partial, 125 provisional, and 267
unresolved team-season cells (512 total). The priority table ranks only missing cells and counts Q
availability from an actual leakage-safe movement baseline rather than merely the existence of a
PAE row.

Top 25, in priority order:

1. 2021 BAL — Greg Roman
2. 2022 TB — Byron Leftwich
3. 2021 DAL — Kellen Moore
4. 2022 ARI — Kliff Kingsbury
5. 2022 WAS — Scott Turner
6. 2021 BUF — Brian Daboll
7. 2021 TB — Byron Leftwich
8. 2021 TEN — Todd Downing
9. 2021 KC — Eric Bieniemy
10. 2020 LAC — Shane Steichen
11. 2022 MIN — Kevin O'Connell
12. 2021 ARI — Kliff Kingsbury
13. 2020 DAL — Kellen Moore
14. 2022 PHI — Shane Steichen
15. 2022 DAL — Kellen Moore
16. 2022 PIT — Matt Canada
17. 2022 CLE — Kevin Stefanski
18. 2021 PIT — Matt Canada
19. 2021 CAR — Joe Brady
20. 2022 IND — Frank Reich
21. 2022 KC — Andy Reid
22. 2022 DET — Dan Campbell
23. 2022 NYG — Mike Kafka
24. 2020 LA — Sean McVay
25. 2021 MIN — Klint Kubiak

These cells prioritize added target folds, common Q/P rows, repeat callers, earlier training
history, and eligible-play volume. Candidate names and source URLs remain leads, not verification.
Explicit play-caller evidence and exact in-season intervals are still mandatory.

| Verified target | Added cells | Added eligible plays | Repeat-caller cells | Potential common Q/P cells | Potential target seasons |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 40% | 86 | 90,399 | 80 | 86 | 6 |
| 50% | 137 | 144,936 | 80 | 137 | 10 |
| 60% | 189 | 198,062 | 80 | 189 | 10 |
| 75% | 265 | 273,301 | 80 | 265 | 10 |
| 90% | 342 | 332,353 | 110 | 297 | 10 |

These are availability upper bounds, not imputed PCAE. Final rows depend on evidence quality,
weekly attribution, repeat-coach history, and successful model construction.

A Fisher-z approximation at two-sided alpha 0.05 and 80% power requires about 194 independent
observations for correlation 0.20, 85 for 0.30, and 47 for 0.40. NFL observations are clustered by
coach/QB/team/season, so actual needs are larger. Learned weights should not be revisited before at
least five target folds and 150 common future rows, with stable signs under season, coach, team,
and QB resampling.

## Corrections to Candidate A

| Candidate A result | Independent correction | Impact |
| --- | --- | --- |
| Core joins and Q/P metrics | Reproduced at intended grains | No decision change |
| Role-pooled zero variance | Estimate each role separately and show estimator sensitivity | Zero is not evidence of identical coaches; still no shrinkage selection |
| All-time portability | Replace as primary evidence with strictly chronological portability | HC/OC/QB-coach evidence weakens; play-caller Q remains exploratory-positive |
| Environment gate failed because error rose | Evaluate estimate/rank/sign stability | Play-caller context robustness becomes supportive, not failed |
| Only 3 scheme traits available | Engineer all 10 from participation, PBP, and FTN windows | Larger descriptive scheme audit; still fails sample/specificity gates |
| Model 5 best | Difference from Model 4 is only 0.00289 RMSE across two folds | Practical tie; no model or weights selected |

Classification: **MIXED — primarily DATA LIMITATION, with secondary MODEL/METHODOLOGY DEFECTS and
role-dependent signal weakness.** The evidence does not establish no coaching signal; it establishes
that the present data cannot identify and validate a production Coach Effect equation.

## Data-expansion roadmap and rerun gate

1. Verify the top-25 play-caller cells first, then continue by priority score. Require explicit
   caller evidence and bounded weekly/in-season intervals; preserve shared and unresolved states.
2. Materialize the ten-feature scheme fingerprints with source hashes and explicit nulls outside
   participation/FTN coverage. Do not infer traits from staff descriptions.
3. Rebuild Q/P folds only from newly verified cells. Keep PAE preseason-safe, PCAE verified-only,
   and all missing PCAE null.
4. Do not revisit equation weights, production shrinkage, confidence mapping, 0–100 scores, or
   rankings until the rerun gate is met.

Minimum rerun condition: at least 50% verified play-caller cells, at least five chronological target
folds, at least 150 common future Q/P rows, and stable coefficient signs under season, coach, team,
and QB resampling. The independent transition confidence intervals must also be reported; passing
the count gate alone does not imply readiness.

## Artifacts and reproducibility

Tracked review files are:

- `research/coach_effect/checkpoint_twelve_review.py`
- `scripts/run_checkpoint_twelve_review.py`
- `tests/test_checkpoint_twelve_review.py`
- this report

The ignored versioned directory contains 12 requested CSV outputs plus `MANIFEST.json`; `LATEST`
points to `c12-review-7897e3d57dd8b22a`. Identity includes Candidate A, production lineage, manual
inputs, PAE/PCAE/environment/team-stat/PBP-related sources, participation/FTN frame hashes, review
code, parameters, and dependency versions. CSV float normalization and total ordering make two
independent empty-directory builds byte-identical.

No production code, model, database, API, frontend, deployment, serving data, equation, score, or
ranking changed. Candidate A and this review remain deliberately uncommitted; nothing was pushed or
deployed.
