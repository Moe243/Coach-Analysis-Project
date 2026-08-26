# Checkpoint one report

Date: 2026-08-25

## Outcome

Checkpoint one established the analytical and engineering contracts for the NFL Coaching Impact Engine. A post-review correction pass resolved all five schema/view findings and added executable PostgreSQL behavior tests. No frontend, production data pipeline, generated coach rankings, or model results were created, and checkpoint two has not begun.

## Post-review corrections

1. QB and coach serving views now calculate `dense_rank` only after filtering to eligible rows; ineligible rows remain visible with a null rank.
2. Moving a citation validates both its old and new assignment, so a verified assignment cannot be orphaned by updating `assignment_id`.
3. Deferred lineage guards require coaching-environment members to match the assignment's coach, role, team, season, sharing status, and covering interval. QB stints must match the QB season and environment team/season and remain inside the environment interval. Parent-row updates are guarded too.
4. Shared role assignments may overlap only other shared assignments; any shared/non-shared overlap is rejected, while the existing non-shared/non-shared exclusion remains in force.
5. Date-valid team aliases for the same source and alias may not overlap, including open-ended ranges.

The former SQL text-inspection test was removed. `tests/test_postgres_behavior.py` installs the full schema in an isolated PostgreSQL schema and verifies successful and rejected transactions plus both ranking views.

## Available data

- Core 2010-2025 play-by-play and player/team metrics
- Schedules, results, rosters, stable player IDs, draft and combine information
- Injury reports covering the analysis boundary
- Depth charts across the analysis boundary
- Snap counts from 2012
- NGS and participation from 2016
- FTN charting from 2022

## Missing or limited data

- Snap counts for 2010-2011
- NGS before 2016 and FTN charting before 2022
- Public historical blocking grades and clean pressure attribution
- A complete, structured coach-role/play-caller history
- A guaranteed NFL-to-college player crosswalk
- Any design that could prove a causal coaching effect

## Manual verification required

Head coach, offensive coordinator, play-caller, QB coach, interim/shared status, and assignment dates must be sourced for every team-season. Missing or conflicting facts remain explicitly marked and never guessed.

## Architecture decision

Use Parquet and Polars for reproducible files/transforms, embedded DuckDB for analytical queries, PostgreSQL for curated application data, and later FastAPI plus Next.js. Keep orchestration CLI-driven and avoid additional services.

## Modeling decision

Use a leakage-safe Elastic Net baseline with a histogram-gradient-boosting challenger. Produce out-of-sample PAE with expanding-season evaluation. Use frequentist role-specific mixed models and QB-season block bootstrap for coach associations; keep crossed-role modeling as sensitivity analysis.

## Files created

- Repository guidance and required root documentation
- Feasibility, architecture, project-plan, and checkpoint-report documents
- PostgreSQL schema and serving views
- Manual coaching-assignment CSV template
- Source-audit script and offline contract tests
- Behavioral PostgreSQL constraint and serving-view tests
- Minimal Python package metadata and Make targets

## Verification performed

- `python3 -m unittest discover -s tests -v`: 14 tests passed in the fully configured run (8 offline/source-contract tests and 6 PostgreSQL behavior tests).
- `python3 -m unittest tests.test_postgres_behavior -v`: 6/6 passed against PostgreSQL 16.15, proving alias intervals, mixed sharing, citation reassignment, environment-member lineage, QB-stint lineage, and eligible-only QB/coach ranks.
- `python3 scripts/audit_sources.py --network --download-samples`: all 12 boundary asset checks and all 5 samples passed on 2026-08-25.
- The PBP audit streamed 45 rows for 2010 and 68 for 2025 to find 25 eligible dropbacks in each. Both samples had 372 columns, 25/25 finite `qb_epa` values, 25/25 resolved QB IDs, and no missing required fields.

The PostgreSQL tests require `TEST_DATABASE_URL`; without it, the general offline discovery command reports the six integration cases as skipped rather than pretending that SQL text proves behavior. `make test-postgres` fails fast when the URL is absent.

## Blockers and unresolved external actions

- No connected GitHub repository exists, so this checkpoint is local only.
- A public repository license has not been selected; `pyproject.toml` therefore declares all rights reserved temporarily.
- CFBD enrichment needs a user-owned API key and remains deferred.
- Writing the verified 2010-2025 coaching table is a major manual workstream.
- PostgreSQL must be available to run the behavioral database suite; the repository does not add a service or container in checkpoint one.

## Exact next checkpoint

Checkpoint two is a boundary-season data vertical slice for 2009, 2010, 2016, 2022, and 2025. One CLI must create validated Bronze/Silver Parquet, canonical IDs, QB game/season metrics, and data-quality/leakage reports. It must not create coach rankings or frontend code.
