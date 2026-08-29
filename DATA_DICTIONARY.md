# Data dictionary

This document defines the core application contract and the implemented historical Parquet tables. Full upstream schemas are versioned in each generated source manifest rather than duplicated here.

## Shared conventions

| Field | Definition |
|---|---|
| `season` | NFL season starting year, not calendar year |
| `team_id` | Repository-controlled canonical franchise/team identifier |
| `player_id` | NFL GSIS player identifier |
| `coach_id` | Repository-controlled coach identity; never a name join |
| `game_id` | nflverse human-readable game identifier |
| `data_version` | Immutable identifier for the processed data build |
| `metric_version` | Version of metric filters and formulas |
| `model_run_id` | Immutable fitted-model execution identifier |

Rates and estimates are nullable. A missing value means unavailable or not computable; it must not be silently replaced with zero.

## Generated ingestion layout

Every Silver table begins with `data_version`. QB metric tables also include `metric_version`. The current versions are immutable content-addressed build identities; generated data is not committed.

| Silver file | Grain | Implemented columns beyond lineage |
|---|---|---|
| `teams.parquet` | One current canonical franchise | `team_id`, `team_abbr`, `team_name`, `nflverse_team_id` |
| `team_aliases.parquet` | Source-system alias | `source_system`, `alias`, `canonical_abbr`, `team_id`, `first_observed_season`, `last_observed_season` |
| `players.parquet` | One valid GSIS player | `player_id`, `display_name`, `birth_date`, `position`, `college` |
| `player_external_ids.parquet` | Unambiguous player/system/ID mapping | `player_id`, `external_system`, `external_id` |
| `conflicting_player_external_ids.parquet` | Ambiguous system/ID value | `external_system`, `external_id`, `distinct_player_count`, `player_ids` |
| `games.parquet` | One selected schedule game | `game_id`, `season`, `week`, `game_type`, `game_date`, home/away team IDs and scores, home/away QB IDs, `scope` |
| `qb_game_performance.parquet` | QB-team-game | identifiers/context; all event counts, numerators, denominators, and rates listed below; `starter` |
| `qb_team_season_performance.parquet` | QB-team-season | game/start counts; all metric components and rates; `scope`, `qualifies_default`; exact prior-season fields |
| `unresolved_qb_plays.parquet` | Eligible play without one safe QB ID | game/play/season/week/team, `resolution_status`, observed passer/rusher IDs and names |
| `source_manifest.parquet` | One upstream asset | source URL, SHA-256, byte/row/column counts, full schema and required-column JSON, validation status |
| `pipeline_manifest.parquet` | One successful content build | pipeline/metric versions, season scopes, source count, season-version and table-count JSON, status |
| `data_quality_checks.parquet` | One executed check | `name`, `status`, `severity`, `failure_count`, `details` |
| `source_coverage.parquet` | Dataset-season expectation | availability expectation, status, reason, source rows and bytes |
| `season_summary.parquet` | One requested season | scope, source-row JSON, football row counts, qualification, unresolved/missing counts, coverage gaps, quality totals |

Checkpoint three also publishes season-partitioned `player_stats`, `injuries`, `depth_charts`, and `snap_counts`. Each row adds `source_dataset`, `source_season`, nullable `canonical_player_id`, and nullable `canonical_team_id` before preserving every upstream field. Snap-count PFR IDs resolve only through the unambiguous external-ID bridge; unmatched identifiers and non-team aggregate labels remain null in canonical fields. No name matching or synthetic identity is used.

Historical content-addressed version directories contain only deterministic artifacts. The mutable `data/processed/historical/EXECUTION_LOG.json` sits outside those directories and records execution timestamps, cache status, HTTP retrieval metadata, preflight measurements, and reuse status. Those operational facts may legitimately differ between runs and are not included in analytical output checksums.

## Expected-performance output layout

Checkpoint five publishes content-addressed files under `data/processed/expected_performance/<data_version>/`:

| File | Grain | Purpose |
|---|---|---|
| `preseason_features.parquet` | QB-team-season, 1999-2025 | Label plus timing-safe prior/career features, missingness, `as_of_season`, and warm-up/analysis scope |
| `model_predictions.parquet` | Model-QB-team-analysis season | All four out-of-sample candidate expectations, PAE, training cutoff, intervals, and Ridge alpha |
| `qb_pae.parquet` | QB-team-analysis season | Selected expectation, actual EPA/dropback, PAE, eligibility, reliability, and uncertainty |
| `model_evaluation.parquet` | Candidate model | OOS MAE, RMSE, R-squared, correlation, calibration, interval coverage, and selection score |
| `threshold_sensitivity.parquet` | Dropback threshold | Selected-model sensitivity at 50, 100, 200, 300, and 400 dropbacks |
| `experience_evaluation.parquet` | Roster experience group | Selected-model diagnostics for true rookies, one-prior-NFL-season players, veterans, and unknown experience when present |

`feature_version = qb-preseason-v2`. Every feature row has `as_of_season = season - 1`; `feature_source_max_season` covers QB-performance history and must be null or earlier than the target. Explicit features are age, roster-reported NFL experience and rookie status, `prior_qb_seasons`, `no_prior_qb_performance`, exact prior-season starts/usage/EPA/CPOE/success/sack/interception/touchdown rates, career starts/usage and the same career rates, opening-week team change, and prior injury-report/out weeks. `experience_group` uses roster metadata; `performance_history_group` independently distinguishes no, one, or multiple prior QB-performance seasons.

`preseason_team_id` comes only from a unique Week 1 regular-season depth-chart snapshot. Every QB-team row for the same player-season receives that same preseason team and `changed_team` value, so a later observed destination cannot enter Ridge. When no unique opening snapshot exists, `changed_team` is null, `changed_team_missing = true`, and `preseason_team_status` explains why. Draft position, draft round, and college production are null with missing indicators because no validated repository dataset supplies them. No coaching field or current-season team result is fitted.

`performance_above_expectation = actual_epa_per_dropback - expected_epa_per_dropback`. `eligibility_status = eligible` requires 200 current-season dropbacks; smaller samples remain stored. Reliability is high for eligible rows with at least 600 prior career dropbacks, medium for other eligible rows, and low below 200 current-season dropbacks. Prediction intervals are the expected value plus/minus 1.96 times an expanding residual RMSE (or prior-training outcome dispersion before enough OOS residuals exist).

QB count/component columns are `dropbacks`, `attempts`, `completions`, `sacks`, `scrambles`, `interceptions`, `passing_touchdowns`, `passing_first_downs`, `explosive_completions`, `positive_epa_dropbacks`, `cpoe_attempts`, `wpa_plays`, `air_yards_attempts`, `total_cpoe`, `total_qb_epa`, `total_wpa`, and `total_air_yards`. Derived rate columns are `epa_per_dropback`, `cpoe`, `success_rate`, `explosive_pass_rate`, `interception_rate`, `touchdown_rate`, `sack_rate`, `air_yards_per_attempt`, `air_yards_coverage_rate`, `first_down_rate`, and `wpa_per_dropback`.

Season rows add `prior_season`, `prior_starts`, `prior_dropbacks`, `prior_qualifies_default`, `prior_season_available`, and prior values for every published rate. They also expose `starts_change`, `dropbacks_change`, and a `<rate>_change` column for every published rate. These represent only season-minus-one player aggregates and are null when that boundary season is absent or, for rates, below the prior-volume rule.

## Identity and provenance

## Coach-impact output layout

Checkpoint six publishes content-addressed files under `data/processed/coach_impact/<data_version>/`:

| File | Grain | Purpose |
|---|---|---|
| `coach_modeling_exposures.parquet` | QB-coach-assignment interval | Compatible observed weeks, interval PAE, actual/expected EPA, verified/provisional status, shared fraction, exposure dropbacks, preseason controls, eligibility, and exclusions |
| `coach_effect_estimates.parquet` | Coach-role | Exploratory empirical-Bayes estimate, raw effect, corrected residual/between-coach variance, degrees of freedom, shrinkage weight, analytic standard error, conditional block-bootstrap interval, successful/attempted draws, interval availability, and identification status; unsupported roles retain null estimates |
| `preliminary_coach_rankings.parquet` | Coach-role | Estimate plus interval support, identification status, verified/provisional/shared exposure, QB seasons, quarterbacks, teams, reliability, suppressed eligibility, exclusion reason, and null rank |
| `model_comparison.parquet` | Role-model | Observation count, MAE, RMSE, and R-squared for the no-coach, fixed-effect, and partial-pooling specifications |
| `sensitivity_results.parquet` | Specification-coach-role | Estimates under provisional inclusion, shared exclusion, weighting, QB/team controls, and interval-dropback thresholds |
| `overlap_diagnostics.parquet` | Role-verification-sharing status | Exposure rows, coaches, and fractional exposure dropbacks |
| `identification_diagnostics.parquet` | Role | Team-season/coach confounding share, primary team-season-control flag, and identification decision |
| `excluded_exposures.parquet` | QB-coach-assignment interval | Explicit modeling exclusions, including intervals below 25 fractional exposure dropbacks |

`coach_interval_pae = interval_actual_epa_per_dropback - season_expected_epa_per_dropback`. Shared simultaneous duties retain separate coach rows and divide `exposure_dropbacks` equally; fractional exposure controls both model weight and minimum-exposure eligibility, while outcome arithmetic uses observed game dropbacks so it remains exact. Primary estimates use only `verification_status = verified`. Mechanical thresholds remain stored, but `identified_effect = false`, `rank_eligible = false`, and `ranking_status = suppressed_exploratory` for every checkpoint-six row.

Every deterministic table includes `data_version` and `coach_model_version`. Timestamps and reuse status are confined to the external `EXECUTION_LOG.json`.

| Table | Grain | Important fields |
|---|---|---|
| `teams` | One canonical team identity | display name, active interval |
| `team_aliases` | One source alias over a valid date interval | alias, source system, valid dates |
| `players` | One GSIS player | display name, birth date, position, college |
| `player_external_ids` | One player and external system | external system and ID |
| `coaches` | One human coach | canonical name and normalized name |
| `coach_aliases` | One observed coach-name variant | alias and source |
| `data_sources` | One registered source | URL, collection method, coverage, usage concern |
| `source_assets` | One retrieved upstream asset | URL, retrieval time, digest, schema and row count |
| `ingestion_runs` | One pipeline ingestion execution | status, code version, start/end times |

## Coaching

| Table | Grain | Important fields |
|---|---|---|
| `coach_assignments` | Coach-team-season-role-interval | role, weeks/dates, interim/shared/retained, verification, confidence, interval basis, notes |
| `coach_assignment_sources` | Assignment-source citation | source, URL, access date, evidence note |
| `coaching_environments` | Team-season interval with a stable staff combination | weeks/dates and environment key |
| `coaching_environment_members` | Environment-role-coach membership | assignment reference and shared duty |

Roles are `head_coach`, `offensive_coordinator`, `play_caller`, and `quarterbacks_coach`. Verification values are `unverified`, `provisional`, `verified`, and `conflicting`.

### Committed checkpoint-four files

| File | Grain | Purpose |
|---|---|---|
| `data/manual/coaches.csv` | Canonical coach | Stable `coach-<normalized-name>` identity used by the manual layer |
| `data/manual/coach_aliases.csv` | Observed spelling variant | Source spelling mapped to exactly one canonical coach identity |
| `data/manual/coaching_assignments.csv` | Coach-team-season-role-interval | Verified fact or provisional designation, confidence, interval basis, flags, primary URL, and notes |
| `data/manual/coach_assignment_sources.csv` | Assignment-citation | Normalized URL, title, source type, access date, evidence locator, and evidence note |
| `data/manual/coaching_change_audit.csv` | Dated coordinator stint | Source-backed in-season split retained for audit |
| `data/manual/coaching_review_queue.csv` | Team-season-role issue | Missing, multiple, or explicit-play-caller evidence work without guessed values |
| `data/manual/coaching_role_definitions.csv` | Role | Definition, acceptance rule, and commonly confused role |
| `data/manual/coaching_source_content_checks.csv` | Representative evidence check | Assignment keys, live source URL, and required content terms |
| `data/manual/coaching_source_registry.csv` | Season source book | URL, access date, SHA-256, and raw-commit prohibition |

`confidence_level` is `high`, `medium`, or `low`. `interval_basis = observed_game_weeks` means game evidence bounded the interval. `interval_basis = dated_source_weeks` means a dated source establishes the change boundary used for the interval. `interval_basis = season_designation` means a preseason source designated the coach for that season; its nominal week range is not evidence that no in-season change occurred. Season-designation OC/QB rows therefore remain `provisional` unless independent evidence verifies the full interval.

`is_interim = true` requires either content-checked citation language supporting an interim/remainder-of-season appointment or a structurally temporary observed head-coach stint: it begins after a predecessor, ends with the team season, and the next season opens with a different verified, non-interim head coach. A midseason promotion alone is not enough, and retained interim coaches require direct checked evidence because the next-season structure does not establish temporary status. `is_shared = true` requires overlapping responsibility supported for every overlapping row. The review issue `shared_duty_verification_required` preserves cases where a sourced shared interval does not resolve the surrounding weekly division of duties.

## Cross-row integrity contracts

- Validity ranges for the same `team_aliases.source_system` and `alias` cannot overlap.
- Non-shared role assignments cannot overlap any assignment for the same team, season, and role. Shared assignments may overlap only other shared assignments.
- A `verified` assignment must retain at least one citation. Inserting, deleting, or moving citation rows is checked at transaction commit.
- Each coaching-environment member must match its assignment's coach, role, team, season, sharing flag, and covering week interval.
- Each QB environment stint must match the QB season and environment team/season and fit inside the environment's week interval.
- Updates to referenced assignments, environments, and QB seasons revalidate these lineage contracts; a valid child insert cannot later be made inconsistent through a parent update.

## Football facts

| Table | Grain | Important fields |
|---|---|---|
| `games` | One NFL game | season/week/type, teams, scores, date, playoff round |
| `qb_game_performance` | QB-team-game | dropbacks, EPA, CPOE components, rates and event counts |
| `qb_seasons` | QB-team-season | actual metrics, ranks, prior-season changes, default qualification |
| `qb_environment_stints` | QB-season-coaching environment | interval exposure, metrics, starts and dropbacks |
| `team_season_features` | Team-season-feature version | lagged and retrospective environment measures with timing label |
| `qb_preseason_features` | QB-team-season-feature version | values and `as_of_season` used for prediction |
| `qb_season_star_teammates` | QB-season-qualifying teammate-rule version | player, position, prior value, percentile and rule version |

## Metric definitions

| Metric | Formula | Timing/use |
|---|---|---|
| `epa_per_dropback` | Sum of `qb_epa` / eligible dropbacks | Primary actual outcome |
| `expected_epa_per_dropback` | Out-of-sample preseason prediction | Expected model output |
| `performance_above_expectation` | Actual minus expected EPA/dropback | Default QB ranking metric |
| `cpoe` | Mean valid play-level CPOE | Secondary outcome |
| `success_rate` | Positive-EPA eligible dropbacks / dropbacks | Secondary outcome |
| `explosive_pass_rate` | Completed passes gaining 20+ yards / attempts | Secondary outcome |
| `interception_rate` | Interceptions / attempts | Secondary outcome |
| `touchdown_rate` | Passing touchdowns / attempts | Secondary outcome |
| `sack_rate` | Sacks / (attempts + sacks) | Secondary outcome/protection proxy |
| `air_yards_per_attempt` | Passing air yards / attempts | Secondary outcome |
| `air_yards_coverage_rate` | Attempts with recorded air yards / attempts | Metric completeness diagnostic |
| `first_down_rate` | Passing first downs / dropbacks | Secondary outcome |
| `wpa_per_dropback` | Summed QB-attributed WPA / dropbacks | Contextual outcome |

Eligible dropbacks are regular-season `qb_dropback = 1` plays excluding kneels and spikes and including sacks and quarterback scrambles.

## Models and serving

| Table/view | Grain/purpose |
|---|---|
| `model_runs` | One expected or coach model execution with lineage and diagnostics |
| `qb_predictions` | One out-of-sample QB-team-season prediction per model run |
| `coach_effect_estimates` | Coach-role-model run estimate, interval, sample size and warnings |
| `v_qb_rankings` | Default QB-season serving contract |
| `v_coach_rankings` | Default coach-role serving contract |
| `v_team_seasons` | Team-season context serving contract |

The ranking views retain ineligible rows for filtering and transparency, but assign `default_rank` only after restricting the ranking population to eligible, out-of-sample QB predictions or eligible coach estimates.
