# Architecture

## Principles

- Reproducible local execution
- Clear separation of factual data, derived metrics, and interpretation
- Stable identifiers and explicit lineage
- No unnecessary services
- A small enough design for a portfolio reviewer to understand

## Data flow

```text
Official sources
      |
      v
Verified cache + byte-identical Bronze Parquet + source manifest
      |
      v
Polars validation and normalization
      |
      v
Processed Parquet queried through embedded DuckDB
      |                         |
      v                         v
Feature/model pipeline      Data-quality reports
      |
      v
Curated PostgreSQL tables and serving views
      |
      v
FastAPI -> Next.js application
```

DuckDB is an embedded transformation/query engine, not a deployed service. PostgreSQL is the sole application database.

## Repository boundaries

- `src/nfl_coaching_impact/sources.py`: exact release registry, verified cache, and Bronze copying
- `src/nfl_coaching_impact/transforms.py`: normalization, identities, and versioned QB metrics
- `src/nfl_coaching_impact/quality.py`: hard checks and explicit warnings
- `src/nfl_coaching_impact/pipeline.py`: atomic orchestration and manifests
- `src/nfl_coaching_impact/cli.py`: thin command-line entry point
- `src/nfl_coaching_impact/features`: timing-safe preseason and retrospective features
- `src/nfl_coaching_impact/models`: expected and coach-impact models
- `src/nfl_coaching_impact/validation`: schemas, join assertions, leakage checks
- `apps/api`: FastAPI in a later checkpoint
- `apps/web`: Next.js in a later checkpoint

The ingestion modules remain intentionally compact. Empty future application/model folders are not created to avoid implying working features.

## Storage layers

### Raw

Original source assets are stored in a verified local cache and copied byte-for-byte into each version's Bronze directory. Deterministic version manifests retain URL, SHA-256 digest, size, row count, schema, and validation status. Retrieval timestamps, cache and HTTP status, preflight measurements, and reuse facts live in a mutable execution log outside the immutable version directory. Generated files are ignored by Git.

### Processed

Normalized Parquet uses canonical player/team IDs and source-preserving columns. Transformations are deterministic and versioned. DuckDB reads these files without requiring an analytical server.

### Serving

PostgreSQL contains immutable load-scoped canonical facts, QB metrics, PAE, coaching facts/citations/reviews, coach exposures/effects, and source/pipeline manifests. Alembic owns schema revision `0001_checkpoint7`. `serving_publication` is the single atomic pointer used by every API view; a failed load never changes it. Content-identical reruns reuse the deterministic UUID load identity after verifying the existing publication is complete.

## Pipeline orchestration

The Python CLI retains the checkpoint-two `vertical-slice` command and adds checkpoint three's `historical` command. Historical ingestion performs a HEAD/cache storage preflight before downloads, materializes only verified cache misses, and processes each season into an immutable checksum-protected season version. A failed season removes only its own staging directory; already published seasons remain reusable. The complete 1999-2025 build is assembled in a separate staging tree and atomically renamed before the root `LATEST` pointer changes. No Airflow or queue is needed. Docker Compose remains deferred until PostgreSQL application loading needs it.

## Identity rules

- Players: GSIS ID is canonical; external IDs live in a bridge.
- Teams: internal `team_id` plus date-valid aliases handle OAK/LV, SD/LAC, and STL/LA without rewriting raw values.
- Coaches: repository-controlled numeric ID plus aliases and citations; names alone never join facts.
- Games: nflverse `game_id`.

## Environments and midseason changes

Coach assignments use week and date bounds. A deterministic environment key represents the team, season, interval, and staff combination. QB season summaries remain the default UI grain; environment stints preserve exposure beneath them.

## API contracts

FastAPI connects through `DATABASE_URL`, marks every request transaction read-only, and queries only current-publication views/tables. Whitelisted sorting, bound parameters, limit 1-200, nonnegative offsets, typed query validation, 404 details, and empty pages form API contract `api-v1`. OpenAPI documents the routes. Authentication and deployment remain deferred; the local server is not safe for public exposure.

## Security and compliance

Credentials come from environment variables. The API key never reaches browser code. Restricted raw inputs remain local. Source attribution and usage concerns are part of data lineage, not an afterthought.
