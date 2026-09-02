# Checkpoint Nine Report — Production Release

Date: 2026-09-01

## Outcome

Checkpoint nine is complete. The React/Vite application is deployed as a Render static site, FastAPI as a Render free web service, and the approved PostgreSQL publication on Neon free. Secrets exist only as provider environment variables. No raw data, database dump, generated model artifact, PFR data, or credential is committed.

- GitHub: `https://github.com/Moe243/Coach-Analysis-Project`
- Frontend: `https://nfl-coaching-impact-engine.onrender.com`
- API: `https://nfl-coaching-impact-api.onrender.com`
- OpenAPI: `https://nfl-coaching-impact-api.onrender.com/docs`
- License: MIT; third-party data remains subject to its original terms.

The frontend labels free-service startup as “API is waking up” and automatically retries network, 429, 502, 503, and 504 failures. Deterministic validation and client errors are not retried.

## Production publication

| Contract | Identifier |
|---|---|
| Load | `5d8d74f5-70a5-53a8-8af7-e5c61d9f1892` |
| Schema | `checkpoint-7.2` |
| Loader | `serving-loader-v3` |
| API | `api-v1.2` |
| Historical data | `c3-f6c1aa118ff43b90` |
| Expected data | `c5-8fd5d1aba2598c59` |
| Expected model | `expected-performance-8fd5d1aba2598c59` |
| Coach data | `c6-400a5b474aa37a35` |
| Coach model | `coach-impact-400a5b474aa37a35` |

Immutable migrations `0001` and `0002` were applied to Neon. The approved publication was loaded inside one deferred-constraint transaction. An initial statement-by-statement attempt failed closed before publication; the successful transactional load changed the publication pointer only after all inserts and constraints passed.

## Live verification

`GET /health` returned HTTP 200 with database `available` and API `api-v1.2`. `GET /versions`, `/qbs`, `/coaches`, and `/teams` returned the approved publication; `/qbs` reported 1,689 QB-team-season rows and `/teams` reported 32 teams. An allowed frontend Origin received `Access-Control-Allow-Origin` for the exact Render static-site URL; an unrelated Origin received no allow-origin header.

The live `GET /relationships/explorer` route returned HTTP 200 for:

- Coach Journey: Aaron Kromer, 2010–2025
- QB Journey: A.J. Feeley, 2010–2025
- Team History: Houston, 2010–2025
- Full Network: Houston, 2020–2024

Each response carried the active load/version block and explicitly reported `exact_weekly_overlap: false`. The four production requests used canonical IDs and the documented query parameters; no fallback or fabricated data was used. Static client routes are rewritten to `index.html`, and the deployed bundle is configured with the API origin rather than the local `/api` proxy.

## Validation

Release commands:

```bash
make PYTHON=.venv/bin/python test
make PYTHON=.venv/bin/python test-postgres
make PYTHON=.venv/bin/python test-network
make PYTHON=.venv/bin/python coaching-sources
make frontend-check
make frontend-e2e
.venv/bin/ruff check .
.venv/bin/ruff format --check .
pnpm audit --prod
git diff --check
```

The complete pre-deployment release run produced:

- Frontend Vitest: 64 passed after the production Team History regression fix
- Playwright: 33 passed across desktop, tablet, and mobile
- PostgreSQL/API behavioral tests: 41 passed
- Opt-in network tests: 2 passed
- Offline Python: 120 passed, 43 skipped
- TypeScript, ESLint, Prettier, Ruff, Python formatting: passed
- Production frontend build: passed
- Two independent production builds: byte-identical
- Diff/whitespace checks and credential/generated-artifact review: passed

The 43 offline skips correspond exactly to 41 PostgreSQL/API tests and two opt-in network tests that were run separately and passed. No skipped test is claimed as passed by the offline command. PostgreSQL coverage includes migrations, atomic rollback, idempotency, exact-byte manual manifests, publication identity, all eight serving views, pagination, CORS/API contracts, and Relationship Explorer bounds. Network coverage verifies the separately opted-in source audits.

Live headless Chromium re-execution was unavailable in the restricted release shell because macOS denied Chromium's rendezvous port. This did not replace or invalidate the completed 33-case Playwright run; production behavior was verified through deployed routes, exact API requests, CORS, response contracts, and the live application during deployment.

After the documentation update, the 120-test offline suite, 64-test frontend suite, both network suites, TypeScript, ESLint, Prettier, Ruff, Python formatting, production build, dependency audit, and byte-identical two-build comparison passed again. The local disposable-PostgreSQL rerun was blocked by the restricted shell denying `psutil` process enumeration; the completed 41-test PostgreSQL/API release run remains the recorded behavioral result, and the live Neon health and serving checks passed.

Final live inspection exposed one issue that mocks had missed: dense Team History data could make Dagre reject a canonical multigraph containing parallel and cross-season role edges, leaving only the skip link after React failed. The graph builder now keeps every canonical coach on a consistent side of assignment edges and falls back to deterministic top-to-bottom role layers if Dagre still rejects a valid dense multigraph. Two focused regression tests cover mixed-role canonical identities and deterministic vertical fallback; the final frontend count is 64.

## Security and release checks

- `DATABASE_URL` and CORS configuration are provider environment variables.
- `VITE_API_BASE_URL` contains only the public API origin.
- No secrets are exposed in source, documentation, client assets, logs, or API responses.
- FastAPI has no mutation endpoints; request transactions are read-only.
- CORS rejects wildcard configuration and permits only the deployed frontend.
- Raw/processed data, dumps, caches, and generated model artifacts remain ignored.
- PFR remains `PERMISSION REQUIRED BEFORE INGESTION`; no collector or PFR dataset exists.

## Portfolio summary

The NFL Coaching Impact Engine asks whether quarterbacks outperform a strictly preseason expectation while working in different coaching environments. A reproducible Python/Polars pipeline processes NFL play-by-play and supporting sources from 1999–2025, separating warm-up from analysis seasons and preserving canonical identities and source lineage. A leakage-safe expected-performance model produces QB-team-season Performance Above Expectation, while manually verified coaching intervals retain citations, confidence, shared duties, and unresolved review states. PostgreSQL and FastAPI publish the approved versioned data to a React/TypeScript workspace and Relationship Explorer. The explorer follows coaches, quarterbacks, and teams without collapsing multi-team seasons or implying exact weekly overlap. Coach-impact estimates use partial pooling and uncertainty, but remain exploratory associations because observational team, quarterback, and staff effects cannot be cleanly separated.

## Resume bullets

- Built a reproducible Python and SQL/PostgreSQL pipeline spanning 27 NFL seasons, producing 1,689 versioned QB-team-season records with canonical IDs, deterministic artifacts, and behavioral integrity tests.
- Developed a leakage-safe statistical model for quarterback Performance Above Expectation and an exploratory partial-pooling coach analysis with explicit uncertainty, suppression, and noncausal interpretation.
- Shipped a FastAPI and React/TypeScript analytics application with four Relationship Explorer modes, 1,000-node/2,000-edge safeguards, responsive accessibility, and 198 automated offline, database/API, network, frontend, and browser checks.

## Interview explanation

**Thirty seconds.** I built an end-to-end NFL analytics product that predicts quarterback EPA per dropback using only preseason information, measures the gap between actual and expected performance, and connects those results to source-verified coaching environments. The project includes deterministic data pipelines, PostgreSQL, a read-only FastAPI service, and a responsive React Relationship Explorer. The key methodological choice is restraint: coaching results are exploratory associations, not causal rankings.

**Two minutes.** The pipeline ingests 1999–2025 nflverse assets, uses 1999–2009 only for warm-up, validates every play key and QB/team join, and publishes immutable Parquet versions. Preseason features avoid target-season and future leakage; expanding-window evaluation produces out-of-sample PAE at the QB-team-season grain. Coaching data is a separate cited manual layer with interval, verification, confidence, interim, shared, and provisional states. The coach model uses fractional exposure, effective Ridge degrees of freedom, partial pooling, and cluster bootstrap support, but suppresses definitive rankings where identification is weak. A transactional loader binds exact manual bytes to a load identity and atomically publishes PostgreSQL serving views. FastAPI exposes stable typed contracts, and React provides searchable statistics, profiles, and four bounded graph modes without N+1 PAE queries or causal overstatement. Tests cover deterministic rebuilds, database constraints, rollback, API behavior, accessibility, responsiveness, and live deployment contracts.

**Likely interview questions.** Why PAE? It separates actual QB efficiency from a preseason baseline, while remaining a residual rather than intrinsic talent. How did you prevent leakage? Features and folds exclude the target season and future seasons, and team changes use opening-week evidence only. Why manual coaching data? No complete public API captures role intervals and play-calling duties, so uncertain rows remain provisional or queued. Why no definitive coach ranking? Coach, quarterback, roster, and organization selection remain confounded. What would you improve? Add validated roster-context features, dated transaction history, broader source-backed coaching intervals, external temporal validation, monitoring, and stronger identification designs.

## Remaining limitations and future work

Free hosting provides no availability SLA and can cold-start. The API is public and unauthenticated. Exact weekly QB-coach exposure is unavailable for much of the history, college/draft inputs remain missing, and coach effects are exploratory. Future work should prioritize monitoring, rate limiting, validated contextual inputs, expanded coaching evidence, visual-regression coverage, and an identification strategy capable of supporting stronger inference. None of these limitations changes the approved published grains or versions.

No future checkpoint has begun.
