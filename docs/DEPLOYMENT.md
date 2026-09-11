# Production deployment

## Phase II / Ask Anything release preparation

The integrated C19 product is **READY WITH CONFIGURATION STEPS**, not deployed by this
closeout. See [Phase II closeout](PHASE_II_CLOSEOUT.md) for the exact snapshot hashes,
Render settings, local release results and supported/refused capabilities.

C19 requires the private `c19-62010b4bfffeb4af` Ask bundle and manifest in `ASK_DATA_DIR` on
the API filesystem. Git/build dependencies and the existing database alone do not supply it.
The bundle includes all 57 approved team-independent 2026 EPA research projections. Restore
and validate it during each build; no runtime model fitting or public raw-data download is
needed. The artifact transport/location still needs configuration at deployment time.

Keep the existing CORS/frontend API origins and SPA rewrite. C19 needs no new migration or
Neon publication. `/health` checks only the DB, so separately test `POST /ask` before declaring
the release healthy. Missing/incompatible Ask data produce sanitized 503 responses.

The checkpoint-nine sequence below is historical deployment guidance; its migration/reload
steps do not mean C19 requires a new database change. No provider settings were changed here.

Verified production endpoints:

- Frontend: `https://nfl-coaching-impact-engine.onrender.com`
- API: `https://nfl-coaching-impact-api.onrender.com`
- OpenAPI: `https://nfl-coaching-impact-api.onrender.com/docs`

Checkpoint nine deploys the project as three independently managed services:

- React/Vite static site on Render
- FastAPI free web service on Render
- PostgreSQL on Neon free

`render.yaml` is the source-controlled Render Blueprint. The frontend receives
only the public API origin through `VITE_API_BASE_URL`. The API receives the
Neon pooled connection string through `DATABASE_URL` and the exact static-site
origin through `CORS_ORIGINS`. Values are configured in provider environment
variables and are never committed.

## Release sequence

1. Run the complete offline, PostgreSQL/API, network, frontend, browser,
   formatting, and deterministic-build checks.
2. Push the validated commit to `main`.
3. Create or sync the Render Blueprint from `render.yaml`.
4. Set `DATABASE_URL`, `CORS_ORIGINS`, and `VITE_API_BASE_URL` in Render.
5. Apply Alembic migrations to Neon and load the approved publication with the
   transactional serving loader.
6. Verify `/health`, `/versions`, all application routes, and all four
   Relationship Explorer modes from the public frontend origin.
7. Record the verified URLs and evidence in `CHECKPOINT_9_REPORT.md`, then tag
   the release.

The deterministic coaching-completeness publication is
`22680407-d503-5290-bda2-18f4cbcb622a` under schema `checkpoint-7.5`, loader
`serving-loader-v7`, and API contract `api-v1.5`. The load identity includes the
captured Eleven-B manual evidence bytes. Migrations are applied from immutable
Alembic revision resources; the loader publishes in one transaction and changes
the active pointer only after every validation succeeds.

The static-site rewrite sends client-side routes to `index.html`. The API CORS
configuration rejects wildcard origins. Render health checks call `/health`,
which verifies database connectivity. During free-service cold starts, the
client labels the API as waking and automatically retries only network, 429,
502, 503, and 504 failures; deterministic client or validation errors are not
retried.

No raw data, generated model artifact, database dump, or credential is part of
the deployment source. Third-party data remains governed by its original terms;
see `THIRD_PARTY_DATA_NOTICE.md` and `DATA_SOURCES.md`.
