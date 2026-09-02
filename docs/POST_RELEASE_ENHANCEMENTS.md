# Post-release enhancement foundation

## Scope

This additive foundation leaves the checkpoint-three history, checkpoint-five PAE model,
checkpoint-six exploratory coach analysis, manual coaching assignments, and Relationship
Explorer grains unchanged. It introduces no Coach QB Impact Score, score weights,
rankings, causal attribution, PFR collection, or source scraping.

## New deterministic artifacts

`nfl-coaching-impact enhancements` writes checksum-protected artifacts under
`data/processed/enhancements/<data-version>/`; generated artifacts remain ignored by Git.

- `qb_supplemental_statistics`: one analysis-scope `(player_id, team_id, season)` row,
  preserving multi-team seasons. It adds starter W-L-T, regular-season team points,
  completion percentage, passing/rushing/total yards, passing/rushing/total touchdowns,
  and fumbles. Results come from canonical schedules; box-score totals come from validated
  nflverse weekly player statistics. `null` stays unavailable.
- `coaching_completeness`: all 2,048 `(season, team, role)` cells for 2010–2025 and the
  four role definitions. It records assignment/review status, citation count, changes,
  interim/shared flags, unclear intervals, exact interval payload, and unresolved issue types.
- `coaching_manual_review_focus`: only cells requiring manual review or carrying uncertain
  intervals; it is an audit output, not a replacement for the source-backed manual queue.
- `COACHING_COMPLETENESS_REPORT.md`: a deterministic season/role/status summary written beside
  the audit tables, so the unresolved and unusual cells can be reviewed without treating the
  report as a source of new assignments.
- `inherited_environment_features`: team-season context whose `feature_source_max_season`
  is always before the target season. It includes prior PBP pressure-event proxy,
  opening-depth-chart WR/TE/RB prior-production composites, and scheduled-opponent prior
  pass-defense strength. No target-season final offensive result or defense control enters
  the feature set.

The published sample currently contains 1,689 supplemental QB-team seasons, 2,048
coaching-completeness cells, and 544 environment rows (2009–2025). The 2025 depth-chart
asset lacks a comparable weekly opening snapshot, so its WR/TE/RB context fields are null;
no roster membership or production is fabricated. The pressure and schedule features remain
available because they only consume the preceding season’s PBP and the published target
schedule. No league-average replacement is used in version one; fields expose observed-player
coverage and missing prior-production counts instead.

## Serving/API contract

Migration `0003_post_release_enhancements` adds load-scoped supplemental, coaching-audit,
and inherited-environment tables. `api_qb_statistics` left joins supplemental facts by the
complete `(load_id, player_id, team_id, season)` key, preserving every existing QB row even
when an additive fact is unavailable. `GET /coaching/completeness` exposes the audit matrix;
`GET /environment` exposes only timing-safe team-season context. API contract `api-v1.3`,
schema `checkpoint-7.3`, and loader `serving-loader-v4` include the enhancement data version
in the deterministic serving identity. These additive code and artifact contracts require an
explicit migration/load/release; this foundation does not mutate the existing deployed
publication by itself.

## Evidence and limits

The completeness matrix does not promote a row to verified. Verified assignments still need
their existing citation contract; provisional, conflicting, missing, and manual-review states
remain explicit. Formal OC/QB titles are not play-caller evidence. Play-calling, in-season
changes, shared duties, aliases, interim labels, and conflicting sources continue through the
existing audited/manual-review workflow. Official NFL/team materials and Record & Fact Books
remain the source hierarchy; secondary reporting may cross-check but cannot silently establish
an assignment.

NGS (2016+) and FTN (2022+) are documented only as optional validation/sensitivity sources.
They are not a 2010–2025 core dependency. The inherited environment fields are preparatory
inputs, not additions to the PAE or coach-impact models.
