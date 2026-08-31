# NFL Coaching Impact Engine

The NFL Coaching Impact Engine is a sports analytics portfolio project that asks:

> Which coaches consistently help quarterbacks outperform expectations, and how large is their impact compared with player talent and team environment?

The project will follow NFL quarterbacks across seasons, teams, and coaching staffs. It will estimate adjusted associations rather than claim that observational data proves causation.

## Project status

Checkpoint seven is implemented and pending final approval. Immutable checkpoint-three through checkpoint-six artifacts and every serving-affecting manual CSV load atomically into versioned PostgreSQL serving tables. The read-only FastAPI application exposes QB, PAE, coaching, citation, review, and exploratory coach-impact results while preserving verification, confidence, interval, uncertainty, identification, eligibility, and suppression labels. No frontend, dashboard, authentication, deployment, or checkpoint-eight work was added.

- Analysis seasons: 2010-2025
- Warm-up only: 1999-2009
- Default QB threshold: 200 dropbacks
- Primary outcome: EPA per quarterback dropback
- Default coach-ranking threshold: three qualifying QB seasons, two distinct quarterbacks, and 600 verified exposure dropbacks

The serving publication contains historical `c3-f6c1aa118ff43b90`, expected performance `c5-8fd5d1aba2598c59`, and coach impact `c6-400a5b474aa37a35` / `coach-impact-400a5b474aa37a35`. Read [the checkpoint-seven report](docs/CHECKPOINT_7_REPORT.md).

## Football decision supported

The eventual application is designed for analysts and football-operations staff evaluating whether quarterback performance changed beyond a reasonable preseason expectation while a coach held a particular role. The answer must always be read alongside player history, supporting cast, team context, sample size, and uncertainty.

The first version focuses on quarterbacks and four coaching roles:

- Head coach
- Offensive coordinator
- Primary or shared offensive play-caller
- Quarterbacks coach

## Repository map

```text
.
├── data/manual/                 # Human-verified, source-backed inputs
├── db/schema.sql                # PostgreSQL analytical and serving schema
├── docs/                        # Audit, architecture, project plan, checkpoint report
├── scripts/audit_sources.py     # Independent boundary/source smoke audit
├── src/nfl_coaching_impact/     # Source, transform, validation, pipeline, and CLI code
├── tests/                       # Offline pipeline/contract and PostgreSQL behavior tests
├── requirements.lock            # Exact ingestion Python environment
├── DATA_SOURCES.md
├── METHODOLOGY.md
├── LIMITATIONS.md
├── MODEL_CARD.md
└── DATA_DICTIONARY.md
```

Raw and processed data directories are deliberately ignored. Large upstream files and API responses must not be committed.

## Run the checkpoint-seven database and API

Set `DATABASE_URL` in an uncommitted `.env`, then migrate, load, and serve:

```bash
DATABASE_URL=postgresql://user:password@localhost:5432/nfl_coaching make db-migrate
DATABASE_URL=postgresql://user:password@localhost:5432/nfl_coaching make db-load
DATABASE_URL=postgresql://user:password@localhost:5432/nfl_coaching make api
```

OpenAPI is available at `/docs`. Routes include health/version, QB and PAE, coaches and exploratory impact, teams, assignments, network data, citations, and review summaries. List responses contain `items`, `total`, `limit`, and `offset`; every ordering ends in a stable business key. Invalid role/status filters return 422, missing details return 404, and no-match lists return an empty page. Network edges retain both assignments' verification, confidence, shared/provisional, interval, and overlap metadata. Coach-impact responses retain identification and suppression labels and are not definitive rankings.

The local API has no authentication and must not be exposed publicly. Every query transaction is read-only, and credentials, filesystem paths, and mutable execution logs are never returned.

## Build checkpoint five

Install the exact Python 3.12 environment, ensure the checkpoint-three historical `LATEST` build exists, and run:

```bash
make PYTHON=.venv/bin/python expected-performance
```

The command builds deterministic preseason features, four expanding-window candidates, evaluation tables, and selected PAE output under `data/processed/expected_performance/<data-version>/`. `LATEST` points to the immutable version. Execution timestamps and reuse status live separately in `EXECUTION_LOG.json`; generated Parquet and model artifacts remain ignored by Git.

## Build checkpoint six

After the approved historical, expected-performance, and manual coaching layers exist, run:

```bash
make PYTHON=.venv/bin/python coach-impact
```

The command publishes interval-compatible exposures, exploratory role-specific coach-associated PAE estimates, coach-specific conditional 200-draw block-bootstrap intervals where support is adequate, identification diagnostics, model comparisons, sensitivity results, overlap diagnostics, exclusions, and suppressed ranking contracts under `data/processed/coach_impact/<data-version>/`. Verified primary estimates never consume provisional assignments. Generated outputs remain ignored by Git.

## Validate checkpoint four

The committed coaching facts are compact manual data, not regenerated by downloading source PDFs. Large NFL books remain uncommitted; their exact URLs and SHA-256 digests are in `data/manual/coaching_source_registry.csv`.

```bash
make PYTHON=.venv/bin/python coaching-validate
make PYTHON=.venv/bin/python test
```

The separately callable network check verifies the 16 source books and all additional assignment-source URLs, then checks live page content for the verified play-caller intervals, exact Houston 2020 boundaries, directly sourced interim head coaches, and representative interval, identity, and compound-title evidence:

```bash
make PYTHON=.venv/bin/python coaching-sources
```

To load the validated compact layer into an existing PostgreSQL schema whose teams are already populated, use `DATABASE_URL=... make coaching-load`. The loader writes `interval_basis` with every assignment and commits verified rows with their citations in one transaction.

## Reproduce checkpoint three

Use Python 3.12. Generated assets are ignored by Git.

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m pip install --no-deps -e .
make PYTHON=.venv/bin/python historical-preflight
make PYTHON=.venv/bin/python historical
```

The preflight resolves every expected asset and checks conservative storage capacity before downloading. The build downloads only cache misses, validates and publishes each season independently, and atomically publishes the complete version only after all seasons pass. Once all assets are cached, prove a network-free checksum-identical rerun with:

```bash
make PYTHON=.venv/bin/python historical-offline
```

`data/processed/historical/LATEST` names the immutable current version. Inside it, `bronze/` contains exact upstream Parquet bytes, `silver/` contains derived and partitioned context tables, and the root contains deterministic JSON/Markdown build evidence plus checksums for every published output. A cached version is reused only after all those checksums pass. Execution timestamps, cache status, retrieval headers, preflight measurements, and reuse status live separately in mutable `data/processed/historical/EXECUTION_LOG.json`; they may differ without changing the analytical version. The cache and all generated Parquet remain local.

Run deterministic tests and lint with:

```bash
make PYTHON=.venv/bin/python test
make PYTHON=.venv/bin/python test-network
.venv/bin/ruff check .
.venv/bin/ruff format --check .
```

The database and API contracts are tested against a disposable real PostgreSQL server, not by inspecting SQL text:

```bash
python3 -m pip install -e '.[application,dev]'
make PYTHON=.venv/bin/python test-postgres
```

The runner starts a bundled isolated PostgreSQL server when `TEST_DATABASE_URL` is unset. It proves immutable/repeatable migrations, bidirectional exposure-assignment lineage, citation guards, old-publication preservation on rollback, exact-byte manual-input identity and mid-load mutation rejection, idempotency, deterministic clean loads across all eight views, stable pagination, serving filters, and API behavior. An external disposable PostgreSQL URL may be supplied instead.

To repeat the network smoke checks:

```bash
python3 scripts/audit_sources.py --network
python3 scripts/audit_sources.py --network --download-samples
```

`--download-samples` downloads three small 2025 CSV files into a temporary directory and streams bounded 2010 and 2025 play-by-play samples. It validates required columns, `qb_dropback`, finite `qb_epa`, and resolved passer/scrambler GSIS IDs, then removes the temporary files. It does not retain or fully download either play-by-play season.

Checkpoints five and six use scikit-learn with Polars/NumPy/SciPy preprocessing, regularization, evaluation, and deterministic empirical-Bayes partial pooling. The planned later stack adds PostgreSQL, SQLAlchemy, Alembic, FastAPI, and Next.js/TypeScript only in their approved checkpoints. DuckDB remains an embedded analysis option.

Secrets will be loaded from environment variables. Copy `.env.example` to `.env` only when a later checkpoint needs credentials, and never commit `.env`.

## Documentation

- [Data feasibility](docs/FEASIBILITY_AUDIT.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Data sources](DATA_SOURCES.md)
- [Methodology](METHODOLOGY.md)
- [Limitations](LIMITATIONS.md)
- [Model card](MODEL_CARD.md)
- [Data dictionary](DATA_DICTIONARY.md)
- [Phased project plan](docs/PROJECT_PLAN.md)
- [Checkpoint four report](docs/CHECKPOINT_4_REPORT.md)
- [Checkpoint five report](docs/CHECKPOINT_5_REPORT.md)
- [Checkpoint six report](docs/CHECKPOINT_6_REPORT.md)
- [Checkpoint seven report](docs/CHECKPOINT_7_REPORT.md)

## Interpretation standard

Coach estimates will be described as adjusted associations. They can be affected by hiring and firing decisions, coach-quarterback matching, roster construction, overlapping staff responsibilities, injuries, schedule, measurement error, and small samples. The application will show uncertainty and supporting evidence rather than a single context-free leaderboard.
