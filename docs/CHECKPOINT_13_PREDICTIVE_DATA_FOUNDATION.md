# Checkpoint 13 — Predictive Data Foundation and Scheme Engine

Status: **COMPLETE**

Data-foundation version: `c13-5e3d7a34ea4d1af5`

Baseline: `e5d931323c35944b4c720fb09f9628bcdbd34bdf`

Checkpoint 12 inputs: `c12-data-250e540b7de79385` and
`c12-final-0c746df0290c836c`

Checkpoint 13 creates the historical feature infrastructure for later Phase II work. It does not
predict quarterback performance, estimate a Player State transition, create a scenario, expose a
new API, or change production data. Outputs are deterministic ignored files beneath
`data/processed/predictive_foundation/<version>/`; PostgreSQL is intentionally not involved.

## Architecture and information boundary

Every predictive record has one registered feature, one versioned entity grain, a source season,
a target season, an August 31 target-season cutoff, raw and intermediate lineage, source and
definition versions, exposure/sample size, explicit missingness, and transformation metadata.

For target season `Y`:

- `HISTORICAL_PRIOR` permits only source seasons through `Y - 1`.
- `PRESEASON_KNOWN` permits a target-season fact only when its recorded availability date is no
  later than August 31 of `Y`. No historical dated assignment snapshots currently satisfy this
  contract, so the reserved assignment indicator remains unavailable rather than inferred.
- `TARGET_SEASON_FORBIDDEN` cannot enter a predictive snapshot.

The central validator rejects unregistered features, entity-grain mismatches, target/future
season rows, post-cutoff preseason rows, forbidden features, incomplete lineage, invalid
missingness values, and duplicate feature-record grains. `AsOfFeatureStore.target_matrix()` and
`training_matrices()` enforce the same registry and chronology rather than asking future model
code to slice arbitrary columns manually.

Supported entity contracts are QB, team, team-season, coach, coach-team-season, QB-team-season,
and scheme-team-season. Checkpoint 13 materializes scheme-team-season records; the other grains
are defined for later checkpoint builders and must still use registered features.

## Scheme Engine

The observed scheme grain is exactly `(team_id, season, feature_name)`. Raw rates are primary.
Same-season z-scores are retained only as retrospective display context. Predictive records use a
rolling five-prior-season reference distribution whose latest source season is `Y - 1`; the fit
window, mean, standard deviation, and source maximum accompany every row. This rolling reference
also limits era drift without choosing an era method for attractive modeling results.

Ten long-window features are `PREDICTIVE_CORE`: shotgun, no huddle, pass rate, early-down pass
rate, neutral-situation pass rate, short/intermediate/deep target rates, average air yards, and
scramble rate. All have 512/512 team-season coverage from 2010–2025.

The frozen nflverse `xpass` and `pass_oe` values remain descriptive because their historical
training lineage is not proven as-of safe. The checkpoint builds separate `expected_pass_rate`
and `proe` features. For each observed season, a smoothed situation model uses only the preceding
five seasons of regular-season run/pass plays. Context is down, distance band, field-position
band, quarter, and score band. The observed source season is then available only to the following
target season. Both features cover 512 team-seasons but remain `PREDICTIVE_CONDITIONAL` because
the new contract has not yet been selected in a future QB model.

Neutral situation retains the approved definition: first or second down, score differential from
-7 through +7, and more than 120 seconds remaining. Eligible run/pass tendency denominators
exclude two-point tries and kneels. Target depth is at most 9, 10–19, and at least 20 air yards.

## Personnel, formation, and mechanics

Structured personnel begins in 2016. Exact groups `00`, `01`, `02`, `03`, `04`, `10`, `11`,
`12`, `13`, `14`, `20`, `21`, `22`, `23`, `30`, `31`, `32`, `40`, and `41` remain descriptive.
Fullbacks count as backs. The six overlapping family rates—11, multiple tight end, multiple back,
spread, heavy, and empty backfield—are conditional candidates, not core. A valid covered team
that records no uses has a real zero; absent source coverage remains null/unavailable.

Under-center, pistol, empty, and other formation values come only from explicit participation or
FTN fields. Under center is not `1 - shotgun`; formation is not inferred from personnel. Motion,
play action, RPO, screen, and FTN QB-location rates remain `EXPERIMENTAL` with 2022–2025 coverage.
Designed-QB-run usage remains `UNAVAILABLE`.

Red-zone, third-down, fourth-down, pass-location, air-yard distribution, and retrospective
outcome fields remain descriptive. Fourth-down go choice stays separate from pass/run choice after
going, and neither is assigned automatically to the play caller. Performance outputs are labeled
as outcomes rather than pure scheme tendencies.

## Coach association and research signals

`coach_scheme_associations.csv` associates the team-season profile with a source-backed
assignment. It preserves `assignment_key`, coach, team, role, start/end week and dates,
verification, confidence, interim/shared/retained flags, interval basis, citation, and week
exposure. It explicitly says the scheme observation is full team-season context and not causal or
exact weekly ownership. Interval-level scheme is **NOT RELIABLE AT INTERVAL GRAIN** under the
available aggregates and is not forced.

PCAE is registered as a conditional, research-ready lagged feature only for explicitly verified,
non-shared play callers. Role-specific Q entries remain experimental and unavailable for model
consumption. No `coach_effect`, composite score, fixed weights, or 0–100 feature exists.

## Coverage, missingness, and outputs

Historical backtest snapshots cover targets 2011–2025; a forward-ready 2026 snapshot is also
created from 2025 sources. This is a **team-feature snapshot**, not a 2026 QB Player State.
Shorter-window families appear only when their prior source season
exists. Missingness uses `SOURCE_NOT_AVAILABLE`, `INSUFFICIENT_SAMPLE`, `ROLE_NOT_VERIFIED`,
`FEATURE_NOT_SUPPORTED_THAT_SEASON`, `ENTITY_NOT_PRESENT`, and `NOT_APPLICABLE`; null is never
converted to zero.

The version contains:

- `feature_registry.csv`
- `feature_availability_by_season.csv`
- `feature_availability_by_target.csv`
- `scheme_team_season.csv`
- `scheme_feature_coverage.csv`
- `scheme_feature_stability.csv`
- `personnel_team_season.csv`
- `personnel_family_team_season.csv`
- `formation_team_season.csv`
- `predictive_feature_records.csv`
- `predictive_asof_snapshot_summary.csv`
- `coach_scheme_associations.csv`
- `leakage_audit.csv`
- `missingness_summary.csv`
- `feature_status.csv`
- `checkpoint_13_summary.csv`
- `MANIFEST.json`

The manifest binds all consumed Checkpoint 12 files, every 1999–2025 PBP parquet used by the
expected-pass builder, dependency versions, transformation constants, the complete registry, and
the relevant source-code hash. Two independent empty-directory builds must have the same version
and byte-identical structured outputs.

## Validation gates and limitations

All five gates pass: registry completeness, leakage enforcement including an injected future row,
scheme grain/source windows, reproducible as-of snapshots, and the future accessor. Checkpoint 14
is ready, but was not implemented.

Limitations remain explicit: no future QB model, Player State, fit model, scenario model, Ask
Anything prediction, or college/rookie model exists. Personnel begins later than long-window PBP;
FTN has only four seasons. Scheme is observational team behavior, coach association is not causal
ownership, and the project still has no approved production composite Coach Effect.

Run the build with:

```bash
make PYTHON=.venv/bin/python checkpoint-thirteen
```
