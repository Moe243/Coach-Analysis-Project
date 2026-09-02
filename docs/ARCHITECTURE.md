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
FastAPI -> React/TypeScript application
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
- `src/nfl_coaching_impact/api.py`: read-only FastAPI serving layer
- `frontend/src/api`: typed HTTP contracts and cancellation-aware client
- `frontend/src/pages`: statistics, QB, coach, Relationship Explorer, and methodology routes
- `frontend/src/components`: reusable state, table, chart, status, and graph UI

The frontend is a pnpm workspace package and does not contain database credentials, embedded production data, or duplicated analytical calculations.

## Storage layers

### Raw

Original source assets are stored in a verified local cache and copied byte-for-byte into each version's Bronze directory. Deterministic version manifests retain URL, SHA-256 digest, size, row count, schema, and validation status. Retrieval timestamps, cache and HTTP status, preflight measurements, and reuse facts live in a mutable execution log outside the immutable version directory. Generated files are ignored by Git.

### Processed

Normalized Parquet uses canonical player/team IDs and source-preserving columns. Transformations are deterministic and versioned. DuckDB reads these files without requiring an analytical server.

### Serving

PostgreSQL contains immutable load-scoped canonical facts, QB metrics, PAE, coaching facts/citations/reviews, coach exposures/effects, source/pipeline manifests, and additive supplemental/audit/context facts. Alembic revision `0001_checkpoint7` reads its revision-specific immutable SQL snapshot rather than mutable `db/schema.sql`; its bytes remain unchanged, revision `0002_checkpoint7_integrity` adds the parent-side lineage trigger, and revision `0003_post_release_enhancements` adds the supplemental QB, coaching-completeness, and inherited-environment tables without changing earlier revisions. Deferred child- and parent-side triggers keep every exposure field synchronized with its assignment while permitting coordinated updates whose final state agrees. `serving_publication` is the single atomic pointer used by every API view; a failed new load leaves the prior pointer and rows untouched. Content-identical reruns reuse the deterministic UUID load identity after verifying the existing publication is complete. Manual CSV bytes are captured once for both parsing and hashing, and a pre-publication stability check rejects concurrent edits. Any serving-affecting manual CSV hash changes both the load identity and the stored manual manifest.

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

FastAPI connects through `DATABASE_URL`, marks every request transaction read-only, and queries only current-publication views/tables. Whitelisted sorting with complete business-key tie-breakers, bound parameters, limit 1-200, nonnegative offsets, typed role/status validation, 404 details, and empty pages form API contract `api-v1.3`. It exposes additive QB/team facts through `api_qb_statistics`, a role-complete coaching audit, and timing-safe inherited environment rows. OpenAPI documents the routes. The API is deployed as a read-only Render service behind provider TLS. It remains intentionally unauthenticated, permits CORS only from the exact frontend origin, and exposes no mutation routes. Neon is the sole production PostgreSQL service.

`GET /relationships/explorer` returns a bounded, deterministic `Coach -> Team-Season <- QB` subgraph without adding a duplicate analytical table. Coach nodes retain canonical `coach_id`; QB nodes retain GSIS `player_id`; team-season nodes serialize `(team_id, season)`. Coach relationships remain one sourced `assignment_key` interval, while QB relationships remain one `(player_id, team_id, season)` record and left-join PAE on that complete key. Team-history and team-anchored full-network scopes come directly from authoritative QB statistics as well as filtered assignments; role, verification, and provisional filters therefore affect coach edges only. Coach, QB, and team-history modes require their corresponding identity. Full-network mode requires an identity/team anchor and is capped at five seasons; all modes also enforce 1,000-node and 2,000-relationship response limits. The endpoint returns one version block and stamps every relationship with the active publication ID, eliminating frontend N+1 PAE requests for the future explorer.

## Frontend contracts

The Vite application uses React Router for deep-linkable routes and search parameters, TanStack Query for request caching/cancellation, and typed API response contracts. Statistics filters, ordering, expanded metrics, eligibility, and pagination are encoded in the URL. The client uses API pagination directly except for the documented coaching-context join, where it retrieves complete bounded API pages and performs a stable client-side team-season intersection. That filter is explicitly not described as exact weekly QB-coach exposure.

No display substitutes zero for a missing value. Verification, confidence, interval basis, provisional/shared flags, identification, suppression, bootstrap support, and model/data versions remain first-class fields. Coach effects are called exploratory associations and are never presented as definitive rankings. The `/network` route now renders the authoritative relationship response in Coach Journey, QB Journey, Team History, or bounded Full Network mode. Pure graph transformation deduplicates canonical entity/relationship IDs and assigns stable chronological or type-column positions; mobile transposes chronological lanes. Cytoscape is dynamically imported inside the lazy route. Selection highlights directly connected nodes and edges and fades unrelated elements, survives a reconstruction when still visible, and clears when filtered out.

The semantic relationship list is an equivalent exploration surface, not a fallback summary. It exposes canonical entity actions, assignment keys, roles, interval bounds/basis, verification, confidence, interim/shared/retained/provisional flags, citation availability, QB dropbacks, actual/expected EPA, PAE, eligibility, reliability, and versions. Select, Focus, Reset, and Back are available without the graph. Supported explorer state is URL-backed with canonical IDs. Client filters operate on the single bounded response and never issue N+1 PAE calls; coach-only filters affect coach assignments without deleting independent QB facts. A server 413 is rendered as a complete failure with narrowing guidance and no partial graph.

Local development proxies `/api` to FastAPI. The Render static build uses the explicit public `VITE_API_BASE_URL`; free-service cold starts are surfaced and retried only for transient failures.

## Security and compliance

Credentials come from environment variables. The API key never reaches browser code. Restricted raw inputs remain local. Source attribution and usage concerns are part of data lineage, not an afterthought.
