# Coach Effect research methodology

Status: exploratory, non-causal research contract; no production Coach Effect score or ranking
exists.

## Scope and lineage

The research reuses immutable checkpoint-three football facts, checkpoint-five out-of-sample
expected QB performance/PAE, nflverse play-by-play, and manually sourced coaching assignments.
Research modules live under `research/coach_effect/`; generated research outputs live only under
the ignored `research/coach_effect/outputs/`. Checkpoint Eleven adds historical eligibility and
PCAE research plus frontend-only Relationship Explorer appearance layouts. It does not change
the production Coach Effect model, database schema, serving publication, deployment, or existing
checkpoint outputs.

Every runnable experiment must record input paths and hashes, configuration, seasons, feature
names, dependency versions, and code identity in its future manifest. Unexpected join
cardinality, duplicate stable keys, missing identifiers, or uncovered play-caller intervals must
fail rather than be imputed.

## Phase 1 definitions

For QB `q`, team `t`, and season `s`:

`PAE(q,t,s) = actual EPA/dropback(q,t,s) - preseason expected EPA/dropback(q,t,s)`

The expectation must be generated without training on season `s` or the future. Eligibility and
reliability never change the PAE arithmetic. Consecutive movement is:

`ΔPAE = PAE(s) - PAE(s-1)`

The exploratory QB-development signal is:

`QB signal = observed ΔPAE - expected ΔPAE given pre-transition information`

Expected movement is estimated only from historically available transitions and must at minimum
control starting PAE or a justified equivalent. Coach identity is not an expectation-model
feature. Same-QB/same-team/same-head-coach OC-change tests require unambiguous role intervals;
multi-interval seasons are not collapsed into a false full-season assignment.

## Phase 2 definitions

The expected-call and expected-EPA models use only pre-snap state: down, distance, field
position, game time, score differential, timeouts, shotgun, and no-huddle indicators. Training
seasons are 2022–2024 and the declared test season is 2025. Separate regressions estimate:

- `E[EPA | call pass, pre-snap state]`
- `E[EPA | call run, pre-snap state]`

For an observed decision:

`Call Value = expected chosen-play EPA - expected alternative-play EPA`

The individual play's actual EPA does not enter Call Value. It is used only after scoring for
aggregate validation of model-preferred versus non-preferred calls. For coach `c` in season `s`:

`PCAE(c,s) = weighted mean Call Value(c,s) - league weighted mean Call Value(s)`

Shared callers receive fractional attribution that sums to one for a play. Assignment grain is
`assignment_key`; team, season, week, coach, role, verification, confidence, shared status,
interval basis, and citation must agree. OC title is not play-caller evidence. Season-designation
intervals are insufficient for weekly attribution.

Checkpoint Eleven's historical extension keeps the same model family and features but uses an
expanding temporal split: target season `S` is fit only on 1999 through `S-1`. The versioned
`pcae-play-eligibility-v2` rule requires a regular-season nflverse `pass`/`run` classification,
non-null unique play keys, team/week/down, and finite EPA, and excludes two-point conversions.
This exactly explains the earlier 502-play difference: 134,138 candidates minus 502 conversions
equals 133,636 eligible 2022–2025 plays. Attribution is stricter than the earlier exploratory run:
only verified, cited, weekly intervals are accepted, and shared/ambiguous plays are suppressed.
The content identity includes every manual CSV and PBP input, relevant source hashes, model
specification, seed, and NumPy/Polars/SciPy/scikit-learn versions. Input hashes are revalidated
immediately before atomic publication so a mid-build edit fails closed.

Repeatability compares the same verified play callers across seasons. One-season reliability is
estimated from repeated-caller between- and within-coach variance; a two-season-average estimate
uses the Spearman–Brown relationship. Shrinkage moves league-centered PCAE toward zero according
to the declared empirical reliability. These are diagnostics, not final Coach Effect weights.

## Phase 3 controls

The final exploratory environment set is:

- prior team offensive EPA, known before the target season;
- checkpoint-five preseason expected QB EPA;
- supporting cast from active/inactive Week 1 WR/RB/TE/FB players, using prior information;
- opponent strength derived without the focal offense to reduce circularity.

Cut, practice/development-squad, and reserve players are excluded from the supporting-cast pool.
Target-season final offensive performance cannot be an input feature when it is also the outcome.
Defense quality is not a positive Coach Effect component. Environment variables are controls and
sensitivity inputs, not points added to a coach score.

Environment-only and environment-plus-PCAE specifications are compared in sample for
description and with leave-one-team-out cross-validation for held-out behavior. Standardized
coefficients describe that sample; they are not causal effects or component weights.

## Phase 4 decomposition

On a common coach-season sample, linear residualization produces:

- `UniqueQB`: PAE signal residualized on PCAE;
- `UniquePCAE`: PCAE residualized on PAE signal;
- `SharedSignal`: an unweighted standardized common-direction diagnostic.

The conceptual expression is:

`Coach Effect_c = Confidence_c × [w_Q × UniqueQB_c + w_P × UniquePCAE_c + w_S × SharedSignal_c]`

`w_Q`, `w_P`, and `w_S` have no numeric values. Future estimation must use expanded historical
data, component reliability, and out-of-sample validation. The shared diagnostic is not itself a
validated latent coaching factor.

## Evidence, eligibility, and confidence

Evidence breadth includes seasons, distinct QBs, distinct teams, play/sample volume,
repeatability, component reliability, verification status, and interval precision. Confidence
has no final numeric formula in checkpoint ten. A production design must publish the underlying
counts, uncertainty, missingness, and suppression reason. One season or one QB cannot support an
unqualified elite ranking.

## Assumptions and interpretation

PAE and PCAE are adjusted observational signals. They can retain staff collaboration, roster
construction, injuries, schedule, opponent, scheme, selection, measurement, and random effects.
Residualization removes only linear overlap in the analyzed sample. Associations must not be
described as causes, and employment, contract, wagering, or medical decisions are prohibited
uses.

## Production implementation gate

Production Coach Effect implementation is blocked until OC, QB-coach, and play-caller
assignments are comprehensively verified. Every play-caller row requires explicit evidence;
weekly or in-season intervals are required where duties changed, were shared, or did not span the
whole season. Before implementation, the project must also reproduce the documented exploratory
counts and metrics, complete historical PCAE expansion and reliability testing, estimate—not
invent—component weights out of sample, define confidence/uncertainty rules and explicit
suppression/evidence thresholds, and pass a separate approval checkpoint.
