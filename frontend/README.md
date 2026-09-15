# Football analytics frontend

The interface is an evidence-first analytics workstation, not a context-free leaderboard.
See the [project case study](../docs/PORTFOLIO_CASE_STUDY.md) for a short product tour and
the [root README](../README.md) for the data, modeling and backend architecture.

## Visual system

Charcoal surfaces, flat panels and tabular numerals prioritize comparison. Orange marks actions
and selection; green/gold distinguish chart series. Evidence labels and line styles preserve
meaning without color alone. Mobile results become cards, search fields remain full-width,
and compact graphs avoid oversized empty canvases. The redesign and portfolio polish are
approved for release; live deployment verification remains pending.

## Checkpoint 19 — isolated Ask Anything addition

The new `/ask` route calls `POST /ask` through the existing API base URL. It displays
approved analytical records, source/uncertainty metadata, canonical clarification candidates
and explicit unsupported answers. It performs no model arithmetic and requires no LLM key.
Existing Statistics and Relationship Explorer routes are unchanged. C19 is **not deployed**.
For local use, first build/configure the backend's immutable `ASK_DATA_DIR` snapshot as
described in [the C19 report](../docs/CHECKPOINT_19_ASK_ANYTHING.md). A missing snapshot is an
error, never a trigger for fixture data. `e2e/checkpoint-nineteen.spec.ts` exercises the real
configured local API; it does not intercept numerical responses.

## Ask Anything 2.0 conversation preview

`/ask/preview` is a **preview-only** conversation interface for the additive `POST /ask/v2`
contract. `/ask` remains the unchanged v1 experience. The preview keeps conversation state in
component memory, sends at most eight recent successful user turns and eight canonical entity
references, and never reconstructs context from assistant prose. A page refresh or **New
conversation** resets the session and cancels any pending request.

Answers lead with the backend-approved football conclusion, then show ranked public evidence,
material uncertainty, supported follow-ups, and expandable methodology/version information.
Partially supported questions retain their useful descriptive evidence while clearly separating
unsupported prediction or causal claims. `Deterministic` and `Grounded AI` describe presentation
modes only; backend analytical authority is identical. Transient network and 503 failures use
bounded automatic retries and retain a retry action for the exact request snapshot.

Focused component tests live beside the preview source. `e2e/ask-v2-preview.spec.ts` intercepts
only `POST /api/ask/v2` with typed deterministic public-contract fixtures, makes no provider call,
and covers the golden conversation flows at desktop, tablet, and mobile widths. The separate v1
browser suite continues to exercise the real configured local snapshot/API.

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

- `/statistics`: canonical-position QB-only, URL-synchronized QB-team-season search, extended metric ordering, compact default comparison columns, grouped expanded metrics, and pagination; coaching filters identify team-season context rather than exact weekly exposure
- `/qbs/:playerId`: actual/expected/PAE history and source-backed coaching environments
- `/coaches/:coachId`: role intervals, exploratory impact/suppression, connected QB contexts, and citations
- `/network`: URL-backed Relationship Explorer with Coach Journey, QB Journey, Team History, and all-years Full Network; Timeline/Tree chronological views use season-specific appearances with canonical identity and distinct continuity edges, while Full Network uses deterministic year bands; source-backed intervals, complete-key QB PAE, focus history, and the keyboard-equivalent relationship surface remain intact
- `/methodology`: metric, evidence, eligibility, uncertainty, and version interpretation
- `/ask`: approved snapshot lookup, uncertainty, source lineage and explicit unsupported-answer states; requires configured backend snapshot
- `/ask/preview`: preview-only Ask v2 conversation using bounded structured context; does not replace `/ask`

## Quality commands

```bash
make frontend-check
make frontend-e2e
```

The first command runs ESLint, Prettier verification, TypeScript checking, Vitest, and the production Vite build. The end-to-end command expects the local checkpoint-seven API at `http://127.0.0.1:8000`; override it with `E2E_API_PROXY_TARGET`. It starts a private Vite server and exercises the statistics/profile journeys plus all four Relationship Explorer modes, URL restoration, selection, Focus/Reset/Back, evidence/role filtering, the 413 complete-failure state, and keyboard/responsive behavior at desktop, tablet, and mobile widths. Install Chromium once with `pnpm --filter nfl-coaching-impact-web exec playwright install chromium` if it is not already available.

Tests cover request serialization and cancellation, URL filters including expanded metrics, multi-query retry, empty/error/loading states, pagination, detail routes, missing values, suppression labels, citation links, relationship evidence metadata, deterministic appearance/continuity transforms, canonical selection reconstruction/highlighting, and automated accessibility checks. Relationship fixtures preserve multi-year/multi-team identities, multi-team same-season QB rows, in-season changes, interim/shared/provisional evidence, missing PAE, and complete-key PAE attachment. Coach-specific filters never erase independent QB facts. Full Network requests all supported years by default and the API returns 413 rather than a partial graph above its measured 2,000-node/4,000-relationship caps.

The production build is configured as a Render static site. Set the public FastAPI origin in Render as `VITE_API_BASE_URL`; it is public configuration, never a credential. The API allows only the exact static-site origin through its server-side `CORS_ORIGINS` value. Free-service cold starts show an “API is waking up” message and automatically retry transient network, 429, 502, 503, and 504 failures.
