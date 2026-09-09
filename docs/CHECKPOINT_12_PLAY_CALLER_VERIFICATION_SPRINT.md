# Checkpoint Twelve — Prompt 9 Play-Caller Verification Sprint

Date: 2026-09-08
Production baseline: `3024ede03de9926a9fd96f98308e3cf9fd4d83c3`
Prompt 6 baseline: `c12-8cd15ae6015e900b`
Prompt 7 baseline: `c12-review-7897e3d57dd8b22a`
Prompt 8 baseline: `c12-data-250e540b7de79385`
Prompt 9 research version: `c12-pc-2cf75b19b3c42914`
Decision: **FINAL COACH EFFECT RERUN NOT READY**

## Scope and boundaries

This was a bounded historical evidence-recovery sprint. It did not change PAE, Q, PCAE,
CallValue, Scheme methodology, production data, models, database state, API, frontend, or
deployment. It did not fit a final Coach Effect equation, select Q/P weights or shrinkage, create
a score/ranking, begin Phase II, or implement Ask Anything. Generated artifacts remain under the
Git-ignored `research/coach_effect/outputs/checkpoint_12_play_caller_verification/` tree.

## Research process

The first batch audited the ten cells mandated by Prompt 9. After that batch, the frozen Prompt 8
queue was recalculated with a deterministic lexicographic policy:

1. direct common-Q/P or future-history value;
2. repeat-caller, consecutive-season, and team-transition value;
3. PCAE-eligible play volume;
4. coverage-only value.

Within those tiers, cells with an identified candidate and stronger frozen Prompt 8 priority were
favored over unidentified archival work. The 40 dynamic cells are exactly ranks 1–40 under the
recalculated policy. The three batch cutoffs were 10, 30, and 50 researched cells. Availability,
folds, histories, and readiness were rebuilt at every cutoff; no model or equation was fit.

## Verification standard and evidence

`VERIFIED` requires explicit play-calling identity, defensible regular-season week bounds,
continuity or source-bounded transitions, and no unresolved contradiction. Head-coach or
coordinator title alone never qualifies. `PARTIAL` retains only the proven intervals.
`PROVISIONAL` preserves a plausible identity when continuity is not established. Explicit shared
duty remains shared and is excluded from individual PCAE.

Every one of the 50 researched team-season cells has a structured audit record with candidate,
starting/ending status, source URL/title/publisher/date/family, locator, paraphrase, week bounds,
proof flags, contradiction field, notes, recoverability, and disposition. The 65 interval records
use 45 official-team, 17 NFL-league, and three major-reporting primary records (57 unique primary
URLs). Corroborating URLs remain attached to the same audit rows.

Representative high-risk decisions include:

- Chicago 2021 is split into Matt Nagy Weeks 1–3, Bill Lazor Weeks 4–14, Nagy Week 15, and Lazor
  Weeks 16–18; the official return evidence preserves the COVID exception rather than flattening
  the year ([Chicago Bears](https://www.chicagobears.com/news/5-things-we-learned-from-bears-coordinators-robert-quinn-roquan-smith)).
- Jacksonville 2022 is `PARTIAL`: Doug Pederson and Press Taylor are stored as shared because the
  source describes a first-half/second-half division that does not support individual play
  attribution ([NFL](https://www.nfl.com/news/jaguars-oc-press-taylor-to-debut-as-new-full-time-play-caller-in-2023)).
- Cleveland 2021 preserves Alex Van Pelt's temporary Week 15 assignment between Kevin Stefanski
  intervals ([Cleveland Browns](https://www.clevelandbrowns.com/news/kevin-stefanski-tests-positive-for-covid-19-will-continue-to-coach-virtually)).
- Detroit 2020 preserves Sean Ryan's one-game Week 16 replacement and Bevell's return rather than
  assigning the whole season to one person ([Detroit Lions](https://www.detroitlions.com/news/lions-shuffle-coaching-staff-ahead-of-saturday-s-game-bevell-prince-ryan)).
- Miami 2021 remains provisional/ambiguous for Eric Studesville and George Godsey. The NFL's
  announcement explicitly said the future play-calling split was unclear, so it does not prove
  either person actually held the duty ([NFL](https://www.nfl.com/news/dolphins-naming-eric-studesville-and-george-godsey-as-offensive-co-coordinators)).
- Philadelphia 2020, Indianapolis 2020/2021, Denver 2021, New Orleans 2022, Tennessee 2022, and
  Carolina 2022 remain provisional because the available evidence did not close the complete
  weekly continuity requirement.

The original top-ten results were:

| Priority | Cell | Result |
|---:|---|---|
| 1 | CHI 2021 — Matt Nagy | VERIFIED with four bounded intervals |
| 2 | ARI 2020 — Kliff Kingsbury | VERIFIED |
| 3 | ATL 2020 — Dirk Koetter | VERIFIED |
| 4 | JAX 2022 — Doug Pederson | PARTIAL / SHARED |
| 5 | WAS 2021 — Scott Turner | VERIFIED |
| 6 | PHI 2020 — Doug Pederson | PROVISIONAL |
| 7 | LV 2022 — Josh McDaniels | VERIFIED |
| 8 | GB 2021 — Matt LaFleur | VERIFIED |
| 9 | LA 2021 — Sean McVay | VERIFIED |
| 10 | GB 2022 — Matt LaFleur | VERIFIED |

Nine of ten were resolved to verified or partial; Philadelphia remained provisional.

## Coverage result

| Status | Starting | Ending | Change |
|---|---:|---:|---:|
| Verified | 144 | 184 | +40 |
| Partial | 2 | 4 | +2 |
| Provisional | 98 | 56 | -42 |
| Unresolved | 268 | 268 | 0 |
| Total | 512 | 512 | 0 |

Final fully verified coverage is **35.94%**. The sprint accepted 55 new verified assignment
intervals across the 40 newly verified cells and two newly partial cells. Two shared intervals
cover one shared-duty cell. Seven team-season cases preserve new in-season transitions: CHI 2020,
CHI 2021, CLE 2021, NO 2021, JAX 2021, DET 2020, and NYJ 2020.

Historical fully verified cells by season are:

| Season | Verified cells | Season | Verified cells |
|---:|---:|---:|---:|
| 2010 | 4 | 2018 | 4 |
| 2011 | 3 | 2019 | 0 |
| 2012 | 3 | 2020 | 22 |
| 2013 | 1 | 2021 | 21 |
| 2014 | 0 | 2022 | 22 |
| 2015 | 1 | 2023 | 32 |
| 2016 | 4 | 2024 | 32 |
| 2017 | 3 | 2025 | 32 |

## PCAE attribution availability

PCAE methodology is unchanged. The same strictly historical expected-call models were regenerated
only where the newly verified intervals required them. Provisional and unresolved intervals were
excluded. Shared Jacksonville 2022 was excluded from individual PCAE; provisional/ambiguous Miami
2021 was also excluded.
Missing attribution remained missing rather than zero.

| Season | PCAE-attributed plays |
|---:|---:|
| 2010 | 1,000 |
| 2011 | 1,016 |
| 2012 | 1,978 |
| 2013 | 946 |
| 2014 | 0 |
| 2015 | 1,470 |
| 2016 | 4,101 |
| 2017 | 19,606 |
| 2018 | 3,889 |
| 2019 | 0 |
| 2020 | 23,168 |
| 2021 | 22,593 |
| 2022 | 23,268 |
| 2023 | 33,836 |
| 2024 | 33,335 |
| 2025 | 32,813 |

Total PCAE-attributed plays are **203,019**, a gain of **41,452** over Prompt 8.

## Q/P availability and season readiness

The final availability set contains 242 common Q/P coach-seasons, 144 future common-Q/P target
rows, 59 repeat play callers, 99 consecutive caller pairs, 84 different-QB samples, and 19
different-team samples. Prompt 9 added 44 future common-Q/P rows. The five eligible target seasons
remain 2021–2025.

| Season | Verified | PCAE plays | Q obs. | Common Q/P | Future targets | Prior training | Fold? |
|---:|---:|---:|---:|---:|---:|---:|:---:|
| 2010 | 4 | 1,000 | 0 | 0 | 0 | 0 | No |
| 2011 | 3 | 1,016 | 0 | 0 | 0 | 0 | No |
| 2012 | 3 | 1,978 | 4 | 4 | 0 | 0 | No |
| 2013 | 1 | 946 | 1 | 1 | 0 | 0 | No |
| 2014 | 0 | 0 | 0 | 0 | 0 | 0 | No |
| 2015 | 1 | 1,470 | 3 | 3 | 0 | 0 | No |
| 2016 | 4 | 4,101 | 8 | 8 | 0 | 0 | No |
| 2017 | 3 | 19,606 | 36 | 36 | 6 | 0 | No |
| 2018 | 4 | 3,889 | 8 | 8 | 3 | 6 | No |
| 2019 | 0 | 0 | 0 | 0 | 0 | 9 | No |
| 2020 | 22 | 23,168 | 27 | 27 | 16 | 9 | No |
| 2021 | 21 | 22,593 | 27 | 27 | 19 | 25 | Yes |
| 2022 | 22 | 23,268 | 24 | 24 | 16 | 44 | Yes |
| 2023 | 32 | 33,836 | 35 | 35 | 25 | 60 | Yes |
| 2024 | 32 | 33,335 | 35 | 35 | 30 | 85 | Yes |
| 2025 | 32 | 32,813 | 34 | 34 | 29 | 115 | Yes |

The stage snapshots were:

| Batch | Researched | Verified | Common Q/P | Future common | Folds |
|---|---:|---:|---:|---:|---:|
| Mandatory top ten | 10 | 152 | 205 | 109 | 5 |
| Dynamic batch 1 | 30 | 169 | 224 | 128 | 5 |
| Dynamic batch 2 | 50 | 184 | 242 | 144 | 5 |

## Readiness gates

| Gate | Threshold | Observed | Result |
|---|---:|---:|:---:|
| A — verified caller coverage | at least 256/512 | 184 | **FAIL** |
| B — chronological target folds | at least 5 | 5 | **PASS** |
| C — common future Q/P rows | at least 150 | 144 | **FAIL** |
| D — resampling feasibility | season/coach/team/QB minimums | 12 seasons; 98 coaches; 32 teams; 427 QB observations | **PASS** |

**FINAL COACH EFFECT RERUN READINESS: NOT READY.** The exact shortfalls are 72 additional fully
verified cells and six future common-Q/P rows. Because Gate A dominates, the smallest plausible
closing set is 72 additional full-season verified cells, with at least six chosen from cells that
create common future-Q/P rows.

## Evidence ceiling and next evidence set

The remaining 328 non-verified cells are classified as 28 highly recoverable, 27 possibly
recoverable, 188 archival/expensive, 80 likely unresolvable, and five known shared/ambiguous. The
highest-value open cells begin with IND 2021 (Frank Reich), DEN 2021 (Pat Shurmur), NO 2022 (Pete
Carmichael Jr), IND 2020 (Frank Reich), and TEN 2022 (Todd Downing). Those already received the
bounded Prompt 9 search and were not promoted because continuity remained incomplete.

The next exact evidence set should start with the other high-value identified candidates in the
structured queue—LV 2021, NYJ 2022, PHI 2021, NYG 2021, NYJ 2021, LV 2020, PIT 2020, HOU 2022,
MIA 2020, NE 2022, and NYG 2020—then move through the remaining priority-ranked candidates until
72 verified cells are obtained. At least six must add future common-Q/P rows. This is a targeted
archival set, not another generic all-history sweep. Broad historical research is **not**
recommended; the marginal work now requires weekly releases/media guides and may encounter a
real public-evidence ceiling.

## Determinism and validation

The new version identity hashes the Prompt 9 evidence CSV, Prompt 9 and Prompt 8 code, the frozen
Prompt 8 manifest and analytical inputs, relevant PBP seasons, PCAE method constants, selection
policy, gate values, and dependency versions. Outputs are atomically written and carry explicit
`research_only=true` and `production_ranking=false` fields.

Focused Prompt 9 tests cover the exact matrix, mandatory queue, evidence requirement, canonical
identity, interval overlap, shared duties, in-season transitions, no HC/OC inference, verified-only
PCAE, partial intervals, priority determinism, batch readiness, common Q/P, fold eligibility,
source record completeness, output checksums, and two independent builds. The final validation
completed with 91/91 offline Prompt 6–9, Checkpoint Eleven/Eleven-B, coaching-assignment, and PCAE
regression tests passing; 3/3 explicitly enabled network suites passing; Ruff, Python formatting,
compilation, and whitespace checks passing; and zero skips in the invoked suites. The Prompt 9
clean-build test rebuilt two independent empty directories and found every deterministic artifact
byte-identical with the same version identifier.
