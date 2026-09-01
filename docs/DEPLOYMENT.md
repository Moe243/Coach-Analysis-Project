# Production deployment

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

The static-site rewrite sends client-side routes to `index.html`. The API CORS
configuration rejects wildcard origins. Render health checks call `/health`,
which verifies database connectivity. During free-service cold starts, the
client labels the API as waking and automatically retries only network, 429,
502, 503, and 504 failures; deterministic client or validation errors are not
retried.

No raw data, generated model artifact, database dump, or credential is part of
the deployment source. Third-party data remains governed by its original terms;
see `THIRD_PARTY_DATA_NOTICE.md` and `DATA_SOURCES.md`.
