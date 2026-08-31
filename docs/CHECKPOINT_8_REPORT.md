# Checkpoint eight report

Date: 2026-08-31
Status: implemented; awaiting approval

## Outcome

Checkpoint eight adds a responsive React/TypeScript frontend over the approved checkpoint-seven FastAPI service. It does not add or alter football metrics, PAE, coach-impact models, rankings, database loaders, authentication, deployment, or production infrastructure.

The interface was exercised against the real local PostgreSQL publication and API, not mocked production data. It displays:

- Historical data version `c3-f6c1aa118ff43b90`
- Expected-performance data version `c5-8fd5d1aba2598c59`
- Expected-performance model `expected-performance-8fd5d1aba2598c59`
- Coach-impact data version `c6-400a5b474aa37a35`
- Coach-impact model `coach-impact-400a5b474aa37a35`
- API contract `api-v1.1`

## Delivered interface

- Statistics workspace at `/statistics` with player, coach, team, season, role, evidence, eligibility, ordering, minimum-dropback, expanded-metric, and pagination state encoded in the URL.
- One QB-team-season result grain with actual and expected EPA/dropback, PAE, coaching context, sample/eligibility labels, and optional CPOE, success, sack, touchdown, interception, explosive-pass, first-down, air-yards, and WPA fields.
- QB detail routes with profile, season history, actual-versus-expected chart, accessible chart table, coaching environments, timing statement, and complete model/version labels.
- Coach detail routes with role intervals, citations, connected QB team-season context, uncertainty, identification, bootstrap support, and prominent exploratory/suppression language. No definitive coach rank is rendered.
- A focused coaching network at `/network`, scoped by coach/season/team/role/evidence state, with zoom/fit controls, selectable nodes, source-backed edge metadata, and an equivalent semantic connection list.
- A methodology route explaining PAE, sample qualification, evidence status, missing values, conditional bootstrap intervals, and why coach estimates must not be ranked or read causally.
- Explicit loading, empty, error, retry, and not-found states.
- Responsive table-to-record-card behavior, keyboard-visible focus, semantic navigation, reduced-motion support, and automated accessibility checks.

The client uses React Router, TanStack Query, a typed cancellation-aware HTTP layer, Cytoscape, Vite, Vitest, Testing Library, axe-core, ESLint, Prettier, and TypeScript. The network route is lazy-loaded so Cytoscape is not part of the initial statistics bundle.

## Validation results

### Frontend

- 26/26 Vitest tests passed across six files.
- 21/21 Playwright end-to-end journeys passed: six required flows plus keyboard/responsive behavior in desktop, tablet, and mobile Chromium projects against the real checkpoint-seven publication.
- ESLint passed with zero warnings.
- Prettier verification passed.
- TypeScript project checking passed.
- Production build passed: main JavaScript 291.61 kB (93.13 kB gzip); lazy network chunk 453.54 kB (145.38 kB gzip).
- Two consecutive production builds produced byte-identical files and SHA-256 manifests.

Tests cover API serialization, pagination, cancellation and errors; missing-value rendering; filter and expanded-metric behavior; populated, empty, loading, and failure states; QB and coach details; suppression and citation presentation; network metadata and shared/provisional edges; selection; and automated accessibility rules. Browser E2E covers QB search/profile, team-season filtering and URL state, PAE explanation, coach search/connected QBs, verified-only network filtering, and suppressed coach-impact language.

### Earlier-checkpoint regression suite

- Offline Python: 74 passed; 33 intentionally skipped because 31 require a separately started PostgreSQL URL and two are opt-in network tests.
- Disposable PostgreSQL/API behavior: 31/31 passed, including migrations, atomic rollback, exact-byte manual-input identity, lineage triggers, idempotency, all eight clean-load view comparisons, filters, pagination, warm-up exclusion, and API responses.
- Opt-in network integration: 2/2 passed, covering nflverse boundary assets and the coaching citation/content registry.
- Python Ruff and formatting checks passed.
- Git whitespace/diff checks passed.

### Browser and responsive QA

Real full-stack browser checks covered statistics search/filter/clear, stable pagination and ordering, minimum-dropback filtering, the Baker Mayfield QB route, the Todd Bowles coach route, Houston's 2020 shared/provisional network intervals, methodology navigation, and version labels. Representative screenshots were captured for all five routes at desktop, tablet, and 390-pixel mobile widths. Mobile views avoid horizontal page scrolling; the statistics table becomes labeled record cards, while the graph retains its visible semantic alternative.

## Data and interpretation controls

- The browser consumes only checkpoint-seven endpoints and contains no hard-coded analytical records.
- `null` remains unavailable and is never converted to zero.
- PAE is displayed as actual minus expected EPA/dropback; the frontend does not recalculate or rerank it.
- Verification, confidence, interval basis and bounds, provisional/shared flags, eligibility, reliability, identification, suppression, bootstrap support, and version fields remain visible.
- The coach statistics join is a stable client-side intersection of complete paginated API results because checkpoint seven has no combined QB/coach search route.
- Network lines represent overlapping staff assignments only. Connected-QB links represent shared team-season context only.

## Files changed

- Added the `frontend/` React/TypeScript application, tests, styles, package documentation, and build configuration.
- Added the root pnpm workspace and lockfile.
- Added frontend commands to `Makefile` and local API proxy variables to `.env.example`.
- Extended `.gitignore` for generated frontend dependencies, builds, coverage, and browser-test output.
- Updated `README.md`, `docs/ARCHITECTURE.md`, `docs/PROJECT_PLAN.md`, `METHODOLOGY.md`, `DATA_DICTIONARY.md`, and `LIMITATIONS.md` for the implemented interface and its boundaries.

## Remaining limitations

- The application remains local and unauthenticated; no deployment, reverse proxy, TLS, rate limit, monitoring, or availability work was added.
- Coach-context statistics filtering uses a client-side fan-out that is suitable for the current publication but should become a joined server query if the dataset grows materially.
- Offset pagination is inherited from checkpoint seven, though its order is stable.
- The graph is deliberately a focused evidence navigator, not a complete all-history network or causal model.
- Automated tests use jsdom; representative real-browser QA is documented, but cross-browser visual regression and device-lab automation remain future work.
- All football, public-data, PAE, identification, and coach-attribution limitations from checkpoints one through seven still apply.

## Exact next checkpoint

Checkpoint nine will add portfolio polish only after approval: CI for Python/frontend/database checks, a documented Docker Compose local workflow, curated screenshots or a short demo, clean-clone verification, deployment guidance, and an employer-oriented project narrative. It must not weaken the existing evidence, uncertainty, suppression, reproducibility, or non-causal interpretation contracts.
