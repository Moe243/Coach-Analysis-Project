# Limitations

## Checkpoint 17 conditional-scenario limitations

- The conditional experiment is estimable but does **not** validate environment response. Both
  main-effect and interaction additions worsen validation error and performance among team
  changers. No 2026 scenario adjustment is approved; C18 remains NOT READY.
- Destination assignment and attaining 50 target-season stint dropbacks are selected events.
  Conditioning on them is not proof of an unconditional forecast or an intervention effect.
  Transfers can depend on performance/injury; absent/unplayed pairings have no observed labels.
- Prior team behavior partly reflects its prior quarterback, personnel and staff. It can change
  when the QB or staff changes; it is not a fixed scheme or a causal coach property. Changer
  results test some transport but cannot establish support for every candidate/team pairing.
- Validation reuses an archive already inspected for C13/C14/C16 development. It is chronological
  at the parameter level, not a fresh prospective experiment for the entire research process.
- Equal stint weights and two separate cluster bootstraps do not jointly resolve repeated-QB,
  team and season dependence. The fixed-prediction bootstrap omits model-refitting uncertainty;
  sign-flip tail fractions are descriptive, not exact randomized-assignment p-values.
- Predictive intervals have measured marginal coverage only. They are not uncertainty intervals
  for a QB-specific environment effect, nor causal, conditional or shift-robust guarantees.
- Many players lack qualified prior style: 234/667 eligible stints lack depth/air-yard estimates;
  192/667 lack scramble/shotgun estimates. Train-only imputation is not an observed value.
- Stable coefficient signs do not establish useful fit: these interactions fail incremental
  prediction tests. No arbitrary score, Coach Effect, PAE forecast or production output is added.

## Current C16 calibration/candidate-state limitations

- Bias-calibrated EPA passes the unchanged research gates but is not uniformly better: validation
  MAE improves in four of seven years. Its 50% interval covers 45.04%, inside the declared tolerance
  but still undercoverage. Rank correlation does not improve. No causal or unconditional guarantee.
- The calibration investigation was prompted by previously seen results. Chronological fitting
  and development-only selection do not make this a prospectively untouched external test.
- PAE remains unapproved; improved linear calibration does not compensate for worsened MAE.
- The 57 candidate QBs are qualified 2025 historical participants, not an inferred 2026 roster.
  No rookies without NFL history, inactive-2025 QBs, current teams, retirement decisions, or
  availability predictions are fabricated. Outcomes were validated conditional on eventual
  target-year volume; forward membership uses past volume, so selection/playing-time risk remains.
- The new 2026 states are a separately versioned research extension, not evidence that the
  previously absent historical-C14 forward artifact had existed. Original artifacts are preserved.
- The C16 follow-up itself supplied no environment validation. C15 remains data-limited;
  the separate C17 experiment above is now complete but unsupported. No production system
  or Coach Effect is changed.

## Original Checkpoint 16 projection limitations (preserved run)

- The historical Player-State-only experiment is complete but neither development-selected
  target passes every acceptance criterion. B2 EPA narrowly misses an intercept guardrail;
  M1 PAE is under-dispersed according to its calibration slope. Positive correlation and later
  M1 gains do not justify changing the selection rule after viewing validation results.
- Frozen C14 feature development/classification and the inherited B2 specification were developed
  in earlier research using this historical archive. Chronological fitting is enforced, but these
  results are not a prospective untouched external test of the entire research process.
- Evaluation is conditional on reaching 50 observed dropbacks; it does not predict playing time,
  injuries, active-roster membership, or availability. The 41 participants outside the as-of state
  universe remain excluded rather than backfilled. Small-volume errors are materially larger.
- Rolling residual intervals are marginal, year/model-level calibrations. Repeated quarterbacks
  and temporal drift prevent unconditional conformal coverage claims; subgroup coverage and
  individual uncertainty are not guaranteed. The first 144 OOS rows lack sufficient calibration.
- EPA and PAE models are separate targets, not a validated joint predictive distribution. The
  paired-error bootstrap resamples QBs without refitting and does not capture shared season shocks.
- Existing C14 Player State ends in 2025. No 2026 universe or forward projections are invented.
  A separately approved forward state and an accepted/calibrated model are prerequisites.
- Target-team evidence is unnecessary for this model but remains necessary for valid Scheme fit,
  context assignment, and scenarios. Retrospective team-change subgroup labels are diagnostic
  only and do not establish a preseason-known move. No Coach Effect or interaction is included.

## Checkpoint 15 Player × Scheme fit limitations

- Pre-2025 roster and depth-chart assets are not timestamped, so they cannot establish a veteran's
  target team by the August 31 boundary. They are not used for hindsight assignment.
- Immutable draft-team facts create historical preseason-known rows, but those rows are rookies
  without prior NFL style profiles. Dated preseason depth charts add veterans only in 2025.
- The resulting evaluation cohort changes composition sharply and is not representative of all
  NFL QB-seasons. M0/M1 backtest metrics are research diagnostics, not production projections.
- There are no qualified historical interaction observations before 2025, so M2, interaction
  coefficient stability, bootstrap uncertainty, permutation evidence, and portability are not
  estimable. This is a data limitation, not evidence that Player × Scheme fit does not exist.
  Empty artifacts mean unavailable, not zero effect.
- The 16-row team-change subset is a small 2025-heavy proxy. It cannot establish generalization or
  verified coach/scheme-change effects.
- Draft team is a known transaction fact, not proof of August 31 retention. Exact-key outcome
  joining prevents substitution of a later destination, and unmatched rows are excluded.
- The audited nflverse trade asset is PFR-derived and cannot enter predictive/model work under the
  approved `PERMISSION REQUIRED BEFORE INGESTION` decision. Weekly/final rosters, legacy depth
  charts, and year-only contracts do not prove an August 31 assignment.
- Scheme features describe prior team behavior. They are not causal coach ownership measures.
- The narrow M0/M1 cohort did not approve a scheme-conditioned projection baseline. That historical
  C15 readiness conclusion does not block a separate full-cohort Player State experiment. No fit
  score, M2 coefficient, or interaction contribution is approved.

## Checkpoint 14 Player State limitations

- The as-of universe intentionally includes historical/drafted quarterbacks without claiming they
  were active in a target season. Active-roster selection is deferred.
- Undrafted rookies without dated pre-August-31 evidence cannot be added retrospectively; 41
  evaluation rows therefore have no valid state-universe membership.
- Target-season Checkpoint 5 prediction availability is cohort-dependent and is not a state
  feature. Prior PAE enters only after it becomes historical.
- Stability and portability are observational screens. They do not prove that conditioned QB
  performance is independent of scheme, teammates, opponents, or coaching.
- Low-volume red-zone, scramble, rushing, and other split results remain descriptive or uncertain.
- Player State is not a transition, projection, simulation, causal, or production model.

## No causal identification

Coaches are not randomly assigned to quarterbacks or teams. Hiring, firing, roster investment, injuries, organizational quality, opponent strength, and quarterback development all affect observed outcomes. Adjusted estimates remain associations.

## Overlapping coaching roles

Head coaches, offensive coordinators, play-callers, and QB coaches often arrive and leave together. A head coach may call plays, and play-calling may be shared or change midseason. This collinearity can make separate role effects unidentified. The project will show overlap warnings and use role-specific models as the primary presentation rather than claim clean additive attribution.

## Quarterback-coach matching and selection

Teams select coaches for particular quarterbacks and quarterbacks for particular systems. Coaches may inherit unusually weak or strong situations, and successful pairings survive longer. Partial pooling and observed covariates reduce variance but do not remove this selection bias.

## Measurement and availability

- Play-by-play corrections can change historical EPA and identifiers.
- CPOE/NGS fields are not consistently available before 2016.
- Snap counts begin in 2012, leaving weaker line-continuity proxies for 2010-2011.
- FTN charting begins in 2022 and cannot define a full-window metric.
- Injury reports indicate listed status, not true severity or health.
- Public data do not provide a clean, historical offensive-line blocking grade.
- Sacks and time to throw reflect both protection and quarterback behavior.
- Receiver production is partly generated by the quarterback and cannot be treated as an independent causal input without care.
- Historical context sources do not have uniform coverage: depth charts begin in 2001, injuries in 2009, and usable snap-count rows in 2013 even though an empty official 2012 asset exists. These gaps are explicit and must not be interpreted as zero injuries, zero depth, or zero snaps.
- Air-yards coverage is extremely limited in the earliest PBP seasons. Coverage denominators are published, values are not imputed, and cross-era comparisons of air-yards metrics require explicit coverage filtering.
- One 2019 eligible dropback lacks finite `qb_epa`; it is quarantined from metrics and reported rather than imputed.
- The unambiguous external-ID bridge leaves 228 snap-count rows without canonical GSIS IDs. Their upstream PFR IDs remain available, but they require resolution before player-level snap analysis.
- Five external roster identifier values mapped to more than one GSIS player in the observed slice. They are quarantined and cannot be used for joins unless a later source-backed resolution is added.
- Upstream schema types drift even when column names remain stable; the pipeline normalizes only fields it actually serves and records the complete observed schema.
- The five-season slice has 6,296 resolved pass attempts without recorded air yards. Air-yards metrics retain all attempts in the denominator, omit missing values from the numerator, and publish coverage so users can judge the resulting downward bias risk.

## Coaching data quality

No audited public API supplies complete role histories, play-callers, shared duties, and midseason intervals for 2010–2025. Checkpoint Eleven-B verifies 404 OC and 383 QB-coach team-season titles, but 108 OC and 129 QB-coach cells remain missing; most verified title rows still carry `season_designation` and an open weekly-continuity review. Play-caller coverage is 96 verified full seasons, seven partial verified seasons, 96 provisional seasons, and 313 manual-review seasons. A formal title is never treated as proof of play-calling duty. A midseason replacement is not labeled interim without content-checked temporary language or the narrowly defined head-coach structural proof. Houston's exact post-Week-4 2020 allocation remains unresolved. Older official books available only from preservation mirrors retain medium confidence, and disappearing or client-rendered pages may require archived or digest-matched replacements.

## Preseason expectation limitations

Rookies and low-experience quarterbacks have little QB-performance history. Roster `years_exp`, `entry_year`, and `rookie_year` now separate actual rookies from veterans without prior QB dropbacks, but those public fields may still contain upstream corrections. Of 1,689 analysis rows, 455 have no prior QB-performance season, 662 lack an exact prior QB season, 688 lack prior CPOE, 804 lack prior injury-report features, and 794 lack a usable team-change feature. Every row lacks validated draft and college-production features.

The team-change feature uses only a unique Week 1 regular-season depth-chart team; it never uses a later observed destination. This prevents transaction leakage but leaves the feature null when no unique opening snapshot exists, including 248 rows without one and additional rows without a prior QB team for comparison. Week 1 is an opening snapshot, not a complete dated transaction history, so late preseason moves may still be coarsely represented.

The selected career baseline is intentionally simple and outperformed corrected Ridge (eligible MAE 0.09172 versus 0.09398). Selection uses the same 2010-2025 expanding-window backtest reported for performance, so it is model-family evaluation rather than a claim about an untouched deployment holdout. Calibration is weaker for true rookies (63 eligible rows, negative R-squared) and one-prior-NFL-season quarterbacks than for veterans. The normal-style residual intervals achieved 94.50% overall coverage but do not model player-specific heteroskedasticity, injury uncertainty, or structural changes in league play.

PAE is a residual from a limited preseason expectation, not an intrinsic quarterback-quality measure. It can absorb unmeasured roster strength, scheme, opponent mix, health, and random variation. The 200-dropback threshold controls eligibility and reliability only; all 1,689 analysis rows remain stored, including 1,107 low-reliability smaller samples. No final quarterback ranking is produced in checkpoint five.

## Aggregation

Season averages hide within-season injuries, opponent changes, garbage time, and scheme evolution. Game-level coach models improve exposure tracking but add noise. Midseason stints can be too small to rank even when stored accurately.

## Ranking uncertainty

Rank order can exaggerate tiny differences. Point estimates, intervals, sample size, and stability matter more than ordinal rank. Coaches below the default exposure thresholds will remain visible but unranked.

Checkpoint six does not publish any coach ranking. Although 81 head coaches clear the mechanical sample thresholds, head-coach identity remains entangled with unmeasured team environment. The primary specification removes near one-to-one team-season fixed effects, records the confounding diagnostic, and labels all estimates exploratory; the contextual team-season specification remains a nonidentified sensitivity. Descriptive model metrics are in-sample and must not be read as out-of-sample coach predictiveness.

The primary model excludes 1,856 QB-coach intervals below 25 fractional exposure dropbacks. This includes Tim Kelly and Bill O'Brien in shared Houston Week 4: each receives 20 effective dropbacks from 40 observed and is excluded. Provisional season designations provide broad OC and QB-coach sensitivity coverage but not verified weekly tenure, so they never enter primary estimates. The single verified QB-coach identity cannot support a role model. Weighted Ridge effective degrees of freedom can leave little residual information in sparse roles, reinforcing their exploratory status. Bootstrap percentiles are conditional on a coach appearing in a QB-season resample; intervals are suppressed below 160 successful appearances out of 200. No validated full-window offensive-line, receiver-quality, defensive-strength, or opponent-strength table exists yet, so those requested contexts remain unmodeled rather than fabricated.

The post-release inherited context artifact is preparatory and is not yet a model covariate.
Protection is a QB-hit/sack proxy, not a blocking grade. Opening depth charts can omit late
preseason movement and the 2025 asset lacks a comparable weekly opening snapshot, leaving its
skill-player context null. Player-stat production can be incomplete or revised upstream, and the
simple position-standardized composites do not measure route quality, blocking, injuries, or
scheme fit. Target schedule is known before the season, but its opponents' prior pass-defense is
an imperfect forecast. NGS and FTN coverage is too recent for a historical core and remains
validation-only. These limitations are why the artifact does not alter PAE or coach estimates.

## External validity

Results apply to NFL quarterback environments observed in this period. They should not be assumed to measure a coach's effect on other positions, future teams, college players, or unobserved tactical responsibilities.

## Database and API

The production API is a public, read-only research service with provider TLS and exact-origin CORS, but it is intentionally unauthenticated and has no application rate limiter or availability SLA. Render and Neon free tiers can cold-start, throttle, or become unavailable. Search is PostgreSQL `ILIKE`; pagination remains offset-based but uses deterministic total ordering. Ordinary Relationship Explorer modes are bounded to 1,000 canonical nodes and 2,000 factual relationships; Full Network uses measured 2,000/4,000 caps so the supported 2010–2025 publication fits without silent truncation. Its coach-to-team-season and QB-to-team-season path establishes season context only, not exact weekly overlap or causation. Appearance nodes and continuity lines are navigation aids, not duplicated data or modeled relationships. Pathological scopes still return 413 with no partial graph. On small screens the metadata-complete relationship list remains the primary equivalent. PostgreSQL timestamps can differ between clean loads; analytical view content and version identities cannot. The API serves the same exploratory/suppressed coach outputs from checkpoint six and does not improve their identification.

## Frontend

The deployed analytical interface inherits all data completeness and identification limits and does not add authentication, durable client caching, active monitoring, or a public availability guarantee. Coach filtering on the statistics route remains a client-side team-season intersection of complete paginated assignment and QB responses; it preserves and displays assignment intervals but does not prove that the QB participated inside each interval. Network team hubs are presentation context derived from assignment edges, not evidence of influence, mentorship, or causation. Connected quarterbacks on coach pages indicate shared team-season context only, not direct coaching exposure.

The Relationship Explorer supports chronological Coach Journey, QB Journey, and Team History views plus an optional-anchor all-years Full Network. The complete network is intentionally dense even with fixed year bands; zoom, pan, filtering, focus, and the authoritative metadata-complete relationship list remain important. Rendering repeats season-specific visual appearances for canonical people, which increases client element count but does not duplicate API facts. Small screens prioritize record cards and horizontal-free page layout over showing every graph label simultaneously. Broad cross-browser/device-lab and automated visual-regression coverage remain future improvements.

Checkpoint Eleven-B still does not complete weekly play-caller history: 416 of 512 cells remain
unresolved, including seven partial verified, 96 provisional, and 313 manual-review cells. The
2023–2025 seasons now have complete verified weekly maps, while older coverage remains sparse.
Zero attribution in an older season means unavailable caller evidence, not zero coaching value.
Shared Houston Week 4 stays unattributed (62 eligible plays) because individual-play ownership is
not supported. The evidence breadth is suitable for continued research but not yet for final
Coach Effect weights, causal claims, or a production ranking.

Stage 1 QB-facing lists and production-bound QB facts use the canonical player position recorded in the historical player dimension. Hybrid-role players classified upstream at another position are intentionally absent even if they logged isolated quarterback plays; immutable checkpoint facts and raw PBP are retained for reproducibility. Canonical position is a single identity-level classification and can therefore exclude players whose historical role once differed. Missing positions are audited rather than inferred. Supplemental box-score fields may be null when weekly player-stat inputs are unavailable. PBP-derived team passing yards are net play yards, including the source's sack-loss behavior, and are not guaranteed to match every official box-score convention. Team ranks are descriptive target-season context and must not be used as preseason model features.

## Licensing and access

Some nflverse datasets originate from third parties with separate terms. Direct Sports Reference scraping is excluded. CFBD raw responses cannot be published as a bulk dataset. Data availability or terms may change, requiring source re-audit before release.
