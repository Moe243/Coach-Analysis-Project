# Checkpoint Twelve — Prompt 10 Final Play-Caller Evidence Sprint

Date: 2026-09-08
Production baseline: `3024ede03de9926a9fd96f98308e3cf9fd4d83c3`
Prompt 6 baseline: `c12-8cd15ae6015e900b`
Prompt 7 baseline: `c12-review-7897e3d57dd8b22a`
Prompt 8 baseline: `c12-data-250e540b7de79385`
Prompt 9 baseline: `c12-pc-2cf75b19b3c42914`
Prompt 10 research version: `c12-pc-final-cac923f086757e5b`
Decision: **STOP HISTORICAL VERIFICATION — EVIDENCE CEILING REACHED**
Readiness: **NOT READY — ONLY RAW COVERAGE GATE REMAINS**

## Scope and hard boundaries

This was the final bounded public-source play-caller evidence sprint. It researched all 28 highly
recoverable cells, all 27 possibly recoverable cells, the five known shared/ambiguous cells, and
15 statistically prioritized archival/expensive cells. It did not attempt the other 173 archival
cells after the observed yield established that the 50% gate was not realistically attainable
with reasonable public-source effort.

The sprint did not alter PAE, Q, the PCAE model or formula, CallValue, verification semantics, or
Scheme methodology. It did not infer that a head coach or offensive coordinator called plays.
It did not fit Coach Effect, select weights or shrinkage, create a ranking or 0–100 score, begin
Phase II, implement Ask Anything, or touch frontend, production database, API, or deployment.
Generated artifacts remain research-only under the Git-ignored
`research/coach_effect/outputs/checkpoint_12_final_play_caller_evidence/` directory.

## Search order and stop logic

The first five cells were the specified smallest high-value set: Indianapolis 2021, Denver 2021,
New Orleans 2022, Indianapolis 2020, and Tennessee 2022. Their verification increased common
future Q/P rows from 144 to 150 while preserving five chronological target folds. The rest of the
28-cell high tier was then completed. Because Gate A still failed, all 27 possibly recoverable
cells were reviewed, followed by five known shared/ambiguous cases and 15 archival cases ordered
for PCAE volume and repeated-caller value.

Readiness was rebuilt at 5, 15, 28, 40, 55, 65, and 75 reviews. The statistical sample gates
passed, but raw coverage never did, so the all-gates early-stop condition was never reached.

| Reviews | Verified | PCAE plays | Common Q/P | Future common | Folds |
|---:|---:|---:|---:|---:|---:|
| 5 | 189 | 208,073 | 248 | 150 | 5 |
| 15 | 196 | 216,169 | 257 | 153 | 5 |
| 28 | 198 | 217,457 | 260 | 156 | 5 |
| 40 | 198 | 217,457 | 260 | 156 | 5 |
| 55 | 203 | 221,033 | 267 | 162 | 5 |
| 65 | 204 | 222,977 | 268 | 163 | 6 |
| 75 | 205 | 226,266 | 269 | 165 | 6 |

## Evidence standard and source audit

A fully verified cell requires explicit actual in-game offensive caller identity and defensible
continuity across the complete regular-season interval. Evidence may be cumulative across strong
sources; a strong retrospective can be sufficient by itself. Point-in-time or game-specific
evidence remains bounded. Silence does not prove continuity. Shared duties remain shared and are
excluded from individual PCAE attribution.

The 35 structured source records comprise 20 current official-team sources, eight official-team
archive records, four NFL reporting records, and three major-reporting records. No Wayback capture
was needed, so explicit `archive_url` usage is zero. Reused evidence retains one source identity;
the 2017 ESPN all-team analysis is referenced by each applicable team cell but counted once in the
source-family distribution.

Important conservative decisions include:

- Denver 2021 is split into Pat Shurmur Weeks 1–9, Mike Shula Week 10, and Shurmur Weeks 11–18.
- Las Vegas 2021 is split into Jon Gruden Weeks 1–5 and Greg Olson Weeks 6–18.
- New York Giants 2021 is split into Jason Garrett Weeks 1–11 and Freddie Kitchens Weeks 12–18.
- New York Giants 2020 preserves the one-game Freddie Kitchens Week 15 exception between Jason
  Garrett intervals.
- Houston 2020 remains partial: Tim Kelly Weeks 1–3 are verified; Kelly and Bill O'Brien are shared
  in Week 4; Kelly Weeks 5–17 remain provisional. Only Weeks 1–3 are individually attributable.
- Philadelphia 2020 remains provisional. December first-person evidence says play-calling had
  recently been shared, and a final-game article does not establish uninterrupted continuity.
- Philadelphia 2021 and Pittsburgh 2021 remain provisional because the available evidence does
  not resolve exact transitions or shared quarterback autonomy.
- The 2017 all-team evidence is bounded through Week 10 rather than extended through the remaining
  games. The New York Giants transition is explicitly split at Week 6.
- New Orleans 2016 is partial for Pete Carmichael Jr. Weeks 1–10; Houston 2013 is partial for Rick
  Dennison Week 10. No unsupported surrounding weeks were inferred.
- The five already proven shared/ambiguous cells remain below full verification.

## Completeness result

| Status | Starting | Ending | Change |
|---|---:|---:|---:|
| Verified | 184 | 205 | +21 |
| Partial | 4 | 37 | +33 |
| Provisional | 56 | 11 | -45 |
| Unresolved | 268 | 259 | -9 |
| Total | 512 | 512 | 0 |

Final fully verified coverage is **40.04%**. Nineteen provisional cells and two unresolved cells
became verified. The 21 newly verified cells contain 27 verified assignment intervals. Thirty-one
provisional cells and two unresolved cells became partial without being over-promoted. Two new
shared intervals preserve Houston's Week 4 ambiguity.

New full-cell verifications are: IND 2021, DEN 2021, NO 2022, IND 2020, TEN 2022, LV 2021,
NYJ 2022, NYG 2021, NYJ 2021, PIT 2020, HOU 2022, MIA 2020, NYG 2020, CAR 2022, CLE 2020,
TEN 2021, ARI 2022, CLE 2022, PIT 2022, DEN 2013, and BUF 2013.

| Season | Verified | Partial | Provisional | Unresolved |
|---:|---:|---:|---:|---:|
| 2010 | 4 | 0 | 0 | 28 |
| 2011 | 3 | 0 | 0 | 29 |
| 2012 | 3 | 0 | 1 | 28 |
| 2013 | 3 | 1 | 1 | 27 |
| 2014 | 0 | 0 | 1 | 31 |
| 2015 | 1 | 1 | 1 | 29 |
| 2016 | 4 | 1 | 0 | 27 |
| 2017 | 3 | 29 | 0 | 0 |
| 2018 | 4 | 0 | 1 | 27 |
| 2019 | 0 | 0 | 0 | 32 |
| 2020 | 27 | 3 | 2 | 0 |
| 2021 | 27 | 1 | 3 | 1 |
| 2022 | 30 | 1 | 1 | 0 |
| 2023 | 32 | 0 | 0 | 0 |
| 2024 | 32 | 0 | 0 | 0 |
| 2025 | 32 | 0 | 0 | 0 |

## Coverage by era and missingness

| Era | Verified | Cells | Verified coverage |
|---|---:|---:|---:|
| 2010–2014 | 13 | 160 | 8.13% |
| 2015–2019 | 12 | 160 | 7.50% |
| 2020–2022 | 84 | 96 | 87.50% |
| 2023–2025 | 96 | 96 | 100.00% |

Missingness is overwhelmingly an older-era public-evidence problem: 295 of the 307 remaining
non-verified cells are in 2010–2019. Team archive availability varies materially. Repeated and
prominent callers are easier to corroborate than one-off or unidentified callers, so the verified
sample is not missing at random. Offensive quality was never used to accept evidence and was not
used to manufacture a verification-bias correction. Later official archives are systematically
more complete, which limits historical representativeness even though the post-2020 statistical
sample is strong.

The remaining 307 cells comprise 36 researched-and-exhausted high/possible cases, 13 researched
archival cases, five known shared/ambiguous cases, 173 unresearched archival/expensive cases, and
80 likely unresolvable cases. No highly or possibly recoverable cell remains unresearched.

## PCAE and common Q/P refresh

The PCAE method is unchanged. Only newly available, source-backed, verified, non-shared intervals
were added; provisional and shared intervals were excluded. Missing attribution stays missing,
not zero.

| Season | PCAE-attributed plays |
|---:|---:|
| 2010 | 1,000 |
| 2011 | 1,016 |
| 2012 | 1,978 |
| 2013 | 3,241 |
| 2014 | 0 |
| 2015 | 1,470 |
| 2016 | 4,713 |
| 2017 | 19,606 |
| 2018 | 3,889 |
| 2019 | 0 |
| 2020 | 28,847 |
| 2021 | 28,911 |
| 2022 | 31,611 |
| 2023 | 33,836 |
| 2024 | 33,335 |
| 2025 | 32,813 |

Total PCAE-attributed plays are **226,266**. The final common set contains 269 Q/P coach-seasons,
165 future target rows, 66 repeat play callers, 113 consecutive caller pairs, 96 different-QB
samples, and 19 different-team samples. Prompt 10 added 21 common future rows over Prompt 9.

The six eligible chronological target seasons and their strictly prior training rows are:

| Target | Future target rows | Prior training rows |
|---:|---:|---:|
| 2020 | 18 | 11 |
| 2021 | 27 | 29 |
| 2022 | 23 | 56 |
| 2023 | 27 | 79 |
| 2024 | 30 | 106 |
| 2025 | 29 | 136 |

Resampling feasibility passes with 12 seasons, 104 coaches, 32 teams, and 476 quarterback
observations in the common Q/P structure.

## Final gates and evidence ceiling

| Gate | Threshold | Observed | Result |
|---|---:|---:|:---:|
| A — verified caller coverage | at least 256/512 | 205 | **FAIL** |
| B — chronological target folds | at least 5 | 6 | **PASS** |
| C — common future Q/P rows | at least 150 | 165 | **PASS** |
| D — resampling feasibility | season/coach/team/QB minimums | 12 / 104 / 32 / 476 | **PASS** |

**FINAL COACH EFFECT RERUN READINESS: NOT READY.** The only remaining blocker is Gate A: 51 more
fully verified cells are required. The common-future statistical structure otherwise satisfies
the Prompt 7 research requirements. The gate is not waived.

The highest-value archival sample produced two full verifications from 15 reviews. Discounting
that 13.33% yield to 70% for declining source access across the remaining 173 archival cells gives
an estimated 16 additional reasonably attainable cells and a defensible public-evidence ceiling
of approximately **221 verified cells (43.16%)**. This is a transparent stop-loss heuristic, not a
claim that verification beyond 221 is logically impossible. It indicates that reaching 256 would
likely require inaccessible, proprietary, or substantially more expensive archival evidence.
Accordingly, the recommendation is **STOP HISTORICAL VERIFICATION — EVIDENCE CEILING REACHED**.

## Determinism and validation

The content identity hashes both Prompt 10 ledgers, Prompt 10/9/8 source code, the frozen Prompt 9
manifest and analytical inputs, relevant PBP inputs, unchanged PCAE method constants, gate and
selection policies, snapshot cutoffs, evidence-ceiling method, and NumPy, Polars, SciPy, and
scikit-learn versions. Each deterministic CSV carries `research_only=true` and
`production_ranking=false`. Publishing is atomic and source bytes are revalidated before and after
the write.

Validation completed with 119/119 offline Prompt 6–10, Checkpoint Eleven/Eleven-B,
coaching-assignment, and PCAE regression tests passing; 4/4 explicitly enabled network suites
passing; the coaching validator passing on 1,639 assignments and 1,673 citations; Ruff, Python
formatting, compilation, and whitespace checks passing; and zero skips in the invoked suites. The
Prompt 10 clean-build regression rebuilt two independent empty directories and found every CSV
and manifest byte-identical with the same content version.
