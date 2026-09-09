# Predictive Feature Dictionary

Contract version: `predictive-feature-contract-v1`

Build version: `asof-scheme-v1`

Machine-readable authority: `feature_registry.csv` in the current ignored Checkpoint 13 output

This document summarizes the public contract. The CSV registry is authoritative for exact source
fields, source windows, timing, minimum samples, missingness, permissions, and versions.

## Status and permission

| Status | Meaning | Prediction permission |
|---|---|---|
| `PREDICTIVE_CORE` | deterministic, long-window, covered, stable, and chronology-safe | `YES` |
| `PREDICTIVE_CONDITIONAL` | safe contract but a shorter window, role gate, or unresolved model-selection question remains | `CONDITIONAL` |
| `DESCRIPTIVE` | useful historical context, not admitted as a future predictor here | `NO` |
| `EXPERIMENTAL` | short history or exploratory signal | `NO` |
| `UNAVAILABLE` | the approved source contract cannot currently support it | `NO` |

The registry contains 81 entries: 10 core, 9 conditional, 49 descriptive, 11 experimental, and
2 unavailable.

## Predictive core

| Feature | Source window | Definition |
|---|---:|---|
| `shotgun_rate` | 2010–2025 | explicit shotgun plays / eligible run-pass plays |
| `no_huddle_rate` | 2010–2025 | explicit no-huddle plays / eligible run-pass plays |
| `pass_rate` | 2010–2025 | pass plays / eligible run-pass plays |
| `early_down_pass_rate` | 2010–2025 | pass rate on first and second down |
| `neutral_pass_rate` | 2010–2025 | first/second-down pass rate, score -7..+7, more than 120 seconds left |
| `target_depth_short_rate` | 2010–2025 | air yards at most 9 / passes with air yards |
| `target_depth_intermediate_rate` | 2010–2025 | air yards 10–19 / passes with air yards |
| `target_depth_deep_rate` | 2010–2025 | air yards at least 20 / passes with air yards |
| `average_air_yards` | 2010–2025 | mean explicit air yards on eligible passes |
| `scramble_rate` | 2010–2025 | explicit QB scrambles / eligible run-pass plays |

## Predictive conditional

| Feature | Source window | Condition |
|---|---:|---|
| `expected_pass_rate` | 2010–2025 | prior-five-season context model only; future model admission still requires selection |
| `proe` | 2010–2025 | observed pass rate minus that safe expected rate |
| `personnel_family_11_rate` | 2016–2025 | structured personnel coverage required |
| `personnel_family_multiple_te_rate` | 2016–2025 | at least two TEs; structured coverage required |
| `personnel_family_multiple_back_rate` | 2016–2025 | at least two RB/FBs; structured coverage required |
| `personnel_family_spread_rate` | 2016–2025 | no more than one back/TE and at least three WRs |
| `personnel_family_heavy_rate` | 2016–2025 | at least two backs or at least two TEs |
| `personnel_family_empty_backfield_rate` | 2016–2025 | zero backs in explicit personnel |
| `pcae_verified_play_caller` | evidence-dependent | lagged PCAE; verified, non-shared play caller only; research-ready, not universal Coach Effect |

## Descriptive families

- Exact personnel groups: `00`, `01`, `02`, `03`, `04`, `10`, `11`, `12`, `13`, `14`, `20`,
  `21`, `22`, `23`, `30`, `31`, `32`, `40`, and `41` from 2016.
- Participation formations: explicit empty, I-form, jumbo, pistol, shotgun, singleback,
  under-center, and wildcat values from 2016. Categories are not inferred or assumed exhaustive.
- Air-yards distribution: median and 90th percentile; pass-location left/middle/right.
- Situations: red-zone pass/rush, third-down pass and air yards, fourth-down go choice, and
  fourth-down play choice conditional on going.
- Outcomes: offensive/pass/rush EPA, success rates, deep-pass EPA, and scramble EPA. These are
  performance descriptors and cannot masquerade as pure scheme tendency.
- `expected_pass_rate_descriptive_nflverse` and `proe_descriptive_nflverse` preserve the frozen
  nflverse fields for description only. They are `TARGET_SEASON_FORBIDDEN` because their
  historical model-training lineage is not established for backtesting.

## Experimental and unavailable

`motion_rate`, `play_action_rate`, `rpo_rate`, `screen_rate`, `ftn_shotgun_rate`,
`ftn_under_center_rate`, and `ftn_pistol_rate` use explicit FTN fields only and begin in 2022.
Role-specific `q_head_coach`, `q_offensive_coordinator`, `q_quarterbacks_coach`, and
`q_play_caller` remain exploratory and are not admitted to prediction.

`designed_qb_run_rate` is unavailable: no approved structured source cleanly separates designed
runs. `preseason_verified_assignment_indicator` is also unavailable until a historically dated
preseason snapshot can prove the fact was known by the August 31 cutoff.

## Feature-record grain and null semantics

The materialized grain is:

```text
(entity_type, entity_id, feature_name, target_season, feature_build_version)
```

For current scheme records, `entity_id` is deterministic
`team:<TEAM>:season:<TARGET_SEASON>`. `raw_value` is the observed prior-season value;
`feature_value` is the rolling-history standardized value. A true observed zero remains zero.
Absent source coverage remains null and receives an approved missingness reason.

Raw source → frozen Checkpoint 12 profile → Checkpoint 13 scheme row → target-season as-of row is
traceable through dataset/version/hash, intermediate artifact/hash, definition/build version, and
optional model version. Any feature that is not in the registry is rejected.
