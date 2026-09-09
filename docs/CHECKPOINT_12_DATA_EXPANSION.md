# Checkpoint Twelve — Historical Data Expansion

Date: 2026-09-08
Prompt 6 baseline: `c12-8cd15ae6015e900b`
Prompt 7 review baseline: `c12-review-7897e3d57dd8b22a`
Prompt 8 research version: `c12-data-250e540b7de79385`
Decision: **FINAL EQUATION RERUN NOT READY**

## Scope and boundaries

This is a research-only data expansion. It leaves production models, PAE, CallValue, PCAE,
databases, API, frontend, deployment, and checkpoint outputs unchanged. It fits no final Coach
Effect equation, estimates no Q/P weights, chooses no production shrinkage, creates no ranking or
0–100 score, and begins no Phase II or Ask Anything work. Generated artifacts remain in the
Git-ignored `research/coach_effect/outputs/checkpoint_12_data_expansion/` tree.

## Play-caller evidence

Starting coverage was 119 verified, 1 partial, 125 provisional, and 267 unresolved across the
fixed 512 team-season matrix (23.24% fully verified). Prompt 8 first researched all 25 Prompt 7
priority cells, producing 18 verified, 1 partial, 5 provisional, and 1 unresolved result. Nine
additional high-value cells were then researched after recalculating the remaining-cell priority.

Ending coverage is 144 verified, 2 partial, 98 provisional, and 268 unresolved: 28.13% fully
verified. The increase is 25 team-season cells and 31 verified assignment intervals. Five cells
preserve sourced in-season boundaries: 2021 Arizona, Carolina, and Detroit; 2022 Denver and
Indianapolis. Arizona remains partial because Weeks 7–18 lack independently verified continuity.
Kansas City 2021 remains unresolved/shared: the evidence supports collaborative calling but not a
defensible weekly split for individual attribution.

Primary-source-family distribution across the 40 researched intervals/candidates is 19 official
team, 7 NFL league, 4 official-team/NFL, 4 reputable retrospective, and one each from official
media guide, official-team/reporting, NFL/reporting, NFL retrospective, NFL game
release/reporting, and contemporaneous reporting. Every verified interval has HTTPS lineage and
explicit play-calling evidence; a title alone is rejected.

The regenerated next priorities begin with 2021 Chicago, 2020 Arizona, 2020 Atlanta, 2022
Jacksonville, 2021 Washington, 2020 Philadelphia, 2022 Las Vegas, 2021 Green Bay, 2021 Los
Angeles, and 2022 Green Bay. These remain provisional because explicit caller evidence and/or
full interval continuity is still missing. The 50% target was not reached because certainty was
not manufactured.

## PCAE availability refresh

Only newly qualifying verified intervals were passed through the unchanged expanding-prior-season
PCAE method. Shared intervals remained excluded. Missing PCAE was never converted to zero.

| Season | Attributed plays |
|---:|---:|
| 2010 | 1,000 |
| 2011 | 1,016 |
| 2012 | 1,978 |
| 2013 | 946 |
| 2015 | 1,470 |
| 2016 | 4,101 |
| 2017 | 19,606 |
| 2018 | 3,889 |
| 2020 | 8,470 |
| 2021 | 8,140 |
| 2022 | 10,967 |
| 2023 | 33,836 |
| 2024 | 33,335 |
| 2025 | 32,813 |

Total attributed plays: 161,567. Seasons absent from the table remain unavailable, not zero.

## Q/P availability and gates

The availability-only join contains 196 common Q/P coach-seasons, 100 chronological future target
rows, 50 repeat play callers, 57 consecutive different-QB observations, and 16 consecutive
different-team observations. It supports five target seasons (2021–2025) under the fixed rule of
at least two target rows and ten strictly prior history rows. No final Models 1–6 were fitted.

| Gate | Threshold | Result |
|---|---:|---|
| A — verified caller coverage | at least 256/512 | **FAIL — 144** |
| B — chronological target folds | at least 5 | **PASS — 5** |
| C — common future Q/P rows | at least 150 | **FAIL — 100** |
| D — resampling feasibility | season/coach/team/QB minimums | **PASS** |

The resampling audit has 14 seasons, 96 callers, 32 teams, and 325 summed quarterback
observations. Those unit counts make resampling mechanically feasible, but do not override failed
coverage and future-row gates. Exact blockers are 112 additional fully verified cells and 50
additional common future rows.

## Scheme foundation

The primary observed grain is `team_id`–`season`. The artifacts keep source hashes, feature
definitions, source-specific denominators, raw values, within-season z-scores, and explicit
missingness. Details are in [the feature dictionary](SCHEME_FEATURE_DICTIONARY.md).

- PBP tendencies cover all 512 team-seasons from 2010–2025.
- Participation covers all 320 team-seasons from 2016–2025, with per-team-season eligible
  denominators ranging from 858 to 1,171 matched run/pass plays.
- Observed personnel groups are 00, 01, 02, 03, 04, 10, 11, 12, 13, 14, 20, 21, 22, 23, 30,
  31, 32, 40, and 41. Zero-use rows remain explicit within the source window.
- Explicit formation categories cover 2016–2025. Under center is not inferred as the shotgun
  complement.
- FTN motion, play action, RPO, screen, and QB-location features cover 128 team-seasons from
  2022–2025 and remain experimental.
- Designed-QB usage remains unavailable rather than inferred.
- Outcomes are stored separately from choice/tendency profiles.

The availability table classifies 12 CORE, 53 DESCRIPTIVE, 7 EXPERIMENTAL, and 1 UNAVAILABLE
features/diagnostics. Personnel-family year-over-year team correlations range from 0.255 for
empty-backfield personnel to 0.687 for multiple-back usage; exact and family rates remain
descriptive pending stronger portability evidence.

## Scheme association and portability

Coach association preserves assignment keys, role, interval, verification, confidence, interim,
shared, and retained fields. It explicitly labels the fingerprint as full team-season context,
not exact weekly ownership. No team scheme is equally assigned to every role as a causal effect.

All qualifying consecutive-season moves were rebuilt: 10 HC, 43 OC, 18 verified play-caller, 9
OC+verified-play-caller, 1 HC+verified-play-caller, and 39 QB-coach moves. Mean standardized
Euclidean adoption is -0.060, 0.022, 0.134, 0.221, 0.688, and -0.137 respectively; positive means
the destination moved toward the coach's prior offense. Samples—especially combined roles—are
small and descriptive, not rankings or causal estimates.

For verified callers, 55.6% of moves moved closer by Euclidean distance. At feature level, 11
personnel moved toward the prior offense in 72.2% of 18 moves; multiple-TE in 66.7%, spread in
61.1%, and heavy/multiple-back in 55.6%. These are exploratory proportions. Same-era deterministic
placebos use 250 draws per move; verified callers show mean observed-minus-placebo adoption of
0.106. Fourteen caller moves have S+1 persistence rows, with mean persistence change -0.323, so
the first-year resemblance does not generally strengthen in the following season.

Multiple qualifying moves are retained rather than hand-picked. They include Kellen Moore (three
verified caller moves) and Klint Kubiak (two), plus John Fox among HCs, seven OCs, and nine QB
coaches in their respective role outputs. Each underlying move is available for audit.

## Determinism and validation

All analytical output floats are deterministically rounded before CSV serialization. Two complete
builds into separate empty directories produced the same `c12-data-250e540b7de79385` identity and
byte-identical manifests and 32 CSV artifacts. Inputs include source hashes for all PBP seasons,
official cached participation/FTN files, manual coaching CSVs, frozen Prompt 6/7/11B inputs, and
relevant code/dependency identity.

Prompt 8 adds focused evidence, personnel, formation, FTN, tendency, missingness,
standardization, and clean-build tests. The opt-in network content test validates representative
official interval evidence rather than URL availability alone. The complete offline suite ran 216
tests: 167 passed and 49 environment-dependent tests were skipped. Those skips comprise 46
PostgreSQL/API tests (no `TEST_DATABASE_URL` was supplied for this research-only checkpoint) and
three opt-in network tests. The three network tests were then run separately and all passed,
including the full coaching source/content registry and representative Prompt 8 interval evidence.
Ruff, Python formatting, compilation, and `git diff --check` also passed. Skips are not counted as
passes.

## Final decision

**FINAL EQUATION RERUN READINESS: NOT READY.** The evidence-backed expansion improves caller and
scheme availability, but verified caller coverage and common future Q/P sample size remain below
the precommitted gates. Prompt 8 stops here without an equation, weights, shrinkage, score,
ranking, production change, Phase II model, or Ask Anything implementation.
