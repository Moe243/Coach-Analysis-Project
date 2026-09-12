# Phase II deployment runbook

Prepared 2026-09-11. **USER ACTION REQUIRED.** No deployment is authorized by this
runbook alone. No model fitting, artifact regeneration, migration or Neon reload is needed.
The pinned analytical version remains `c19-62010b4bfffeb4af`.

Preparation validation: 62 snapshot/Ask tests, 89 frontend tests and 46 disposable
PostgreSQL/API tests passed; none of these selected tests skipped. The compiled SPA passed
real local `/ask`, `/statistics` and `/network` checks at 1440, 820 and 390 pixels, using a
disposable database and the unchanged approved snapshot. `/health`, six supported lookups
and five refusals passed over HTTP. TypeScript, ESLint, Prettier, Ruff, Python formatting,
compilation and diff checks passed. Both the loopback rehearsal build and the final build
with the production API origin passed. The existing Starlette/httpx deprecation warning
was non-failing. No live GitHub asset download or Render deployment is claimed by these tests.

## 1. Which Render services to open

Sign in to [Render](https://dashboard.render.com). Open **nfl-coaching-impact-api**
(Python Web Service) and **nfl-coaching-impact-engine** (Static Site).
Keep Auto-Deploy **Off** on both, and Blueprint Auto Sync **No** if a Blueprint is used.
Record the current successful deploy for each before changing settings. Never copy deploy
hook URLs or credentials into chat. The preparation audit reached the Render sign-in page;
dashboard values could not be independently verified.

The preparation commit uses `[skip render]` in its body, per
[Render's skip-commit behavior](https://render.com/docs/deploys#skipping-an-auto-deploy).
It does not change `render.yaml`, avoiding an automatic Blueprint configuration sync.
The existing Blueprint commands are historical defaults: apply the overrides below manually
at the authorized deployment, and do not resync the old Blueprint over these settings.

## 2. Environment variables to confirm/add

API service, repository-root working directory (leave Root Directory blank):

| Variable | Value/action |
|---|---|
| `ASK_DATA_DIR` | `/opt/render/project/src/data/processed/ask_anything/c19-62010b4bfffeb4af` |
| `ASK_ARTIFACT_REPOSITORY` | `Moe243/Coach-Analysis-Artifacts` — private repository created in step 3 |
| `ASK_ARTIFACT_TOKEN` | Fine-grained token from step 3, entered only in Render Environment |
| `PYTHON_VERSION` | `3.12.11` (existing pinned runtime) |
| `DATABASE_URL` | Confirm existing value is present; retain unchanged, never reveal it |
| `CORS_ORIGINS` | `https://nfl-coaching-impact-engine.onrender.com` |
| `PORT` | Render-supplied; do not override |

Frontend service: retain `NODE_VERSION=22.14.0` and set
`VITE_API_BASE_URL=https://nfl-coaching-impact-api.onrender.com` **without `/api`**.
This public value is compiled into the frontend. Never put artifact tokens or database
credentials in any `VITE_` variable. Existing CORS permits GET/POST with Accept/Content-Type,
credentials disabled. Save configuration without deploying until all steps are ready.

## 3. Snapshot transport setup

Use a **private GitHub Release**. Do not attach these generated files to the public project
repository or commit them. The repository rules and third-party terms preclude using tracked
raw/model data as the transport. No paid artifact service is required.

1. On GitHub, create **Moe243/Coach-Analysis-Artifacts**, visibility **Private**, initialize
   with a README. Do not connect it as a Render service or make it public.
2. Create and publish a release in that private repository with tag
   **c19-62010b4bfffeb4af**. Upload only these two files from the existing local folder
   `/Users/moesrour/Desktop/Coach Analysis Project/data/processed/ask_anything/c19-62010b4bfffeb4af/`:

   | File | Bytes | SHA-256 |
   |---|---:|---|
   | `MANIFEST.json` | 5,273 | `e13a911037ef1761f6d9d0882a274745c0dfb563aecd3990ecdf7b72b73c2657` |
   | `analytical_bundle.json` | 46,987,140 | `cc2666a8b7506e3b7e766ec687043e24d3d4be454f8e97545e4dab26223d533d` |

3. Create a fine-grained GitHub token limited to **only that private repository**, with
   **Contents: Read-only** and the automatically required metadata access. Select an expiry
   and set a renewal reminder. Store it directly in Render's API `ASK_ARTIFACT_TOKEN`; never
   paste it in chat, shell commands, source, screenshots or documentation.
4. Set `ASK_ARTIFACT_REPOSITORY` as above. No asset IDs or signed download URLs need copying.
   The restore code resolves the exact tag and filenames, requires private visibility, and
   checks hard-coded hashes. Replacing release assets cannot change the accepted bytes.

[GitHub's release asset API](https://docs.github.com/en/rest/releases/assets#get-a-release-asset)
supports authenticated downloads with Contents read permission. The downloader accepts a
direct response or one HTTPS GitHub asset-CDN redirect, strips the token on redirect, limits
download sizes, validates a temporary directory, and atomically publishes it. A corrupt
existing directory fails closed instead of being overwritten. No fixture fallback is used.

This private repository/upload/token was **not created** during preparation. End-to-end
authenticated GitHub transport remains unverified until the user completes these steps;
local tests exercise the protocol and exact approved bytes without using real credentials.

## 4. API build command

Set on **nfl-coaching-impact-api**:

```sh
pip install -r requirements.lock && pip install --no-deps -e . && PYTHONPATH=src python -m nfl_coaching_impact.release_snapshot restore
```

Restore occurs during **every build**, not in a paid pre-deploy step or ad hoc runtime upload.
The loader reports fixed operation labels and HTTP status codes without printing tokens,
URLs or upstream response bodies. A repository/release/asset 401 means authentication was
rejected; 403 means access was denied (permissions or rate limits); 404 may mean an absent
resource or inaccessible private content. Check the scoped token and selected private
repository in provider settings, never by printing the token. Transport errors remain
sanitized. All failures still block publication/startup.
Render Free storage is ephemeral; build-time restoration is required after clean rebuilds.
The gate checks both file hashes, manifest/version/code identity, 57 distinct approved C16
2026 EPA projections and the pinned unsupported-question metadata/behavior. It fits nothing.
For a separately callable integrity check:

```sh
PYTHONPATH=src python -m nfl_coaching_impact.release_snapshot validate
```

## 5. Start command and frontend build configuration

API start command:

```sh
PYTHONPATH=src python -m nfl_coaching_impact.release_snapshot start
```

This validates before binding a socket, primes the existing Ask cache, removes the artifact
token from the Python environment, then runs the existing FastAPI app on Render's `PORT`.
Missing/corrupt/incompatible snapshots exit nonzero with a sanitized error. No download or
regeneration happens at startup. Use this entry point rather than bypassing the gate with
plain Uvicorn. `/health` remains a DB health check and does not replace Ask smoke checks.

Frontend build command (unchanged):

```sh
pnpm install --frozen-lockfile && pnpm --filter nfl-coaching-impact-web build
```

Publish directory: `frontend/dist`. No static-site start command. Preserve the rewrite
`/*` → `/index.html` for reloads/deep links. No C19/C20 migration is needed: historical routes
continue using the existing approved publication through `0005_coaching_completeness`.

## 6. Deploy order

Only after separate deployment authorization and completed configuration:

1. **API first:** manually deploy the preparation commit; verify restore/start gates and all
   API checks below. Do not continue if any fail.
2. **Frontend second:** manually deploy the same commit with the confirmed API base URL.
3. Verify browser routes and CORS. Keep auto-deploy off until the release is accepted.

Do not run migrations or reload Neon. Do not train anything. Keep the snapshot private on the
API filesystem, never in `frontend/dist`. Local checks do not certify free-tier RAM, cold-start
latency or uptime; verify those during the authorized live deployment.

## 7. Live URLs

- API health: <https://nfl-coaching-impact-api.onrender.com/health>
- API Ask: `POST https://nfl-coaching-impact-api.onrender.com/ask`
- Ask UI: <https://nfl-coaching-impact-engine.onrender.com/ask>
- Statistics: <https://nfl-coaching-impact-engine.onrender.com/statistics>
- Explorer: <https://nfl-coaching-impact-engine.onrender.com/network>

## 8. Live verification questions

Send JSON `{"question":"..."}` to POST `/ask`, then repeat via the UI:

- **How did Josh Allen perform in 2022?** — supported historical EPA/PAE with provenance.
- **Josh Allen projection 2026** — one frozen team-independent EPA research projection,
  C19 `c19-62010b4bfffeb4af`, model `qb-calibrated-8c8063c5954e2a22`.
- **What type of quarterback is Lamar Jackson?** — supported historical state/style.
- **Show Andy Reid's coach history** — source-backed assignments, not causal ownership.
- **What type of offense did Miami run in 2024?** — historical scheme.
- **What does PCAE say about Andy Reid?** — separate PCAE research, not Coach Effect.
- **What would Kyler Murray do in Minnesota?** — refuse numerical transfer.
- **What if Mahomes was drafted by Chicago?** — refuse career counterfactual.
- **How much better does Andy Reid make quarterbacks?** — refuse universal Coach Effect.
- **How will this college QB perform in the NFL?** — refuse rookie projection.
- **How much better does college coach Nick Saban make quarterbacks?** — refuse coach effect.

Refusals must have empty metrics, no model version and an available alternative. Rookie wire
status remains `NOT_YET_SUPPORTED` for compatibility, not a claim that a model exists.
Reload `/ask`, search Baker on `/statistics`, and open Houston 2020 in `/network` on desktop
and mobile. Check source/verification labels and absence of failed API calls. Test after a cold
start: transient wake-up retries are acceptable; persistent missing-snapshot errors are not.

## 9. Rollback instructions

If API restore or startup validation fails, stop; do not deploy the frontend. Never bypass the
gate, substitute fixtures or regenerate research. Correct configuration or restore the exact
pinned assets. A partial download is not published.

If live behavior regresses, use Render's prior successful API deploy and prior successful
frontend deploy recorded in step 1. Restore the corresponding prior build/start settings if
performing a rebuild of older code (which lacks `release_snapshot`), using plain Uvicorn only
for that older release. Retain existing DATABASE_URL/CORS and disable auto-deploy. No database
rollback is needed because this preparation changes no schema/publication. Prior C19-capable
releases require their matching snapshot; pre-C19 releases will not expose working Ask.
Do not select a research/main SHA merely because it exists: use the recorded successful release.
