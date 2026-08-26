# Repository instructions

These instructions apply to the entire repository.

## Scope and checkpoints

- Work only on the checkpoint explicitly approved by the user.
- Do not begin the frontend before the data pipeline, coaching assignments, metrics, and models are validated.
- Version one is quarterback-only. Preserve extension points, but do not implement other positions prematurely.
- Never invent a coach assignment, player identifier, metric, source, or model result.

## Data handling

- Keep raw, processed, and manually verified data separate.
- Do not commit raw nflverse files, API responses, model artifacts, database dumps, or credentials.
- Use GSIS IDs for players, canonical internal IDs for teams, and repository-controlled IDs for coaches.
- Normalize historical team aliases through the date-valid alias table; never overwrite upstream values silently.
- A coaching assignment may be marked `verified` only when a source row exists.
- Missing or disputed facts remain null or `conflicting` and must be explained in notes.
- Record source URL, access date, coverage, collection method, and usage concern in `DATA_SOURCES.md`.

## Analytics

- Enforce preseason feature cutoffs. Never use the predicted season or a future season to construct a preseason feature.
- Do not use current-season honors as preseason predictors.
- Do not use same-season team offensive EPA as a coach-model control because it contains the QB outcome.
- Treat protection, receiver, rushing, injury, defense, and schedule variables as proxies or contextual measures where appropriate.
- Generate published PAE values from truly out-of-sample predictions.
- Report sample size, different quarterbacks, uncertainty, and stability with every coach estimate.
- Use association language, not causal claims.

## Engineering

- Prefer small, deterministic CLI pipeline stages over notebooks as production logic.
- Put reusable Python under `src/nfl_coaching_impact`; scripts should be thin entry points.
- Add tests for transformations, joins, identifiers, metric formulas, leakage, and database constraints.
- Make joins fail loudly on unexpected cardinality or missing stable IDs.
- Keep calculated metric definitions synchronized with `DATA_DICTIONARY.md`.
- Update `MODEL_CARD.md`, `METHODOLOGY.md`, and `LIMITATIONS.md` when modeling behavior changes.
- Do not add services such as Airflow, Redis, or dbt without a demonstrated project need.

## Verification

Before handing off a checkpoint, run the relevant tests, schema checks, and build commands. Report commands and outcomes honestly, including skipped checks and external blockers.
