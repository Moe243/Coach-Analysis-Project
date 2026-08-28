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

Checkpoint five derives exact prior-season and career EPA/dropback, CPOE, success, sack, interception, and touchdown rates from metric numerators and denominators through `S-1`. It also uses prior/career dropbacks and starts, age on September 1, observed NFL seasons, team change, and prior injury-report/out weeks. Small prior samples are retained as inputs and handled by shrinkage or preprocessing rather than discarded. Missing-value indicators are explicit.

No validated college-production, draft, or combine dataset exists in the repository. The profile college-name field is not production data and is excluded. College production, draft position, and draft round remain null with missing indicators. No current-season coaching assignment, coach identity, team record, ranking, or supporting-cast result is read by the model pipeline.

### Models, timing, and selection

Four candidates are implemented: a dropback-weighted prior-league average; exact prior-season EPA shrunk toward that average with 200 pseudo-dropbacks; prior-career EPA shrunk with 500 pseudo-dropbacks; and standardized/imputed Ridge regression. Ridge alpha is selected from `0.1, 1, 10, 100` inside time-ordered folds using training seasons only. Rows with at least 50 actual dropbacks enter fitting with capped dropback weights; 200 dropbacks controls evaluation eligibility and reliability, not the PAE formula.

For every prediction season `S`, training contains only seasons earlier than `S`; 2010 therefore uses 1999-2009 warm-up outcomes. Published predictions cover 2010-2025 and exclude every warm-up season. The primary candidate minimizes OOS MAE plus declared penalties for absolute calibration intercept and slope departure from one. On 582 eligible rows, career performance won with MAE 0.09172, RMSE 0.11752, R-squared 0.18925, correlation 0.44673, calibration intercept 0.00707, slope 0.82192, and 94.50% interval coverage. Ridge was close but worse on both MAE (0.09209) and the composite selection score.

Rookies and QBs without exact prior-season data fall back to the expanding league average in the recent and career baselines; Ridge uses training-only median imputation plus explicit missing indicators. One-prior-season players use the same shrinkage rules. Team changes are explicit. Prediction intervals use only residuals from earlier evaluated seasons, falling back to prior-training outcome dispersion until 20 eligible OOS residuals exist.

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

The primary analysis fits one mixed model per coaching role at the QB-game level. The focal coach and quarterback receive partially pooled random intercepts; team/franchise and season/context terms address repeated environments. Uncertainty uses block bootstrap samples drawn by QB-season.

Role-specific estimates describe the association attached to a coach occupying that role, including inseparable staff effects. A crossed-role joint model is a sensitivity analysis only. Effects are suppressed or flagged when role overlap produces weak identification or unstable estimates.

Same-season team offensive EPA is reported as context but excluded as a control because it contains the QB outcome. Same-season protection, receiving, rushing, injury, defense, and schedule measures may appear only in retrospective models and must be labeled contextual or post-treatment.

## Ranking and uncertainty

- Default QB qualification: at least 200 eligible dropbacks.
- Default coach qualification: at least three qualifying QB seasons and two distinct quarterbacks.
- Below-threshold records remain queryable but are not assigned a default rank.
- Coach output includes adjusted estimate, interval, qualifying QB seasons, distinct QBs, average PAE, offensive context, continuity, and warning flags.

## Star teammates

Star teammates are identified without subjective labels. A player qualifies from prior-year, position-standardized production using a documented composite and minimum usage. The exact composite and percentile are versioned when implemented. Current-season Pro Bowl/All-Pro selections are not preseason predictors.

## Reproducibility

Every derived table records an immutable `data_version`; metric facts also record `metric_version`. Source assets record URLs, retrieval timestamps, SHA-256 digests, byte/row counts, and schemas. Pipeline joins assert their expected cardinality and emit unresolved/conflicting-ID reports. Output is published by an atomic directory rename only after all hard checks pass.
