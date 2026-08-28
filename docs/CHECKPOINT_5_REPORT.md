# Checkpoint five report — expected quarterback performance and PAE

Date: 2026-08-28

## Outcome

Checkpoint five is implemented and pending approval. One deterministic command builds leakage-safe preseason features, four expanding-window candidates, out-of-sample expectations, uncertainty, evaluation tables, and normalized PAE output. No coach effects, coach rankings, final quarterback rankings, API, frontend, college ingestion, or checkpoint-six work was added.

- Source data: `c3-f6c1aa118ff43b90`
- Checkpoint-five data: `c5-98c98cdcc8492333`
- Model: `expected-performance-98c98cdcc8492333`
- Feature version: `qb-preseason-v1`
- Build command: `make PYTHON=.venv/bin/python expected-performance`

## College and feature availability

No validated college-performance dataset exists. The repository contains only a profile college-name field, which is not used as production evidence. College production, draft position, and draft round remain null with explicit missing indicators; no values were fabricated or backfilled.

The fitted features are age, observed NFL experience, exact season-minus-one starts/dropbacks and EPA/CPOE/success/sack/interception/touchdown rates, career starts/dropbacks and the same career rates through `S-1`, team change, and prior injury-report/out weeks. Coaching assignments, coach identities, current-season results, records, rankings, supporting-cast results, and future seasons are absent from the model feature contract.

Analysis-season missingness is:

| Missing feature | Rows |
|---|---:|
| Exact prior season | 662 |
| Prior CPOE | 688 |
| Prior injury information | 804 |
| Draft position | 1,689 |
| Draft round | 1,689 |
| College production | 1,689 |
| Age | 0 |

There are 455 rookie rows, 265 with one prior observed season, 969 veteran rows, and 290 team-change rows.

## Models and selection

All published predictions are expanding-window OOS: season `S` uses only seasons earlier than `S`. Ridge hyperparameters are tuned inside time-ordered training folds. The evaluation population is 582 QB-team-seasons with at least 200 dropbacks.

| Candidate | MAE | RMSE | R² | Correlation | Calibration intercept | Calibration slope | Interval coverage | Selection score |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Career performance (selected) | 0.09172 | 0.11752 | 0.18925 | 0.44673 | 0.00707 | 0.82192 | 94.50% | 0.09705 |
| Ridge | 0.09209 | 0.11907 | 0.16762 | 0.44447 | 0.01769 | 0.72057 | 94.85% | 0.10210 |
| Recent performance | 0.09519 | 0.12135 | 0.13541 | 0.41666 | 0.01580 | 0.68326 | 95.19% | 0.10547 |
| League average | 0.10565 | 0.13273 | -0.03435 | -0.01722 | 0.06944 | -0.31157 | 93.47% | 0.14924 |

Career performance won the declared score: OOS MAE plus penalties for absolute calibration intercept and slope departure from one. Its advantage over Ridge is small, so both outputs and diagnostics remain published. A mixed-effects expectation model was not added because the required candidates were reliable and the extra hierarchy was not necessary for checkpoint five.

## PAE, eligibility, and uncertainty

The output contains 1,689 analysis-season PAE rows and 6,756 candidate prediction rows. Exactly 582 PAE rows are eligible at 200 dropbacks; 1,107 smaller samples remain visible but low reliability. Reliability is high for 417 eligible rows with at least 600 prior career dropbacks and medium for 165 other eligible rows.

```text
PAE = actual EPA/dropback - expected EPA/dropback
```

Recent and career baselines shrink small histories toward the prior league average with 200 and 500 pseudo-dropbacks. Rookies and missing-history cases fall back to that average. Intervals use only earlier-season OOS residual RMSE, with prior-training outcome dispersion as the early fallback. The mean 95% interval width is 0.47506 EPA/dropback.

Representative eligible rows demonstrate output shape, not a ranking:

| QB | Season | Team | Actual | Expected | PAE | Dropbacks | Reliability |
|---|---:|---|---:|---:|---:|---:|---|
| Kerry Collins | 2010 | TEN | 0.08877 | 0.03727 | 0.05150 | 291 | high |
| Brett Favre | 2010 | MIN | -0.11644 | 0.09511 | -0.21156 | 384 | high |
| Peyton Manning | 2010 | IND | 0.18962 | 0.23548 | -0.04586 | 696 | high |
| Tom Brady | 2010 | NE | 0.28994 | 0.15777 | 0.13217 | 522 | high |
| Mike Vick | 2010 | PHI | 0.20969 | -0.03644 | 0.24613 | 459 | high |

## Validation and reproducibility

Hard checks reject target/future feature seasons, any `as_of_season` other than `S-1`, duplicate QB seasons or predictions, non-finite actual/expected/PAE values, arithmetic or dropback mismatch, warm-up PAE, forbidden coaching/current-result features, and valid-looking partial output after failure. The explicit adversarial leakage test changes a target-season EPA value and proves every expectation for that season is unchanged.

The content version hashes the historical QB-season, player, and injury inputs plus the full feature/model specification. Deterministic artifacts contain no timestamps or cache state. `EXECUTION_LOG.json` is outside the immutable version and may legitimately differ. A two-empty-directory fixture test compares every deterministic Parquet, JSON, checksum, and version byte-for-byte.

The real historical build was also rebuilt into a second empty directory. Its data/model versions, every Parquet and JSON artifact, checksum manifest, and `LATEST` value were byte-identical. A normal rerun validated all checksums and reused the existing immutable version.

## Test results

The complete discovery run found 67 tests: 56 passed and 11 skipped. Nine behavioral PostgreSQL tests were skipped because `TEST_DATABASE_URL`, a PostgreSQL client/server, and `psycopg` were unavailable. Two deliberately opt-in checkpoint-three/four network tests were skipped because checkpoint five requires no network inputs. All 11 checkpoint-five offline tests passed. The checkpoint-four validator still reports 1,343 assignments, 1,349 citations, 281 coaches, 512 team-seasons, and 1,527 open reviews. Ruff lint passed, Ruff formatting reported all 41 Python files formatted, and `git diff --check` passed.

## Files created or changed

- Modeling: `src/nfl_coaching_impact/expected_performance.py`, `src/nfl_coaching_impact/cli.py`, `Makefile`, `requirements.lock`
- Schema: `db/schema.sql`
- Tests: `tests/test_checkpoint_five_expected_performance.py`, `tests/test_postgres_behavior.py`, `tests/test_repository_contract.py`
- Documentation: `README.md`, `DATA_DICTIONARY.md`, `METHODOLOGY.md`, `LIMITATIONS.md`, `MODEL_CARD.md`, `docs/PROJECT_PLAN.md`, `docs/CHECKPOINT_5_REPORT.md`

Generated PAE, features, evaluation tables, and execution logs remain under ignored `data/processed/`; no generated model artifact, raw data, credential, coaching assignment change, or ranking was committed.

## Remaining limitations

The selected baseline narrowly beats Ridge and is not proof that career EPA is the universally best forecast. Rookie performance is poorly explained, validated draft/college features are absent, and intervals are not player-specific. PAE can reflect supporting cast, scheme, injuries, opponent mix, and chance; it is not a causal or intrinsic-quality measure. Smaller samples remain noisy even though they are stored.

## Exact next checkpoint

Checkpoint six will estimate role-specific coach associations from QB-game performance and approved PAE/context inputs, with partial pooling, QB/team effects, block-bootstrap uncertainty, role-overlap diagnostics, and eligibility warnings. It must not start until checkpoint five is explicitly approved. Provisional coaching assignments and unresolved manual-review items must remain excluded or visibly flagged; no API or frontend belongs in checkpoint six.
