# Methodology

## Research estimand

The project estimates how quarterback performance differs from a preseason expectation and how those residual differences are associated with coaching roles after adjustment for observable context. It does not identify a treatment effect in the causal-inference sense.

Analysis covers completed 2010-2025 regular seasons. Data from 1999-2009 may be used only as model warm-up and will not appear in rankings.

## Analytical grains

- **QB game:** one quarterback, team, and game; used by role-specific coach-impact models.
- **QB season:** one quarterback, team, and season; default ranking grain.
- **QB environment stint:** one quarterback within a date/week-bounded coaching environment; preserves midseason changes.
- **Coach assignment:** one coach, team, season, role, and assignment interval.

A quarterback traded midseason produces a separate QB-season row for each team. A staff change can create multiple environment stints beneath one QB-team-season.

## Primary metric

EPA per dropback uses regular-season plays where `qb_dropback = 1`, excluding kneels and spikes. Pass attempts, sacks, and quarterback scrambles are included. The quarterback is resolved to a GSIS ID using passer fields and the scramble rusher where necessary. Plays whose quarterback cannot be resolved remain in a data-quality report and are not assigned by name guessing.

```text
EPA/dropback = sum(qb_epa) / eligible dropbacks
```

The project calculation is authoritative even when an upstream season-summary field uses a slightly different definition.

## Secondary metrics

- CPOE: mean play-level CPOE on eligible pass attempts with a non-null value.
- Passing success rate: eligible dropbacks with `qb_epa > 0` divided by eligible dropbacks.
- Explosive-pass rate: completed passes gaining at least 20 yards divided by pass attempts.
- Interception and touchdown rates: events divided by pass attempts.
- Sack rate: sacks divided by pass attempts plus sacks.
- Air yards per attempt: the sum of recorded passing air yards divided by all pass attempts. Missing play-level air yards are not imputed; `air_yards_attempts` and `air_yards_coverage_rate` expose the incomplete numerator coverage.
- First-down rate: passing first downs divided by eligible dropbacks.
- WPA/dropback: summed QB-attributed WPA divided by eligible dropbacks.
- Year-over-year change: current value minus the prior NFL season for the same player after combining any multi-team rows; team changes remain visible in the current grain.

Denominators of zero produce null, not zero. Every published rate stores its numerator and denominator or can be reconstructed from stored fields.

Checkpoint three exposes exact season-minus-one prior metrics across the complete consecutive history. It aggregates a player's multi-team prior season before joining, requires 200 prior dropbacks before exposing prior EPA/dropback or CPOE, and never fills a missing year with an older or future season. Warm-up seasons from 1999-2009 seed historical context but are never analysis-qualified.

Eligible plays without finite `qb_epa` are retained in `unresolved_qb_plays` with `resolution_status = invalid_qb_epa` and excluded before metric aggregation. The pipeline warns on the raw gap and separately asserts that every resolved play entering QB metrics has finite EPA.

Before any play filtering or metric aggregation, every seasonal PBP asset must have non-null, unique `(game_id, play_id)` keys. A violation fails the season with separate null counts, duplicate-excess counts, and at most five safe key samples; duplicated source plays can never inflate metric reconciliation silently.

Canonical player identity is always GSIS. Blank identifiers normalize to missing only in Silver; Bronze remains unchanged. An external system/ID pair observed against multiple GSIS players is quarantined in `conflicting_player_external_ids` and excluded from the usable crosswalk.

## Expected-performance model

### Feature timing

Each feature has an `as_of_season`. A prediction for season `S` may use values known before the first regular-season game of `S`, including:

- Draft capital, combine/profile information, age, and experience
- Career starts and performance through `S-1`
- Prior usage and injuries
- Team change, career stage, and prior-year team environment
- Preseason-known coaching continuity indicators, but not coach identity effects

Current-season results, honors, injuries, supporting-cast production, or revised future data are forbidden as preseason features.

### Implemented features and missingness

Checkpoint five derives exact prior-season and career EPA/dropback, CPOE, success, sack, interception, and touchdown rates from metric numerators and denominators through `S-1`. It also uses prior/career dropbacks and starts, age on September 1, roster-reported NFL experience/rookie status, opening-week team change, and prior injury-report/out weeks. `no_prior_qb_performance` and the count/group of prior QB seasons are separate from actual NFL experience. Small prior samples are retained as inputs and handled by shrinkage or preprocessing rather than discarded. Missing-value indicators are explicit.

Team change never compares an observed target-season QB-team stint directly with the prior year. A unique Week 1 regular-season depth-chart team is the player-season preseason snapshot and is applied identically to every later QB-team stint. Post-cutoff destinations therefore cannot alter Ridge features, training rows, or predictions. If the opening snapshot is absent or ambiguous, team change remains null with an explicit status instead of being inferred.

No validated college-production, draft, or combine dataset exists in the repository. The profile college-name field is not production data and is excluded. College production, draft position, and draft round remain null with missing indicators. No current-season coaching assignment, coach identity, team record, ranking, or supporting-cast result is read by the model pipeline.

### Models, timing, and selection

Four candidates are implemented: a dropback-weighted prior-league average; exact prior-season EPA shrunk toward that average with 200 pseudo-dropbacks; prior-career EPA shrunk with 500 pseudo-dropbacks; and standardized/imputed Ridge regression. Ridge alpha is selected from `0.1, 1, 10, 100` inside time-ordered folds using training seasons only. Rows with at least 50 actual dropbacks enter fitting with capped dropback weights; 200 dropbacks controls evaluation eligibility and reliability, not the PAE formula.

For every prediction season `S`, training contains only seasons earlier than `S`; 2010 therefore uses 1999-2009 warm-up outcomes. Published predictions cover 2010-2025 and exclude every warm-up season. The primary candidate minimizes OOS MAE plus declared penalties for absolute calibration intercept and slope departure from one. On 582 eligible rows, career performance won with MAE 0.09172, RMSE 0.11752, R-squared 0.18925, correlation 0.44673, calibration intercept 0.00707, slope 0.82192, and 94.50% interval coverage. After removing team-destination leakage and correcting experience features, Ridge records MAE 0.09398 and composite score 0.10642.

Rookies and veterans without prior QB performance both fall back to the expanding league average in the recent and career baselines, but Ridge can distinguish them through roster experience, rookie status, and `no_prior_qb_performance`. One-prior-NFL-season and one-prior-QB-season fields remain distinct. Prediction intervals use only residuals from earlier evaluated seasons, falling back to prior-training outcome dispersion until 20 eligible OOS residuals exist.

The content version hashes every source Parquet that affects features, all declared modeling/shrinkage/selection/interval/reliability/sensitivity parameters, NumPy/Polars/SciPy/scikit-learn versions, and hashes of the model, constants, and deterministic publishing code. SciPy is included explicitly because scikit-learn Ridge uses its numerical routines. A parameter, modeling-dependency, or relevant source-code change therefore creates a new immutable directory rather than reusing stale outputs.

```text
QB Performance Above Expectation = actual EPA/dropback - expected EPA/dropback
```

## Coaching-assignment verification

Checkpoint four separates a formal staff title from the distinct fact of play-calling duty. Head coaches are accepted from game-level nflverse coach fields and compressed into non-overlapping observed-week stints. A unique offensive-coordinator or primary quarterback-coach title in a preseason NFL Record & Fact Book establishes a `provisional` season designation, not verified weekly tenure. Dated change reports replace those nominal rows with non-overlapping `dated_source_weeks` stints. All other season designations remain queued for interval verification. Assistant quarterback coaches are never promoted to the primary role.

Every verified assignment must join to at least one citation. Citations retain the exact HTTPS URL, source title/type, access date, page locator, and a short evidence note. Source confidence is high for nflverse or NFL/club-hosted evidence and medium for an official book available only through a preservation mirror. Play callers require explicit evidence of actual responsibility and an interval; no HC or OC title is used as a proxy. Ten intervals are verified, while Tim Kelly's post-Week-4 2020 Houston interval remains provisional and queued because the public evidence does not resolve the exact later weekly split. Live-source checks require assignment-specific names and role language for every verified play-caller interval rather than accepting HTTP availability alone. Houston has four separate content contracts for Weeks 1-3, shared Week 4, the preseason later designation, and the post-Week-4 boundary.

Interim status is not inferred from a midseason replacement. A non-head-coach assignment is interim only when a content-checked citation explicitly uses interim language or limits the duty to the remainder of that season. An observed head-coach stint may instead use structural proof only when it begins after a predecessor, reaches the end of that team's season, and the next season opens with a different verified, non-interim head coach. Retained interim head coaches require direct content-checked evidence. The validator enforces these rules across every true flag without rejecting valid permanent midseason changes. Shared duties require every overlapping assignment to carry `is_shared = true`; otherwise the overlap fails validation.

Houston's 2020 play-calling record follows those rules: Tim Kelly is verified for Weeks 1-3, Kelly and Bill O'Brien are both marked shared for the directly reported Week 4 process, and Kelly is provisional for Weeks 5-17. The open `shared_duty_verification_required` review retains uncertainty about the exact post-Week-4 weekly allocation rather than converting a preseason designation into weekly fact.

Source spelling variants map through `coach_aliases.csv` to one canonical coach ID. The validator rejects duplicate normalized identities and assignments whose canonical name does not match their ID. Compound titles are expanded into every checkpoint role explicitly named; for example, the official 2020 Houston `offensive coordinator/quarterbacks` title creates both OC and QB-coach rows for Tim Kelly, while a separate team source establishes his play-calling duty.

The offline validator rejects duplicate keys, unresolved identities, illegal seasons/teams/roles, invalid intervals, overlapping non-shared assignments, verified rows without citations, non-HTTPS sources, incomplete role definitions, and any team-season-role that is neither assigned nor queued.

## Coach-impact models

Checkpoint six first joins each QB game to the selected season expectation and to coaching assignments whose team, season, and week interval cover that game. It then aggregates to one QB-coach-assignment interval. This grain preserves midseason changes without pretending a partial stint lasted a full season. Simultaneous sourced shared duties receive separate rows and fractional exposure dropbacks; unsupported overlaps fail validation. Interval PAE is the dropback-weighted game EPA minus the unchanged preseason expectation and must reconcile exactly.

The primary analysis uses verified assignments only and fits each role separately. A regularized no-coach baseline adjusts for timing-safe age, NFL experience, rookie/history status, prior and career QB performance, opening-team change, prior injuries, season, and repeated-quarterback indicators. Team-season fixed effects are excluded from the primary specification because full-season assignments make them nearly one-to-one with coach identity; that contextual specification remains a sensitivity labeled nonidentified. A regularized coach fixed-effects candidate is compared with a two-stage normal empirical-Bayes model that partially pools coach residual means. Because no validated team-era or complete roster-context controls separate coaches from their environments, every effect remains exploratory and every ranking is suppressed.

Interval residuals are means. The fitted weighted Ridge baseline's effective degrees of freedom are calculated as the trace of its hat matrix: one unpenalized intercept plus `sum(lambda / (lambda + alpha))` over the eigenvalues of the weighted, centered transformed-design Gram matrix. Residual variance is `sum(exposure_dropbacks * residual²) / (independent_intervals - effective_df)`. That dropback-level variance feeds coach sampling variance, between-coach variance, shrinkage, standard errors, estimates, and every bootstrap refit consistently. Uncertainty uses 200 deterministic QB-season block-bootstrap samples. The percentile interval estimand is explicitly conditional on the coach appearing in a resample; successful appearances are counted, and an interval is suppressed below 160 of 200 successful draws. Sparse roles remain present with a null estimate and `insufficient_role_identification`; checkpoint six does not manufacture a QB-coach estimate from one verified coach. Reported MAE/RMSE/R-squared are descriptive in-sample comparisons, not deployment validation or causal evidence.

Role-specific estimates describe an exploratory association attached to a coach occupying that role, including inseparable team and staff effects. Sensitivities add provisional rows, exclude shared duties, use equal rather than dropback weighting, remove QB effects, add a contextual team-season specification explicitly labeled nonidentified, and require 100 or 200 fractional exposure dropbacks. Effects and intervals are suppressed or flagged when identification or bootstrap support is inadequate. A crossed-role joint model is deferred because the verified non-head-coach sample cannot support it defensibly.

Same-season team offensive EPA is reported as context but excluded as a control because it contains the QB outcome. Same-season protection, receiving, rushing, injury, defense, and schedule measures may appear only in retrospective models and must be labeled contextual or post-treatment.

## Ranking and uncertainty

- Default QB qualification: at least 200 eligible dropbacks.
- Default coach qualification: at least three qualifying QB seasons, two distinct quarterbacks, and 600 verified exposure dropbacks.
- Below-threshold records remain queryable but are not assigned a default rank.
- Coach output includes exploratory adjusted estimate, conditional interval where supported, successful/attempted bootstrap draws, identification status, qualifying QB seasons, distinct QBs/teams, verified/provisional/shared exposure, reliability, and exclusion reason. All checkpoint-six ranks are suppressed.

## Star teammates

Star teammates are identified without subjective labels. A player qualifies from prior-year, position-standardized production using a documented composite and minimum usage. The exact composite and percentile are versioned when implemented. Current-season Pro Bowl/All-Pro selections are not preseason predictors.

## Reproducibility

Every derived table records an immutable `data_version`; metric facts also record `metric_version`. Source assets record URLs, retrieval timestamps, SHA-256 digests, byte/row counts, and schemas. Pipeline joins assert their expected cardinality and emit unresolved/conflicting-ID reports. Output is published by an atomic directory rename only after all hard checks pass.

The checkpoint-six identity hashes the historical QB-game input, checkpoint-five PAE, coaching assignments and identities, every model/ranking/bootstrap/sensitivity parameter, NumPy/Polars/SciPy/scikit-learn versions, and relevant source code. Clean builds compare every Parquet, JSON, checksum, and version byte-for-byte; execution timestamps remain outside the immutable directory.

Checkpoint seven does not recompute metrics or models. It verifies every upstream checksum, required column, business key, lineage, interval, citation, fractional exposure, and model/data version before insertion. Exposure lineage is checked in Python and by deferred PostgreSQL triggers in both directions against coach, team, season, role, interval, verification, confidence, interval basis, and shared status; coordinated assignment/exposure changes remain valid when their final deferred state agrees. Each manual CSV is captured once, hashed and parsed from those same bytes, then rehashed immediately before publication so a mid-load edit aborts the transaction. All tables and the publication-pointer swap share one PostgreSQL transaction; a failed candidate load preserves the previous publication. The load identity hashes schema/loader/API versions, all upstream analytical identities, and every `data/manual/*.csv` file. Independent empty databases must produce the same load ID and identical ordered JSON checksums for all eight serving views; database timestamps are execution metadata and may differ.

## Interface interpretation

Checkpoint eight performs no new football aggregation or model fitting. It displays the checkpoint-seven contracts at QB-team-season, coach-role, assignment-interval, citation, and relationship grains. PAE remains actual EPA/dropback minus the preseason expectation; eligibility changes the reliability label and available filters, never the arithmetic. Missing numeric values render as unavailable rather than zero. Coach estimates retain exploratory, identification, suppression, and conditional-bootstrap language, and no ordinal coach rank is derived in the browser.

Every visible coaching relationship preserves the source assignment's verification, confidence, interval, shared-duty, and provisional status. Coach Journey and QB Journey preserve canonical identities across teams and years; Team History preserves season lanes and in-season changes; Full Network remains anchored and bounded. These are navigation and evidence views, not causal or social-network models. Deterministic layout positions are a display transformation only and carry no analytical weight.

The relationship contract models two independently sourced facts: a coach assignment interval connects a canonical coach to a team-season, and an authoritative QB-team-season record connects a canonical QB to that same team-season. Team-anchored scopes seed QB facts directly from `api_qb_statistics`; coaching role, verification, and provisional filters cannot erase those independent records. PAE is joined only on `(load_id, player_id, team_id, season)`, so multi-team seasons cannot inherit another team's value. The resulting two-edge path means only: “QB participated for this team-season while this coaching assignment existed within the same season.” It does not establish weekly overlap, mentorship, influence, or causation. Exact weekly overlap would require a separate validated join to QB-game weeks or exposure lineage and is not asserted by this endpoint.

The frontend transforms one server response into both the visual graph and the accessible relationship cards. Client-side role, interim, and shared filters affect coach-assignment relationships only; QB eligibility, dropback, and PAE filters affect QB-team-season facts only. Selection highlights direct graph adjacency. Focus replaces the current scope with the selected canonical coach/QB journey or one-season team history, while an explicit in-memory focus stack supports Back; Reset clears presentation filters without widening the server anchor. None of these interactions changes the source relationship grain.
