# Checkpoint four report — verified coaching assignments

Date: 2026-08-27

## Outcome

Checkpoint four created the source-backed manual coaching layer for all 512 NFL team-seasons from 2010 through 2025. It contains 1,323 verified assignment rows, 1,323 normalized citations, 285 canonical coach identities, four explicit role definitions, a 16-season source-book registry, and 753 open manual reviews. No rankings, models, PAE calculations, API, or frontend were created.

| Role | Verified assignment rows | Evidence basis | Open review policy |
|---|---:|---|---|
| Head coach | 540 | Coach observed on regular-season team games in validated nflverse PBP | Multiple coaches become non-overlapping observed-week stints; later stints are flagged interim |
| Offensive coordinator | 401 | Unique formal title in the season NFL Record & Fact Book | Missing or multiple primary candidates are queued |
| Quarterbacks coach | 382 | Unique primary QB-coach title in the season NFL Record & Fact Book | Assistants are excluded; missing/multiple primary candidates are queued |
| Offensive play caller | 0 | Requires dated explicit evidence of actual duty | All 512 team-seasons are queued; title-based inference is prohibited |

## Evidence and confidence

Every verified assignment has an HTTPS citation, title, source type, access date, evidence locator, and evidence note. NFL/nflverse/official-club assets are high confidence. Official NFL books that can currently be retrieved only from a preservation mirror are medium confidence. The registry stores the SHA-256 of each reviewed PDF and records that raw source books are not committed.

Head-coach intervals use `observed_game_weeks`. OC and QB-coach rows use `season_designation`: weeks 1-17 or 1-18 encode the nominal season scope of the preseason appointment, not independently observed weekly tenure. This distinction prevents downstream code from treating the two interval types as equally strong evidence.

## Manual-review queue

The queue contains 512 explicit play-caller evidence requests and 241 unresolved formal OC/QB-coach grains. Each row includes season, canonical team, role, issue type, candidates when available, priority, status, source URL, and next-step notes. No missing role is filled by assumption. Coaching environments are intentionally deferred until interval and play-caller reviews are resolved.

## Validation and tests

`scripts/validate_coaching_data.py` validates canonical seasons/teams/roles, unique assignment and review keys, resolved coach identities, legal intervals, non-overlap of non-shared assignments, confidence and interval-basis values, verified-row citations, HTTPS URLs, complete role definitions, full 512-team-season coverage, and assignment-or-queue coverage for every team-season-role.

Offline regression tests prove the committed dataset passes, verified rows fail without citations, overlapping non-shared intervals fail, and an absent role fails unless it is routed to review. `scripts/check_coaching_sources.py` and the opt-in checkpoint-four network test verify the 16 source-book URLs independently of the offline suite.

The complete offline suite discovered 39 tests: 31 passed and eight were skipped. Six skips were PostgreSQL behavioral tests because `TEST_DATABASE_URL` was unavailable; the other two were opt-in network integrations. The checkpoint-four network integration was then called separately and passed for all 16 registered source URLs. Ruff passed for source, tests, and both checkpoint-four scripts.

## Files created or changed

- Created six compact CSVs in `data/manual/` for assignments, citations, identities, role definitions, source registry, and review work.
- Added `src/nfl_coaching_impact/coaching.py` and two validation scripts.
- Added checkpoint-four offline and network tests.
- Added PostgreSQL `assignment_confidence` and `coach_assignments.confidence_level` contracts.
- Updated README, source register, methodology, limitations, data dictionary, project plan, Makefile, and repository contract test.

## Blockers and boundaries

The review queue is deliberately not resolved with inferred play callers. Source-backed weekly OC/QB changes, shared duties, and explicit play-caller intervals require additional manual research before coaching environments or role models can be built. These are data-quality tasks, not permission to begin modeling.

## Exact next checkpoint

Checkpoint five will build leakage-safe preseason quarterback features and out-of-sample expected-performance models. It must not begin until checkpoint four is approved. Before any coach-impact modeling, the open play-caller and interval-review work must be resolved or the affected coaching environments must remain excluded/flagged.
