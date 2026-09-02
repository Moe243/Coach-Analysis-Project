# Checkpoint-eight frontend

This package is the React/TypeScript interface for the NFL Coaching Impact Engine. The production site is [live on Render](https://nfl-coaching-impact-engine.onrender.com). It reads the FastAPI contract and contains no embedded production data, database credentials, or model calculations.

## Local setup

From the repository root:

```bash
corepack enable
pnpm install --frozen-lockfile
DATABASE_URL=postgresql://user:password@localhost:5432/nfl_coaching make api
make frontend-dev
```

The default Vite proxy sends `/api` to `http://127.0.0.1:8000`. Set `VITE_API_PROXY_TARGET` to point at a different local API. For a built client, keep `VITE_API_BASE_URL=/api` behind a same-origin reverse proxy or set it to the intended API origin at build time. Never place `DATABASE_URL` or a secret in a `VITE_*` variable because Vite exposes those values to the browser.

## Routes

- `/statistics`: URL-synchronized QB-team-season search, filters, ordering, expanded metrics, and pagination; coaching filters identify team-season context rather than exact weekly exposure
- `/qbs/:playerId`: actual/expected/PAE history and source-backed coaching environments
- `/coaches/:coachId`: role intervals, exploratory impact/suppression, connected QB contexts, and citations
- `/network`: URL-backed Relationship Explorer with Coach Journey, QB Journey, Team History, and bounded Full Network; deterministic chronological layouts, canonical selection/focus history, source-backed assignment intervals, complete-key QB PAE context, and a keyboard-equivalent relationship surface
- `/methodology`: metric, evidence, eligibility, uncertainty, and version interpretation

## Quality commands

```bash
make frontend-check
make frontend-e2e
```

The first command runs ESLint, Prettier verification, TypeScript checking, Vitest, and the production Vite build. The end-to-end command expects the local checkpoint-seven API at `http://127.0.0.1:8000`; override it with `E2E_API_PROXY_TARGET`. It starts a private Vite server and exercises the statistics/profile journeys plus all four Relationship Explorer modes, URL restoration, selection, Focus/Reset/Back, evidence/role filtering, the 413 complete-failure state, and keyboard/responsive behavior at desktop, tablet, and mobile widths. Install Chromium once with `pnpm --filter nfl-coaching-impact-web exec playwright install chromium` if it is not already available.

Tests cover request serialization and cancellation, URL filters including expanded metrics, multi-query retry, empty/error/loading states, pagination, detail routes, missing values, suppression labels, citation links, relationship evidence metadata, deterministic graph transforms, selection reconstruction/highlighting, and automated accessibility checks. Relationship fixtures preserve canonical multi-year/multi-team identities, multi-team same-season QB rows, in-season changes, interim/shared/provisional evidence, missing PAE, and complete-key PAE attachment. Coach-specific filters never erase independent QB facts.

The production build is configured as a Render static site. Set the public FastAPI origin in Render as `VITE_API_BASE_URL`; it is public configuration, never a credential. The API allows only the exact static-site origin through its server-side `CORS_ORIGINS` value. Free-service cold starts show an “API is waking up” message and automatically retry transient network, 429, 502, 503, and 504 failures.
