# Coach Effect research narrative

Status: checkpoint-ten research foundation; exploratory, non-causal, and not production-serving.

This document preserves the sequence of experiments that motivated a possible Coach Effect
framework. Numbers labeled **historically documented** came from the completed exploratory run
described in the checkpoint specification. They are not silently recast as current production
results. The current repository can reproduce the formulas and methods, but some exact results
cannot yet be rerun because the original comprehensive weekly play-caller map and saved Phase
2–4 modeling tables are absent. See [Reproduction status](#reproduction-status).

## Phase 1 — QB development / PAE

### Question

Does quarterback performance above preseason expectation contain a repeatable coaching signal?
PAE remains exactly:

`Actual EPA/dropback - Expected EPA/dropback`

The expected-performance model uses only information available before the target season and its
published PAE is out of sample.

### Test

The research first compared QB PAE after generic offensive-coordinator turnover. Because poor
seasons both invite staff change and tend to rebound, it then stratified transitions by starting
PAE. A stricter test held QB, team, and head coach constant while the OC changed. Finally, it
defined an individual exploratory signal:

`Actual QB change in PAE - Expected QB change in PAE from normal year-to-year movement`

The preserved SQL excludes ambiguous full-season contexts with multiple OC or head-coach
intervals instead of collapsing them.

### Result

Generic OC turnover did not reliably improve PAE. After starting PAE was stratified, most of the
broad new-OC difference disappeared. Holding the same QB, team, and head coach constant still
showed no general improvement.

Historically documented individual examples were:

- Gary Kubiak: approximately `+0.0659` and `+0.0684` across Joe Flacco and Kirk Cousins.
- Brian Schottenheimer: approximately `+0.0127` and `+0.0763`.
- Other coaches were inconsistent, and one extreme transition was not treated as a coach effect.

### What we learned

Regression to the mean is a major confound. Any coach-associated QB signal must account for
magnitude, consistency, breadth across QBs and teams, and sample size. The repeated-QB-transition
sample is too sparse to estimate a stable universal PAE reliability weight.

### Next step

Retain PAE as one uncertain component, expand verified role histories, and estimate normal
movement using time-ordered data before using any transition in evaluation.

## Phase 2 — Play calling / PCAE

### Question

Can decision quality be evaluated from pre-snap context without scoring a call by its individual
realized result, and does that measure repeat across play callers?

### Test

The exploratory run used regular-season run/pass plays from 2022–2025. An expected-pass-call
classifier and separate expected-pass-EPA and expected-run-EPA models trained on 2022–2024 and
tested on 2025. Decision value was:

`Call Value = Expected EPA of chosen play type - Expected EPA of alternative play type`

Actual EPA was used only for aggregate validation. Coach-season PCAE was league-centered:

`PCAE = Coach average Call Value - League average Call Value`

The research attributed plays to actual offensive play callers by week, including in-season
changes and shared duties, rather than treating OC title as play-calling proof. It compared
repeat callers from 2024 to 2025 and estimated empirical reliability.

### Result

The historically documented initial sample was `133,636` usable plays. On the 2025 test set:

- actual pass rate: approximately `0.5682`
- average predicted pass probability: approximately `0.5746`
- accuracy: approximately `0.6488`
- log loss: approximately `0.6213`
- Brier score: approximately `0.2153`

The expected-EPA models preferred pass in approximately `67.1%` of situations; actual calls
matched the preferred option approximately `44.7%` of the time. Aggregate validation showed:

| Modeled advantage | Followed preferred EPA | Ignored preferred EPA | Difference |
|---|---:|---:|---:|
| All plays | +0.0873 | -0.0571 | +0.1444 |
| At least 0.05 | — | — | +0.1663 |
| At least 0.10 | — | — | +0.2139 |
| At least 0.20 | — | — | +0.3401 |

The historically documented 2025 league-average raw Call Value was approximately `-0.0423`.
That negative level does not mean league play calling was universally bad; PCAE centers it for
comparison. Coach-level PCAE correlated approximately `0.5717` with actual offensive EPA.
Illustrative historically documented PCAE values were Shane Steichen `+0.0199`, Liam Coen
`+0.0145`, Sean McVay `+0.0130`, and Andy Reid `+0.0127`.

The completed exploratory attribution reported all `32,813` usable 2025 plays assigned to
weekly callers, including confirmed in-season changes. From 2024 to 2025, repeat-caller PCAE
correlation was approximately `0.4491` and same-direction rate was approximately `0.6818`.
Repeated positive examples were:

- Andy Reid: `+0.0140` to `+0.0127`
- Sean McVay: `+0.0103` to `+0.0130`
- Shane Steichen: `+0.0060` to `+0.0199`
- Liam Coen: `+0.0054` to `+0.0145`
- Ben Johnson: `+0.0027` to `+0.0023`

The four exploratory team switches were Ben Johnson (`DET` to `CHI`), Liam Coen (`TB` to
`JAX`), Klint Kubiak (`NO` to `SEA`), and Kellen Moore (`PHI` to `NO`). Three of four new teams
moved toward the incoming caller's earlier PCAE (`75%`). This sample is far too small for a
causal claim.
The historically documented reliability estimates were approximately `0.4372` for one season
and `0.6084` for a two-season average.

### What we learned

Expected decision value had aggregate validation signal and moderate repeatability, but PCAE is
still an observational association containing scheme, staff, roster, opponent, and model error.
It must be attributed to an explicitly verified play caller and shrunk for limited evidence.

### Next step

Recreate the missing weekly 2024/2025 play-caller evidence table with citations and intervals,
then rerun the preserved code and reconcile the exact eligibility counts before publication.

## Phase 3 — Environment controls

### Question

Does exploratory PCAE retain descriptive value after reasonable inherited-environment controls?

### Test

The first 2025 regressions compared prior-team EPA alone with prior-team EPA plus PCAE, then
added preseason expected QB EPA. The initial supporting-cast construction was rejected because
Week 1 roster data included cut, practice/development-squad, and reserve players. The corrected
scope used active/inactive Week 1 WR/RB/TE/FB players. Opponent strength was corrected for
circularity by calculating defensive EPA while leaving out the focal offense. The final
robustness test used leave-one-team-out cross-validation over the 32 teams.

### Result

Historically documented in-sample comparisons were:

| Specification | R² |
|---|---:|
| Prior team EPA | 0.1767 |
| Prior team EPA + PCAE | 0.5190 |
| Prior team + expected QB | 0.2048 |
| Prior team + expected QB + PCAE | 0.5320 |

In the latter pair, PCAE added approximately `0.3271` R². The corrected supporting-cast scope
contained 431 usable players, approximately 13.47 per team. Environment with prior team,
expected QB, and corrected supporting cast produced R² `0.2212`; adding PCAE produced `0.5329`,
an addition of approximately `0.3117`.

The historically documented final leave-one-team-out results were:

- environment-only CV R²: approximately `-0.1168`
- environment-plus-PCAE CV R²: approximately `+0.2413`
- improvement: approximately `+0.3581`
- environment-only RMSE: approximately `0.0970`
- environment-plus-PCAE RMSE: approximately `0.0800`
- RMSE reduction: approximately `0.0171`

Final standardized descriptive coefficients were prior team `0.315`, expected QB `0.134`,
supporting cast `-0.0557`, opponent strength `0.0024`, and PCAE `0.5662`.

### What we learned

PCAE survived these limited controls and improved held-out explanatory performance in that run.
The coefficients are not final weights. With only 32 teams and overlapping predictors, the
negative supporting-cast coefficient must not be interpreted as evidence that supporting cast
hurts offense. Environment belongs in controls and sensitivity analysis, not as an automatically
positive Coach Effect component.

### Next step

Expand years, preserve preseason timing, keep roster eligibility auditable, and validate each
environment definition before estimating any production relationship.

## Phase 4 — Coach Effect framework

### Question

Do PAE and PCAE describe the same signal, and how can their shared linear information be kept
separate from their unique components?

### Test

The 2025 paired coach-level analysis measured correlation and direction agreement. It then
residualized PAE on PCAE and PCAE on PAE. The research code preserves the two unique residuals
and an unweighted shared standardized diagnostic; it does not produce a ranking.

### Result

Historically documented 2025 PAE-versus-PCAE correlation was approximately `0.5926`, shared
variance `0.3512`, and same-direction rate `0.75`. After residualization, PAE correlation with
unique PCAE and PCAE correlation with unique PAE were each approximately zero, as required by
the linear projection.

### What we learned

PAE and PCAE overlap, but most variance was not shared in that sample. The conceptual components
are Unique QB Development Signal, Unique Play Calling Signal, and Shared Coaching Signal. Their
combination remains deliberately unestimated:

`Coach Effect_c = Confidence_c × [w_Q × UniqueQB_c + w_P × UniquePCAE_c + w_S × SharedSignal_c]`

No values are assigned to `w_Q`, `w_P`, or `w_S`.

### Next step

Estimate reliability and weights only after expanded historical data, comprehensive assignment
verification, and out-of-sample validation. One season or one QB can never support an
unqualified elite label.

## Rejected or corrected approaches

- Generic staff turnover without starting-PAE controls: rejected because regression to the mean
  dominated the comparison.
- One extreme QB transition as a coach signal: rejected for inadequate breadth and stability.
- OC title as automatic play-caller identity: rejected; explicit evidence is mandatory.
- Individual actual play EPA as Call Value: rejected; only expected chosen-versus-alternative EPA
  defines the decision score.
- Negative raw league Call Value as universal failure: rejected; PCAE is league-centered.
- Week 1 roster membership without status filtering: corrected to active/inactive eligible skill
  players.
- Opponent defense including the focal offense: corrected with leave-each-offense-out strength.
- In-sample R² as final validation: supplemented by leave-one-team-out testing.
- Environment as a positive additive component: rejected; it is a control/sensitivity input.
- Subjective final component weights: prohibited until empirical validation supports them.

## Reproduction status

| Artifact/result | Current status | Reason |
|---|---|---|
| PAE formula and out-of-sample rows | Reproducible | Checkpoint-five artifact and code are present. |
| Phase 1 transition methods | Recreated | SQL/Python are preserved; the original saved transition table is absent. |
| Exact Kubiak/Schottenheimer examples | Historically documented | Original transition result rows are not committed. |
| 2022–2025 PBP source | Available locally | Official cached Parquet exists; generated outputs remain ignored. |
| `133,636` initial plays | Historically documented, not yet reconciled | A simple current run/pass/REG filter gives 134,138; the original 502-play eligibility exclusion was not saved. |
| `32,813` attributed 2025 plays | Historically documented, not reproducible yet | Current verified manual play-caller coverage is intentionally incomplete. |
| Phase 2 metrics, PCAE examples, repeatability | Historically documented | Exact weekly caller map and saved model outputs are absent. |
| Phase 3 32-team environment results | Historically documented | Exact corrected 32-team input table is absent. |
| Earlier `coach_qb_equation_v0` environment test | Separate experiment | It used 582 QB-team-season rows and a different target/grain; its negative held-out R² must not be conflated with this 32-team PCAE test. |
| Phase 4 paired correlations | Historically documented | Exact paired 2025 coach-level table is absent. |

No number was substituted to make the current repository appear to reproduce an absent artifact.

## Production gate

Production Coach Effect implementation is **blocked** until offensive coordinators,
quarterbacks coaches, and play callers are comprehensively verified. Play-caller assignments
must have explicit evidence and weekly or in-season intervals where duties changed, were shared,
or cannot safely be represented as a season-long assignment. The current manual-review queue is
evidence that this gate is not yet met. Production also requires historical PCAE expansion,
reconciliation of the Phase 2 eligibility count, exact reruns, expanded reliability testing,
out-of-sample weight estimation, explicit confidence/uncertainty rules, suppression/evidence
thresholds, and approval of non-causal presentation.
