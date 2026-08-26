# Data sources

Last updated: 2026-08-25

This register records planned and audited sources. Coverage describes the source, not a guarantee that every row or field is complete. Each ingestion run records its exact asset URL, retrieval timestamp, SHA-256 digest, byte and row counts, and observed schema.

| Source | URL | Variables | Observed/planned coverage | Collection method | Usage and licensing concerns | Known limitations |
|---|---|---|---|---|---|---|
| nflverse via nflreadpy | https://nflreadpy.nflverse.com/ | Play-by-play, EPA, CPOE, WPA, player/team stats, schedules, players, rosters, snaps, injuries, depth charts, draft, combine, contracts, NGS, participation, FTN charting | Core PBP and player stats available for 1999 onward; analysis uses 2010-2025 and warm-up uses 1999-2009 | Version-pinned Python loaders or official GitHub release assets | nflverse repositories commonly use Creative Commons licenses, but each upstream dataset must be checked and attributed separately | Release documentation can lag assets; schemas and coverage vary by dataset and season |
| nflverse play-by-play release | https://github.com/nflverse/nflverse-data/releases/tag/pbp | Play identifiers, teams, QB dropback flags, EPA/qb_epa, WPA, CPOE, sacks, scrambles, air yards, results | 1999 onward; 2010 and 2025 boundary assets returned HTTP 200 on 2026-08-25; bounded samples exposed 372 columns and each resolved 25/25 eligible dropbacks to a QB ID with finite `qb_epa` | `nflreadpy.load_pbp` or official release assets; the checkpoint audit streams bounded CSV samples without retaining them | CC BY 4.0 at the producing repository; retain attribution and source metadata | Event corrections can change historical rows; full files are large |
| nflverse player stats release | https://github.com/nflverse/nflverse-data/releases/tag/stats_player | GSIS player ID, position, games, passing EPA/CPOE, attempts, sacks, interceptions, first downs, air yards | 1999 onward; sampled 2025 regular-season CSV had 2,020 rows, 81 QB rows, and 148 columns | `nflreadpy.load_player_stats` | Attribute nflverse and document upstream fields | Season summaries may not exactly equal custom project dropback definitions |
| nflverse schedules | https://nflreadr.nflverse.com/reference/load_schedules.html | Games, regular/postseason type, scores, rest, betting context, stadium | Historical and current schedules | `nflreadpy.load_schedules` | Maintained by nflverse contributors; record exact release | Postponements and corrections require refreshes |
| nflverse players and rosters | https://nflreadr.nflverse.com/articles/dictionary_players.html | GSIS and external IDs, names, positions, birth date, college, team membership, experience | Players master plus historical rosters; 2010 and 2025 roster assets verified | `load_players`, `load_rosters`, `load_rosters_weekly` | Do not republish headshots or unrelated personal fields without need | Names and positions change; a roster row is not proof of game participation |
| nflverse injuries | https://nflreadr.nflverse.com/reference/load_injuries.html | Weekly report/practice status and injury labels | Documented since 2009; 2010 and 2025 assets verified; sampled 2025 file had 6,068 rows and 16 columns | `nflreadpy.load_injuries` | Record upstream provenance; use only football-relevant fields | Reports measure listed status, not severity; documentation previously lagged 2025 asset availability |
| nflverse depth charts | https://nflreadr.nflverse.com/reference/load_depth_charts.html | Team, position, depth order, player ID | Documented since 2001; 2010 and 2025 assets verified | `nflreadpy.load_depth_charts` | Record source change and access time | From 2025, snapshots use timestamps rather than a weekly field |
| nflverse snap counts | https://nflreadr.nflverse.com/reference/load_snap_counts.html | Offensive, defensive, and special-teams snaps | 2012 onward; 2010 returned 404 and 2012 returned 200 on 2026-08-25 | `nflreadpy.load_snap_counts` | Upstream is Pro Football Reference; do not scrape PFR directly and document downstream usage concern | Missing for 2010-2011 and occasionally incomplete players/games |
| NFL Next Gen Stats via nflverse | https://nflreadr.nflverse.com/reference/load_nextgen_stats.html | CPOE, expected completion, time to throw, air-yards measures, aggressiveness | 2016 onward | `nflreadpy.load_nextgen_stats` | Attribute NFL Next Gen Stats via nflverse | Minimum-volume filters omit small samples; not available for 2010-2015 |
| Participation via nflverse | https://nflreadr.nflverse.com/reference/load_participation.html | Players on field, personnel, formation, pass rushers, coverage fields when present | 2016 onward; source changes beginning in 2023 | `nflreadpy.load_participation` | Attribute NFL NGS via nflverse through 2022 and FTN via nflverse from 2023 | Historical fields differ; post-2023 data arrives after postseason completion |
| FTN charting via nflverse | https://nflreadr.nflverse.com/reference/load_ftn_charting.html | Motion, play action, screen/RPO, blitzers, QB-fault sack and charted pass traits | 2022 onward | `nflreadpy.load_ftn_charting` | CC BY-SA 4.0; attribution to FTN Data via nflverse is required | Not available for most of the analysis window; charting is human-generated |
| CollegeFootballData API | https://api.collegefootballdata.com/ | College production, recruiting, team strength, advanced metrics | Deferred until after the baseline model | Authenticated API using `CFBD_API_KEY` from server environment | Current terms prohibit publishing raw API data as a standalone dataset or bulk mirror; never commit key or raw responses | NFL-to-college identity matching is not reliably turnkey; quotas and historical sparsity apply |
| Official NFL team sites and media guides | https://www.nfl.com/teams/ | Coaching roles, biographies, staff announcements, interim dates | Manually collected for 2010-2025 | Human verification with source URL and access date | Store factual assignment fields and citations, not copied biographies or documents | Older pages disappear; play-calling responsibilities may be ambiguous or shared |
| Pro Football Reference | https://www.pro-football-reference.com/ | Potential historical cross-check only | No automated direct collection | Manual reference only when permitted | Direct scraping is excluded under the Sports Reference data-use policy; PFR-derived nflverse fields retain an upstream concern | Not a source for the public project pipeline unless explicit permission is obtained |

## Source acceptance rules

1. A dataset is usable only after its observed columns and season coverage pass an audit.
2. Documentation and release assets are both checked; discrepancies are recorded.
3. Missing fields remain missing. No synthetic substitute may appear in a factual table.
4. Restricted raw data is never published. Only reproducible code and compact, permitted derived results are candidates for Git.
5. Source-dependent advanced fields must degrade gracefully so the 2010-2025 core metrics remain comparable.

The reproducible checkpoint-one audit is `python3 scripts/audit_sources.py --network --download-samples`. Its PBP sample contract requires game/play context, season/week/team fields, EPA and `qb_epa`, dropback/kneel/spike/scramble flags, passer and rusher IDs, CPOE, WPA, sack/interception/attempt/completion/touchdown indicators, yards gained, air yards, and passing first downs. Resolved quarterback IDs must have the GSIS `00-` prefix.

## Checkpoint-two observed assets

The official-asset run for data version `c2-424bdc8859118b9f` retrieved 13 direct release Parquet files: play-by-play and seasonal rosters for each of 2009, 2010, 2016, 2022, and 2025, plus global schedules, players, and teams. The pipeline fetches these exact URL patterns rather than delegating retrieval, so cache identity and source-to-Bronze checksums are under project control:

- `.../releases/download/pbp/play_by_play_<season>.parquet`
- `.../releases/download/rosters/roster_<season>.parquet`
- `.../releases/download/schedules/games.parquet`
- `.../releases/download/players/players.parquet`
- `.../releases/download/teams/teams_colors_logos.parquet`

| Dataset | 2009 | 2010 | 2016 | 2022 | 2025 |
|---|---:|---:|---:|---:|---:|
| Play-by-play rows | 46,519 | 46,892 | 47,651 | 49,434 | 48,771 |
| Play-by-play columns | 372 | 372 | 372 | 372 | 372 |
| Roster rows | 2,104 | 2,152 | 3,061 | 3,134 | 3,137 |
| Roster columns | 36 | 36 | 36 | 36 | 36 |

Column names were stable across the five play-by-play and roster assets. Observed type drift is explicit in the source manifest: play-by-play `goal_to_go` changed from `Int32` to `Float64` in 2025; roster `draft_number` and `jersey_number` changed from string to integer by 2016; roster `height` was `Float64` in 2009 and `Int32` in 2025. Required checkpoint-two fields passed in every season.

Source metadata is available in both `SOURCE_MANIFEST.json` and `silver/source_manifest.parquet`, including an explicit `validation_status`. Bronze SHA-256 digests are verified against the cache after copying. `OUTPUT_CHECKSUMS.json` protects every published Bronze, Silver, and report file before cached reuse. Retrieval uses a pinned `certifi` CA bundle with certificate and hostname validation enabled.

## Checkpoint-three historical assets

The official full-history run `c3-f6c1aa118ff43b90` validated 140 Parquet assets totaling 540,760,962 bytes. The registry uses these additional release patterns:

- `.../releases/download/stats_player/stats_player_week_<season>.parquet`
- `.../releases/download/injuries/injuries_<season>.parquet`
- `.../releases/download/depth_charts/depth_charts_<season>.parquet`
- `.../releases/download/snap_counts/snap_counts_<season>.parquet`

PBP, rosters, and player statistics are expected for 1999-2025. Depth charts are expected from 2001, injuries from 2009, and snap counts from 2012. The 25 earlier dataset-season combinations are recorded as `expected_gap`, not requested and not treated as failures. The official 2012 snap-count asset exists and passes its schema contract but contains zero rows, so it is recorded separately as `ingested_empty`. The 2025 depth-chart schema differs materially from prior seasons; Silver remains partitioned by source season so upstream fields are preserved without coercing incompatible schemas.

Preflight uses cached sizes or HTTPS HEAD responses before any download. The final checkpoint-three run found all 540,760,962 source bytes in the verified cache and required 1,215,739,652 free bytes. Deterministic source manifests retain exact URLs, schemas, row counts, byte sizes, validation status, and SHA-256 values. Execution timestamps, cache status, HTTP retrieval headers, preflight measurements, and reuse status are separated into mutable `data/processed/historical/EXECUTION_LOG.json` outside the content-addressed version directory.
