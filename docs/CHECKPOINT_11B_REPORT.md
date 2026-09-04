# Checkpoint Eleven-B report

Date: 2026-09-04
Status: implemented locally; uncommitted; not pushed or deployed

## Scope and evidence decision

Checkpoint Eleven-B evaluates all 512 team-season cells for offensive coordinator, quarterbacks
coach, and play caller across 2010–2025. Every cell retains the strongest defensible status; no
assignment is fabricated to improve coverage. Formal OC/QB-coach titles are verified in the
research-only `coaching_evidence_11b.csv` overlay when the cited NFL Record & Fact Book is
explicit, while `season_designation`, original source confidence, and open interval reviews
preserve uncertainty about uninterrupted weekly tenure. The frozen serving assignments remain
unchanged for those formal roles, so Checkpoint Six exposure lineage is not rewritten. Play
calling remains a separate fact and is never inferred from a staff title.

The recent priority pass uses ESPN's explicit all-32 caller audits for 2023–2025, official team or
NFL change reports for bounded transitions, and an official Jacksonville article resolving Press
Taylor as the 2023 full-time caller. The 2020 4for4, 2021 FantasyData, and 2022 ESPN tables remain
provisional where they do not establish retrospective weekly continuity. ESPN's 2017 midseason
audit supplies candidates only and leaves boundaries unresolved.

## Final coaching coverage

| Role | Verified | Partial verified | Provisional | Missing | Manual review | Total | Verified |
|---|---:|---:|---:|---:|---:|---:|---:|
| Head coach | 512 | 0 | 0 | 0 | 0 | 512 | 100.000% |
| Offensive coordinator | 404 | 0 | 0 | 108 | 0 | 512 | 78.906% |
| Quarterbacks coach | 383 | 0 | 0 | 129 | 0 | 512 | 74.805% |
| Play caller | 96 | 7 | 96 | 0 | 313 | 512 | 18.750% |

The unresolved play-caller artifact contains 416 cells at
`research/coach_effect/outputs/checkpoint_11b/c11b-665304acc3cf9842/unresolved_play_callers.csv`.
There are 22 distinct verified in-season caller transition boundaries (23 assignment rows because
Houston Week 4 has two shared coaches) and one verified shared interval grain
(two coaches in Houston Week 4). Both 2024 and 2025 contain 32 full, zero partial, and zero
unresolved team maps. The 2023 map is also complete.

## Historical PCAE attribution

The formulas remain unchanged. `pcae-play-eligibility-v2` supplies eligible run/pass plays;
`pcae-expanding-prior-seasons-v1` trains only on prior seasons. A play is attributed only when one
verified, explicit, non-shared caller interval covers its team, season, and week.

| Season | Eligible | Attributed | Ambiguous/shared | Unattributed | Attribution | Callers | Full | Partial | Unresolved |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2010 | 31,894 | 0 | 0 | 31,894 | 0.000% | 0 | 0 | 0 | 32 |
| 2011 | 32,150 | 0 | 0 | 32,150 | 0.000% | 0 | 0 | 0 | 32 |
| 2012 | 32,437 | 293 | 0 | 32,144 | 0.903% | 1 | 0 | 1 | 31 |
| 2013 | 32,850 | 0 | 0 | 32,850 | 0.000% | 0 | 0 | 0 | 32 |
| 2014 | 32,325 | 0 | 0 | 32,325 | 0.000% | 0 | 0 | 0 | 32 |
| 2015 | 32,503 | 809 | 0 | 31,694 | 2.489% | 2 | 0 | 2 | 30 |
| 2016 | 32,291 | 2,787 | 0 | 29,504 | 8.631% | 4 | 0 | 4 | 28 |
| 2017 | 31,987 | 0 | 0 | 31,987 | 0.000% | 0 | 0 | 0 | 32 |
| 2018 | 31,751 | 0 | 0 | 31,751 | 0.000% | 0 | 0 | 0 | 32 |
| 2019 | 32,046 | 0 | 0 | 32,046 | 0.000% | 0 | 0 | 0 | 32 |
| 2020 | 32,444 | 160 | 62 | 32,284 | 0.493% | 1 | 0 | 0 | 32 |
| 2021 | 33,986 | 0 | 0 | 33,986 | 0.000% | 0 | 0 | 0 | 32 |
| 2022 | 33,652 | 0 | 0 | 33,652 | 0.000% | 0 | 0 | 0 | 32 |
| 2023 | 33,836 | 33,836 | 0 | 0 | 100.000% | 36 | 32 | 0 | 0 |
| 2024 | 33,335 | 33,335 | 0 | 0 | 100.000% | 36 | 32 | 0 | 0 |
| 2025 | 32,813 | 32,813 | 0 | 0 | 100.000% | 36 | 32 | 0 | 0 |

## Joinability and repeatability readiness

| Component | PAE observations | Unique QBs | Unique coaches | Teams | Seasons |
|---|---:|---:|---:|---:|---:|
| Head coach | 1,689 | 555 | 120 | 32 | 16 |
| Offensive coordinator | 1,313 | 493 | 140 | 32 | 16 |
| Quarterbacks coach | 1,242 | 475 | 133 | 32 | 16 |
| Play caller | 362 | 208 | 62 | 32 | 7 |
| PCAE | 362 | 208 | 62 | 32 | 7 |

PAE retains `(data_version, player_id, team_id, season)` before the verified team-season evidence
join. The verified PCAE sample contains 116 coach-team-season observations, 62 unique callers, 35
repeat callers, 48 consecutive-season pairs, 62 callers seen with multiple QBs, 15 callers seen
with multiple teams, and 16 team-switch observations. Season breadth is 27 callers with one
season, 17 with two, 17 with three, and one with four or more.

## Reproducibility and release boundary

Research version: `c11b-665304acc3cf9842`. The deterministic publication contains the coverage matrix,
unresolved callers, eligibility reconciliation, season attribution, historical PCAE, PAE
joinability, repeatability readiness, and a manifest. All mutable manual CSVs, PBP assets, the PAE
artifact, dependency versions, and relevant source code participate in content identity. Two
independent clean builds must match byte-for-byte.

This checkpoint does not alter PAE, PCAE, environment methodology, Coach Effect weights,
rankings, database schema, API, frontend, deployment, or production Neon. The broader recent
caller sample is sufficient to begin a separately reviewed final-equation research phase, but
the 416 unresolved historical caller cells and formal-role interval uncertainty still block a
production Coach Effect implementation.

## Validation

- Offline Python: 167 discovered; 121 passed and 46 intentionally skipped. The skips correspond
  exactly to the separately executed 44 PostgreSQL/API tests and two opt-in network tests.
- Disposable PostgreSQL/API: 44/44 passed; no production database was used.
- Network/source validation: 2/2 passed, including all retained assignment URLs and required
  content terms plus the nflverse boundary preflight.
- Ruff lint, Ruff formatting, and `git diff --check`: passed.
- Determinism: two independent empty-directory Eleven-B builds produced identical versions and
  byte-identical deterministic artifacts.
- Frontend tests were not run because no frontend file, route, contract, or presentation changed.
