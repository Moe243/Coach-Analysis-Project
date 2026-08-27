# Checkpoint four report — coaching-assignment review fixes

Date: 2026-08-27

## Outcome

Checkpoint four remains pending approval. The review fixes preserve complete 2010-2025 team-season coverage while separating observed or dated intervals from preseason designations. The committed layer now contains 1,343 assignment rows, 1,344 assignment citations, 281 canonical coach identities, and 1,527 open manual reviews. There are 566 verified intervals and 777 provisional rows. No rankings, PAE, expected-performance model, coach-impact model, API, or frontend was added.

| Role | Assignment rows | Verified | Provisional | Open reviews |
|---|---:|---:|---:|---:|
| Head coach | 540 | 540 | 0 | 0 |
| Offensive coordinator | 409 | 15 | 394 | 504 |
| Quarterbacks coach | 383 | 1 | 382 | 511 |
| Offensive play caller | 11 | 10 | 1 | 512 |

The review queue contains 776 season-interval checks, 239 missing formal-role checks, 504 team-seasons without explicit play-caller evidence, seven partial play-caller intervals whose earlier weeks remain unresolved, and one shared-duty verification item for Houston 2020.

## Corrected intervals and play callers

The preseason OC designations were audited as a class. Rows without independent weekly evidence are now `provisional` with `interval_basis = season_designation` and a corresponding interval-review item. Seven directly documented team-season changes were split into 14 verified `dated_source_weeks` rows:

- 2012 BAL: Cam Cameron, weeks 1-14; Jim Caldwell, weeks 15-17.
- 2012 TEN: Chris Palmer, weeks 1-12; Dowell Loggains, weeks 13-17.
- 2015 DET: Joe Lombardi, weeks 1-7; Jim Bob Cooter, weeks 8-17.
- 2015 IND: Pep Hamilton, weeks 1-8; Rob Chudzinski, weeks 9-17.
- 2016 BAL: Marc Trestman, weeks 1-5; Marty Mornhinweg, weeks 6-17.
- 2016 MIN: Norv Turner, weeks 1-8; Pat Shurmur, weeks 9-17.
- 2016 JAX: Greg Olson, weeks 1-8; Nathaniel Hackett, weeks 9-17.

Ten play-caller intervals now have direct evidence. Seven are the dated partial-season assignments for Dowell Loggains, Zac Taylor, Rob Chudzinski, Anthony Lynn, Marty Mornhinweg, Pat Shurmur, and Nathaniel Hackett. Houston 2020 contributes three verified intervals: Tim Kelly in Weeks 1-3, then shared Week 4 rows for Kelly and Bill O'Brien. Kelly's Weeks 5-17 interval is provisional, and an open shared-duty review preserves the unresolved exact weekly allocation after O'Brien's firing. Titles alone never create play-caller rows.

## Interim and shared-duty audit

All `is_interim = true` rows were audited. The final data contains 32: 28 observed head-coach temporary-replacement stints, Pat Shurmur's explicitly sourced 2016 Minnesota interim OC stint, and three play-caller stints with direct temporary-duty language (Zac Taylor, Nathaniel Hackett, and Pat Shurmur). Midseason replacement alone is no longer treated as an interim designation.

The unsupported interim flags removed from OC rows were Jim Caldwell (2012 BAL), Dowell Loggains (2012 TEN), Jim Bob Cooter (2015 DET), Rob Chudzinski (2015 IND), Marty Mornhinweg (2016 BAL), and Nathaniel Hackett (2016 JAX). Hackett retains the separately sourced interim play-caller flag. Unsupported play-caller interim flags were removed from Loggains, Chudzinski, Mornhinweg, and Anthony Lynn; Lynn's source expressly calls him the full-time play caller. The validator now rejects unsupported interim labels and requires both sides of every overlapping shared interval to be marked shared.

## Identity and compound-title audit

Four duplicate identities were removed, reducing the canonical coach table from 285 to 281 rows:

- `Matt LaFluer` and `Matt LeFleur` map to Matt LaFleur.
- `Rod Chudzinski` maps to Rob Chudzinski.
- `Frank Cignetti` maps to Frank Cignetti Jr.

The remaining canonical names were pairwise audited for close normalized spellings; the only remaining near match was the distinct Wade Phillips/Wes Phillips pair. The spelling mappings are preserved in `coach_aliases.csv`, and regression tests require identity continuity.

The complete source-title audit found one title spanning multiple checkpoint roles: Tim Kelly's 2020 Houston `offensive coordinator/quarterbacks` designation. It now creates both OC and QB-coach rows. His play-caller row comes from separate explicit team reporting, not from that compound title.

## Provenance and PostgreSQL

`assignment_interval_basis` is now a PostgreSQL enum with `observed_game_weeks`, `season_designation`, and `dated_source_weeks`; `coach_assignments.interval_basis` is non-null. The PostgreSQL loader passes the CSV value for every assignment and loads verified assignments with their citations in the same transaction. Offline loader behavior and PostgreSQL enum behavior both have regression coverage.

The network citation test checks all 16 source-book URLs and every additional assignment-source URL. It fetches assignment pages and requires content terms for all ten verified play-caller intervals, plus representative coordinator-change and compound-title assignments. HTTP availability alone is insufficient for these content checks.

## Validation and test results

The full offline discovery run found 50 tests: 40 passed and ten were skipped. Eight PostgreSQL behavior tests were skipped because `TEST_DATABASE_URL` was not configured, no PostgreSQL client/server was available, and `psycopg` was not installed. The other two skips were the deliberately opt-in checkpoint-three and checkpoint-four network integrations. The checkpoint-four network test was invoked separately and passed: 16 source books and 32 distinct additional assignment-source URLs resolved, and all 12 assignment-content checks matched. Ruff lint passed, and Ruff formatting reported all 19 checked Python files formatted.

Regression coverage proves the Baltimore split, unsupported-interim rejection, non-interim replacements, shared play-caller overlap rules, Tim Kelly's split 2020 Houston assignment and open review, his OC/QB compound expansion, canonical identity continuity, content matching, all three interval bases through the loader, the PostgreSQL interval-basis enum when a database is available, and the pre-existing citation/overlap/review contracts.

## Remaining limitations

Public sources still do not provide a complete weekly role and play-caller history. The 777 provisional rows are appointments or unresolved intervals rather than verified weekly tenure, 512 play-caller review items remain open, and Houston's post-Week-4 2020 weekly division is unresolved. The seven corrected coordinator changes are a conservative evidence-backed audit, not a claim that no other in-season changes occurred. Mirror-hosted official books remain medium-confidence, and live pages can disappear or change.

## Exact next checkpoint

Checkpoint five will build leakage-safe preseason quarterback features and out-of-sample expected-performance models. It must not begin until checkpoint four is explicitly approved. The remaining coaching review items must stay excluded or flagged in any later coaching-environment or coach-impact work.
