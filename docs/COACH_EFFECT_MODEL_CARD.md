# Coach Effect research model card

Status: research foundation only; exploratory, unweighted, non-causal, and blocked from
production implementation.

Checkpoint Eleven historical research version: `c11-75bc9b540fe22610`; expected-play model
version `pcae-expanding-prior-seasons-v1`; eligibility version
`pcae-play-eligibility-v2`. These ignored artifacts are not production model outputs.

## Intended use

The Phase 1–4 artifacts support reproducible investigation of whether leakage-safe QB PAE and
expected play-call value contain stable coach-associated information after limited environment
controls. They support method critique, sensitivity analysis, attribution auditing, and planning
future out-of-sample validation.

## Non-intended use

These artifacts must not produce or imply production coach rankings, employment or compensation
recommendations, wagering decisions, causal claims, or a definitive comparison of coaches. They
must not be loaded by the database, API, frontend, or deployed pipeline. No numerical `w_Q`,
`w_P`, or `w_S` exists.

## Data coverage and current reproducibility

- QB expectation/PAE: checkpoint-five analysis seasons 2010–2025, with 1999–2009 warm-up.
- Play research: cached nflverse regular-season PBP for 1999–2025; each scored season uses only
  earlier seasons for training. Verified interval coverage currently permits PCAE rows in 2012,
  2015, 2016, and 2020.
- Coach assignments: repository manual tables preserve identity, role, source, verification,
  confidence, shared/interim status, and intervals, but are intentionally incomplete outside
  verified head-coach coverage.
- Environment and decomposition: the exact corrected 32-team 2025 input and paired coach-level
  table from the historical exploratory run are not committed.

The specification's exact Phase 1 examples and Phase 2–4 summary numbers are retained as
historically documented results unless explicitly reproduced. The current audit proves that the
134,138 regular-season run/pass candidates in 2022–2025 include exactly 502 two-point
conversions, yielding the documented 133,636 under `pcae-play-eligibility-v2`. The same rule
yields exactly 32,813 eligible 2025 plays, but none can currently be assigned under the strict
verified-weekly-caller contract. The historical claim that all 32,813 were attributed therefore
still depends on the missing comprehensive caller map.

## Outputs

Research code may emit transition rows, expected call probabilities, expected pass/run EPA,
Call Value, league-centered PCAE, repeatability/reliability diagnostics, environment model
comparisons, leave-one-team-out predictions, residual components, and research manifests. All
generated files belong under the ignored `research/coach_effect/outputs/`. No combined Coach
Effect score is emitted.

## Reliability and uncertainty

The repeated-QB-transition sample is too sparse for a stable universal PAE reliability weight.
The historically documented PCAE one-season and two-season-average reliabilities were about
0.4372 and 0.6084, but require exact reproduction from the missing caller table. Future results
must report seasons, QBs, teams, play volume, repeatability, component reliability, uncertainty,
and suppression. One season or one QB is insufficient for an unqualified ranking.

## Principal risks

- **Attribution:** OC and play caller are not synonyms; duties may be shared or change midseason.
- **Coverage:** missing or provisional OC, QB-coach, and play-caller intervals prevent complete
  production attribution.
- **Confounding:** staff, team, scheme, roster, schedule, health, and selection can move together.
- **PAE measurement:** expected QB performance is limited and PAE can absorb omitted context.
- **PCAE measurement:** expected pass/run EPA depends on model specification and historical call
  selection; aggregate validation does not establish causal value for an individual call.
- **Environment:** 32 teams is a small sample with overlapping predictors; coefficient signs are
  unstable and are not component weights.
- **Overlap:** residualization removes only fitted linear overlap and is sample-dependent.
- **Survivorship and matching:** repeated coaches and QBs are selected rather than randomized.

## Safeguards

The code requires stable play keys, explicit team/week caller intervals, verified evidence,
deterministic ordering, and explicit suppression of shared, ambiguous, or uncovered attribution.
Call Value excludes the individual actual result. Research and serving directories are separated,
formula contracts are tested, output identity records NumPy, Polars, SciPy, and scikit-learn,
mutable input hashes are revalidated immediately before publication, arbitrary final weights are
prohibited, and documentation uses association language.

## Production release gate

Production Coach Effect implementation is blocked until offensive-coordinator, quarterbacks-
coach, and play-caller assignments are comprehensively verified. Play callers require explicit
evidence from a source and weekly/in-season intervals wherever applicable. Historical PCAE
expansion, the play-count discrepancy, missing exact research inputs, expanded reliability
testing, out-of-sample weight estimation, confidence/uncertainty rules, explicit
suppression/evidence thresholds, and independent review must also be resolved. Until then, the
framework remains exploratory and no production Coach Effect ranking is supportable.
