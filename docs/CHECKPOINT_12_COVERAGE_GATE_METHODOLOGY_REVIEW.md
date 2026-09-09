# Checkpoint Twelve — Prompt 11 Play-Caller Coverage-Gate Methodology Review

Date: 2026-09-08
Production baseline: `3024ede03de9926a9fd96f98308e3cf9fd4d83c3`
Prompt 6 baseline: `c12-8cd15ae6015e900b`
Prompt 7 baseline: `c12-review-7897e3d57dd8b22a`
Prompt 8 baseline: `c12-data-250e540b7de79385`
Prompt 9 baseline: `c12-pc-2cf75b19b3c42914`
Prompt 10 baseline: `c12-pc-final-cac923f086757e5b`
Prompt 11 research version: `c12-gate-38dc6c52c7f74b88`
Original-gate decision: **REPLACE 50% GATE**
Final-equation research rerun: **GO, AFTER METHODOLOGY APPROVAL**
Production publication/ranking: **NOT READY**

## Scope and hard boundaries

This is a methodology review, not another evidence sprint and not an equation run. It uses the
frozen Prompt 10 evidence state. It does not promote, infer, or modify any play-caller assignment;
alter PAE, Q, PCAE, CallValue, or Scheme; fit Models 1–6; select weights or shrinkage; create a
ranking or 0–100 score; change a production surface; begin Phase II; or implement Ask Anything.

The review asks whether a count of 256 fully verified team-season cells is the right prerequisite
for *researching* a final architecture. It separately asks what would be required before production
publication. Those are not the same decision.

## Origin of the 50% gate

The rule first appears as a minimum rerun condition in the independent Prompt 7 adversarial review:
at least 50% verified play-caller cells, at least five chronological target folds, at least 150
common future Q/P rows, and stable signs under season, coach, team, and QB resampling. The review's
roadmap then encoded the phrase “at least 50% verified cells” without deriving 256 from an effect
size, variance, power target, confidence-interval width, missing-data model, or fold requirement.

Prompt 7 did include a separate Fisher-z power illustration: approximately 194 independent rows for
correlation 0.20, 85 for 0.30, and 47 for 0.40 at two-sided alpha 0.05 and 80% power. It explicitly
warned that clustered NFL observations require more data. Nothing in that calculation maps 50% of
512 inventory cells to those effective sample sizes. The 50% rule was therefore a prudent
**heuristic research safeguard against sparse and selected coverage**, not a statistically derived
power threshold or an engineering limitation. This review does not retrofit a rationale that was
not present.

## Which denominator measures identifiability?

| Denominator | Result | Direct methodological meaning |
|---|---:|---|
| Complete inventory | 512 team-season cells | Coverage universe; not an estimation sample |
| Fully verified cells | 205 / 512 (40.04%) | Complete regular-season continuity |
| Partial cells with usable verified intervals | 36 / 37 partial cells | Valid bounded evidence without full-cell promotion |
| Source-backed bounded intervals | 291 | Includes four shared intervals that cannot be individually attributed |
| Individually attributable intervals | 287 | Direct interval units supporting PCAE |
| Verified attributable plays | 226,266 / 522,300 (43.32%) | Play-weighted support across 2010–2025 |
| Recent fully verified cells | 180 / 192 (93.75%) | Primary-window inventory coverage, 2020–2025 |
| Recent attributable plays | 189,353 / 200,066 (94.65%) | Primary-window play-weighted support |
| Common Q/P coach-seasons | 269 | Direct joint-signal rows |
| Common future Q/P rows | 165 | Rows with strictly prior caller history |
| Credible target folds | 5 / 6 | Independent temporal replication under the reviewed rule |

The full 512-cell denominator is important for describing historical completeness and selection
bias. It is not the denominator most directly tied to joint Q/P identifiability. Bounded verified
intervals, attributable plays, common coach-season rows, repeated callers, portable transitions,
and credible chronological folds are more direct.

Partial never means verified. Of the 37 partial cells, 36 contain at least one individually usable
verified interval. Those cells contribute 39 non-shared intervals and 19,617 attributed plays.
One partial cell has only non-individually-attributable shared evidence. The 205 full cells yield 199
cells with PCAE, 248 non-shared intervals, and 206,649 plays; six full cells have no joined usable
PCAE for the current Q/P contract. Provisional, unresolved, and shared intervals contribute zero
individual PCAE.

## Era coverage and sample contribution

| Era | Full cells | Partial | Usable cells/intervals | Play coverage | Q rows/QB obs | Common Q/P | Repeat callers | Future Q/P |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2010–2014 | 13 / 160 (8.13%) | 1 | 8 / 10 | 7,235 / 161,656 (4.48%) | 7 / 12 | 7 | 0 | 0 |
| 2015–2019 | 12 / 160 (7.50%) | 31 | 43 / 56 | 29,678 / 160,578 (18.48%) | 56 / 85 | 56 | 7 | 11 |
| 2020–2022 | 84 / 96 (87.50%) | 5 | 88 / 111 | 89,369 / 100,082 (89.30%) | 102 / 180 | 102 | 30 | 68 |
| 2023–2025 | 96 / 96 (100.00%) | 0 | 96 / 110 | 99,984 / 99,984 (100.00%) | 104 / 199 | 104 | 31 | 86 |

2010–2019 contributes 63 of 269 common Q/P rows (23.42%) but only 11 of 165 future rows
(6.67%). All 11 come from 2015–2019; 2010–2014 contributes no row with usable prior caller
history. The 2020–2025 period contributes 206 common rows (76.58%) and 154 future rows (93.33%).

Older data remain useful as secondary history, robustness evidence, and a warning about archival
selection. They do not supply final target folds. The 11 older future rows make up all of 2020's
available training set and remain in every later fold, but 2020 itself fails the stricter fold
credibility rule. The final architecture research should therefore use 2020–2025 as the primary
analysis window and 2010–2019 only as explicitly labeled secondary evidence.

## Missing-not-at-random and sample-composition audit

Verification is demonstrably not missing at random.

- Era dominates: full-cell rates are 8.13% and 7.50% in the two pre-2020 eras, versus 87.50% and
  100% after 2020.
- Team rates range from 25.00% to 62.50%, consistent with unequal archive availability.
- An observed repeated-name/prominence proxy is strongly selected: 194 of 230 cells with a caller
  name recurring elsewhere are verified (84.35%), versus 11 of 282 without that observed proxy
  (3.90%). This is partly a measurement fact—unresolved identities cannot be recognized as
  repeated—and is not treated as a causal predictor.
- In Prompt 10's bounded source sample, current official-team sources yielded verified cells in 16
  of 21 linked cells (76.19%), compared with 2 of 8 official-team archive cells (25.00%) and 1 of
  31 major-reporting cells (3.23%). Linked cells can appear in multiple source-family groups.
- Prompt 10's observed full-verification yields were 14/28 highly recoverable, 5/27 possibly
  recoverable, 2/15 archival/expensive, and 0/5 known shared/ambiguous. These labels describe the
  evidence process; they are not outcomes and were not used to promote cells.
- HC and OC continuity have comparatively small verified/non-verified differences. Supporting-role
  assignment counts are also much less imbalanced than season or observed caller-name availability.

Standardized differences reinforce the era selection. Mean season is 2021.57 for verified cells,
2017.30 for partial, 2017.91 for provisional, and 2014.29 for unresolved; the corresponding
verified-versus-other standardized differences are 1.62, 1.06, and 2.29. The observed repeat-name
proxy is also severely imbalanced. It is excluded from the propensity model because identity
availability is too close to the observation process itself.

Outcome fields were inspected only as diagnostics and never used to assign verification. The
verified sample is not monotonically the “best offense” sample:

- win percentage is 0.499 verified, 0.478 partial, 0.511 provisional, and 0.504 unresolved;
- offensive EPA/play is 0.005 verified, -0.020 partial, 0.002 provisional, and 0.001 unresolved;
- pass EPA/dropback is 0.050 verified, 0.029 partial, 0.042 provisional, and 0.063 unresolved;
- team QB PAE is -0.0188 verified, -0.0337 partial, -0.0230 provisional, and +0.0038 unresolved.

The largest of these outcome standardized differences is approximately 0.305 (partial versus
verified offensive EPA/play); unresolved versus verified team QB PAE is approximately -0.212.
These are real selection warnings, but they do not show that verification was awarded for favorable
outcomes.

## Inverse-probability sensitivity

A diagnostic L2-logistic verification propensity used only season, team, era, supporting-role
counts, and HC/OC continuity. It used no offensive outcome, PAE, Q, PCAE, or evidence-acceptance
result beyond the binary response. Its AUC is 0.971 because era separation is extreme. Overall
predicted propensity falls to 0.00169; the minimum among common Q/P rows is 0.00615. The maximum
raw stabilized weight is 236.6, so weights were capped at 10. The weighted effective sample falls
from 269 to 61.2 rows.

The sensitivity does not overturn the descriptive signals: common Q/P Pearson changes from 0.069
to 0.060, Spearman from 0.027 to 0.027, Q repeatability from -0.004 to 0.021, and P repeatability
from 0.380 to 0.363. Because positivity/overlap is poor and clipping is material, this is an
**unreliable extrapolation and sensitivity diagnostic only**, not an identification correction or
an argument that the full historical sample has become representative.

## Missing-data stress test

No identity or PCAE was imputed. The stress test asks how many hypothetical unit-negative
standardized pair-products would be needed to bring an observed positive cross-product average to
zero, and how many all-mismatch pairs would lower same-direction agreement to 50%.

| Signal/subset | Pairs | Pearson | Same direction | Negative products to non-positive | Mismatches to ≤50% |
|---|---:|---:|---:|---:|---:|
| Q, all consecutive | 113 | -0.004 | 53.10% | 0 | 8 |
| Q, different QB | 96 | -0.003 | 53.13% | 0 | 6 |
| Q, different team | 19 | 0.012 | 63.16% | 1 | 5 |
| P, all consecutive | 113 | 0.380 | 61.06% | 43 | 25 |
| P, different QB | 96 | 0.372 | 59.38% | 36 | 18 |
| P, different team | 19 | 0.401 | 52.63% | 8 | 1 |

P repeatability across all and different-QB pairs requires a substantial block of adverse omitted
relationships to erase the correlation, while direction agreement is less robust. Different-team
portability remains fragile because only 19 full-window and 17 recent pairs exist; one additional
sign mismatch removes its direction majority. Q is already centered near zero, so no missing-data
argument is needed to overturn a positive Q-repeatability claim. These bounds support another
architecture study, not a production effect claim.

## Temporal-window and leave-era-out sensitivity

| Window | Common rows | Coaches | Pairs | Diff-QB | Diff-team | Q/P r | Q repeat r | P repeat r | P diff-QB r | P diff-team r |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2010–2025 | 269 | 104 | 113 | 96 | 19 | 0.069 | -0.004 | 0.380 | 0.372 | 0.401 |
| 2016–2025 | 259 | 100 | 113 | 96 | 19 | 0.078 | -0.004 | 0.380 | 0.372 | 0.401 |
| 2020–2025 | 206 | 81 | 107 | 92 | 17 | 0.096 | -0.018 | 0.399 | 0.370 | 0.385 |
| 2021–2025 | 172 | 73 | 84 | 72 | 15 | 0.057 | 0.027 | 0.431 | 0.409 | 0.270 |

The 2021–2025 window is viable as a short-window sensitivity but not a replacement for the
six-season primary window. P repeatability remains positive and similar across all windows. Q
repeatability stays near zero and changes sign around zero. Common Q/P association is small. The
different-team P coefficient remains positive but changes materially in magnitude and is based on
only 15–19 pairs.

| Exclusion | Common rows | Pairs | Q/P r | Q repeat r | P repeat r | P diff-team r |
|---|---:|---:|---:|---:|---:|---:|
| Leave 2010–2014 out | 262 | 113 | 0.077 | -0.004 | 0.380 | 0.401 |
| Leave 2015–2019 out | 213 | 107 | 0.087 | -0.018 | 0.399 | 0.385 |
| Leave all 2010–2019 out | 206 | 107 | 0.096 | -0.018 | 0.399 | 0.385 |

No core sign changes materially when older eras are removed: P repeatability stays positive near
0.38–0.40, Q stays effectively zero, and Q/P stays small positive. The magnitude of thin
different-team portability remains too unstable for a definitive claim.

## Six-fold quality audit

The Prompt 7 gate called all six 2020–2025 folds eligible using at least two targets and ten prior
rows. Prompt 11 independently applies a credibility screen of at least 20 target rows, at least 20
strictly prior training rows, and at least 80% target-season attributable-play coverage.

| Target | Target rows | Prior training | Callers | Teams | QB obs | Play coverage | Training 2010–14 / 2015–19 / 2020+ | Credible |
|---:|---:|---:|---:|---:|---:|---:|---:|:---:|
| 2020 | 18 | 11 | 18 | 16 | 31 | 88.91% | 0 / 11 / 0 | No |
| 2021 | 27 | 29 | 27 | 24 | 45 | 85.07% | 0 / 11 / 18 | Yes |
| 2022 | 23 | 56 | 23 | 22 | 46 | 93.93% | 0 / 11 / 45 | Yes |
| 2023 | 27 | 79 | 27 | 25 | 51 | 100.00% | 0 / 11 / 68 | Yes |
| 2024 | 30 | 106 | 30 | 27 | 61 | 100.00% | 0 / 11 / 95 | Yes |
| 2025 | 29 | 136 | 29 | 28 | 55 | 100.00% | 0 / 11 / 125 | Yes |

The 2020 fold is not credible for architecture selection: 18 targets and 11 prior rows are below
the independent 20/20 screen, even though play coverage passes. It may be reported as a sparse
sensitivity fold. The effective credible fold count is five, covering 136 target rows. The 2021
fold is the weakest accepted fold because its training set still contains only 29 rows and its
play coverage is 85.07%; it must be shown separately rather than hidden inside an average.

## Cluster-aware sample size and precision

The 165 future rows contain 66 coaches, 32 teams, 106 individual QBs under multi-membership, and
nine seasons. One-way ICC design-effect diagnostics reduce the 165 raw rows to approximately:

- P: 100.4 by coach, 123.5 by team, 162.8 by QB multi-membership, and 165 by season;
- Q: 165 by coach/team, 148.8 by QB multi-membership, and 138.4 by season.

Thus 165 rows are enough to study a moderate architecture signal: the conservative P effective
count exceeds Prompt 7's independent-row illustration of 85 for correlation 0.30. It is not enough
to guarantee detection of correlation 0.20, which required about 194 independent rows even before
clustering. “Sufficient” here means **sufficient for a preregistered exploratory architecture
rerun with cluster uncertainty and suppression**, not for production ranking or small-effect
precision.

Five recent-window diagnostics were resampled 500 times independently by coach, team, season, and
individual-QB membership. All 10,000 requested draws succeeded. For recent P repeatability
(r=0.399), every cluster scheme's 95% percentile interval excludes zero: coach [0.174, 0.552], team
[0.164, 0.574], season [0.349, 0.470], and QB [0.256, 0.499]. Recent different-QB P repeatability
(r=0.370) also remains positive under all four schemes. Different-team P portability (r=0.385)
has a coach-cluster interval crossing zero [-0.124, 0.737], confirming fragility.

Recent Q repeatability is -0.018; all four intervals include zero. Common Q/P correlation is 0.096;
coach, team, and season intervals include zero, while the QB-membership interval narrowly excludes
zero. No final weight follows from these results.

## Candidate gate systems

### System A — original raw full-cell threshold

Requirement: 256/512 fully verified cells. Result: **FAIL, 205/512**. This system is conservative
but insensitive to interval evidence, play volume, era concentration, actual common Q/P rows,
fold history, and cluster structure. It also cannot be reached by the Prompt 10 public-evidence
ceiling estimate without weakening verification.

### System B — effective sample and recent coverage

Predefined requirements and results:

- recent full-cell coverage at least 90%: 93.75%, pass;
- recent attributable-play coverage at least 90%: 94.65%, pass;
- at least five credible folds, each with 20 targets, 20 prior rows, and 80% play coverage: five,
  pass;
- at least 150 total future rows: 165, pass;
- at least 125 target rows across credible folds: 136, pass;
- at least 50 repeated recent callers: 52, pass;
- at least 475/500 successful draws for every requested cluster bootstrap: 500/500, pass.

System B result: **PASS**.

### System C — model-specific, no global raw threshold

System C retains all System B coverage/fold safeguards and requires the actual relevant structures:

- at least 150 recent common Q/P rows: 206, pass;
- at least 75 recent consecutive pairs: 107, pass;
- at least 60 recent different-QB pairs: 92, pass;
- at least 15 recent different-team pairs: 17, pass but thin;
- at least five credible folds and 125 credible target rows: 5 and 136, pass;
- at least 475/500 successful draws for each cluster design: 500/500, pass.

System C result: **PASS**. A thin or unstable sub-signal is studied and then suppressed; the gate
does not require a desired correlation sign. The tests explicitly reverse the observed signal signs
and confirm the gate result is unchanged. This prevents retrospective threshold fitting.

### Separate production system

Production publication should require at least 95% full-cell and 95% attributable-play coverage
within every claimed analysis window, zero individual attribution of provisional/shared duties,
and model-specific out-of-sample, cluster, uncertainty, and per-coach eligibility rules. The present
2020–2025 evidence is 93.75% by cell and 94.65% by play, so this preliminary production coverage
screen **fails** before any model is considered. A 50% all-history gate would be too weak for public
ranking and should not be retained as the production rule.

## Decision

**ORIGINAL 50% GATE DECISION: REPLACE 50% GATE.**

The original rule was an honest conservative heuristic, but it measures the wrong denominator for
research identifiability and disproportionately penalizes sparse archival eras that provide only
6.67% of future rows. Replace it with System C: a model-specific research gate anchored to recent
coverage, attributable plays, common Q/P rows, transitions, credible folds, cluster resampling, and
mandatory missingness sensitivity.

**FINAL EQUATION RESEARCH RERUN: GO after this methodology is approved.** Entry criteria are:

1. primary analysis fixed to 2020–2025; 2010–2019 secondary only;
2. full-cell and play-weighted recent coverage each at least 90%;
3. at least five credible chronological target folds using the 20-target/20-prior/80%-play rule;
4. at least 150 total future rows and 125 rows across credible target folds;
5. at least 150 recent common rows, 75 consecutive pairs, 60 different-QB pairs, 15 different-team
   pairs, and 50 repeat callers;
6. at least 475/500 successful resamples in every coach/team/season/QB cluster design;
7. all coefficients, interval widths, signs, missingness/IPW sensitivity, and thin portability
   results reported without selecting a specification for attractiveness;
8. unstable components suppressed rather than rescued by changing thresholds.

These thresholds are design and replication requirements declared before the final equation run.
They are not fitted to the observed Q/P signs; gate evaluation does not inspect sign direction.

The role-specific research readiness is:

- **Head coach:** Q-component architecture research may proceed; play-caller missingness is not its
  prerequisite. No production ranking is authorized.
- **Offensive coordinator:** Q-component architecture research may proceed. Production remains
  blocked until coordinator assignments are comprehensively verified.
- **Quarterbacks coach:** Q-component architecture research may proceed. Production remains blocked
  until QB-coach assignments are comprehensively verified.
- **Play caller:** 2020–2025 architecture research may proceed with explicit verified/bounded
  attribution and the restrictions above. Full-history claims and production rankings remain
  blocked; different-team portability must remain exploratory unless precision improves.

No further **broad** play-caller evidence collection is recommended. If production publication is
later pursued, only targeted work on the 12 non-full recent cells and the 10,713 recent unattributed
plays is justified; verification standards must not be weakened.

## Reproducibility and outputs

The Prompt 11 identity hashes the frozen Prompt 10 manifest and core tables, Prompt 7/10 methods,
this Prompt 11 code, the source audit, team/Pae diagnostics, all 2010–2025 PBP inputs used for
eligible-play denominators, the gate policies, random seed, bootstrap count, and NumPy, Polars,
SciPy, and scikit-learn versions. Generated files are research-only, non-ranking artifacts in the
ignored `research/coach_effect/outputs/checkpoint_12_coverage_gate_review/` tree.

Deterministic outputs are:

- `coverage_denominator_comparison.csv`
- `verified_interval_coverage.csv`
- `play_weighted_coverage.csv`
- `era_coverage.csv`
- `missingness_diagnostics.csv`
- `selection_bias_diagnostics.csv`
- `inverse_probability_sensitivity.csv`
- `missing_data_stress_test.csv`
- `temporal_window_sensitivity.csv`
- `leave_era_out_results.csv`
- `fold_quality_analysis.csv`
- `cluster_aware_precision.csv`
- `candidate_gate_comparison.csv`
- `final_methodology_decision.csv`
- `MANIFEST.json`

Focused Prompt 11 tests cover full-cell and interval coverage, partial inclusion, play weighting,
no provisional/unresolved/shared attribution, temporal windows, leave-era-out logic, fold history,
cluster-resampling determinism, gate evaluation independent of observed signs, research-only
contracts, and two independent byte-identical builds.

Validation completed with:

- 72/72 offline Prompt 6–11 tests passing, including 15 Prompt 11 tests;
- 3/3 explicitly enabled Prompt 8–10 network source-content tests passing;
- zero skips in either invoked regression set;
- Ruff passing repository-wide;
- all 124 Ruff-formatted Python files passing the formatting check;
- Python compilation passing for `src`, `research`, `scripts`, and `tests`;
- `git diff --check` passing;
- two independent empty-directory Prompt 11 builds producing the same content identity and
  byte-identical manifest and CSV artifacts.

No final Coach Effect equation, weight, shrinkage method, confidence mapping, score, or ranking was
implemented. Nothing was committed, pushed, or deployed. Phase II and Ask Anything were not
started.
