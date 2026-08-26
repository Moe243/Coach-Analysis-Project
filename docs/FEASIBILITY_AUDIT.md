# Data feasibility audit

Audit date: 2026-08-25

## Executive result

The core 2010-2025 quarterback analysis is feasible with public, reproducible data. The largest non-technical dependency is a manually verified coaching assignment dataset. Advanced context is uneven across eras and must enhance rather than define the core model.

## Direct observations

Read-only HTTP checks against official nflverse GitHub release assets produced:

| Asset | Boundary/result |
|---|---|
| Play-by-play | 2010 HTTP 200; 2025 HTTP 200 |
| Regular-season player stats | 2010 HTTP 200; 2025 HTTP 200 |
| Rosters | 2010 HTTP 200; 2025 HTTP 200 |
| Injuries | 2010 HTTP 200; 2025 HTTP 200 |
| Depth charts | 2010 HTTP 200; 2025 HTTP 200 |
| Snap counts | 2010 HTTP 404 as expected; 2012 HTTP 200 |

Representative 2025 CSV downloads showed:

| File | Rows | Columns | Key finding |
|---|---:|---:|---|
| Regular-season player stats | 2,020 | 148 | 81 quarterback rows; GSIS IDs and passing EPA/CPOE present |
| Rosters | 3,137 | 36 | GSIS and multiple external IDs present |
| Injuries | 6,068 | 16 | Weekly report/practice statuses and GSIS IDs present |

The reproducible source audit also streamed bounded play-by-play samples without retaining either full season:

| Season | Rows scanned | Columns | Eligible QB dropbacks | Finite `qb_epa` | Resolved QB IDs |
|---:|---:|---:|---:|---:|---:|
| 2010 | 45 | 372 | 25 | 25 | 25 |
| 2025 | 68 | 372 | 25 | 25 | 25 |

Both samples contained every required game/play, season/week/team, EPA/`qb_epa`, dropback, kneel/spike/scramble, passer/rusher ID, CPOE, WPA, sack, interception, attempt, completion, touchdown, yards-gained, air-yards, and passing-first-down field. Resolved quarterback IDs used the GSIS `00-` prefix. These are sample-level feasibility checks, not season-level completeness claims.

## Availability by requested capability

| Capability | Classification | Coverage/decision |
|---|---|---|
| EPA/dropback, success, explosive passes, interceptions, TDs, sacks, air yards, first downs, WPA | Direct plus derivation | Core 2010-2025 PBP |
| CPOE | Direct where populated | Verify 2010 completeness; NGS alternative starts 2016 |
| Stable player identity | Direct | GSIS master and roster IDs |
| Team record and playoffs | Direct plus derivation | Schedules/results |
| Draft and combine profile | Direct | nflverse loaders; audit identity completeness in checkpoint two |
| Experience, career starts, team changes | Derivable | Historical rosters, games, starts, and stats |
| Injury burden | Derivable proxy | Reports since 2009; listed status is not severity |
| Receiving/rushing/defense context | Derivable proxy | Player/team/PBP data; separate lagged from current-season measures |
| Protection quality | Weak proxy | Snap continuity from 2012, sacks/hits/time-to-throw where available |
| NGS advanced passing | Direct, partial era | 2016 onward; never required for the full-window score |
| Participation/personnel | Direct, partial era | 2016 onward; source transition in 2023 |
| FTN charting | Direct, partial era | 2022 onward; attribution required |
| Coaching assignments and play-callers | Manual | Official team sources/media guides; no complete audited API |
| College production/recruiting | Deferred | CFBD after baseline; key and redistribution controls required |
| All-Pro/Pro Bowl labels | Excluded from baseline | Avoid current-season leakage and extra licensing dependency |
| True causal coach effect | Unavailable | Observational adjusted association only |

## Important discrepancies and risks

The nflverse availability page previously reported no 2025 injury data, while the official `injuries_2025` release asset is now populated. Each pipeline run must inspect release assets and schema directly and retain the observation date.

Some nflverse data are derived from PFR, OverTheCap, NFL NGS, or FTN and carry source-specific concerns. Direct PFR scraping is excluded. `DATA_SOURCES.md` is the controlling register.

## Manual verification workload

There are 512 team-seasons in the 2010-2025 window before midseason splits. Each requires four role checks and potentially multiple interval rows. Verification should proceed team-season by team-season with explicit `provisional`, `verified`, or `conflicting` status. Automated name suggestions may assist later, but cannot promote a row to verified.

## Feasibility conclusion

Proceed with a boundary-season vertical slice before downloading all seasons. The core score must rely on fields available throughout the window. NGS, participation, FTN, and snap-count features should be optional enrichments or sensitivity analyses with missingness/era controls.
