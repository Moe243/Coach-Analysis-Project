# Data dictionary

## Checkpoint 17 conditional scenario research

Ignored root: `data/processed/qb_scenario/c17-9f582e4ac18d8cd6/`. Model
`qb-scenario-9f582e4ac18d8cd6`; approved C16 anchor `c16r-8c8063c5954e2a22`.

| Artifact | Grain / contract |
|---|---|
| `feature_registry.csv`, `interaction_definitions.csv` | Ten prior scheme measures, six player style measures, eight predeclared interaction families |
| `modeling_cohort.parquet` | `(player_id, team_id, target_season)`; condition basis, state identity/cutoff, scheme cutoff, raw nullable features, stint EPA/dropbacks, exclusions, diagnostic prior-team-change and multi-team flags |
| `player_feature_lineage.parquet` | Unchanged C14 style records including samples, raw/shrunk values, qualification, reliability, uncertainty and source lineage |
| `scheme_feature_lineage.parquet`, `destination_scheme.parquet` | Validated C13 prior-source records and raw team/target-year matrix; raw units are train-standardized, not target-year realized behavior |
| `rolling_folds.csv`, `hyperparameter_audit.csv` | Model/outer-year train bounds/counts; model/outer/inner/alpha training-only MAE and cutoff |
| `oos_predictions.parquet` | Stint/model; actual, exact C16 `base_epa`, diagnostic `adjustment`, `prediction = base_epa + adjustment`, empirical 50/80/95 bounds and prior calibration window/count |
| `model_comparison.csv`, `fold_metrics.csv` | Model/development-validation-all/diagnostic subset and year; n, QBs, folds, MAE/RMSE, correlations, direction, calibration |
| `interaction_coefficients.csv` | Model/year/transformed predictor coefficient in EPA/DB per training standard deviation; missingness terms explicitly suffixed; not a causal effect |
| `interval_coverage.csv` | Model/nominal interval level; validation coverage, available/missing n |
| `cluster_bootstrap.csv`, `placebo_results.csv` | Candidate/comparator/subset/cluster fixed-OOS error uncertainty and descriptive QB sign-flip diagnostics |
| `scenario_decisions.csv` | Explicit approval booleans, status and failed predeclared gates; both M1/M2 NOT SUPPORTED |
| `missingness.csv`, `leakage_audit.csv` | Null counts on eligible stints; chronology/assignment-claim gates |
| `hypothetical_scenarios_2026.parquet` | **Zero rows** because no response model passed. Typed empty artifact, not zero-valued fitted effects |
| `MANIFEST.json`, family `LATEST` | All captured input hashes, configs, code, dependencies, decisions and output checksums; atomic content-addressed publication |

`team_change` means current conditioned team absent from the player's >=50-dropback prior-season
teams; no qualifying prior season leaves it null. It is a retrospective diagnostic only.
`observed_team_count` counts all recorded target-year stints before the evaluation volume filter.
`preseason_assignment_claim = false` always. No PAE, coach-identity or Coach Effect feature enters.
OOS adjustments remain diagnostic and must not be presented as approved scenario estimates.

## C16 calibration refinement and research candidates

Ignored outputs: `data/processed/qb_projection_refinement/c16r-8c8063c5954e2a22/`.
Historical C14 and original C16 artifacts remain unchanged.

| Artifact | Grain / contract |
|---|---|
| `original_selection_audit.csv` | Outcome/challenger development metrics and frozen original family choice |
| `calibration_selection_audit.csv` | Outcome/method; qualified development folds, gain threshold, and eligibility |
| `calibration_parameters.csv` | Outcome/method/target year; bias, slope, prior-OOS fit count/window, fallback status |
| `calibrated_oos_predictions.parquet` | Canonical player/target year/outcome/method; point and predictive intervals from prior method-specific residuals |
| `model_comparison.csv`, `fold_metrics.csv`, `interval_coverage.csv` | Before/after metrics, fold stability, and marginal coverage; NONE reproduces original |
| `outcome_decisions.csv` | Unchanged acceptance checks, extra accuracy guard, selected method, separate outcome status |
| `candidate_universe_2026.parquet` | One canonical 2025 QB with ≥50 historical dropbacks; no current-roster or team claim |
| `candidate_player_states_2026.parquet` | One player/2026 state, C14 profile lineage, source cutoff, uncertainty, candidate-only label |
| `candidate_feature_records_2026.parquet` | C14 feature-record contract with new source version and source/fit seasons ≤2025 |
| `candidate_predictors_2026.parquet` | Existing 19-feature allowlist, one player/2026 row; no target-team/coach/Scheme fields |
| `projections_2026.parquet` | Player/2026/approved outcome; point, 50/80/95 bounds, as-of, versions, calibration metadata, research label |
| `forward_model_parameters.json` | Unchanged B2 extension and prior-OOS calibration parameters used for forward projections |
| `forward_state_audit.json` | A/reporting-error classification; C13 team versus C14 historical-state distinction |
| `leakage_audit.csv`, `MANIFEST.json` | Chronology/allowlist checks, captured input hashes, configuration/code/dependencies, atomic output checksums |

`label = TEAM-INDEPENDENT RESEARCH PROJECTIONS`; `active_roster_claim = false`.
2026 has 57 candidate states, 57 EPA projections, and no PAE forecasts. Missing candidate estimates
remain null. A prediction interval is not a coefficient confidence interval, availability estimate,
team assignment, ranking, or causal effect.

## Checkpoint 16 team-independent projection artifacts

Ignored research outputs: `data/processed/qb_projection/c16-c7cee27a36eb0445/`.
Model identity: `qb-projection-c7cee27a36eb0445`; state identity: `c14-43283062e788e686`.
These are historical OOS research artifacts, not serving rows or approved live forecasts.

| Artifact | Grain / meaning |
|---|---|
| `projection_feature_registry.csv` | Allowlisted CORE state/header predictor, source, and timing rule |
| `state_predictors.parquet` | One independent frozen `(player_id, target_season)` state; no target environment |
| `state_input_lineage.parquet` | Selected C14 feature records, including timing, raw/shrunk values, reliability, uncertainty, and missingness |
| `projection_cohort.parquet` | State plus canonical all-stint outcome at player-season grain; 50-dropback evaluation eligibility |
| `cohort_coverage.csv`, `missingness_coverage.csv` | Cohort reconciliation and per-season feature coverage, with nulls preserved |
| `fold_assignments.csv` | Outcome/model/target-year fold, training season bounds and row counts, target count, tuning history, and calibration history; row membership follows cohort eligibility and year |
| `baseline_comparison.csv`, `model_comparison.csv` | B0/B1/B2/M1 metrics, with development/validation/all-OOS scopes distinguished |
| `oos_predictions.parquet` | One player-season/outcome/model point prediction, 50/80/95 interval bounds, calibration history, and explicit B1 fallback flag |
| `selected_oos_projections.parquet` | Development-selected model rows with data/model/state identity, as-of date, approval status, and non-live use label |
| `subgroup_diagnostics.csv` | Retrospective diagnostic population metrics; never predictors |
| `interval_coverage.csv` | Model/outcome/scope/nominal-level observed coverage and available interval count |
| `bootstrap_comparison.csv` | QB-cluster paired OOS MAE-gain uncertainty, not player prediction intervals |
| `selected_model_parameters.json` | Selected models/cutoff, baseline definitions and source identity, per-fold training-only Ridge/preprocessing parameters; full rules reside in the manifest |
| `leakage_audit.csv` | State, fit/tuning, and calibration chronology checks |
| `checkpoint_decision.csv` | Selected target, calibration/acceptance results, research status |
| `forward_readiness.csv` | Explicit absent 2026 state / zero-forward-projection status |
| `MANIFEST.json` | Content identity, input hashes, configuration, code/dependencies, all output checksums |

`outcome_epa` is summed QB EPA divided by summed dropbacks across team stints. `outcome_pae`
subtracts the invariant existing preseason expectation; a missing stint expectation leaves PAE
null without deleting EPA. Prediction intervals are null until 100 strictly historical same-model
OOS residuals exist. Team labels and target outcomes are evaluation-only. No new team-assignment,
Scheme, Coach Effect, ability score, or ranking field is introduced.

## Checkpoint 15 Player × Scheme fit artifacts

Generated files live under ignored
`data/processed/player_scheme_fit/c15-c4d7c86f56238a49/`; original run
`c15-2ac7553234223553` remains preserved.

| Artifact | Grain / contract |
|---|---|
| `fit_feature_registry.csv` | One registered Player State, Scheme, or predeclared interaction feature |
| `modeling_cohort.parquet` | One entering state per `(player_id, target_season, cohort_version)`; target team and outcome remain separately sourced |
| `preseason_target_team_assignments.parquet` | One resolved/ambiguous player-target-season assignment with evidence type/date/precision, source hash, as-of date, and verification |
| `target_team_contract.csv` | One accepted evidence-family contract with date rule, precedence, and required lineage |
| `target_team_source_audit.csv` | One audited source family with acceptance decision and additive coverage |
| `target_team_coverage_by_season.csv` | One target season with state, safe-assignment, retrospective-participant, matching-team, and eligibility coverage |
| `target_team_coverage_by_category.csv` | One evaluation-only returning-veteran, team-changer, rookie, or other/new-entrant coverage row |
| `rolling_fold_assignments.csv` | One player-state fold membership; training season is always earlier than fold season |
| `model_comparison.csv` | One outcome-model aggregate over rolling out-of-sample predictions |
| `rolling_fold_metrics.csv` | One outcome-model-fold metric row |
| `model_predictions.parquet` | One `(player_id, target_team_id, target_season, outcome, model)` prediction |
| `interaction_definitions.csv` | One predeclared football-defined Player × Scheme interaction |
| `interaction_coefficients.csv` | One estimable standardized interaction coefficient per fold; empty when M2 is unavailable |
| `interaction_effects.parquet` | Paired M2-minus-M1 prediction delta; empty rather than zero when M2 is unavailable |
| `fold_stability.csv` | Fold/model estimability and qualified-interaction diagnostics |
| `team_change_validation.csv` | Rolling predictions restricted to safely identified team changers |
| `environment_change_validation.csv` | Large as-of Scheme-change subset plus explicit unavailable verified coach-change status |
| `portability_sensitivity.csv` | Dropback, personnel-family, and PCAE/M3 sensitivity status |
| `bootstrap_uncertainty.csv` | QB-cluster bootstrap M2-minus-M1 MAE delta or explicit non-estimability |
| `permutation_placebo.csv` | Deterministic interaction placebo result or explicit non-estimability |
| `missingness_coverage.csv` | Feature and exclusion counts without zero-filling unsupported values |
| `fit_approval_decision.csv` | Fit status, standalone-quantity decision, interaction permission, and Checkpoint 16 boundary |
| `leakage_audit.csv` | Player/scheme source season, assignment cutoff, and entering-state grain gates |
| `checkpoint_15_summary.csv` | Compact completion and handoff gates |
| `MANIFEST.json` | Content identity, upstream versions, grains, counts, and output checksums |

Player uncertainty columns retain feature-specific reliability, missingness, shrinkage weight,
standard error, and interval. Scheme metadata retains feature status, predictive permission,
sample size, and missingness. Exact dated evidence stores its source date. Immutable draft facts
store August 31 only as a conservative pre-cutoff availability upper bound and label the precision
accordingly; it is not represented as the actual draft date. `outcome_pae` is always actual minus
expected EPA/dropback on the complete player-team-season key.

## Checkpoint 14 QB Player State artifacts

`qb_state_universe` records one outcome-independent player-target-season membership with its
August-31 evidence basis. `player_states` records one header at the same grain, including safe age
and experience proxies, prior/career exposure, state availability, and the distinct preseason EPA
ability estimate. `qb_state_feature_records` is the authoritative long-form vector with raw and
shrunk values, numerator, denominator, uncertainty, reliability, timing, lineage, and missingness.

`qb_team_season_profiles` preserves player-team-season-feature stints. `qb_season_profiles`
rebuilds player-season features from additive totals. `qb_state_evaluation_links` connects the
separate retrospective QB-team-season cohort without creating or backfilling Player States.

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
| `coach_effect_estimates.parquet` | Coach-role | Exploratory empirical-Bayes estimate, raw effect, weighted Ridge effective/residual degrees of freedom, residual/between-coach variance, shrinkage weight, analytic standard error, conditional block-bootstrap interval, successful/attempted draws, interval availability, and identification status; unsupported roles retain null estimates |
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

### Checkpoint-seven serving layer

Every `serving_*` fact includes `load_id`; composite foreign keys prevent facts from crossing versions. `serving_loads` records schema, loader, API, historical, PAE, coach model/data, and enhancement data versions plus combined upstream and manual-input manifest digests. `serving_publication` selects exactly one visible load. The current candidate uses schema `checkpoint-7.5`, loader `serving-loader-v7`, and API `api-v1.5`. Manual CSV rows are parsed from the exact captured bytes used for their digest, and a final pre-publication hash check fails closed if any file changes during loading.

| Table/view | Grain or contract |
|---|---|
| `serving_teams`, `serving_team_aliases` | Canonical team and source alias per load |
| `serving_players`, `serving_player_external_ids` | GSIS player and external identifier per load |
| `serving_games`, `serving_qb_games`, `serving_qb_seasons` | Game, QB-game-team, and QB-team-season facts with scope |
| `serving_qb_pae` | One out-of-sample expected/actual/PAE record per QB-team-season |
| `serving_qb_supplemental` | Additive QB-team-season starter record, completions/attempts, production, sacks, fumbles/lost, yards/attempt, and adjusted net yards/attempt; complete key matches `serving_qb_seasons` |
| `canonical_qb_game_performance`, `canonical_qb_team_season_performance`, `canonical_qb_pae` | Versioned production-bound copies containing only identities whose canonical position is `QB`; source checkpoints remain immutable |
| `qb_eligibility_exclusions` | Explicit audit rows removed from QB publication, retaining source dataset, canonical position, and exclusion reason |
| `serving_team_season_statistics` | One team-season with W-L-T, points, PBP-derived yards/TD/turnovers/sacks, EPA and success rates, and within-season competition ranks |
| `serving_coaching_completeness` | One `(team_id, season, role)` audit cell with final Eleven-B status, evidence version, source URLs, and person/no-role interval evidence. `verified` means a named assignment is verified; `verified_no_designated_role` means the sourced absence of a separate role holder is verified; `partial`, `provisional`, `conflicting`, and `unresolved` preserve incomplete states. The legacy API filter `missing` aliases `unresolved`. No-role cells never create coach identities or assignments. |
| `serving_inherited_environment` | One team-season, strictly preseason context row with `feature_source_max_season < season` |
| `serving_coach_assignments`, `serving_coach_citations` | Source-backed role interval and evidence |
| `serving_review_queue` | Manual-review item with full source payload |
| `serving_coach_exposures` | QB-assignment interval with observed/fractional dropbacks and assignment-matching coach, team, season, role, weeks, verification, confidence, basis, and shared status; deferred triggers revalidate changes from either side |
| `serving_coach_effects`, `serving_coach_rankings` | Exploratory estimate and suppression contract per coach-role |
| `serving_source_manifests`, `serving_pipeline_manifests` | Source and pipeline/model provenance |
| `api_qb_statistics`, `api_qb_pae` | Published analysis-only, canonical-position `QB` metrics and PAE; direct PAE attachment uses `(load_id, player_id, team_id, season)` |
| `api_team_season_statistics` | Published team-season result, offense, efficiency, and rank facts |
| `api_coaching_completeness`, `api_inherited_environment` | Complete coaching-role audit and leakage-safe inherited context |
| `api_coach_impact`, `api_coach_comparisons` | Effects plus identification and suppression fields |
| `api_coaching_assignments`, `api_coaching_network_edges` | Role intervals and staff edges with source/target verification, confidence, shared/provisional flags, full intervals, and overlap bounds |
| `api_source_citations`, `api_review_queue_summary` | Evidence and unresolved-review counts |
| `GET /relationships/explorer` coach node | One canonical `coach_id`; serialized node ID is `coach:<coach_id>` |
| `GET /relationships/explorer` QB node | One canonical GSIS `player_id`; serialized node ID is `qb:<player_id>` |
| `GET /relationships/explorer` team-season node | One `(team_id, season)`; serialized node ID is `team-season:<team_id>:<season>` |
| Relationship coach-assignment edge | One `assignment_key`; retains role, weeks, interval basis, verification, confidence, shared/interim/retained/provisional flags, citations, and publication version |
| Relationship QB-team-season edge | One `(player_id, team_id, season)`; retains dropbacks, actual/expected EPA per dropback, PAE, qualification, eligibility, reliability, out-of-sample status, metric/model/data versions, and publication version. Missing PAE fields remain null. |

Team-history and team-anchored full-network scopes source QB-team-season records independently from `api_qb_statistics`. Coaching role, verification, and provisional filters apply only to coach-assignment relationships; PAE joins retain the complete `(load_id, player_id, team_id, season)` key.

Checkpoint Eleven adds no database grain. Its frontend tree/network projection creates a coach
appearance keyed by `(coach_id, assignment_key)` and a QB appearance keyed by
`(player_id, team_id, season)`; each retains the canonical API node ID. Team-season node IDs are
unchanged. A `visual_continuity` edge links consecutive appearances of one canonical identity and
is explicitly distinct from factual `coach_assignment` and `qb_team_season` relationships.

The ignored Checkpoint Eleven research export contains `coaching_coverage.csv` at one
`(season, team_id, role)` cell, `unresolved_play_callers.csv` at the same filtered grain,
`eligibility_reconciliation.csv` and `season_attribution.csv` at season grain, and
`historical_pcae.csv` at verified caller/team/season/assignment-interval grain. Coverage status
`partial_verified` means at least one interval is verified but complete team-season coverage is
not. Research PCAE retains the formula/model/eligibility/data versions and explicitly states that
shared or ambiguous plays were excluded.

### Post-release QB/team and environment fields

`api_qb_statistics` now exposes additive `starter_wins`, `starter_losses`, `starter_ties`,
`starter_decisions`, `team_points_scored`, `completion_percentage`, `passing_yards`,
`rushing_yards`, `total_yards`, `passing_touchdowns`, `rushing_touchdowns`,
`total_touchdowns`, and `fumbles`. Results and points derive from regular-season nflverse
schedules; box-score fields derive from regular-season nflverse weekly player statistics.
These are factual supplemental fields, not PAE inputs. A null field is unavailable, not zero.

`api_inherited_environment` exposes only inputs known entering a target season:
prior-season PBP pressure-event protection proxy, opening-depth-chart WR/TE/RB prior-production
scores and coverage, plus target-schedule opponents' prior-season pass-defense strength.
`feature_source_max_season` guards timing. There is no league-average fill in version one and
no target-season final offensive performance or defensive control in the first equation work.

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

## Frontend display contract

Checkpoint eight creates no analytical tables. Its default statistics grain is one published QB-team-season row from `api_qb_statistics`, augmented with the matching `api_qb_pae` row and source-backed staff intervals. The Relationship Explorer uses only the canonical node and factual relationship grains documented above; Checkpoint Eleven appearance and continuity elements are deterministic presentation state rather than duplicated analytical identities. Visual positions, selection, focus, and URL filters are likewise presentation state. `null` remains unavailable; it is never displayed as zero. The interface preserves `data_version`, `metric_version`, `model_version`, `training_cutoff_season`, `eligibility_status`, `reliability_label`, verification/confidence fields, interval bounds and basis, shared/provisional flags, identification and suppression reasons, and coach-specific bootstrap support.

The legacy staff-overlap endpoint remains available, but `/network` now renders `GET /relationships/explorer`. Both Cytoscape and the accessible cards receive the same canonical node and relationship objects; the client does not reconstruct PAE or coaching semantics from separate requests. Coach-page quarterback links remain team-season overlaps filtered to published player position `QB`; they are not a new coach-exposure fact.
