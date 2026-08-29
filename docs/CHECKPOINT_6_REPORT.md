# Checkpoint six report — coach-associated PAE

Date: 2026-08-29

## Outcome

Checkpoint six is implemented and pending approval. It produces source-compatible coaching exposures, role-specific adjusted associations, uncertainty, sensitivity results, and explicitly preliminary non-publishable rankings. No causal claim, college data, API, frontend, coaching network visualization, production dashboard, or checkpoint-seven work was added.

- Historical source: `c3-f6c1aa118ff43b90`
- Expected-performance source: `c5-8fd5d1aba2598c59`
- Coach-impact data: `c6-4037f7ff531cd69f`
- Coach-impact model: `coach-impact-4037f7ff531cd69f`
- Command: `make PYTHON=.venv/bin/python coach-impact`

## Exposure construction

The modeling grain is QB-coach-assignment interval. QB-game performance is joined to a coaching assignment only when team, season, and observed week fit its supported interval, then aggregated with dropbacks. This preserves midseason changes and rejects illegal non-shared overlaps. Shared play-calling creates separate rows with fractional exposure: Houston Week 4 assigns 20 exposure dropbacks each to Tim Kelly and Bill O'Brien from the same 40 observed QB dropbacks. Interval PAE reconciles exactly as interval actual EPA/dropback minus the unchanged preseason expected EPA/dropback.

| Role | Status | Rows | Coaches | Exposure dropbacks |
|---|---|---:|---:|---:|
| Head coach | Verified | 1,729 | 120 | 319,285 |
| Offensive coordinator | Verified | 34 | 15 | 5,326 |
| Offensive coordinator | Provisional | 1,280 | 136 | 244,861 |
| Play-caller | Verified | 20 | 9 | 2,593 |
| Play-caller | Provisional | 3 | 1 | 502 |
| Quarterbacks coach | Verified | 3 | 1 | 660 |
| Quarterbacks coach | Provisional | 1,239 | 132 | 236,539 |

The primary model excludes 1,854 intervals below 25 observed dropbacks: 746 verified head-coach, 11 verified OC, six verified play-caller, two verified QB-coach, and 1,089 provisional intervals. These remain in the exposure and exclusion tables rather than disappearing.

## Model specifications and selection

All roles are modeled separately. The compared specifications are:

1. A no-coach Ridge baseline with preseason QB controls, season, repeated-QB indicators, and team-season context.
2. A regularized coach fixed-effects Ridge model with the same controls.
3. A weighted empirical-Bayes partial-pooling model applied to baseline residuals, shrinking sparse coach means toward zero.

The empirical-Bayes model is selected for reporting because it explicitly shrinks small samples, slightly improves the verified head-coach baseline, remains deterministic, and does not force a crossed-role model onto sparse verified non-head-coach data. Metrics are descriptive in-sample diagnostics, not out-of-sample coach validation.

| Role | Model | Observations | MAE | RMSE | R² |
|---|---|---:|---:|---:|---:|
| Head coach | No-coach baseline | 983 | 0.05972 | 0.10980 | 0.68488 |
| Head coach | Coach fixed effects | 983 | 0.06098 | 0.11094 | 0.67831 |
| Head coach | Partial pooling | 983 | 0.05895 | 0.10815 | 0.69425 |
| Offensive coordinator | No-coach baseline | 23 | 0.06287 | 0.10483 | 0.49429 |
| Offensive coordinator | Coach fixed effects | 23 | 0.03874 | 0.08814 | 0.64256 |
| Offensive coordinator | Partial pooling | 23 | 0.04635 | 0.09224 | 0.60849 |
| Play-caller | No-coach baseline | 14 | 0.01181 | 0.01766 | 0.98698 |
| Play-caller | Coach fixed effects | 14 | 0.01657 | 0.02766 | 0.96806 |
| Play-caller | Partial pooling | 14 | 0.01004 | 0.01662 | 0.98848 |

The unusually high play-caller R² reflects only 14 usable verified intervals and extensive fixed controls; it is not evidence of strong generalization. The single usable verified QB-coach interval cannot identify a role model, so its estimate is null and its exclusion reason is `insufficient_role_identification`.

## Preliminary rankings and uncertainty

Rank eligibility requires an estimable verified effect, at least three eligible QB seasons, at least two distinct quarterbacks, and at least 600 verified exposure dropbacks. Exposure is an eligibility/reliability rule, never the ranking formula. Eligible coaches are ordered only by the shrunken estimated association.

| Role | Coach results | Estimated | Rank eligible |
|---|---:|---:|---:|
| Head coach | 120 | 120 | 81 |
| Offensive coordinator | 15 | 15 | 0 |
| Play-caller | 9 | 9 | 0 |
| Quarterbacks coach | 1 | 0 | 0 |

All ranking rows carry `ranking_status = preliminary_non_publishable`. The first head-coach point estimates are small and their bootstrap intervals commonly cross zero; for example, Romeo Crennel's estimate is 0.02553 EPA/dropback with a -0.00418 to 0.04698 interval. This ordering is exploratory, not a publishable claim that one coach caused better quarterback play.

Uncertainty uses 200 deterministic QB-season block-bootstrap draws. Coaches appear in 115-200 resamples depending on whether their QB-season blocks are selected; all estimable coaches receive an interval. Reliability is based on verified exposure and remains separate from rank.

## Sensitivity and stability

Sensitivity outputs cover verified plus provisional assignments, excluding shared duties, equal rather than dropback weighting, removing QB effects, removing team-season controls, and minimum interval exposure of 100 or 200 dropbacks.

- Head-coach rank correlation versus primary is 0.768 without QB effects but 0.466 without team-season controls, 0.437 under equal weighting, 0.576 at 100 interval dropbacks, and 0.464 at 200. The ordering is not stable enough for publication.
- OC estimates are more rank-stable across available verified rows, but only 23 usable intervals and zero eligible coaches make that apparent stability weak evidence. Adding provisional designations changes median absolute OC effects by 0.02332 EPA/dropback.
- Play-caller results use only 14 verified usable intervals. Adding the provisional Tim Kelly interval yields rank correlation 0.524; no play-caller qualifies.
- Excluding the shared Houston Week 4 rows does not materially change matched estimates, but the shared rows are below the 25-dropback primary threshold and remain visible in the diagnostics.

## Validation and reproducibility

Hard checks cover duplicate assignment/exposure grains, team-season-week lineage, unsupported overlaps, shared fractions, interval boundaries, future-feature leakage, verified/provisional separation, exact PAE arithmetic, ranking eligibility, deterministic bootstrap behavior, content identity, atomic failure, and byte-identical clean rebuilds. Model identity includes source checksums, every model/ranking/bootstrap/sensitivity parameter, NumPy/Polars/SciPy/scikit-learn versions, and relevant code hashes. Deterministic floating outputs are normalized to 12 decimal places before serialization so harmless BLAS-order differences cannot change bytes under the same identity. Execution timestamps remain outside deterministic artifacts.

The complete offline discovery run contains 81 tests: 70 passed and 11 skipped. Nine behavioral PostgreSQL tests were skipped because `TEST_DATABASE_URL`, a PostgreSQL client/server, and `psycopg` are unavailable; checkpoint six does not add a PostgreSQL loader, so this remains a checkpoint-seven integration risk. The two opt-in network tests were then run explicitly and both passed. All ten checkpoint-six tests passed, including an independent-process clean-rebuild comparison. Ruff lint, Ruff formatting, and `git diff --check` passed.

## Missing context and limitations

No validated complete-window offensive-line, receiver-quality, defensive-strength, or schedule-strength feature table exists, so those variables are not invented. Prior injury counts and preseason QB history are included; team-season indicators are retrospective context and can absorb coach-associated variation. Coaches and quarterbacks are not randomly matched, staff roles overlap, successful pairings survive, and PAE contains unmeasured roster, scheme, health, opponent, and luck effects. These estimates are adjusted associations, not causal effects.

## Files created or changed

- Modeling and CLI: `src/nfl_coaching_impact/coach_impact.py`, `src/nfl_coaching_impact/cli.py`, `Makefile`, `requirements.lock`
- Tests: `tests/test_checkpoint_six_coach_impact.py`, `tests/test_repository_contract.py`
- Documentation: `README.md`, `DATA_DICTIONARY.md`, `METHODOLOGY.md`, `LIMITATIONS.md`, `MODEL_CARD.md`, `docs/PROJECT_PLAN.md`, `docs/CHECKPOINT_6_REPORT.md`

Generated Parquet, JSON, checksums, rankings, and execution logs remain under ignored `data/processed/`; none are committed.

## Exact next checkpoint

Checkpoint seven will create Alembic migrations and deterministic loaders for approved historical, PAE, coaching, and coach-impact outputs; populate the curated PostgreSQL schema and serving views; and build tested FastAPI search, filter, pagination, QB/coach/team detail, lineage, uncertainty, and methodology endpoints. It must not start until checkpoint six is explicitly approved. The frontend, network graph, production dashboard, deployment, and college enrichment remain out of scope.
