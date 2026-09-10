# Opening Week target-team source audit

Audit date: 2026-09-10. Baseline: `e8ea74aabb9c3d06d5c9f11e16f76cc1793cb967`.
Branch: `codex/preseason-qb-team-assignment-recovery`.

## Decision

**B. CONDITIONAL — SOURCE USEFUL BUT TIMING/PROVENANCE NOT STRONG ENOUGH YET.**

The weekly source materially improves hypothetical matching. It does not establish that its
historical records were available before regular-season performance. No assignment contract,
assignment-data version, raw-data ingestion, or model rerun is authorized by this result.

- Checkpoint 15 remains **COMPLETE** (`c15-c4d7c86f56238a49`).
- Player × Scheme Fit remains **NOT ESTIMABLE / DATA-LIMITED**.
- Checkpoint 15 rerun readiness: **NOT READY**.
- Checkpoint 16 readiness: **NOT READY**.
- Player State remains August 31; Scheme remains source season `Y-1`.

## Provenance and historical semantics

The [loader documentation](https://nflreadr.nflverse.com/reference/load_rosters_weekly.html)
distinguishes weekly records from latest/season rosters and advertises coverage back to 2002.
The [release](https://github.com/nflverse/nflverse-data/releases/tag/weekly_rosters), ID 73313637,
was first published in 2022. Its current Parquet index contains every season **2002–2026**;
2002–2025 are completed historical seasons, while 2026 is partial. All 2011–2025 assets were
inspected for this pilot, totaling 10,300,255 bytes. Earlier seasons were index-checked, not
row-validated. Checkpoint 3's `rosters/roster_<season>.parquet` files are different assets.

The Shield-only release description is incomplete. The code audit pins nflverse/nflverse-rosters
to `7f6cde68323ec2dfe77e6a7a06d1d8bb9427b871`:

- **2002–2015:** the [Data Exchange builder](https://github.com/nflverse/nflverse-rosters/blob/7f6cde68323ec2dfe77e6a7a06d1d8bb9427b871/R/rosters_dataexchange.R)
  requests NFL `getRoster` by season, season type, and club, with `lWeek=0`. It takes the feed's
  `Week`, `GsisID`, `CurrentClub`, and status-description fields. It normalizes week numbers with
  `dense_rank`; the exported label does not preserve an original availability timestamp.
- **2016 onward:** the [NGS builder](https://github.com/nflverse/nflverse-rosters/blob/7f6cde68323ec2dfe77e6a7a06d1d8bb9427b871/R/rosters_ngs.R)
  enumerates team/week requests using schedule weeks and calls `ngsscrapR::scrape_roster`.
  It also normalizes weeks. Its current-roster fallback is intended to leave weeks null and
  cannot qualify as historical Week 1 evidence. The underlying ngsscrapR repository could not
  be independently inspected through its public GitHub endpoint (404); its inner behavior
  therefore remains an explicit provenance gap.
- The [main builder](https://github.com/nflverse/nflverse-rosters/blob/7f6cde68323ec2dfe77e6a7a06d1d8bb9427b871/R/rosters.R)
  enriches from Shield and player master data. For 2002–2015 it **replaces weekly `status` with
  season-level Shield `status`**, joining by GSIS. Original weekly `status_description_abbr`
  remains separate. Such enriched fields cannot be assumed to describe the beginning of Week 1.
  Master identity/demographic enrichment is not a dated preseason Player State snapshot.
- [Weekly-to-season conversion](https://github.com/nflverse/nflverse-rosters/blob/7f6cde68323ec2dfe77e6a7a06d1d8bb9427b871/R/utils_rosters_weekly_to_season.R)
  runs from weekly histories to season summaries, not the reverse. This does not make the
  exported weekly history an immutable pregame archive.

The [older builder at bb35d6f6a125e2288171b1f373e0b48825554b1b](https://github.com/nflverse/nflverse-rosters/blob/bb35d6f6a125e2288171b1f373e0b48825554b1b/src/update_roster.R)
was also inspected: it predates the September 2023 historical asset replacements and contains
the same Data Exchange/NGS routes and pre-2016 Shield-status replacement. Findings are not based
solely on a newer refactor.

**Participation test:** no PBP, box-score, snap-count, or player-statistics reconstruction of team
membership appears in the inspected caller code. These are roster endpoint calls, not demonstrated
participation rows. However, the private/unavailable dependency and undocumented source snapshot
semantics prevent a stronger guarantee. Schedule-scoped retrieval alone is not proof that a QB
played. Conversely, a roster label alone is not proof of a contemporaneous pregame capture.

**Historical revision risk:** [maintainer issue 56 and its comments](https://github.com/nflverse/nflverse-rosters/issues/56)
document duplicate 2021 weekly rows, inconsistent status fields, and a September 2023 correction
of historical Week 1 statuses. Published yearly assets are replaceable, not append-only evidence
captures. The 2011–2015 files have September 2023 update dates; 2016–2022 also have September 2023
updates. The 2023, 2024, and 2025 files were updated in March of the following year. Those dates
are not historical pregame evidence dates.

Concrete field contamination: Minnesota's 2011 Week 1 Donovan McNabb record has `status=CUT` but
weekly `status_description_abbr=A01`. His release occurred December 1, 2011, according to the
[NFL release report](https://www.nfl.com/_amp/vikings-grant-qb-mcnabb-s-request-to-be-released-09000d5d824a3ca3).
This demonstrates unsafe status enrichment, not that his Minnesota membership itself was false.
In 2017 only 30 teams have Week 1 QB records: Miami and Tampa Bay first appear at week 2.
Do not silently relabel their first available record as a safe opening-day snapshot.

## Fields and license

All 15 sampled files have the same 36 column names:

```text
season, team, position, depth_chart_position, jersey_number, status,
full_name, first_name, last_name, birth_date, height, weight, college,
gsis_id, espn_id, sportradar_id, yahoo_id, rotowire_id, pff_id, pfr_id,
fantasy_data_id, sleeper_id, years_exp, headshot_url, ngs_position,
week, game_type, status_description_abbr, football_name, esb_id,
gsis_it_id, smart_id, entry_year, rookie_year, draft_club, draft_number
```

Relevant keys are string `gsis_id`, `team` abbreviation, integer `season`/`week`, and
`game_type=REG`; postseason values include WC/DIV/CON/SB. No retained `observed_at`,
`published_at`, evidence date, or snapshot timestamp establishes pregame availability.
Jersey/draft-number and height types vary historically. The audit maps abbreviations through
the existing canonical team mapper, preserving the source schema in its aggregate output.
No new player identities are created. Every sampled Week 1 QB has a non-null GSIS ID matching
`00-` plus seven digits; sampled files have no null weeks. QB row counts vary from 82 to 129.

The [published data repository license](https://github.com/nflverse/nflverse-data/blob/main/LICENSE.md)
is **CC BY 4.0**: attribution, a license link, and change notices must accompany reused data.
The roster-building code's MIT license is separate. This audit uses only published nflverse
files, not authenticated NFL collection endpoints, and does not redistribute raw files or
headshots. Record NFL Data Exchange/NGS/Shield upstream provenance and field-specific terms;
nflverse's license does not prove historical availability or grant blanket rights to unrelated
upstream assets. No PFR ingestion was performed.

## Proposed timing rule — not implemented or approved

Define `B_Y` as the earliest scheduled regular-season kickoff in season `Y`, represented in UTC
from a verified preseason schedule snapshot. Require an immutable roster observation with both
effective membership and original publication/capture evidence strictly before `B_Y`. Also
require evidence strictly before the assigned team's first regular-season kickoff. Date-only
evidence qualifies only if its latest possible timestamp is before those boundaries; unknown
time zones or same-day ordering ambiguity fail closed.

Player State stays at August 31. Team assignment alone would use `OPENING_WEEK`; Scheme remains
`Y-1`. Only regular-season target-team outcomes beginning after `B_Y` could be evaluated.
Conflicting simultaneous team memberships are excluded, not resolved through later outcomes.
Week-one labels, today's download time, later release updates, final roster status, and a player's
eventual games cannot substitute for original availability evidence.

To reconsider approval, obtain a documented immutable snapshot/correction history or independently
timestamped pregame membership evidence, verify the Data Exchange and NGS time/status semantics,
and audit the inaccessible roster dependency. Exclude or repair unsafe enrichments. More matching
rows alone cannot satisfy this gate.

## Coverage pilot — candidate matches, not legal training rows

The pilot reads frozen C14 states and canonical QB outcomes, hashes/validates them against C15,
and reuses the existing coverage helper. It never rebuilds Player State or fits a model.
Only REG Week 1 `position=QB` records are considered. Duplicate identical canonical
player/team/season rows are collapsed; multiple distinct teams are excluded before outcomes
are inspected (zero such conflicts in this sample). No outcomes choose assignments.

Two diagnostic variants bracket status sensitivity:

1. All Week 1 QB rows, including inactive/cut/reserve records: **1,393 / 8,032** state matches,
   **1,002 / 1,058** participant matches, **728** matching outcome rows with at least 50 dropbacks.
2. Status screen: before 2016 retain original weekly codes matching `^(A|I|P|R)\d{2}$` except
   `R02`, ignoring overwritten Shield status; from 2016 retain ACT/INA/DEV/RES and exclude
   CUT/TRT/RET and other/null statuses. This is a declared coverage sensitivity, **not** a vetted
   historical membership rule. It gives **1,309 / 8,032** state matches, **998 / 1,058** participant
   matches, and **727** matching 50-dropback outcome rows.

These counts measure the weekly source alone, not its union with existing safe assignments.
The 1,459 unique status-screen candidates include 150 player-seasons outside C14's universe;
they do not backfill it. A separate 37 retrospective participant player-seasons outside that
universe also remain excluded. The 8,032-state denominator includes inactive historical players.
Passing a 50-dropback outcome threshold does not establish input timing or M2 feature eligibility.

| Season | Participant states | Safe → candidate state assignments | Safe → candidate participant matches | Safe → candidate ≥50-DB rows |
|---|---:|---:|---:|---:|
| 2011 | 73 | 12 → 79 | 8 → 66 | 6 → 49 |
| 2012 | 66 | 11 → 73 | 9 → 63 | 8 → 43 |
| 2013 | 57 | 10 → 72 | 4 → 56 | 4 → 43 |
| 2014 | 69 | 12 → 77 | 7 → 65 | 4 → 47 |
| 2015 | 70 | 7 → 78 | 3 → 65 | 2 → 47 |
| 2016 | 68 | 15 → 100 | 8 → 64 | 6 → 47 |
| 2017 | 67 | 10 → 80 | 6 → 59 | 5 → 43 |
| 2018 | 67 | 13 → 88 | 6 → 61 | 5 → 46 |
| 2019 | 65 | 11 → 89 | 8 → 63 | 7 → 50 |
| 2020 | 74 | 12 → 98 | 6 → 72 | 6 → 48 |
| 2021 | 76 | 10 → 98 | 8 → 72 | 6 → 51 |
| 2022 | 81 | 9 → 96 | 7 → 77 | 6 → 57 |
| 2023 | 75 | 14 → 92 | 9 → 70 | 6 → 52 |
| 2024 | 77 | 11 → 94 | 7 → 73 | 6 → 50 |
| 2025 | 73 | 108 → 95 | 69 → 72 | 53 → 54 |
| **Total** | **1,058** | **265 → 1,309** | **165 → 998** | **130 → 727** |

| Evaluation-only category | Participant denominator | Safe matches | Status-screen matches | Safe → candidate ≥50-DB rows |
|---|---:|---:|---:|---:|
| Returning veteran | 533 | 35 (6.57%) | 526 (98.69%) | 28 → 426 |
| Team changer | 235 | 23 (9.79%) | 208 (88.51%) | 16 → 128 |
| Rookie | 104 | 103 (99.04%) | 103 (99.04%) | 84 → 84 |
| Other/new entrant | 186 | 4 (2.15%) | 161 (86.56%) | 2 → 89 |

Categories reproduce C15 exactly for a fair comparison: rookie status comes from frozen states;
non-rookie categories compare adjacent primary outcome teams (highest dropbacks, deterministic
team tie-break). They are retrospective labels only. The helper's participant window begins in
2011, so it has no 2010 prior-team category for 2011; OTHER_NEW_ENTRANT must not be read as
"true NFL rookie." A matching assignment can match any actual team stint, never a substituted
destination. The year/category definitions and outcome threshold were not changed.

**M2 validation pilot not run:** the prerequisite timing/provenance gate failed. Existing approved
M2 folds remain **zero**. The number achievable after hypothetical approval is **not calculated**,
not asserted to be zero or inferred from 727 rows. No interaction definitions or modeling
thresholds changed.

## Reproduction, integrity, and checks

Run from the recovery checkout using an environment with project dependencies:

```sh
PYTHONPATH=src python scripts/audit_opening_week_rosters.py --project-root '/path/to/existing/project/data-root-parent'
```

The project root must contain the existing ignored artifacts. The CLI retrieves public release
bytes into memory, hashes and parses those same bytes, and emits only aggregate audit results to
stdout. It does not retain upstream rows, populate raw/processed/source caches, or publish an
assignment dataset. Unapproved candidate status strings exist only inside the audit's coverage
helper inputs and must not be consumed by a model. Future source changes require renewed review;
this script is not an ingestion authorization.

Input pins:

- C14 `c14-43283062e788e686`, `player_states.parquet`:
  `27b0d0e485326ae0a1c4739cddb2b162d3877ff1e88bc47359c02d15ffb028a5`.
- Enhancements `enh-04254065cafd92ba`, canonical QB-team-season performance:
  `4ab14dee57c7e0b0cc9dcebc209fc290a08ce4ed7c408bc2aed3b3c569687aec`.
- Existing assignments are checked against C15's `output_checksums` before parsing.

Source URL pattern:
`https://github.com/nflverse/nflverse-data/releases/download/weekly_rosters/roster_weekly_<season>.parquet`.

| Season | Week 1 QB rows | Raw Parquet SHA-256 |
|---|---:|---|
| 2011 | 83 | `1764068c995dbb842baa936bff4abcc399f4738f0b4bb321fc437ed8eadbc426` |
| 2012 | 82 | `32a218e187e553abdeacd107ae9c76c321e258809d18578f1b1267882f1c0b29` |
| 2013 | 87 | `bb68c0e5dba854c4d0b7dda4331456df701c06a66160b96decdfdc1b71147663` |
| 2014 | 82 | `51ae5047bb95297e039ba3d6560cee1ed16407f2e91897f6c9c79aafecdef397` |
| 2015 | 89 | `61a57f4484a556d4cad1cf50030a8a8822a345eace783e013f8ba8ae2f721243` |
| 2016 | 117 | `70d0ceab697860e946a2acdafcae48809015dcdaf06bd21d26777473cff7db8f` |
| 2017 | 113 | `2f633cf331f561ea5346238a1808e8a68811eb280084e75f0dd09880535c5012` |
| 2018 | 120 | `0fcd3c3f098dbb5350be2095959acf38202602c6b3c71475e883fabda23077a8` |
| 2019 | 128 | `08ef64996cecdff2f4631ca26b21ed9a39bf5fba0b3379d902e531facf81e5c4` |
| 2020 | 125 | `8d601bf5c5d669465481421ad5cd1a1470d51792054e84bdc04f3620785f7530` |
| 2021 | 111 | `3e9f67569e940b54b3778ef2c9150850920b5bf93143bad3bd158e649825cf6b` |
| 2022 | 118 | `063c0da93f612811e1c4a4c12727a56fd2716197864795f15aa2f10a591b00c0` |
| 2023 | 117 | `0fa5abf9b462a087ecb17f3268ed7233ce9935e95d77be94ad6bac66adf8e281` |
| 2024 | 128 | `4b144e8eda5a159f36037b02e8b7d5a7861acb65b0816b0a063244992038dcf8` |
| 2025 | 129 | `a8764c947bfe6a9d8f122a194e3f026973c8efcc8a3456c67cbfac4371c20342` |

Validation:

- Two independent live audit executions produced byte-identical aggregate JSON,
  SHA-256 `8356822e4cfe12bbe50d2cdb43890c4ca2c91358714a9463fea63ee84944aa96`.
- Source size, available release digest, season/schema checks, pinned input checksums, baseline
  reconciliation, canonical uniqueness, and reversed-row-order invariance passed.
- Focused audit regressions cover source-byte hashing, REG/week/position filtering, unexpected
  timing fields, multi-team ambiguity, duplicate collapse, no outcome-driven team replacement,
  no state backfill, and status sensitivity. Existing non-build C15 regressions are also checked.
- Final focused run: **23 passed, 1 deselected** (4 new audit tests and 19 existing C15 tests).
  Command: `PYTHONPATH=src python -m pytest -q tests/test_opening_week_roster_audit.py
  tests/test_checkpoint_fifteen_player_scheme_fit.py -k 'not two_independent_clean_builds_are_byte_identical'`.
  Ruff, formatting, Python compilation, and whitespace checks passed for the changed files.
- An initial run of the entire C15 test file hit its existing real-data clean-build test: it
  failed before modeling because the recovery worktree has no C13 `LATEST` artifact path.
  No artifacts were linked/copied and no C15 model was rerun to bypass the explicit scope limit.
  The independent audit-repeat check above is not a C15 model-build claim.

Only this audit document, the source register, audit script, and its focused tests change.
No C14/C15 artifacts, models, production schema/API/frontend, Neon, Render, or deployment are
modified. No commit, merge, push, or Checkpoint 16 implementation is performed.
