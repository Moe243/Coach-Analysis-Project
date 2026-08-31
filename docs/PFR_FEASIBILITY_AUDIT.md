# Pro Football Reference Feasibility Audit

## A. Executive Summary

**Decision: PERMISSION REQUIRED BEFORE INGESTION**

As of 2026-08-31, Pro Football Reference (PFR) is not approved as an ingested source for this project. Sports Reference permits ordinary human viewing and limited, attributed sharing or reuse from individual pages, but its current Terms expressly restrict automated collection, substitute databases, and use of its content to support machine-learning methods that predict, classify, label, or score inputs. Those restrictions directly conflict with systematic historical ingestion and with the Expected EPA/PAE modeling workflow.

PFR contains useful standard, advanced, and curated quarterback statistics. Most standard fields are already available from or reproducibly derivable through nflverse. The most distinctive PFR advanced fields are sourced from third-party charting, begin only in 2018 (with some beginning in 2019), and do not cover the project's full 2010-2025 analysis window. PFR's Total QBR column is an ESPN metric, not a PFR-authored open statistic. None of these fields justifies introducing an unlicensed, fragile dependency.

The project may continue to use PFR manually for limited validation and source discovery, with page-level attribution and access dates, provided it does not build a systematic copy of the site. It may link users to PFR. It must not scrape, bulk export, ingest, redistribute, or use PFR content in models unless Sports Reference and any relevant third-party rightsholders grant written permission covering the intended collection, storage, publication, and predictive use.

This is a technical and project-risk assessment, not legal advice.

## B. Audit Date and Scope

- **Audit date:** 2026-08-31
- **Project window:** 2010-2025 analysis seasons, with 1999-2009 warm-up data
- **Audited properties:** current Sports Reference/PFR access rules; public technical access; manual export and Stathead paths; candidate quarterback, advanced-passing, team-context, and curated fields; historical coverage; nflverse overlap; model/UI/cross-check suitability; attribution and reproducibility risk
- **Out of scope:** implementing a scraper, collecting PFR records, changing the data pipeline, fixing Checkpoint Eight defects, building the Relationship Explorer, obtaining legal advice, or interpreting a paid Stathead subscription as a separate data license
- **Repository baseline:** the existing source register already excludes direct PFR scraping and treats PFR-derived nflverse fields as carrying upstream concerns

Primary official materials reviewed:

- [Sports Reference Data Use](https://www.sports-reference.com/data_use.html)
- [Sports Reference Terms of Use](https://www.sports-reference.com/termsofuse.html) (last updated 2023-05-19)
- [Bot Traffic and Request Limiting](https://www.sports-reference.com/bot-traffic.html) (updated 2024-05-29)
- [How to Download Data](https://faq.sports-reference.com/portal/en/kb/articles/how-to-download-data)
- [Sharing Information](https://www.sports-reference.com/sharing.html)
- [Stathead Terms of Use](https://stathead.com/stathead/termsofuse.html)
- [PFR Data Coverage](https://www.pro-football-reference.com/about/coverage.htm)
- [PFR Advanced Statistics](https://www.pro-football-reference.com/about/advanced_stats.htm)
- [PFR Data Sources](https://www.pro-football-reference.com/about/sources.htm)
- [PFR Contact and Citation Guidance](https://www.pro-football-reference.com/about/contact.htm)

Policy pages should be re-audited immediately before any future collection because terms, access controls, and upstream licenses can change.

## C. Current Policy Findings

| Activity and status | Official source (reviewed 2026-08-31) | Concise interpretation | Project consequence |
|---|---|---|---|
| Human viewing and linking — clearly permitted | [Terms of Use](https://www.sports-reference.com/termsofuse.html); [Sharing Information](https://www.sports-reference.com/sharing.html) | Ordinary human use and linking are contemplated by the public service. | PFR pages may be consulted manually and linked from research notes or UI copy. |
| Limited page-level sharing/reuse — clearly permitted within stated limits | [Terms of Use](https://www.sports-reference.com/termsofuse.html); [Data Use](https://www.sports-reference.com/data_use.html) | The Terms generally welcome sharing data from an individual page, subject to restrictions and explicit credit. | Suitable only for small, attributed examples or manual validation—not a season-spanning project database. |
| Manual Export Data / CSV copy — technically possible; downstream use remains constrained | [How to Download Data](https://faq.sports-reference.com/portal/en/kb/articles/how-to-download-data) | The official UI supports one table/page at a time. | Technical availability is not a license for systematic ingestion, model use, or redistribution. |
| Automated retrieval — permission required / policy-risky | [Terms of Use](https://www.sports-reference.com/termsofuse.html); [Bot Traffic](https://www.sports-reference.com/bot-traffic.html) | Express written permission is required for automated means that adversely affect performance or access; operational rate limits also apply. | No crawler or automated downloader should be created. Staying below a block threshold would not establish permission. |
| Database or service substitute — clearly prohibited | [Terms of Use](https://www.sports-reference.com/termsofuse.html); [Data Use](https://www.sports-reference.com/data_use.html) | A material database, archive, or substitute for Sports Reference services is prohibited. | Systematic local replication of PFR tables is outside the permitted project posture. |
| AI/ML and predictive use — clearly prohibited absent permission | [Terms of Use](https://www.sports-reference.com/termsofuse.html); [Data Use](https://www.sports-reference.com/data_use.html) | The Terms prohibit using content to train, fine-tune, prompt, instruct, or support machine-learning methods that predict, classify, label, or score inputs. | PFR-derived features must not enter Expected EPA, PAE, coach-impact, ranking, or other predictive/scoring models without written permission. |
| Redistribution — ambiguous by field; permission required | [Data Use](https://www.sports-reference.com/data_use.html); [PFR Data Sources](https://www.pro-football-reference.com/about/sources.htm) | Sports Reference notes that it cannot redistribute some datasets because of third-party licenses. | Public raw or row-level PFR-derived data must not be committed or served; permission from Sports Reference alone may not cover every field. |
| Stathead subscription — access permitted under subscription, bulk/model rights not established | [Stathead Terms](https://stathead.com/stathead/termsofuse.html) | Provides individual or seat-based access under separate subscription Terms. | A subscription does not, by itself, grant bulk extraction, model-training, sublicensing, or redistribution rights. A separate service order/license would be required. |
| Custom dataset request — permission route available | [Data Use](https://www.sports-reference.com/data_use.html); [Feedback](https://www.sports-reference.com/feedback/) | Sports Reference directs custom requests through its feedback process and states a $5,000 minimum. | This is the documented route for a commercial/custom license inquiry, not a guaranteed approval. |

The distinction is material: **what a browser can technically display or export is broader than what this project is authorized to collect and use**. The project should seek a written license describing exact fields, seasons, collection method, retention, derived outputs, predictive use, public display, redistribution, and attribution before ingestion.

## D. Technical Access Findings

- Public PFR HTML pages and human-facing table exports exist. The export workflow is page-scoped and manual.
- Sports Reference states that it does not provide a public API, citing third-party data licenses and its business model.
- The bot-control page reports blocking above 20 requests per minute for most Sports Reference sites (and 10 for FBref/Stathead). This is an operational ceiling, **not authorization** to automate below it.
- A single, non-aggressive request for `https://www.pro-football-reference.com/robots.txt` from the audit environment received a Cloudflare managed-challenge page rather than reliably inspectable robots content. No bypass was attempted. Robots rules therefore could not be independently verified in this environment.
- Several public PFR/Stathead pages were retrievable through indexed search but returned access errors to direct automated opening. Cloudflare behavior, blocking, and client-rendered pages make unattended builds fragile.
- PFR provides no documented, versioned schema or immutable release artifacts. HTML IDs, column headings, comments, pagination, and table structure may change without a data-version contract.
- Stathead offers richer human query capabilities, but it is still a subscription interface—not a reproducible bulk-data API or automatically sufficient downstream-use license.

Accordingly, an automated collector would be both policy-incompatible and operationally unreliable. This audit performed no scraping, table extraction, anti-bot bypass, authenticated access, or data retention.

## E. PFR Statistics Inventory

Classification used below:

- **A. MODEL FEATURE** — approved for predictive/model input under current evidence
- **B. DESCRIPTIVE UI STATISTIC** — approved only for descriptive display, not modeling
- **C. VALIDATION/CROSS-CHECK ONLY** — manual, limited validation or source discovery; not ingested
- **D. EXCLUDED** — do not collect or use from PFR under the present project posture

No PFR field qualifies as **A**. A field that can be recomputed from nflverse may be shown in the product, but its value should be calculated from nflverse and attributed accordingly—not copied from PFR.

Each candidate row below must be read together with its group's shared metadata. This avoids repeating the same URL and coverage statement while preserving every requested audit attribute; a row-level statement overrides the group default.

| Inventory group | Page/source type and example official page | Default grain | Regular season / playoffs | Earliest / latest usable season | Historical gaps and missingness behavior | Definition and coverage-change status | Intended-use policy status |
|---|---|---|---|---|---|---|---|
| Standard quarterback | PFR standard passing leaderboard and player season tables: [2025 passing](https://www.pro-football-reference.com/years/2025/passing.htm), [example player page](https://www.pro-football-reference.com/players/T/TagoTu00.htm) | Player-team-season; player pages may add career and `TOT` rows | Both, on separate tables/tabs | 1920 / 2025 generally; project uses 2010-2025 | Null when a denominator is zero or a field is not applicable; traded players may have team rows plus an aggregate row | Standard fields are broadly stable, but PFR corrections and page presentation can change; field-specific historical starts are stated below | Manual individual-page use only; systematic ingestion and model use require permission |
| Advanced passing | Sportradar-charted PFR advanced table: [2025 advanced passing](https://www.pro-football-reference.com/years/2025/passing_advanced.htm), [definitions](https://www.pro-football-reference.com/about/advanced_stats.htm) | Player-team-season | Both, on separate tabs | 2018 / 2025 for core fields; 2019 / 2025 for `*` fields | Structurally absent before coverage starts; ratios null when denominators are zero; charting corrections may occur | Coverage changes at 2018 and 2019; provider definitions are charting-dependent and must not be assumed stable across unrelated sources | Third-party rights plus Sports Reference ingestion/model restrictions; excluded except limited manual cross-checks explicitly marked **C** |
| Team context | PFR season index, standings, offense, and team pages: [2025 season](https://www.pro-football-reference.com/years/2025/index.htm), [2025 team advanced](https://www.pro-football-reference.com/years/2025/advanced.htm) | Team-season unless stated otherwise | Both, presented separately | 1920 / 2025 for team-season totals generally; project uses 2010-2025 | Null when not applicable; ranks depend on season population and tie convention | Standard results are stable but can be corrected; derived SRS, ranks, drive, and advanced definitions/coverage can change | Manual individual-page use only; systematic ingestion and model use require permission |

Across all groups, “nflverse/open equivalent” identifies direct or alternative access, “derive” identifies whether nflverse play-by-play can recreate the football concept, and the final cell records uniqueness, intended use, and the exact A/B/C/D recommendation. “Complete” means no known structural gap in the 2010-2025 project window, not a warranty that every value is non-null or immutable.

### Standard quarterback and curated season fields

Example source: `https://www.pro-football-reference.com/years/2025/passing.htm` or a player page such as `https://www.pro-football-reference.com/players/T/TagoTu00.htm`.

| Field | PFR definition / source type | Grain and split | Coverage in project window; gaps/change risk | nflverse or open equivalent | Value and policy classification |
|---|---|---|---|---|---|
| Games (`G`) | Games played; standard passing table | Player-team-season; regular season and playoffs separable | Complete 2010-2025; traded-player total rows can change grain | nflverse player stats, rosters, PBP | Commodity cross-check; **C** |
| Starts (`GS`) | Games started | Player-team-season; regular/playoffs | Complete 2010-2025 | Schedules/PBP/rosters; nflverse player stats where available | Useful validation only; **C** |
| Completions (`Cmp`) | Completed forward passes | Player-team-season; regular/playoffs | Complete 2010-2025 | nflverse player stats/PBP | Direct equivalent; **C** |
| Attempts (`Att`) | Forward pass attempts | Player-team-season; regular/playoffs | Complete 2010-2025 | nflverse player stats/PBP | Direct equivalent; **C** |
| Completion percentage (`Cmp%`) | `100 * Cmp / Att` | Player-team-season | Complete; denominator conventions must match | Derive from nflverse | UI should compute locally; PFR copy **C** |
| Passing yards (`Yds`) | Net yards gained on completed forward passes, excluding sack yards | Player-team-season | Complete | nflverse player stats/PBP | Direct equivalent; **C** |
| Passing TD (`TD`) | Touchdown passes | Player-team-season | Complete | nflverse player stats/PBP | Direct equivalent; **C** |
| Interceptions (`Int`) | Passes intercepted | Player-team-season | Complete | nflverse player stats/PBP | Direct equivalent; **C** |
| TD percentage (`TD%`) | `100 * TD / Att` | Player-team-season | Complete | Derive from nflverse | UI should compute locally; PFR copy **C** |
| INT percentage (`Int%`) | `100 * Int / Att` | Player-team-season | Complete | Derive from nflverse | UI should compute locally; PFR copy **C** |
| Yards/attempt (`Y/A`) | Passing yards divided by attempts | Player-team-season | Complete | Derive from nflverse | UI should compute locally; PFR copy **C** |
| Adjusted yards/attempt (`AY/A`) | `(passing yards + 20*passing TD - 45*interceptions) / attempts` | Player-team-season | Complete; null with no attempts | Derive from nflverse standard box score | PFR validation only; **C** |
| Passer rating (`Rate`) | NFL formula: cap each of `(Cmp/Att-.3)*5`, `(Yds/Att-3)*.25`, `(TD/Att)*20`, and `2.375-(INT/Att*25)` to 0-2.375; sum, divide by 6, multiply by 100 | Player-team-season | Complete; null with no attempts | Derive from nflverse | Not unique; PFR validation only; **C** |
| Sacks (`Sk`) | Times sacked on pass plays | Player-team-season | Complete for project window | nflverse player stats/PBP | Direct equivalent; **C** |
| Sack yards (`Yds`) | Yards lost on sacks | Player-team-season | Complete for project window | nflverse player stats/PBP | Direct equivalent; **C** |
| Sack percentage (`Sk%`) | `100 * sacks / (attempts + sacks)` | Player-team-season | Complete | Derive from nflverse | Already in project metric family; **C** |
| Net yards/attempt (`NY/A`) | `(pass yards - sack yards) / (attempts + sacks)` | Player-team-season | Complete | Derive from nflverse | UI should compute locally; **C** |
| Adjusted net yards/attempt (`ANY/A`) | `(pass yards + 20*pass TD - 45*INT - sack yards) / (attempts + sacks)` | Player-team-season | Complete | Derive exactly from nflverse | Valuable descriptive comparator, but PFR ingestion unnecessary; **C** |
| Passing first downs (`1D`) | First downs produced by completed passes | Player-team-season | PFR coverage since 1977; complete 2010-2025 | nflverse PBP/player stats | Direct/derivable equivalent; **C** |
| Passing success rate (`Succ%`) | Percentage of pass plays gaining at least 40% of yards-to-go on first down, 60% on second down, or 100% on third/fourth down | Player-team-season | PFR coverage since 1977; definition is not identical to positive-EPA success | Derive this rule or the project's separately named positive-EPA measure from nflverse PBP | Definition-sensitive validation only; **C** |
| Fourth-quarter comebacks (`4QC`) | Team win/tie where offense scores while trailing in Q4/OT and tying/winning scoring drive concludes in Q4/OT | QB-season/career; regular/playoff context shown by PFR | Coverage since 1950; manual judgment/corrections possible | Derivable only with a separately specified algorithm; no identical nflverse field | Distinct curated context, but manual spot-check/link only; **C** |
| Game-winning drives (`GWD`) | Team win where possession starts tied/down one score in Q4/OT and winning offensive drive concludes in Q4/OT | QB-season/career | Coverage since 1950; manual judgment/corrections possible | Approximate derivation from PBP, not guaranteed identical | Distinct curated context, but manual spot-check/link only; **C** |
| Total QBR (`QBR`) | ESPN's proprietary play-level efficiency metric, including context, opponent adjustment, credit allocation, and a 0-100 scale | QB-season/game; regular season | ESPN introduced it in 2011 and publishes historical series from 2006; formula/inputs not fully reproducible | No open exact equivalent; project EPA/dropback and PAE answer different questions | Not a PFR-authored open field; exclude absent ESPN license; **D** |

### PFR advanced passing fields

Example source: `https://www.pro-football-reference.com/years/2025/passing_advanced.htm`. PFR states that advanced data are provided by Sportradar, are available from 2018 onward, and fields marked with an asterisk begin in 2019. Tables expose regular-season and playoff tabs. Definitions below follow [PFR's advanced-statistics guide](https://www.pro-football-reference.com/about/advanced_stats.htm).

| Field | Exact PFR meaning | Grain / split | Coverage and missingness | nflverse/open equivalent | Value and policy classification |
|---|---|---|---|---|---|
| Intended air yards (`IAY`) | Air yards on all pass attempts | QB-team-season; regular/playoffs | 2018-2025; absent 2010-2017 | `air_yards` from nflverse PBP; NGS 2016+ | Existing open path; **C** |
| IAY/pass attempt (`IAY/PA`, ADOT) | Intended air yards divided by pass attempts | Same | 2018-2025; null with no attempts | Derive from nflverse PBP | Existing open path; **C** |
| Completed air yards (`CAY`) | Air yards on completed passes | Same | 2018-2025 | Derive from nflverse `air_yards` on completions | Existing open path; **C** |
| CAY/completion (`CAY/Cmp`) | Completed air yards divided by completions | Same | 2018-2025; denominator missingness | Derive from nflverse | Existing open path; **C** |
| CAY/pass attempt (`CAY/PA`) | Completed air yards divided by attempts | Same | 2018-2025 | Derive from nflverse | Existing open path; **C** |
| Yards after catch (`YAC`) | Receiving yards minus air yards, subject to PFR's fumble-yard caveat | Same | 2018-2025; definition/correction risk | nflverse player stats/PBP include YAC-compatible fields | Existing open path, reconcile caveat; **C** |
| YAC/completion (`YAC/Cmp`) | YAC divided by completions | Same | 2018-2025 | Derive from nflverse | Existing open path; **C** |
| Batted passes (`Bats`)* | Passes batted at the line | Same | 2019-2025; absent earlier | No full-window open equivalent identified | Potentially useful mechanics context but restricted and short; **D** |
| Throwaways (`ThAwy`) | Passes intentionally thrown away | Same | 2018-2025 | FTN charting 2022+ (`is_throw_away`) | Short and charting-dependent; **D** |
| Spikes (`Spikes`) | Passes intentionally spiked | Same | 2018-2025 | nflverse PBP `sp`/spike flag | Existing open path; **C** |
| Drops (`Drops`) | Catchable passes missed with reasonable effort | Same | 2018-2025; subjective charting | FTN 2022+ `is_drop`; no complete 2010-2025 equivalent | Useful receiver-context proxy but post-treatment and restricted; **D** |
| Drop percentage (`Drop%`) | Drops divided by pass attempts | Same | 2018-2025 | Derive only where permitted FTN coverage exists | Restricted/incomplete; **D** |
| Bad throws (`BadTh`) | Throws uncatchable with normal effort, excluding spikes/throwaways | Same | 2018-2025; subjective | FTN catchable/interception-worthy proxies 2022+, not identical | Distinct but restricted/incomplete; **D** |
| Bad-throw percentage (`Bad%`) | Bad throws divided by pass attempts excluding spikes/throwaways | Same | 2018-2025 | No exact full-window open equivalent | Distinct but restricted/incomplete; **D** |
| On-target throws (`OnTgt`)* | Throws that would have hit the intended target | Same | 2019-2025; subjective, absent 2018 | FTN catchable-ball proxy 2022+, not identical | Distinct but restricted/incomplete; **D** |
| On-target percentage (`OnTgt%`)* | On-target throws divided by attempts excluding spikes/throwaways | Same | 2019-2025 | No exact full-window open equivalent | Distinct but restricted/incomplete; **D** |
| Pocket time (`PktTime`) | Average time from snap to throw or pocket collapse | Same | 2018-2025; charting definition risk | NFL NGS time-to-throw 2016+, not identical | NGS is preferred documented alternative; **D** |
| Blitzes (`Bltz`) | Plays with five or more pass rushers or a defensive back rushing | Same | 2018-2025 | nflverse participation 2016+ pass-rusher count; FTN 2022+ blitzers | Existing open alternatives with explicit definitions; **D** |
| Hurries (`Hrry`) | QB forced to throw early or chased because of pressure | Same | 2018-2025; subjective | Participation `was_pressure` 2016+ is broader; no exact equivalent | Useful but restricted/definition-sensitive; **D** |
| Hits (`Hits`) | QB knocked down after throwing, excluding sacks | Same | 2018-2025; subjective | No exact complete open equivalent identified | Useful protection context but restricted; **D** |
| Pressures (`Prss`) | PFR pressure composite based on charted hurries, hits/knockdowns, and sacks | Same | 2018-2025; provider/definition-sensitive | Participation pressure 2016+; PBP sacks; not identical | Avoid mixed definitions; **D** |
| Pressure percentage (`Prss%`) | Pressures per dropback under PFR's denominator | Same | 2018-2025 | Derive a clearly named nflverse pressure rate where coverage permits | PFR value excluded; **D** |
| Scrambles (`Scrm`) | Scrambles from designed pass plays | Same | 2018-2025 | nflverse PBP `qb_scramble` | Existing open path; **C** |
| Yards/scramble (`Yds/Scr`) | Scramble yards divided by scrambles | Same | 2018-2025 | Derive from nflverse PBP | Existing open path; **C** |
| RPO plays/yards (`RPO` family)* | Charted run-pass-option plays and associated pass/rush attempts and yards | Same | 2019-2025; absent 2010-2018 | FTN 2022+ `is_rpo`; no full-window open equivalent | Tactical but restricted and incomplete; **D** |
| Play-action attempts/yards (`PA` family)* | Charted play-action pass attempts and passing yards | Same | 2019-2025; absent 2010-2018 | FTN 2022+ `is_play_action` | Tactical but restricted and incomplete; **D** |

`*` means the PFR definition page identifies the measure as available only from 2019. Missing historical advanced values must remain unavailable; they must never be zero-filled or back-cast.

### Team and environmental fields

Example source: `https://www.pro-football-reference.com/years/2025/index.htm`, team pages, standings, and team advanced pages such as `https://www.pro-football-reference.com/years/2025/advanced.htm`.

| Field | PFR meaning / source | Grain | Coverage and change risk | nflverse/open equivalent | Value and policy classification |
|---|---|---|---|---|---|
| Wins/losses/ties and win percentage | Official results and standings | Team-season; regular/postseason separately | Complete 2010-2025 | nflverse schedules | Direct equivalent; **C** |
| Points for/against/differential | Team scoring totals | Team-season | Complete | nflverse schedules/PBP/team stats | Direct/derivable; **C** |
| Margin of victory (`MoV`) | Average scoring margin | Team-season | Complete | Derive from schedules | Direct/derivable; **C** |
| Strength of schedule (`SoS`) | PFR/SRS schedule-strength component | Team-season | Complete, but tied to SRS methodology and revisions | Build a transparent prior-year/opponent measure from schedules | Method-sensitive; manual validation only; **C** |
| Simple Rating System (`SRS`) | Point-differential rating adjusted for schedule | Team-season | Complete | Reimplement transparently from schedules if needed | Not needed as copied input; **C** |
| Offensive/defensive SRS (`OSRS`, `DSRS`) | PFR decomposition of SRS | Team-season | Complete; method-sensitive | Transparent project-derived alternatives | Same-season controls could be post-treatment; **D** for modeling, **C** validation |
| Team passing/rushing totals and rates | Standard team box-score aggregation | Team-season | Complete | nflverse team stats/PBP | Direct equivalent; **C** |
| Offensive yards and yardage rank | Total offense and its league ordinal rank | Team-season | Complete; tied ranks and presentation may change | nflverse team stats/PBP; compute rank from frozen project population | Direct/derivable; **C** |
| Passing offense and rank | Team passing production and league ordinal rank | Team-season | Complete; ranking population/ties require specification | nflverse team stats/PBP | Direct/derivable; **C** |
| Rushing offense and rank | Team rushing production and league ordinal rank | Team-season | Complete; ranking population/ties require specification | nflverse team stats/PBP | Direct/derivable; **C** |
| Offensive points and rank | Team offensive scoring and league ordinal rank; defensive/special-teams scoring must be scoped explicitly | Team-season | Complete totals; attribution/ranking conventions can differ | nflverse PBP permits transparent offensive-point attribution | Define and compute locally; PFR validation **C** |
| Turnovers | Offensive interceptions plus lost fumbles under the table's convention | Team-season | Complete; team/opponent table orientation can be misread | nflverse PBP/team stats | Direct/derivable; **C** |
| Sacks allowed | Times the team's passers were sacked | Team-season | Complete in project window | nflverse PBP/player/team stats | Direct/derivable; **C** |
| Drive statistics | Starts, plays, yards, points, turnovers, time and outcomes per drive | Team-season | Complete in project window; drive parsing can differ | Derive from nflverse PBP or use documented PBP drive IDs | Definition-sensitive validation; **C** |
| Scoring percentage / turnover percentage per drive | Share of drives ending in scores/turnovers | Team-season | Complete in project window; denominator differences possible | Derive from PBP | Validation only; **C** |
| Average starting field position | Mean drive start | Team-season | Complete in project window | Derive from PBP | Validation only; **C** |
| Team advanced passing context | Team aggregate of PFR advanced fields above | Team-season | 2018+, starred fields 2019+ | NGS/participation/FTN alternatives by coverage | Restricted/incomplete; **D** |
| Opponent-adjusted ranks and league ranks | Ordinal rank of a displayed team statistic | Team-season | Depends on table and tie treatment | Compute from project's own frozen dataset | UI may show project-computed ranks; PFR copy **C** |
| Playoff qualification/results | Postseason participation and game outcomes | Team-season/game | Complete | nflverse schedules | Direct equivalent; **C** |
| Coach names on team pages | Named team head coach and staff references | Team-season/page | Historical page conventions and midseason changes require citations | Existing verified coaching-assignment pipeline using NFL publications/PBP | Not a replacement for role verification; **C** |

## F. Coverage by Year

| Season range | Standard QB/team statistics | PBP-derived PFR measures | Advanced Sportradar passing | Project implication |
|---|---|---|---|---|
| 1999-2009 warm-up | Available | PFR reports full PBP-derived coverage since 1977 | Unavailable | Standard fields are redundant with nflverse; do not introduce PFR. |
| 2010-2015 analysis | Available | Available | Unavailable | Advanced PFR cannot support this portion of the analysis window. |
| 2016-2017 analysis | Available | Available | Unavailable | nflverse NGS/participation begins in 2016 and is the preferable documented alternative. |
| 2018 analysis | Available | Available | Core advanced fields begin | One-year definition boundary; starred fields still absent. |
| 2019-2021 analysis | Available | Available | Core plus starred fields | Short, third-party charted period; still permission-restricted. |
| 2022-2025 analysis | Available | Available | Core plus starred fields | FTN charting via nflverse supplies a documented alternative for selected tactical fields from 2022. |

PFR separately reports snap-count coverage beginning in 2012, matching the upstream concern already documented for nflverse snap counts. Data availability does not cure usage restrictions. Historical PFR records and advanced tables can be revised; PFR does not expose immutable release versions or checksums.

## G. Grain and Definition Review

PFR pages mix player-team-season rows, traded-player aggregate (`TOT`) rows, player-career rows, team-season rows, league-season rows, game logs, splits, and playoff/regular-season tabs. A naive collector could double count a traded player, combine regular and postseason records, or silently change denominators. PFR player identifiers are site-specific and are not the project's canonical GSIS identifiers.

The following semantic differences require explicit reconciliation even for manual cross-checks:

- A PFR pass attempt excludes sacks; project EPA/dropback includes attempts, sacks, and QB scrambles while excluding kneels and spikes.
- PFR `Succ%` must not be equated with the project's positive-EPA success rate.
- PFR advanced `Prss`/`Prss%` is a charted composite; nflverse participation pressure is not definitionally identical.
- PFR pocket time is not necessarily equivalent to NFL NGS time to throw.
- PFR drops, bad throws, on-target throws, hurries, hits, RPO, and play action involve charting judgments and provider definitions.
- 4QC and GWD are curated, rule-based quarterback credits rather than direct box-score facts.
- Team SRS/SoS values are retrospective and should not enter preseason models unless lagged and independently specified.
- Regular-season and playoff tables must remain separate. The current project publishes regular-season PAE; PFR playoff tabs cannot be merged implicitly.
- Missing advanced seasons mean unavailable, not zero. A structural coverage indicator is mandatory in any licensed future use.

## H. NFLVERSE Overlap

The current stack already covers the defensible core:

| Need | Preferred source/path | Why it is preferable |
|---|---|---|
| Attempts, completions, yards, TD, INT, sacks, first downs | nflverse PBP and player/team stats | Stable GSIS IDs, existing manifests/checksums, full project window, reproducible definitions |
| EPA/dropback, WPA, CPOE, success | nflverse PBP | Already validated and directly aligned with project outcomes |
| Air yards and YAC | nflverse PBP/player stats | Available without PFR; coverage can be published explicitly |
| Scrambles and sack rate | nflverse PBP | Existing play-level flags support exact project definitions |
| Time to throw, expected completion, aggressiveness | NFL Next Gen Stats via nflverse, 2016+ | Documented alternative, though not full-window and still requires upstream attribution |
| Pressure / participation context | nflverse participation, 2016+ | Play-level context with stated source changes; definitions must remain distinct from PFR |
| Play action, RPO, motion, blitzers, throwaways, drops | FTN charting via nflverse, 2022+ | Documented coverage and fields; CC BY-SA attribution obligations apply |
| Team record, playoffs, opponent context | nflverse schedules and PBP | Reproducible and already in the pipeline |
| Passer rating, NY/A, ANY/A, rankings | Calculate from nflverse inputs | Transparent formulas and version-controlled outputs |

The nflverse `dictionary_pfr_passing` dataset exposes PFR-derived advanced fields, and snap-count assets also originate upstream from PFR. The project's existing warning remains necessary: an intermediary repository is not a mechanism for evading PFR/Sportradar restrictions. Although the nflverse-data repository applies CC BY 4.0 to rights it controls, third-party rights and contractual limits can remain. PFR-derived datasets require separate upstream permission review before new public/model use.

## I. Unique / Potentially Valuable PFR Fields

Potentially distinctive fields are 4QC/GWD, bad throws, on-target throws, drops, batted passes, hurries, hits, pocket time, pressure composition, RPO/play-action summaries, and Total QBR. Their practical value is limited here:

- **4QC/GWD:** useful narrative context with published definitions, but not a preseason model feature. Link or manually spot-check; build an independently specified PBP version only if needed.
- **Bad/on-target throws, drops, batted passes, hurries/hits:** conceptually helpful for separating QB, receiver, and protection context, but charted, subjective, third-party sourced, and only available late in the project window.
- **Pocket time and pressure:** potentially useful, but NGS/participation provides a documented alternative from 2016. Definitions must not be conflated.
- **RPO/play action:** useful scheme descriptors, but PFR's series begins in 2019 and FTN's open path begins in 2022. These should remain optional sensitivity/context variables, never silently imputed across earlier seasons.
- **Total QBR:** ESPN's proprietary metric and not reproducible from public inputs. It should be excluded, not reverse engineered.

No unique field is both sufficiently licensed, full-window, definitionally stable, reproducible, and important enough to approve PFR ingestion today.

## J. Model-Usage Permission and Risk

PFR content must not be used in the Expected EPA, PAE, coach-impact, ranking, eligibility, feature-selection, labeling, calibration, validation-target, or other predictive/scoring workflows under the current Terms. This includes manually exported tables and values obtained through Stathead; acquisition method does not change the intended-use restriction.

If permission is later obtained, the license must explicitly cover predictive machine learning and derived metrics. The model version would then need to hash the licensed source artifact, license/version identifier, extraction specification, coverage map, and transformation code. Preseason cutoffs and post-treatment rules would still apply. Same-season PFR team context could leak or absorb the outcome and must not enter preseason expectation features.

Current classification: **no PFR candidate is A. MODEL FEATURE**.

## K. UI-Usage Permission and Risk

The UI may safely link to a relevant PFR page and may use project-computed fields such as ANY/A when calculated from nflverse. A small, manually selected PFR factual example may be defensible under the individual-page sharing language when directly attributed, but persistent systematic display across players/seasons could become a database substitute and should not be implemented without permission.

Do not expose copied PFR tables, advanced charting series, PFR ranks, or QBR in the application. Do not label an independently calculated value as “PFR” unless its formula and result truly follow PFR's definition and the provenance is clear. A Stathead paywall or account must never be proxied through the API or frontend.

## L. Validation / Cross-Check Use

Permitted conservative use is human, sparse, and non-ingested:

1. Open an individual public PFR page manually.
2. Compare a small number of standard totals against project results.
3. Record the page URL, access date, season, regular/postseason scope, and observed discrepancy in a review note—not a replicated table.
4. Investigate differences through primary or reproducible sources.
5. Do not treat PFR as an automated test oracle or commit copied row-level data.

Cross-check priorities are games, attempts, sacks, passing yards, and ANY/A arithmetic. Advanced-provider differences should be documented rather than forced to reconcile. PFR can also point reviewers toward underlying official sources, but the final citation should prefer the primary source when available.

## M. Recommended Alternative Sources

| Statistics replaced | Recommended source and access method | Historical coverage | Licensing/use advantage | Major limitations |
|---|---|---|---|---|
| Core QB/team performance, air yards, sacks, scrambles | [nflverse PBP releases](https://github.com/nflverse/nflverse-data/releases/tag/pbp) and [player stats](https://nflreadr.nflverse.com/reference/load_player_stats.html), using pinned release assets/loaders | 1999 onward for this project's core sources | Reproducible releases and a repository-level [CC BY 4.0 license](https://github.com/nflverse/nflverse-data/blob/main/LICENSE.md) for rights the licensor controls | Attribute nflverse, record exact assets, and review every upstream field; corrections can change history and third-party rights remain. |
| Time to throw, expected completion, aggressiveness, air-yards context | [NFL Next Gen Stats via nflverse](https://nflreadr.nflverse.com/articles/dictionary_nextgen_stats.html), through documented loaders | 2016 onward | Documented and machine-readable alternative to copying PFR presentation | Minimum-volume filters, upstream NFL terms, and no 2010-2015 coverage. |
| Participation, pass-rusher count, pressure context | [nflverse participation](https://nflreadr.nflverse.com/articles/dictionary_participation.html), through documented loaders | 2016 onward | Play-level reproducible access with source notes | Provider/field changes from 2023; pressure is not definitionally identical to PFR. |
| Play action, RPO, motion, blitzers, throwaways, drops | [FTN charting via nflverse](https://nflreadr.nflverse.com/articles/dictionary_ftn_charting.html), through documented loaders | 2022 onward | Documented fields and CC BY-SA attribution path are preferable to PFR extraction | Human-charted, short coverage, share-alike/attribution obligations; do not extrapolate backward. |
| Results, records, playoff outcomes, schedule strength | [nflverse schedules](https://nflreadr.nflverse.com/reference/load_schedules.html) and PBP with version-controlled formulas | Historical schedules cover the project window | Inputs and algorithms can be frozen and checksummed | Retrospective schedule strength leaks if used as a same-season preseason feature; corrections/postponements require refreshes. |
| Coaching facts | Official NFL/team releases, media guides, and Record & Fact Books, manually cited | Project-specific 2010-2025 verification | Primary/official evidence is preferable to copying a PFR staff label | No uniform API; ambiguous intervals and duties must remain in the review queue. |
| QBR-like evaluation | Existing nflverse EPA/dropback and out-of-sample project PAE | 2010-2025 publication with 1999-2009 warm-up | Transparent, versioned definitions avoid a proprietary ESPN metric | Do not call either measure QBR; they measure different constructs. |
| 4QC/GWD-like narrative | Independently specified algorithm over nflverse PBP | PBP available from 1999 for the project | Reproducible and auditable without copying PFR's curated series | Use a distinct project label unless exact equivalence is validated; edge-case adjudication is still needed. |

Other commercial charting providers may be considered only through explicit licenses that cover predictive use and public derived outputs. “Publicly visible” should never be treated as synonymous with “open data.”

## N. Reproducibility Risks

- No public versioned PFR API or immutable release bundle exists.
- Cloudflare and request blocking can make the same automated request succeed or fail across environments.
- Human exports are page-scoped, mutable, and not content-addressed.
- Historical corrections can change values without an asset checksum or release identifier.
- HTML schemas and table locations can change.
- Provider and definition boundaries occur in 2018 and 2019, with systematic missingness before them.
- Third-party charting can be corrected and may carry rights that Sports Reference cannot sublicense.
- Player/team identifiers and traded-player aggregate rows require mappings and grain controls absent from a simple export.
- Paid Stathead results depend on account state, query configuration, and subscription terms.
- A future license change would not automatically establish the provenance of previously copied values.

These risks are inconsistent with the project's deterministic, independently rebuildable artifact standard unless a licensed, immutable delivery mechanism is negotiated.

## O. Attribution Requirements

For any permitted manual reference, follow PFR's recommended citation form: Sports Reference LLC, page title, Pro-Football-Reference.com, full URL, and date visited. Online materials should link to the individual page or PFR homepage. When a page credits an upstream provider or contributor—such as Sportradar for advanced statistics or Scott Kacsmar for 4QC/GWD—that provenance should also be retained.

Attribution is necessary but not sufficient: it does not grant automated access, model rights, redistribution rights, or a right to reproduce third-party charting. Any future written license should be stored as non-public compliance metadata and summarized in `DATA_SOURCES.md`, including permitted fields, seasons, users, purposes, derivative outputs, retention, display, attribution, and expiration.

## P. Recommendation

**PERMISSION REQUIRED BEFORE INGESTION**

Do not build a PFR scraper, automated exporter, Stathead extraction process, PFR-backed table, or model feature. Continue using nflverse and documented open alternatives for production data. PFR may be used only for limited, human validation, page-level linking, and source discovery under the boundaries above.

If PFR content becomes materially necessary, contact Sports Reference through its [feedback/licensing channel](https://www.sports-reference.com/feedback/) with a written specification. Ask for explicit permission covering automated delivery, the exact 2010-2025 fields, local retention, content-addressed reproducibility, predictive ML/PAE use, derived coach analysis, public portfolio display, API exposure, redistribution boundaries, attribution, third-party provider rights, corrections, and termination. Do not begin collection while the request is pending.

### Relationship Explorer Impact

The Relationship Explorer can proceed later without PFR. It should use the project's verified/provisional coaching assignments, nflverse-derived QB and team metrics, and existing evidence metadata. PFR links may appear only as optional external references; PFR-derived statistics, QBR, advanced charting, and copied tables must not be added unless the permission decision changes.
