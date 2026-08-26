# Checkpoint three report — complete historical ingestion

Date: 2026-08-26

Status: complete

Published local data version: `c3-f6c1aa118ff43b90`

Pipeline version: `checkpoint-3.3`
Metric version: `qb-dropback-v1`

## Outcome

Checkpoint three expands the validated pipeline to every NFL season from 1999 through 2025. Seasons 1999-2009 are warm-up only; 2010-2025 are analysis seasons. The build ingests official play-by-play, schedules, rosters, weekly player statistics, injuries, depth charts, and snap counts where historically available. It preserves exact Bronze bytes, season-partitioned contextual Silver tables, canonical team and GSIS player identities, complete QB-game and QB-team-season tables, source and output checksums, and machine-readable coverage and quality results.

No coaching assignments were collected. No expected-performance model, PAE, coach-impact model, ranking, database load, API, or frontend was started.

## Preflight and publishing

The final full-history run resolved all 140 expected assets from the verified cache before transformation. Total source size was 540,760,962 bytes, download size was zero, the conservative free-space requirement was 1,215,739,652 bytes, and 147,367,481,344 bytes were available.

Each season is transformed in its own staging directory and atomically published as a checksum-protected immutable season version. Before football filtering or aggregation, a hard check rejects null `game_id`, null `play_id`, and duplicate `(game_id, play_id)` keys with season-specific counts and bounded safe samples. All 27 official seasons passed with zero null or duplicate play keys. The observed 1999 blank aliases, empty 2012 snap-count asset, and one invalid-EPA play in 2019 were handled without modifying previously completed seasons. The full dataset was assembled in a separate staging tree and the root `LATEST` pointer changed only after all seasons passed.

Content-addressed version directories now contain only deterministic analytical artifacts. Execution timestamps, cache/retrieval status, preflight details, and reuse status are written separately to mutable `data/processed/historical/EXECUTION_LOG.json`; those operational facts may legitimately differ. A fixture-backed clean rebuild into two independent empty output directories produced the same data version and byte-identical deterministic manifests, every Parquet output, checksum manifest, report, Bronze file, and season artifact.

## Complete results

| Output | Rows |
|---|---:|
| Source assets | 140 |
| Coverage expectations | 162 |
| Teams | 32 |
| Team aliases | 143 |
| Players | 15,930 |
| Usable player external IDs | 156,578 |
| Quarantined external-ID conflicts | 20 |
| Games | 7,276 |
| QB-team-games | 17,255 |
| QB-team-seasons | 2,899 |
| Resolved dropbacks | 517,712 |
| Default-qualified analysis QB-team-seasons | 582 |
| Unresolved/quarantined QB plays | 1 |
| Weekly player-stat rows | 476,159 |
| Injury rows | 90,752 |
| Depth-chart rows | 1,423,400 |
| Snap-count rows | 324,611 |
| Data-quality results | 905 |

The 905 quality results contain 870 passes, 35 explicit warnings, and zero failures. All requested seasons produced QB metrics. All warm-up rows are ineligible for the default ranking population. Source play keys and game, QB-team-game, and QB-team-season grains are unique. Every resolved metric play has a syntactically valid GSIS quarterback ID and finite `qb_epa`; aggregated dropbacks reconcile to resolved play counts.

## Source rows and historical coverage

An em dash means the dataset is outside its declared historical coverage. The official 2012 snap-count file exists and passes its schema contract but has zero rows.

| Season | PBP | Rosters | Player stats | Injuries | Depth charts | Snap counts |
|---:|---:|---:|---:|---:|---:|---:|
| 1999 | 46,136 | 2,039 | 16,839 | — | — | — |
| 2000 | 45,491 | 2,046 | 16,623 | — | — | — |
| 2001 | 44,969 | 2,045 | 16,789 | — | 36,736 | — |
| 2002 | 47,355 | 2,031 | 17,481 | — | 34,594 | — |
| 2003 | 46,811 | 2,034 | 17,232 | — | 34,298 | — |
| 2004 | 46,705 | 2,063 | 17,272 | — | 28,898 | — |
| 2005 | 46,823 | 2,048 | 17,355 | — | 32,803 | — |
| 2006 | 46,299 | 2,061 | 17,214 | — | 33,721 | — |
| 2007 | 46,266 | 2,076 | 17,265 | — | 38,547 | — |
| 2008 | 45,917 | 2,077 | 17,212 | — | 38,651 | — |
| 2009 | 46,519 | 2,104 | 17,690 | 4,821 | 38,423 | — |
| 2010 | 46,892 | 2,152 | 17,590 | 4,491 | 38,421 | — |
| 2011 | 47,448 | 2,099 | 17,440 | 4,971 | 37,941 | — |
| 2012 | 47,834 | 2,120 | 17,419 | 5,533 | 37,312 | 0 |
| 2013 | 48,158 | 2,137 | 17,248 | 5,070 | 37,066 | 23,799 |
| 2014 | 47,629 | 2,153 | 17,622 | 5,078 | 32,542 | 23,864 |
| 2015 | 48,122 | 2,190 | 17,613 | 5,232 | 37,058 | 23,842 |
| 2016 | 47,651 | 3,061 | 17,552 | 5,115 | 36,612 | 23,890 |
| 2017 | 47,245 | 3,082 | 17,477 | 5,104 | 36,620 | 23,862 |
| 2018 | 47,109 | 3,142 | 17,414 | 5,133 | 36,560 | 23,877 |
| 2019 | 47,260 | 3,114 | 17,362 | 5,392 | 36,308 | 23,862 |
| 2020 | 47,705 | 3,068 | 17,602 | 5,661 | 36,168 | 24,999 |
| 2021 | 49,922 | 2,961 | 18,969 | 5,587 | 37,487 | 26,468 |
| 2022 | 49,434 | 3,134 | 18,831 | 5,682 | 37,780 | 26,381 |
| 2023 | 49,665 | 3,090 | 18,643 | 5,599 | 37,327 | 26,540 |
| 2024 | 49,492 | 3,216 | 18,983 | 6,215 | 37,312 | 26,615 |
| 2025 | 48,771 | 3,137 | 19,422 | 6,068 | 554,215 | 26,612 |

Coverage contains 136 populated ingested dataset-seasons, one ingested-empty asset, and 25 expected gaps: injuries before 2009, depth charts before 2001, and snap counts before 2012. The 2025 depth-chart source uses a materially different, much denser schema and remains in its own partition.

The unambiguous PFR-to-GSIS external-ID bridge resolved 324,383 of 324,611 snap-count rows to canonical players. The remaining 228 rows retain their upstream PFR IDs with null canonical IDs; no name match was attempted.

## QB and quality results by season

`Missing air` is the number of pass attempts without recorded air yards. `Gaps` counts datasets outside expected historical coverage. Quality counts shown here are the season-local checks; five additional all-season checks passed.

| Season | Scope | Games | QB games | QB seasons | Qualified | Dropbacks | Unresolved | Invalid EPA | Missing air | Gaps | Checks | Warnings |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1999 | warm-up | 259 | 651 | 109 | 0 | 17,762 | 0 | 0 | 17,701 | 3 | 27 | 3 |
| 2000 | warm-up | 259 | 637 | 102 | 0 | 17,712 | 0 | 0 | 17,229 | 3 | 27 | 2 |
| 2001 | warm-up | 259 | 620 | 114 | 0 | 17,916 | 0 | 0 | 17,427 | 2 | 30 | 1 |
| 2002 | warm-up | 267 | 655 | 113 | 0 | 19,061 | 0 | 0 | 18,511 | 2 | 30 | 1 |
| 2003 | warm-up | 267 | 669 | 123 | 0 | 17,560 | 0 | 0 | 17,560 | 2 | 30 | 1 |
| 2004 | warm-up | 267 | 647 | 118 | 0 | 17,530 | 0 | 0 | 17,528 | 2 | 30 | 1 |
| 2005 | warm-up | 267 | 636 | 101 | 0 | 17,618 | 0 | 0 | 17,618 | 2 | 30 | 1 |
| 2006 | warm-up | 267 | 623 | 103 | 0 | 18,030 | 0 | 0 | 1,231 | 2 | 30 | 1 |
| 2007 | warm-up | 267 | 648 | 110 | 0 | 18,581 | 0 | 0 | 1,193 | 2 | 30 | 1 |
| 2008 | warm-up | 267 | 628 | 105 | 0 | 18,070 | 0 | 0 | 1,101 | 2 | 30 | 1 |
| 2009 | warm-up | 267 | 664 | 112 | 0 | 18,587 | 0 | 0 | 1,158 | 1 | 33 | 1 |
| 2010 | analysis | 267 | 627 | 106 | 34 | 19,005 | 0 | 0 | 1,171 | 1 | 33 | 1 |
| 2011 | analysis | 267 | 618 | 101 | 34 | 19,284 | 0 | 0 | 1,223 | 1 | 33 | 1 |
| 2012 | analysis | 267 | 606 | 90 | 38 | 19,603 | 0 | 0 | 1,216 | 0 | 36 | 2 |
| 2013 | analysis | 267 | 595 | 87 | 39 | 20,181 | 0 | 0 | 1,354 | 0 | 36 | 1 |
| 2014 | analysis | 267 | 618 | 101 | 37 | 19,765 | 0 | 0 | 1,255 | 0 | 36 | 1 |
| 2015 | analysis | 267 | 593 | 93 | 36 | 20,231 | 0 | 0 | 1,260 | 0 | 36 | 1 |
| 2016 | analysis | 267 | 612 | 96 | 34 | 20,072 | 0 | 0 | 1,198 | 0 | 36 | 1 |
| 2017 | analysis | 267 | 600 | 96 | 36 | 19,414 | 0 | 0 | 1,258 | 0 | 36 | 1 |
| 2018 | analysis | 267 | 630 | 109 | 37 | 19,765 | 0 | 0 | 1,379 | 0 | 36 | 1 |
| 2019 | analysis | 267 | 623 | 110 | 34 | 19,921 | 1 | 1 | 1,359 | 0 | 36 | 3 |
| 2020 | analysis | 269 | 656 | 121 | 36 | 20,024 | 0 | 0 | 1,232 | 0 | 36 | 1 |
| 2021 | analysis | 285 | 692 | 125 | 35 | 20,907 | 0 | 0 | 1,354 | 0 | 36 | 1 |
| 2022 | analysis | 284 | 669 | 117 | 35 | 20,298 | 0 | 0 | 1,386 | 0 | 36 | 1 |
| 2023 | analysis | 285 | 695 | 121 | 39 | 20,770 | 0 | 0 | 1,488 | 0 | 36 | 1 |
| 2024 | analysis | 285 | 678 | 112 | 40 | 20,215 | 0 | 0 | 1,413 | 0 | 36 | 1 |
| 2025 | analysis | 285 | 665 | 104 | 38 | 19,830 | 0 | 0 | 1,383 | 0 | 36 | 2 |

No season has a quality failure. The single unresolved row is a 2019 play without finite `qb_epa`; it is retained with `resolution_status = invalid_qb_epa` and excluded from metrics. Missing air yards are never imputed. Blank team aliases on non-team plays are normalized to missing, while eligible possession teams and normalized PBP home/away fields must still match the joined schedule exactly.

## Validation and tests

Offline tests cover source-registry boundaries, expected gaps, insufficient-storage rejection before cache writes, accepted empty official assets, season-failure isolation, complete historical assembly, warm-up exclusion, contextual partitions, null game IDs, null play IDs, duplicate composite play keys, and a genuine byte-identical rebuild into a second empty output directory. Existing checkpoint-one and checkpoint-two tests remain in the same discovery suite. Network integration tests are separately callable with `make test-network` and perform official HEAD preflight without retaining downloads.

The final network-enabled repository run discovered 34 tests: 28 passed and six PostgreSQL behavioral tests were skipped because this host has no `TEST_DATABASE_URL`, PostgreSQL tools, or Docker. The nflverse network integration test passed. Ruff check and format verification passed for `src` and `tests`.

## Exact next checkpoint

Checkpoint four is coaching-data verification, not modeling. It will build the manually verified, citation-backed 2010-2025 coach-team-season-role history for head coaches, offensive coordinators, play-callers, and quarterbacks coaches, including intervals, interim/shared/retained flags, conflicts, and completeness reporting across all 512 team-seasons.

Checkpoint four must not fit expected-performance or coach-impact models, calculate PAE, create rankings, build an API, or build the frontend. Work stops here for approval.
