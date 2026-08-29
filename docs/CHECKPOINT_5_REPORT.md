# Checkpoint five report — expected quarterback performance and PAE

Date: 2026-08-29

## Outcome

Checkpoint five is implemented and pending approval. One deterministic command builds leakage-safe preseason features, four expanding-window candidates, out-of-sample expectations, uncertainty, evaluation tables, and normalized PAE output. No coach effects, coach rankings, final quarterback rankings, API, frontend, college ingestion, or checkpoint-six work was added.

- Source data: `c3-f6c1aa118ff43b90`
- Checkpoint-five data: `c5-8fd5d1aba2598c59`
- Model: `expected-performance-8fd5d1aba2598c59`
- Feature version: `qb-preseason-v2`
- Build command: `make PYTHON=.venv/bin/python expected-performance`

## College and feature availability

No validated college-performance dataset exists. The repository contains only a profile college-name field, which is not used as production evidence. College production, draft position, and draft round remain null with explicit missing indicators; no values were fabricated or backfilled.

The fitted features are age, roster-reported NFL experience/rookie status, prior QB-season count and no-history flag, exact season-minus-one starts/dropbacks and EPA/CPOE/success/sack/interception/touchdown rates, career starts/dropbacks and the same career rates through `S-1`, opening-week team change, and prior injury-report/out weeks. Coaching assignments, coach identities, current-season results, records, rankings, supporting-cast results, and future seasons are absent from the model feature contract.

Analysis-season missingness is:

| Missing feature | Rows |
|---|---:|
| Exact prior season | 662 |
| Prior CPOE | 688 |
| Prior injury information | 804 |
| Team-change information | 794 |
| Draft position | 1,689 |
| Draft round | 1,689 |
| College production | 1,689 |
| Age | 0 |

Roster metadata identifies 187 true-rookie rows, 191 one-prior-NFL-season rows, and 1,311 veteran rows. Performance history is tracked independently: 455 rows have no prior QB performance, 265 have one prior QB season, and 969 have multiple prior QB seasons. A unique opening-week team is available for 1,441 rows; 248 lack that snapshot. Among rows with both an opening team and prior QB-team history, 208 are team changes and 687 are continuations.

## Review-finding corrections

- **Target-season destinations:** `changed_team` uses only a unique Week 1 regular-season depth-chart team and is identical across every player-season stint. Trent Edwards' 2010 Buffalo and Jacksonville rows both retain Buffalo as the opening team; Jacksonville cannot affect Ridge features, 2010 predictions, or later training.
- **Rookie versus performance history:** `years_exp`, `entry_year`, and `rookie_year` distinguish actual rookies from veterans without prior recorded QB dropbacks. Austin Davis, Trevor Siemian, Jeff Driskel, and Mason Rudolph are correctly non-rookies with `no_prior_qb_performance = true`; a true rookie remains in the rookie group.
- **Content versioning:** source Parquet checksums, all declared shrinkage/selection/interval/reliability/sensitivity/weight parameters, NumPy/Polars/SciPy/scikit-learn versions, and relevant source-code hashes participate in the data/model version. Career-shrinkage and recorded-SciPy-version regressions each create and rebuild a different immutable directory rather than reusing stale output.

## Models and selection

All published predictions are expanding-window OOS: season `S` uses only seasons earlier than `S`. Ridge hyperparameters are tuned inside time-ordered training folds. The evaluation population is 582 QB-team-seasons with at least 200 dropbacks.

| Candidate | MAE | RMSE | R² | Correlation | Calibration intercept | Calibration slope | Interval coverage | Selection score |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Career performance (selected) | 0.09172 | 0.11752 | 0.18925 | 0.44673 | 0.00707 | 0.82192 | 94.50% | 0.09705 |
| Recent performance | 0.09519 | 0.12135 | 0.13541 | 0.41666 | 0.01580 | 0.68326 | 95.19% | 0.10547 |
| Ridge | 0.09398 | 0.12104 | 0.13985 | 0.43562 | 0.02288 | 0.66433 | 94.67% | 0.10642 |
| League average | 0.10565 | 0.13273 | -0.03435 | -0.01722 | 0.06944 | -0.31157 | 93.47% | 0.14924 |

Career performance won the declared score: OOS MAE plus penalties for absolute calibration intercept and slope departure from one. Both Ridge and every baseline remain published for audit. A mixed-effects expectation model was not added because the required candidates were reliable and the extra hierarchy was not necessary for checkpoint five.

## PAE, eligibility, and uncertainty

The output contains 1,689 analysis-season PAE rows and 6,756 candidate prediction rows. Exactly 582 PAE rows are eligible at 200 dropbacks; 1,107 smaller samples remain visible but low reliability. Reliability is high for 417 eligible rows with at least 600 prior career dropbacks and medium for 165 other eligible rows.

```text
PAE = actual EPA/dropback - expected EPA/dropback
```

Recent and career baselines shrink small histories toward the prior league average with 200 and 500 pseudo-dropbacks. True rookies and veterans without QB-performance history both fall back to that average in these baselines but remain distinct Ridge inputs. Intervals use only earlier-season OOS residual RMSE, with prior-training outcome dispersion as the early fallback. The mean 95% interval width is 0.47506 EPA/dropback.

Representative eligible rows demonstrate output shape, not a ranking:

| QB | Season | Team | Actual | Expected | PAE | Dropbacks | Reliability |
|---|---:|---|---:|---:|---:|---:|---|
| Kerry Collins | 2010 | TEN | 0.08877 | 0.03727 | 0.05150 | 291 | high |
| Brett Favre | 2010 | MIN | -0.11644 | 0.09511 | -0.21156 | 384 | high |
| Peyton Manning | 2010 | IND | 0.18962 | 0.23548 | -0.04586 | 696 | high |
| Tom Brady | 2010 | NE | 0.28994 | 0.15777 | 0.13217 | 522 | high |
| Mike Vick | 2010 | PHI | 0.20969 | -0.03644 | 0.24613 | 459 | high |

## Validation and reproducibility

Hard checks reject target/future performance seasons, any `as_of_season` other than `S-1`, destination-dependent model features within a player-season, duplicate QB seasons or predictions, non-finite actual/expected/PAE values, arithmetic or dropback mismatch, warm-up PAE, forbidden coaching/current-result features, and valid-looking partial output after failure. Adversarial tests change target-season EPA and a midseason destination independently and prove expectations/training remain unchanged.

The content version hashes the historical QB-season, player, injury, roster, and depth-chart inputs plus the full feature/model specification, relevant code, and modeling dependencies. SciPy is recorded explicitly because Ridge depends on its numerical routines. Deterministic artifacts contain no timestamps or cache state. `EXECUTION_LOG.json` is outside the immutable version and may legitimately differ. A two-empty-directory fixture test compares every deterministic Parquet, JSON, checksum, and version byte-for-byte.

The real historical build was also rebuilt into a second empty directory. Its data/model versions, every Parquet and JSON artifact, checksum manifest, and `LATEST` value were byte-identical. A normal rerun validated all checksums and reused the existing immutable version.

## Test results

The complete discovery run found 71 tests: 60 passed and 11 skipped. Nine behavioral PostgreSQL tests were skipped because `TEST_DATABASE_URL`, a PostgreSQL client/server, and `psycopg` remain unavailable; the updated checkpoint-five schema behavior is therefore still an integration risk, not a silently claimed pass. The two opt-in checkpoint-three/four network tests were then run explicitly and both passed. All 15 checkpoint-five offline tests passed, including the Trent Edwards, roster-status, parameter-version, SciPy-version, and two-clean-build regressions. The real historical output also rebuilt into a second empty directory with the same version and byte-identical Parquet, JSON, checksum, and `LATEST` artifacts. Ruff lint passed, Ruff formatting reported all 41 Python files formatted, and `git diff --check` passed.

## Files created or changed

- Modeling: `src/nfl_coaching_impact/expected_performance.py`, `src/nfl_coaching_impact/cli.py`, `Makefile`, `requirements.lock`
- Schema: `db/schema.sql`
- Tests: `tests/test_checkpoint_five_expected_performance.py`, `tests/test_postgres_behavior.py`, `tests/test_repository_contract.py`
- Documentation: `README.md`, `DATA_DICTIONARY.md`, `METHODOLOGY.md`, `LIMITATIONS.md`, `MODEL_CARD.md`, `docs/PROJECT_PLAN.md`, `docs/CHECKPOINT_5_REPORT.md`

Generated PAE, features, evaluation tables, and execution logs remain under ignored `data/processed/`; no generated model artifact, raw data, credential, coaching assignment change, or ranking was committed.

## Remaining limitations

The selected baseline beats corrected Ridge but is not proof that career EPA is universally best. True-rookie performance is poorly explained, 794 rows lack a team-change value under the conservative cutoff, validated draft/college features are absent, and intervals are not player-specific. PAE can reflect supporting cast, scheme, injuries, opponent mix, and chance; it is not a causal or intrinsic-quality measure. Smaller samples remain noisy even though they are stored.

## Exact next checkpoint

Checkpoint six will estimate role-specific coach associations from QB-game performance and approved PAE/context inputs, with partial pooling, QB/team effects, block-bootstrap uncertainty, role-overlap diagnostics, and eligibility warnings. It must not start until checkpoint five is explicitly approved. Provisional coaching assignments and unresolved manual-review items must remain excluded or visibly flagged; no API or frontend belongs in checkpoint six.
