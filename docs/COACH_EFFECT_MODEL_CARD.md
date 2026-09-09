# Coach Effect research model card

Status: Checkpoint 12 research complete; no composite or production Coach Effect approved.

Final research version: `c12-final-0c746df0290c836c`. Final architecture status: **E — NO
COMPOSITE COACH EFFECT APPROVED**. Production Coach Effect: **NO-GO**.

Checkpoint Eleven historical research version: `c11-75bc9b540fe22610`; expected-play model
version `pcae-expanding-prior-seasons-v1`; eligibility version
`pcae-play-eligibility-v2`. These ignored artifacts are not production model outputs.

## Intended use

The Phase 1–4 artifacts support reproducible, non-causal investigation of whether leakage-safe QB PAE and
expected play-call value contain stable coach-associated information after limited environment
controls. They support method critique, sensitivity analysis, attribution auditing, and planning
future out-of-sample validation.

The historical PCAE expansion retains explicit confidence/uncertainty rules and
suppression/evidence thresholds; these safeguards do not authorize a production composite.

## Non-intended use

These artifacts must not produce or imply production coach rankings, employment or compensation
recommendations, wagering decisions, causal claims, or a definitive comparison of coaches. They
must not be loaded by the database, API, frontend, or deployed pipeline. Fold-specific research
coefficients exist only as failed stability diagnostics; no fixed `w_Q`, `w_P`, or `w_S` is
approved.

## Data coverage and current reproducibility

- QB expectation/PAE: checkpoint-five analysis seasons 2010–2025, with 1999–2009 warm-up.
- Play research: cached nflverse regular-season PBP for 1999–2025; each scored season uses only
  earlier seasons for training. Prompt 10 now supports 287 verified non-shared PCAE intervals,
  278 coach-seasons, 105 callers, 14 seasons, and 226,266 attributed plays.
- Coach assignments: repository manual tables preserve identity, role, source, verification,
  confidence, shared/interim status, and intervals. Research coverage is substantially expanded,
  but OC, QB-coach, and play-caller coverage is not comprehensively production-complete.
- Environment and decomposition: deterministic preseason-context, common Q/P, temporal, and
  residualization artifacts are available in the ignored final research publication.

The specification's exact Phase 1 examples and Phase 2–4 summary numbers are retained as
historically documented results unless explicitly reproduced. The current audit proves that the
134,138 regular-season run/pass candidates in 2022–2025 include exactly 502 two-point
conversions, yielding the documented 133,636 under `pcae-play-eligibility-v2`. The same rule
yields exactly 32,813 eligible 2025 plays. Checkpoint Eleven initially could not attribute those
plays under the strict contract; Prompts 8–10 subsequently added only explicit source-backed
weekly intervals. The final PCAE output therefore reflects verified attribution rather than the
earlier unsupported comprehensive-caller assumption.

## Final validation result

Models 0–5 were compared on the same 136 future rows across independently approved 2021–2025
folds. The lowest candidate RMSE improved on the no-coach baseline by only 0.12%, kept negative
pooled correlation, and did not improve direction accuracy. Learned Q/P signs changed across
folds and cluster-bootstrap intervals included zero. Model 6 was not identifiable. The
prior-scheme challenger worsened error.

Modern PCAE repeatability was 0.354 with a coach-bootstrap interval [0.119, 0.517], but
different-team portability remained uncertain. Q repeatability was near zero for every role.
PCAE is retained as a separate research-ready decision-value association; HC Q is not
identifiable, all other role Q results remain exploratory, and no composite is approved.

## Outputs

Research code may emit transition rows, expected call probabilities, expected pass/run EPA,
Call Value, league-centered PCAE, repeatability/reliability diagnostics, environment model
comparisons, rolling predictions, role-specific shrinkage diagnostics, residual components, and
research manifests. All generated files belong under the ignored
`research/coach_effect/outputs/`. No combined Coach Effect score is emitted.

## Reliability and uncertainty

The repeated-QB-transition sample does not support a stable universal Q weight. Final modern PCAE
one-, two-, and observed multi-season reliability estimates are 0.293, 0.453, and 0.585. The
expanded values are lower than the historically documented sparse estimates of about 0.437 and
0.608. Research outputs report seasons, QBs, teams, play volume, uncertainty, evidence grade,
and suppression. Confidence never multiplies an estimate, and all production rows are
suppressed.

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

Production Coach Effect implementation remains blocked until offensive-coordinator, quarterbacks-
coach, and play-caller assignments are comprehensively verified. Play callers require explicit
evidence from a source and weekly/in-season intervals wherever applicable. Recent full-cell and
play coverage are 93.75% and 94.65%, below the 95% production minima. A stable OOS architecture,
role-specific uncertainty, and production eligibility also remain unresolved. No production
Coach Effect ranking is supportable.
