# Checkpoint Eleven report

Date: 2026-09-03
Status: implemented locally; pending review; not committed or deployed

## Scope and release boundary

Checkpoint Eleven adds a complete coaching-role status matrix, a research-only historical PCAE
run where verified weekly play-caller evidence permits, and deterministic chronological
Relationship Explorer layouts. The public Methodology page now explains Coach Effect through
expectation, decision quality, inherited environment, and evidence that repeats with the coach,
without exposing or inventing a production equation or weights. The checkpoint does not change
the production Coach Effect model or weights, database schema, serving publication, deployed
application, or existing checkpoint outputs. It does not create a Coach Effect ranking.

## Coaching evidence coverage

The matrix contains exactly 2,048 unique cells: 16 seasons × 32 teams × four roles. Cell status
reflects complete team-season coverage, not merely the presence of one row. `partial_verified`
means a sourced weekly interval exists but the rest of that team-season is unresolved.

| Role | Verified | Partial verified | Provisional | Missing | Manual review | Total |
|---|---:|---:|---:|---:|---:|---:|
| Head coach | 512 | 0 | 0 | 0 | 0 | 512 |
| Offensive coordinator | 8 | 0 | 394 | 110 | 0 | 512 |
| Quarterbacks coach | 1 | 0 | 382 | 129 | 0 | 512 |
| Play caller | 0 | 7 | 32 | 0 | 473 | 512 |

Assignment-row counts are 540 verified head-coach intervals, 15 verified and 394 provisional OC
intervals, one verified and 382 provisional QB-coach intervals, and ten verified plus 32
provisional play-caller intervals. The distinction between row and cell counts prevents a partial
late-season interval from being reported as full-season verification.

The checkpoint adds 31 explicit, source-supported 2020 play-caller designations from the cited
contemporaneous all-team table. They remain `provisional`, `medium` confidence, and
`season_designation`; the open queue now records that weekly continuity and in-season changes
still require verification. Houston retains its independently sourced Weeks 1–3, shared Week 4,
and provisional Weeks 5–17 split.

Every one of the 512 play-caller cells remains in the unresolved export because no cell yet has
both full verified weekly coverage and a closed review. The exhaustive list, including candidate
names, intervals, evidence status, source URLs, and review IDs, is
`research/coach_effect/outputs/checkpoint_11/c11-75bc9b540fe22610/unresolved_play_callers.csv`.
By season, this is all 32 teams in every season from 2010 through 2025. Seven cells have only a
verified partial interval (2012 TEN; 2015 IND and MIA; 2016 BAL, BUF, JAX, and MIN); the 32 2020
cells have provisional full-range support, with Houston additionally preserving verified Weeks
1–3 and explicitly shared Week 4. The other 473 cells require initial explicit caller evidence.

The interval audit finds 36 team-season-role cells with multiple recorded intervals: 28 head
coach, seven offensive coordinator, and one play-caller cell. These comprise 38 interval rows
beyond a one-row-per-cell representation; no QB-coach cell has a recorded in-season split.

## PCAE eligibility and historical output

The 502-play discrepancy is exactly reproduced and explained. From 2022–2025, nflverse classifies
134,138 regular-season plays as `pass` or `run`. Exactly 502 have `two_point_attempt = 1` (and
null scrimmage down), leaving 133,636 eligible plays. No extra rule was introduced to force the
historical count.

`pcae-play-eligibility-v2` requires:

- regular season and nflverse `play_type` of `pass` or `run`;
- non-null and unique `(game_id, play_id)` plus non-null team and week;
- exclusion of two-point conversions;
- a non-null scrimmage down and finite EPA after that exclusion.

For target season `S`, `pcae-expanding-prior-seasons-v1` fits the unchanged expected-pass-call
Logistic model and separate pass/run Ridge EPA models using only 1999 through `S-1`, with the
existing pre-snap features. Call Value and PCAE formulas remain unchanged. Attribution accepts
only verified, cited, non-season-designation intervals matching team, season, and week. Shared,
multiple, provisional, and uncovered matches remain unattributed; OC title is never substituted.

Research data version: `c11-75bc9b540fe22610`.

| Season | Eligible | Attributed | Unattributed | Attribution |
|---:|---:|---:|---:|---:|
| 2010 | 31,894 | 0 | 31,894 | 0.000% |
| 2011 | 32,150 | 0 | 32,150 | 0.000% |
| 2012 | 32,437 | 293 | 32,144 | 0.903% |
| 2013 | 32,850 | 0 | 32,850 | 0.000% |
| 2014 | 32,325 | 0 | 32,325 | 0.000% |
| 2015 | 32,503 | 809 | 31,694 | 2.489% |
| 2016 | 32,291 | 2,787 | 29,504 | 8.631% |
| 2017 | 31,987 | 0 | 31,987 | 0.000% |
| 2018 | 31,751 | 0 | 31,751 | 0.000% |
| 2019 | 32,046 | 0 | 32,046 | 0.000% |
| 2020 | 32,444 | 160 | 32,284 | 0.493% |
| 2021 | 33,986 | 0 | 33,986 | 0.000% |
| 2022 | 33,652 | 0 | 33,652 | 0.000% |
| 2023 | 33,836 | 0 | 33,836 | 0.000% |
| 2024 | 33,335 | 0 | 33,335 | 0.000% |
| 2025 | 32,813 | 0 | 32,813 | 0.000% |

The historical 32,813 figure is reproduced exactly as 2025 play eligibility, but not as current
verified attribution. Reproducing the latter requires the absent complete weekly 2025 caller map.
Zero attribution is unavailable evidence, never a zero PCAE estimate.

## Relationship Explorer

- **QB Journey:** one canonical QB behind season/team appearances on a fixed vertical chronology;
  connected assignments stay interval-distinct.
- **Coach Journey:** one canonical coach behind assignment appearances ordered by season, team,
  role, and start week; connected QB facts remain team-season context.
- **Team History:** team-seasons form the fixed vertical backbone; each actual QB-team-season and
  coaching interval appears in its season lane.
- **Full Network:** defaults to the complete 2010–2025 scope, uses fixed year bands, and permits
  optional coach/QB/team focus. Ordinary modes retain 1,000/2,000 API caps; Full Network uses
  measured 2,000 canonical-node/4,000 factual-relationship caps and never silently truncates.

The frontend creates deterministic coach appearances keyed by `(coach_id, assignment_key)` and QB
appearances keyed by `(player_id, team_id, season)`. Underlying API nodes remain one canonical
coach/QB identity and one team-season. Dotted continuity edges link consecutive appearances for
navigation and are explicitly distinct from factual assignment and QB-team-season edges.
Selecting any appearance resolves to the canonical ID, highlights every visible appearance and
the relevant team-season branches, and fades unrelated elements. The accessible list continues
to expose the original relationship facts and evidence rather than treating continuity as data.

The complete 2010–2025 publication measures 1,056 canonical API nodes (281 coaches, 263 QBs,
and 512 team-seasons) and 2,561 factual relationships (1,374 assignment intervals and 1,187
QB-team-season facts). The compact API payload is below its dedicated 2,000/4,000 limits. The
frontend deterministically reconstructs 3,089 visual nodes, including 16 year headers, and 4,578
visual edges, including 2,017 explicitly non-factual continuity edges. No record is silently
truncated. No N+1 PAE query is introduced; PAE remains attached in the API on
`(load_id, player_id, team_id, season)`.

## Validation

Focused development checks pass:

- coaching and Checkpoint Eleven Python: 28 passed;
- Relationship Explorer transformer, graph-selection, and page tests: 42 passed.

The final validation pass completed locally without using production infrastructure:

- offline Python: 158 run, 112 passed, 46 intentionally skipped;
- the 46 skips correspond exactly to 44 separately executed PostgreSQL/API tests and two
  separately executed opt-in network tests; all 46 passed in those environments;
- PostgreSQL/API: 44/44 passed against disposable PostgreSQL, including complete Full Network
  equality with the serving views and no truncation;
- network integration: 2/2 passed, covering official nflverse boundaries plus every registered
  coaching URL and representative content check;
- frontend unit/component: 72/72 passed, including the public Coach Effect interpretation and
  accessibility checks;
- Playwright: 33/33 passed against a disposable local publication and local API at desktop,
  tablet, and mobile sizes;
- TypeScript, ESLint, Prettier, Ruff, and Python formatting passed;
- the Vite production build passed, and two independent builds had identical filenames and
  SHA-256 hashes for all ten generated files;
- two empty-directory Checkpoint Eleven research rebuilds produced the same
  `c11-75bc9b540fe22610` identity and byte-identical bytes for all seven deterministic files;
- Git whitespace/diff checks passed.

## Remaining production gate

Production Coach Effect remains blocked until OC, QB-coach, and play-caller assignments are
comprehensively verified. Play callers require explicit evidence and weekly/in-season intervals;
shared or ambiguous intervals require support or suppression. Historical PCAE breadth,
reliability, out-of-sample Coach Effect weight estimation, uncertainty rules, and independent
approval also remain outstanding.
