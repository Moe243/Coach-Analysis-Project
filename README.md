# NFL Coaching Impact Engine

The NFL Coaching Impact Engine is a sports analytics portfolio project that asks:

> Which coaches consistently help quarterbacks outperform expectations, and how large is their impact compared with player talent and team environment?

The project will follow NFL quarterbacks across seasons, teams, and coaching staffs. It will estimate adjusted associations rather than claim that observational data proves causation.

## Project status

All nine checkpoints are complete. The responsive application and bounded Relationship Explorer are deployed on Render against the approved PostgreSQL publication on Neon. Coach Journey, QB Journey, Team History, and bounded Full Network preserve canonical identities, assignment intervals, QB-team-season PAE grain, missingness, evidence states, and suppression language. The graph and keyboard-accessible relationship explorer share the same response objects; neither turns same-team-season context into exact weekly overlap or causal coach attribution.

- [Live application](https://nfl-coaching-impact-engine.onrender.com)
- [Live API](https://nfl-coaching-impact-api.onrender.com)
- [Interactive API documentation](https://nfl-coaching-impact-api.onrender.com/docs)
- [Checkpoint-nine release report](docs/CHECKPOINT_9_REPORT.md)

- Analysis seasons: 2010-2025
- Warm-up only: 1999-2009
- Default QB threshold: 200 dropbacks
- Primary outcome: EPA per quarterback dropback
- Default coach-ranking threshold: three qualifying QB seasons, two distinct quarterbacks, and 600 verified exposure dropbacks

The approved serving publication contains historical `c3-f6c1aa118ff43b90`, expected performance `c5-8fd5d1aba2598c59`, and coach impact `c6-400a5b474aa37a35` / `coach-impact-400a5b474aa37a35`. The additive enhancement artifacts are local, checksum-protected inputs for the next intentional serving publication; they do not alter the deployed publication automatically. Read [the checkpoint-eight report](docs/CHECKPOINT_8_REPORT.md) and [post-release enhancement foundation](docs/POST_RELEASE_ENHANCEMENTS.md).

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
├── frontend/                    # React, TypeScript, Vite, tests, and responsive UI
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

OpenAPI is available at `/docs`. Routes include health/version, QB and PAE, team-season statistics, coaches and exploratory impact, teams, assignments, coaching completeness, inherited environment context, network data, citations, review summaries, and `GET /relationships/explorer`. List responses contain `items`, `total`, `limit`, and `offset`; every ordering ends in a stable business key. Invalid role/status filters return 422, missing details return 404, and no-match lists return an empty page. Network edges retain both assignments' verification, confidence, shared/provisional, interval, and overlap metadata. Coach-impact responses retain identification and suppression labels and are not definitive rankings.

The local Stage 1 serving candidate implements schema `checkpoint-7.4`, loader `serving-loader-v5`, and API contract `api-v1.4`, returning a deterministic, bounded `Coach -> Team-Season <- QB` subgraph. Coach-assignment relationships remain one `assignment_key`; QB relationships remain one `(player_id, team_id, season)` and receive PAE only through that complete key. Team-history and team-anchored full-network requests seed canonical-position QB facts independently from `api_qb_statistics`, so role, verification, and provisional filters affect coach edges without deleting valid QB-team-season facts. Coach/QB/team-history modes require the corresponding anchor. Full-network mode requires an anchor and at most five seasons, and every response is capped at 1,000 nodes and 2,000 relationships. The response explicitly labels coach-QB context as same-team-season context, not exact weekly exposure or causation.

The `/network` Relationship Explorer stores supported mode, Timeline/Network display, canonical anchor, year range, role/evidence/QB filters, selected entity, and focused entity in the URL. Timeline is the default for journeys and Team History; Full Network defaults to the canonical graph. Timeline orders team-seasons chronologically while preserving every assignment and QB-team-season relationship; the bounded Network display retains canonical nodes and stable type columns. Select highlights the direct neighborhood, Focus opens a bounded canonical journey/history, Reset clears view filters while retaining the current scope, and Back restores the prior meaningful focus. HTTP 413 is shown as a complete failure with narrowing guidance; partial graphs are never presented.

The public API is intentionally read-only and unauthenticated. Production CORS is restricted to the exact deployed frontend origin. Every query transaction is read-only, and credentials, filesystem paths, and mutable execution logs are never returned.

## Run the checkpoint-eight frontend

Start the checkpoint-seven API first, then install and run the workspace frontend:

```bash
corepack enable
pnpm install --frozen-lockfile
make frontend-dev
```

Vite serves the local interface and proxies `/api` to `http://127.0.0.1:8000` by default. Override `VITE_API_PROXY_TARGET` for another local API or set `VITE_API_BASE_URL` when building for a reverse-proxied environment. The browser never receives `DATABASE_URL` or any other credential. See [the frontend guide](frontend/README.md) for routes and production-build details.

Run the frontend quality suite with:

```bash
make frontend-check
```

Filters, expanded metrics, and pagination are URL-addressable. The interface retries every required query after a dependency failure. Graph selection highlights connected nodes and edges, fades unrelated elements, and clears when filtering removes the selected node. The keyboard-readable graph alternative exposes coach names, roles, team-season, full assignment intervals, verification, confidence, provisional/shared, interim, and retained status when available. Statistics coach filters are described accurately as team-season coaching context rather than exact weekly overlap. Compact screens switch the statistics table to labeled record cards.

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

## Build post-release enhancement artifacts

```bash
PYTHONPATH=src .venv/bin/python -m nfl_coaching_impact.cli enhancements --project-root .
```

This additive command does not modify checkpoint-three, five, or six outputs. It produces
QB box-score/rate facts, team-season result/offense facts, a complete coaching-role audit, and strictly preseason
inherited environment features. It does not calculate or publish a Coach QB Impact Score.

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

Checkpoints five and six use scikit-learn with Polars/NumPy/SciPy preprocessing, regularization, evaluation, and deterministic empirical-Bayes partial pooling. Checkpoint seven adds PostgreSQL, SQLAlchemy, Alembic, and FastAPI; checkpoint eight adds a React/TypeScript/Vite client with TanStack Query and Cytoscape. DuckDB remains an embedded analysis option.

Secrets will be loaded from environment variables. Copy `.env.example` to `.env` only when a later checkpoint needs credentials, and never commit `.env`.

## Deployment and licensing

The reproducible Render/Neon release procedure is documented in [the deployment guide](docs/DEPLOYMENT.md). Render receives `DATABASE_URL`, `CORS_ORIGINS`, and `VITE_API_BASE_URL` through provider environment variables only. The client shows an “API is waking up” state and retries transient cold-start failures automatically. The public API is intentionally read-only and unauthenticated; free-tier cold starts and availability limits remain explicit.

Original code and documentation are available under the [MIT License](LICENSE). Third-party datasets and derived material remain subject to their original terms; read the [third-party data notice](THIRD_PARTY_DATA_NOTICE.md) and [data-source register](DATA_SOURCES.md). The PFR decision remains `PERMISSION REQUIRED BEFORE INGESTION`.

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
- [Checkpoint eight report](docs/CHECKPOINT_8_REPORT.md)
- [Checkpoint nine report](docs/CHECKPOINT_9_REPORT.md)

## Interpretation standard

Coach estimates will be described as adjusted associations. They can be affected by hiring and firing decisions, coach-quarterback matching, roster construction, overlapping staff responsibilities, injuries, schedule, measurement error, and small samples. The application will show uncertainty and supporting evidence rather than a single context-free leaderboard.
