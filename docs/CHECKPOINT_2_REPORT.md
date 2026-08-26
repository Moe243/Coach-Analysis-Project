# Checkpoint two report — NFL data vertical slice

Date: 2026-08-26

Status: complete

Published local data version: `c2-424bdc8859118b9f`

Pipeline version: `checkpoint-2.5`
Metric version: `qb-dropback-v1`

## Outcome

Checkpoint two implements one reproducible command that retrieves and validates 2009 warm-up plus 2010, 2016, 2022, and 2025 analysis boundaries; preserves exact source bytes in Bronze; and publishes canonical Silver identities, games, QB metrics, manifests, and quality reports. Output is local and Git-ignored. No coaching data, expected-performance model, coach ranking, database load, API, frontend, or college enrichment was started.

## Reproduction

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m pip install --no-deps -e .
make PYTHON=.venv/bin/python vertical-slice
make PYTHON=.venv/bin/python vertical-slice-offline
```

The first command downloads cache misses. The second requires the verified cache and makes no network request. Both produce the same data version for the same source checksums and pipeline/metric versions. A failed run removes its staging directory and never updates `LATEST`.

## Observed source assets

The run validated 13 Parquet assets: five play-by-play files, five roster files, and one each for schedules, players, and teams. Every required field passed. The Bronze copies matched their cached source SHA-256 digests.

| Season | PBP rows | PBP columns | Roster rows | Roster columns |
|---:|---:|---:|---:|---:|
| 2009 | 46,519 | 372 | 2,104 | 36 |
| 2010 | 46,892 | 372 | 2,152 | 36 |
| 2016 | 47,651 | 372 | 3,061 | 36 |
| 2022 | 49,434 | 372 | 3,134 | 36 |
| 2025 | 48,771 | 372 | 3,137 | 36 |

Column names were stable. Observed type differences versus 2009 were: 2025 PBP `goal_to_go` (`Int32` to `Float64`); roster `draft_number` and `jersey_number` (`String` to `Int32`) from 2016 onward; and 2025 roster `height` (`Float64` to `Int32`). The complete observed schemas and checksums are in the generated source manifest.

## Silver results

| Table | Rows |
|---|---:|
| Teams | 32 |
| Team aliases | 142 |
| Players | 9,070 |
| Usable player external IDs | 108,773 |
| Quarantined external-ID conflicts | 5 |
| Games, including postseason | 1,370 |
| QB-team-games | 3,237 |
| QB-team-seasons | 535 |
| Unresolved eligible QB plays | 0 |
| Source manifest | 13 |
| Pipeline manifest | 1 |
| Data-quality checks | 26 |

| Season | QB-team-season rows | Distinct QBs | Resolved dropbacks | Default-qualified rows | Prior-season available |
|---:|---:|---:|---:|---:|---:|
| 2009 | 112 | 112 | 18,587 | 0 | 0 |
| 2010 | 106 | 105 | 19,005 | 34 | 67 |
| 2016 | 96 | 96 | 20,072 | 34 | 0 |
| 2022 | 117 | 116 | 20,298 | 35 | 0 |
| 2025 | 104 | 103 | 19,830 | 38 | 0 |

The nonconsecutive boundary design intentionally exposes exact prior-season values only for 2010 from 2009. Prior metrics combine multi-team player seasons and require 200 dropbacks. The 2009 rows are marked `warmup` and can never satisfy default analysis qualification.

An illustrative 2010 sample, selected by dropback volume rather than performance rank, is:

| GSIS player | Team | Dropbacks | Starts | EPA/DB | CPOE | Success | Sack rate | Prior EPA/DB | EPA/DB change |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `00-0010346` | `team_ind` | 696 | 16 | 0.1896 | 4.1300 | 0.5115 | 0.0225 | 0.2948 | -0.1052 |
| `00-0020531` | `team_no` | 683 | 16 | 0.1248 | 5.9919 | 0.4963 | 0.0368 | 0.2991 | -0.1743 |
| `00-0027854` | `team_la` | 637 | 16 | -0.0724 | -4.4203 | 0.4082 | 0.0519 | null | null |

## Quality findings

Twenty-two hard checks passed with zero failures. They cover registry completeness, required schemas, team alias resolution, non-null game IDs before uniqueness evaluation, game and QB grains, canonical teams, binary dropback flags, finite eligible-play `qb_epa`, possession-team validity, game-season joins, exact normalized PBP/schedule home-and-away agreement, dropback reconciliation, GSIS syntax, source coverage, lag direction, and warm-up exclusion. Schedule validation runs across every eligible play before unresolved quarterback IDs are separated from metric inputs.

Observed duplicate counts were zero for games, QB-team-games, and QB-team-seasons. Missing player display names and unresolved/ambiguous eligible QB plays were also zero in the official run.

Two warning checks passed with zero observations: unresolved eligible dropbacks and missing player names. One warning quarantined five upstream external system/ID values because each mapped to multiple GSIS players. A second warning records 6,296 resolved pass attempts with missing air yards; no values are imputed, and each QB aggregate exposes numerator coverage. The external-ID conflicts are retained in `conflicting_player_external_ids.parquet` and excluded from the usable crosswalk. No ID was guessed.

## Behavioral validation

The offline fixture pipeline proves:

- attempts, sacks, scrambles, EPA/dropback, success, explosive-pass, and sack-rate formulas;
- passer and scramble-rusher GSIS resolution plus unresolved-play retention;
- exact source-to-Bronze checksums and verified offline cache reuse;
- 2009 warm-up exclusion, strict season-minus-one lagging, and behavioral year-over-year deltas;
- historical team-alias normalization, duplicate-game failure, kneel/spike/postseason exclusion, ambiguity retention, and null divide-by-zero rates;
- null game-ID rejection before uniqueness checks and fail-closed PBP/schedule team validation;
- lexicographically sorted fixture schemas independent of input collection or hash iteration order;
- source and pipeline lineage on every output, explicit asset validation, matching manifest counts, and full-output checksum verification before reuse;
- schema failure leaves no published partial version or `LATEST` pointer.

Repository validation completed with 22 tests: 16 passed locally and six checkpoint-one PostgreSQL integration tests were skipped because `TEST_DATABASE_URL` was not configured. The suite proves null game IDs fail at the intended check, mismatched PBP/schedule teams fail the pipeline, and every fixture Parquet schema is sorted deterministically. Ruff passed for `src` and `tests`. The PostgreSQL tests are behavioral database tests and remain available through `make test-postgres`; checkpoint two did not change the schema.

## Files added or changed

- Pipeline package: `constants.py`, `errors.py`, `sources.py`, `quality.py`, `transforms.py`, `pipeline.py`, `cli.py`, and package version metadata.
- Reproducibility: `requirements.lock`, `pyproject.toml`, `Makefile`, `.gitignore`.
- Tests: `tests/test_checkpoint_two_pipeline.py` plus import-only formatting in existing tests.
- Documentation: `README.md`, `DATA_SOURCES.md`, `DATA_DICTIONARY.md`, `METHODOLOGY.md`, `LIMITATIONS.md`, `data/README.md`, `docs/ARCHITECTURE.md`, `docs/PROJECT_PLAN.md`, and this report.

No generated Parquet, cache object, credential, `.Rhistory`, `.RData`, coaching assignment, or fabricated football row is committed.

## Exact next checkpoint

There is no implementation blocker for checkpoint two. PostgreSQL integration tests require an explicitly configured disposable database if they are to be rerun. GitHub publication remains deferred because this local repository has no connected remote.

Checkpoint three is the next approved planning boundary, not work started here. It will expand core ingestion to 1999-2025, expose completed 2010-2025 analysis seasons, and build the manually verified, citation-backed coach-team-season-role history with interval/conflict reporting. It must not fit expected-performance or coach-impact models until its own exit criteria pass.
