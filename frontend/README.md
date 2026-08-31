# Checkpoint-eight frontend

This package is the local React/TypeScript interface for the NFL Coaching Impact Engine. It reads the checkpoint-seven FastAPI contract and contains no embedded production data, database credentials, or model calculations.

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

- `/statistics`: URL-synchronized QB-team-season search, filters, ordering, expanded metrics, and pagination
- `/qbs/:playerId`: actual/expected/PAE history and source-backed coaching environments
- `/coaches/:coachId`: role intervals, exploratory impact/suppression, connected QB contexts, and citations
- `/network`: focused season/team staff graph with an equivalent semantic connection list
- `/methodology`: metric, evidence, eligibility, uncertainty, and version interpretation

## Quality commands

```bash
make frontend-check
make frontend-e2e
```

The first command runs ESLint, Prettier verification, TypeScript checking, Vitest, and the production Vite build. The end-to-end command expects the local checkpoint-seven API at `http://127.0.0.1:8000`; override it with `E2E_API_PROXY_TARGET`. It starts a private Vite server and runs the six required real-publication journeys plus keyboard/responsive behavior at desktop, tablet, and mobile widths. Install Chromium once with `pnpm --filter nfl-coaching-impact-web exec playwright install chromium` if it is not already available.

Tests cover request serialization and cancellation, URL filters, empty/error/loading states, pagination, detail routes, missing values, suppression labels, citation links, network evidence metadata, and automated accessibility checks. End-to-end coverage searches and opens QB and coach profiles, filters team/season and verified network edges, reads PAE methodology, and verifies suppressed coach-impact language.

The frontend is not deployed and has no authentication. Public hosting, production reverse-proxy configuration, visual-regression automation, and cross-browser device-lab coverage are deferred to checkpoint nine.
