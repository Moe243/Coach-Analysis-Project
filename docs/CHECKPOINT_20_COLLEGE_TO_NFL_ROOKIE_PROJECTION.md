# Checkpoint 20 — College → NFL / Rookie Projection

Closeout date: 2026-09-11. Source audit: 2026-09-10.

**ROOKIE MODEL STATUS: NOT ESTIMABLE / DATA-LIMITED**

The source gate was completed and stopped modeling as required. This is a completed
data-gate research closeout, not a validated rookie model. B0, B1, B2, M1 and the optional
M2 were not fitted. No forecasts, fitted intervals or rookie Player States were created.

## Integration and scope

C19 commit `16b1c2f99985af7b4f9d40d1dff43c23eb5a499d` was fast-forwarded from
`8142227a6d2baef1656f149d6bfe3367ade546e2` and pushed to `origin/main`. Its 40 focused Python
and 89 frontend tests passed again before C20 implementation. No deployment was performed.

C20 is isolated on `codex/phase2-checkpoint-20-rookie-projection`, based on that C19 commit.
Its output version is `c20-4b0f9b23785508dc`. C20 is not merged or pushed. C19 continues to
refuse rookie projections. C18 remains NOT READY. No college coach, coach effect, fit score,
production API, database, frontend, Neon or Render change belongs to C20.

## Source gate

The reproducible audit input is `research/rookie_projection/source_audit.json`. It preserves
URLs, audit/terms dates, source versions, coverage statements, decisions and reuse concerns.
External pages were inspected for documentation and terms only; no college dataset was
downloaded. Documentation ranges below are provider claims, not observed data coverage.

| Source | Decision and evidence |
|---|---|
| Existing nflverse player master, C3 `c3-f6c1aa118ff43b90` | Reuse approved canonical QB and immutable draft/birth facts for a cohort audit. It is not an independently verified exhaustive draft ledger. |
| Existing canonical QB outcomes, `enh-04254065cafd92ba` | Reuse regular-season additive PBP totals as evaluation-only facts. Preserve source hashes and nflverse attribution. |
| [CFBD API](https://api.collegefootballdata.com/getting-started) | No configured `CFBD_API_KEY` in the execution environment and no cached college corpus. Its [terms](https://collegefootballdata.com/terms), effective 2026-08-12, permit private research/model training and derived outputs, with restrictions on raw redistribution and keys. Authenticated ingestion is a potential route, not prohibited in principle. |
| [CFBD coverage](https://api.collegefootballdata.com/data-availability) | Player season stats and rosters are documented from 2004; enriched passing/rushing from 2025. Historical completeness and a college-to-GSIS crosswalk still require validation. |
| [SportsDataverse/cfbfastR](https://github.com/sportsdataverse/cfbfastR-data) | The repository identifies ESPN as upstream. Its software license does not establish the needed upstream data/modeling permission. [Disney/ESPN terms](https://disneytermsofuse.com/english/) restrict automated extraction and AI/ML uses. No applicable separate permission was established; this project declines ingestion pending resolution. This is a project acceptance decision, not a universal legal conclusion about factual data. |
| Sports Reference college/draft sources | The approved [PFR feasibility audit](PFR_FEASIBILITY_AUDIT.md) still requires permission before ingestion. No new PFR/college-reference collection or downstream draft-data download occurred. |

Existing `data/` and `research/` artifacts were inventoried, including ignored files: no
college-production corpus, CFBD responses or college identity crosswalk was present. The NFL
master's school strings do not establish dated college careers; an NFL ESPN ID is not assumed
to equal a college ESPN/CFBD ID. No name-only or school-string matching was invented.

To reopen the gate: configure authorized CFBD access server-side (never paste the key into
chat), or provide a licensed, versioned historical college corpus; audit its actual fields,
coverage and identity mapping; preserve private raw snapshots and hashes; then reassess
chronological sample size before fitting. C20's current implementation deliberately rejects
an audit that claims an ingested college corpus rather than silently activating an untested model.

## Cohort, grain and outcome definitions

The independent universe is one canonical drafted QB per `(player_id, target_season)` for
draft years 1999–2025; `target_season = draft_year`. Membership requires only existing
canonical QB position and immutable draft facts. Future master status, latest team, last NFL
season and actual NFL participation cannot add or remove a row. Undrafted QBs and absent or
historically reclassified master identities remain outside this audited drafted cohort.
Completeness relative to all real draft picks is unknown and must be checked against a
permitted draft ledger before modeling. This limitation is not hidden by an outcome filter.

The August 31 boundary is reused from C13. Age is elapsed days since birth divided by
365.2425 at that date. Round and overall pick are retained with missingness; no current
master school/conference or NFL experience fields become college features. This is a
retrospective cohort audit, not a prospective candidate roster. Unusual delayed-entry or
supplemental-draft timing still requires individual evidence before future model admission.

NFL targets are left-joined only on canonical player ID and the draft year. Multiple team
stints stay distinct in the source and aggregate by additive totals, never mean-of-rates:

- EPA/dropback = summed `total_qb_epa` / summed `dropbacks`.
- Success rate = summed `positive_epa_dropbacks` / summed `dropbacks`.
- CPOE = summed `total_cpoe` / summed covered `cpoe_attempts`; absent coverage stays null.

These inherit approved regular-season QB dropbacks, excluding kneels/spikes, including
sacks and scrambles. The primary proposed outcome is rookie EPA/dropback; success/CPOE
are secondary observed facts only. PAE is deferred: no college-calibrated rookie expectation
exists here, so the older NFL-history prior is not relabeled as a college translation result.

The predeclared evaluation-volume screen is **100 rookie dropbacks**. It defines an audit
stratum only: low-volume QBs remain in the cohort with raw rates, and **all model eligibility
is false** because the college gate failed. Any later model must examine sensitivity to this
screen and the selection problem created by receiving NFL playing time.

| Outcome status | QBs |
|---|---:|
| EVALUATION_ELIGIBLE (volume and timing only) | 110 |
| INSUFFICIENT_SAMPLE (recorded outcome below 100 DB) | 81 |
| NO_RECORDED_DRAFT_YEAR_QB_OUTCOME | 108 |
| ROOKIE_SEASON_UNRESOLVED | 5 |
| Total drafted canonical QBs | 304 |

191 have a recorded, timing-consistent rookie outcome. 0/304 have verified college histories
or a college identity match. Missing NFL outcome is not zero EPA or proof of no NFL activity.
All 304 have observed draft year/round/pick and birth date, but no college production,
college experience, reliable school/conference history or college style features.

Five entry-year discrepancies remain visible and evaluation-suppressed:

| QB | Draft year | Reported rookie year |
|---|---:|---:|
| Marc Bulger | 2000 | 2001 |
| Drew Henson | 2003 | 2004 |
| Andy Hall | 2004 | 2005 |
| Bradlee Van Pelt | 2004 | 2005 |
| Jordan Palmer | 2007 | 2008 |

The pipeline does not advance to the reported year or first productive NFL season. It does
not resolve this discrepancy from hindsight. The entire year-by-year cohort/outcome and
missingness table is in `missingness_coverage.csv`. Rounds 1–2 contain 108 QBs / 76
volume-qualified outcomes; later rounds contain 196 / 34. Mobile/nonmobile groups cannot
be constructed without college evidence.

## Feature, validation and uncertainty contracts

The C13-compatible registry reserves college passing volume/rates, rushing usage/production,
sacks, seasons/starts and air yards, all UNAVAILABLE with `SOURCE_NOT_AVAILABLE` and predictive
permission NO. College completion rate, YPA, TD rate and INT rate divide their recorded
numerator by attempts; missing/zero denominators yield null. These formula helpers are tested
on synthetic fixtures only. They do not imply that a college profile has been observed.
School/conference fields are null; there are no arbitrary conference bonuses or college-coach
features. C13's feature-record validator enforces registration, historical timing, source
lineage and training-window cutoff; C20 additionally rejects post-cutoff availability dates.

Planned chronological folds record earlier draft-year candidates and the held-out year.
They are explicitly `NOT_RUN_SOURCE_GATE`, with no usable modeling rows. B0 rookie mean,
B1 draft only, B2 college only, M1 combined and optional M2 have null metrics and
`NOT_FIT_SOURCE_GATE`. Even draft-only fitting stops at the user's college-source gate.
No preprocessing, tuning, OOS prediction or model selection is executed. Accordingly,
RMSE/MAE/correlations/calibration, baseline improvement and fold stability are unavailable.

No historical-residual interval calibration was fitted. The 50%/80%/95% coverage table has
`n = 0` and null empirical coverage. College mobility → NFL scramble and college depth → NFL
depth translation are data-limited. No point prediction, rookie Player State, future prospect
projection or new C19 numerical response was issued. A future rookie state would need
college-derived provenance and calibrated uncertainty, with prior NFL performance absent;
no such state is implemented in this checkpoint.

## Deterministic outputs and execution

Run from the isolated worktree:

```sh
PYTHONPATH=src:. python scripts/run_checkpoint_twenty.py
```

An optional `--output-root` enables independent clean builds. Output is ignored under
`data/processed/rookie_projection/c20-4b0f9b23785508dc/`:

- Source audit JSON/CSV and `source_lineage.json` with exact approved input hashes.
- `player_identity_crosswalk.parquet`: NFL IDs resolved, college IDs null with reason.
- `rookie_state_universe.parquet`: cohort membership only, **not a generated Player State**.
- `historical_rookie_cohort.parquet` and null `college_qb_profiles.parquet`.
- `feature_registry.csv` and planned `fold_assignments.parquet`.
- Baseline/model comparison tables, empty typed OOS predictions and uncertainty coverage.
- Missingness/coverage, subgroup, style-translation and leakage audits.
- `final_decision.json` and `MANIFEST.json`; atomic `LATEST` outside the version directory.

19 files, including the manifest, describe the audit. Source artifacts are checksum-verified
before parsing; hashed and parsed bytes are the same capture. Identity includes input hashes,
source audit, C13 identity/code, relevant source code, Python/Polars versions, thresholds and
serialization, plus every analytical output hash. Immutable publications are byte-checked on
reuse; corruption fails closed. No timestamps, host paths, secrets or cache-hit state enter
analytical outputs. The fixed audit date belongs to source evidence; a changed audit changes
the content version. Temporary directory names and terminal execution logs may differ.

## Validation

- Focused C20: **32 passed**. Includes canonical/null/duplicate IDs, multi-team reconciliation,
  missing CPOE, minimum volume, independent universe, future-status/outcome mutations,
  unresolved entry years, C13 chronology/lineage, college formulas, forbidden features,
  chronological fold determinism, no fitting after the gate, checksum failure/immutable
  output protection and input/threshold/dependency version invalidation.
- Independent synthetic-fixture builds and independent full-input builds: byte-identical
  versions, all files/checksums/manifests and `LATEST`.
- Full offline regression: **412 passed, 51 skipped**, one Starlette/httpx deprecation
  warning, 1,071.50 seconds. All 32 C20 tests also passed inside this full run.
- Ruff: passed. Python formatting: passed, 167 files already formatted.
- Python compilation (`compileall -q src scripts tests`): passed. `git diff --check`: passed.

The full offline runner reuses hash-verified approved participation/FTN inputs in nflreadpy's
memory cache so old C12 tests do not download them. It does not alter assertions. The 51
intentional skips comprise 46 PostgreSQL/API tests and five opt-in network tests. They were
not executed for this offline C20 run and are not claimed as passes. C20 introduces no
production integration; C19's previous integration results are not substituted for this run.

## Decision and continuation

**C20 research source-gate closeout is complete; rookie modeling remains DATA-LIMITED.**
This is not evidence that college features cannot predict NFL performance. The question
has not been estimated. C19 rookie support remains NOT READY, C18 remains NOT READY,
and neither is bypassed by draft-only numbers. Reopen only after licensed accessible college
histories, canonical mappings and entry-year evidence pass the source and chronology audits.
