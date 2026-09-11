# Phase II closeout and C19 release readiness

Date: 2026-09-11. **Release decision: READY WITH CONFIGURATION STEPS.**
This is an offline/local release audit, not a live deployment certification. No provider
settings, production database, deployment hooks or live publication were changed or inspected.

C20 `d921de0f883bc1a302d2dd176a21ae94c8d267aa` was approved, fast-forwarded from
`16b1c2f99985af7b4f9d40d1dff43c23eb5a499d`, and pushed to `origin/main`. C20's branch was
clean; all 32 focused tests, Ruff, formatting and diff checks passed again. This documentation
closeout is a separate commit on main; no new checkpoint branch or modeling run was created.

## Final scientific status

| Checkpoint | Final status | Interpretation |
|---|---|---|
| C13 — Predictive Data Foundation + Scheme Engine | COMPLETE | Reusable as-of features, timing/lineage validation and historical scheme profiles. |
| C14 — QB Style Profile + Player State | COMPLETE | Interpretable history/state, sample qualification and uncertainty; no arbitrary ability grade. |
| C15 — Player × Coach / Scheme Fit | COMPLETE — NOT ESTIMABLE / DATA-LIMITED | Historical preseason target-team assignment coverage prevented the intended estimation. |
| C16 — One-Year QB Projection | COMPLETE — EPA RESEARCH-READY WITH LIMITATIONS | Approved calibration refinement supports team-independent EPA research projections. Forward PAE remains NOT SUPPORTED. |
| C17 — One-Year Scenario Simulator | COMPLETE — scenario model NOT SUPPORTED | Tested environment main effects and interactions failed to improve out-of-sample prediction. |
| C18 — Career Counterfactual Simulator | NOT READY / NOT IMPLEMENTED | C17 did not establish a defensible environment-response mechanism; implementation was withheld. |
| C19 — Ask Anything | COMPLETE | Deterministic routing and explanations over approved analytical records, with explicit refusals. |
| C20 — College → NFL / Rookie Projection | COMPLETE — NOT ESTIMABLE / DATA-LIMITED | Source/data-gate closeout; college modeling remains blocked. |

An **unsupported tested model** (C17) differs from **unavailable data preventing estimation**
(C15/C20) and from **implementation withheld because a prerequisite failed** (C18). These are
scientific outcomes, not unfinished engineering to be solved by enabling a UI or inventing a
score. C17's validation MAE worsened by 0.000379 for environment main effects and another
0.000327 for interactions. Its failure cannot be bypassed with career simulation.

C20 version `c20-4b0f9b23785508dc` preserves 304 drafted QBs, 191 timing-consistent rookie
outcomes and 110 with at least 100 dropbacks, but zero verified college histories. No college
data were ingested, no rookie model fitted, no rookie Player State created, no current/future
rookie forecasts issued, and no college coaches modeled. See the individual
[C15](CHECKPOINT_15_PLAYER_SCHEME_FIT.md), [C16 refinement](CHECKPOINT_16_CALIBRATION_REFINEMENT.md),
[C17](CHECKPOINT_17_SCENARIO_SIMULATOR.md) and [C20](CHECKPOINT_20_COLLEGE_TO_NFL_ROOKIE_PROJECTION.md)
reports for the unchanged evidence and limitations.

## Supported product boundary

The integrated code and approved artifacts support historical QB statistics and PAE, C14
QB state/style profiles, source-backed coaching history and QB-coach team-season context,
historical team/scheme profiles, separate PCAE research, and team-independent one-year EPA
research projections. C19 supplies routing, explanations, uncertainty and provenance for those
capabilities. Its frozen C16 refinement snapshot contains exactly **57 approved 2026 EPA
projections**, labeled **TEAM-INDEPENDENT RESEARCH PROJECTION**. They are not active-roster or
destination-team claims. Historical PAE remains distinct from unsupported forward PAE.

Numerical QB-to-team transfer projections, Player × Scheme Fit scores, career counterfactuals,
universal Coach Effect scores, rookie/college-to-NFL projections and college coach effects
remain unsupported. Coaching relationships describe team-season context unless their source
supports a more precise interval; they do not establish causal improvement.

“Supported” here describes the approved implementation, not a claim that C19 is already live.
The release configuration below is still required.

## Ask refusal and lookup checks

Actual local HTTP requests through the integrated FastAPI app returned:

| Question | Wire status | Result |
|---|---|---|
| What would Kyler Murray do in Minnesota? | NOT_SUPPORTED | No metrics; historical scheme/team-independent projection alternative. |
| What if Mahomes was drafted by Chicago? | NOT_SUPPORTED | No metrics; actual historical records alternative. |
| How much better does Andy Reid make quarterbacks? | NOT_SUPPORTED | No universal number; staff history/PCAE alternative. |
| How will this college QB perform in the NFL? | NOT_YET_SUPPORTED | Existing C19 refusal enum; no metrics, no model version, NFL history/research alternative. |

The rookie enum is retained for compatibility and is not a promise of imminent support.
Its underlying model remains NOT ESTIMABLE / DATA-LIMITED. A real HTTP lookup for Josh Allen's
2026 projection matched the frozen `qb-calibrated-8c8063c5954e2a22` record exactly. The C19 tests
also verify multi-team historical PAE, missing values, 422 validation, bounded responses,
source/code hashes and corrupted-snapshot rejection. `POST /ask` is in OpenAPI and has no
`/api` prefix on the backend. The Vite development proxy removes `/api`; production uses the
configured API origin directly.

## Required snapshot and production publication

C19 snapshot: `c19-62010b4bfffeb4af`, contract `ask-v1`. The approved local artifact was rebuilt
from frozen source inputs without fitting anything and retained exactly that content version.
Runtime needs only these two files in the same version directory:

| File | Bytes | SHA-256 |
|---|---:|---|
| `analytical_bundle.json` | 46,987,140 | `cc2666a8b7506e3b7e766ec687043e24d3d4be454f8e97545e4dab26223d533d` |
| `MANIFEST.json` | 5,273 | `e13a911037ef1761f6d9d0882a274745c0dfb563aecd3990ecdf7b72b73c2657` |

The bundle already embeds all 57 C16 projections, 8,457 C14 state headers, 50,787 profile
records, 6,144 scheme records, 1,187 historical QB-team-seasons, 1,857 assignments and 287
PCAE records. No separate projection file or fitted model weights are needed at runtime.
Existing production historical tables alone are insufficient to construct these additional
capabilities; the Ask bundle must be packaged separately from the database publication.

The files remain Git-ignored and must be delivered to the **API build**, never placed in
`frontend/dist`, committed, or exposed as a bulk-download endpoint. Use a controlled private
artifact store/build input and retain third-party notices. Pin both hashes above, restore to
a temporary directory, verify them, validate `AnalyticalService.from_directory`, then rename
the completed directory into place before starting the app. Do not update a live file in place:
the running service caches its loaded snapshot, so deploy/restart with the matching code and
immutable directory. Source code changes to C19 require a new matching snapshot identity.

The current repository build command installs dependencies but **does not restore this
ignored snapshot**. The private artifact location and delivery mechanism are not configured
or uploaded in this closeout. That is a required release configuration step, not a claimed
existing facility. Raw historical inputs and research-training caches need not be shipped.

## Exact Render configuration required at a later authorized deployment

Settings below describe the source-controlled native-Python/static configuration. Dashboard
values were not inspected. Retain the existing Git repository, `main` branch and root directory.

| Service/setting | Required value/action |
|---|---|
| API `ASK_DATA_DIR` | `data/processed/ask_anything/c19-62010b4bfffeb4af` relative to the repository-root working directory. Set the version directory, not its parent or `LATEST`. |
| API artifact delivery | Restore the two pinned files above into `ASK_DATA_DIR` during every build, before validation/startup. Configure private transport credentials only in provider environment settings; never log signed URLs or secrets. |
| API `CORS_ORIGINS` | `https://nfl-coaching-impact-engine.onrender.com` (or the exact replacement frontend origin). No wildcard. Existing middleware allows GET/POST and Accept/Content-Type with credentials disabled. |
| API `DATABASE_URL` | Retain the existing provider-managed secret unchanged. C19 does not consume it, but historical endpoints and `/health` still do. |
| API base build command | Retain `pip install -r requirements.lock && pip install --no-deps -e .`; append the configured private restore and the fail-closed validation command below. The transport command cannot be finalized until its private artifact location is supplied. |
| API start command | Retain `PYTHONPATH=src python -m uvicorn nfl_coaching_impact.api:app --host 0.0.0.0 --port $PORT`. Single process; no training at startup. |
| API health check | Retain `/health`, but separately gate release on a real `POST /ask` success and the refusal checks. `/health` only checks the DB. |
| Frontend `VITE_API_BASE_URL` | `https://nfl-coaching-impact-api.onrender.com` with no `/api` suffix. This is public, compile-time configuration; rebuild after changing it. |
| Frontend build/output | Retain `pnpm install --frozen-lockfile && pnpm --filter nfl-coaching-impact-web build` and `frontend/dist`. Preserve Node 22.14.0 and the existing lockfile-compatible pnpm setup. |
| Frontend rewrite | Preserve `/*` → `/index.html` so `/ask` reloads and deep links work. No new frontend secret or separate Ask API origin. |

After restoring the snapshot, this exact validation command must succeed before startup:

```sh
PYTHONPATH=src python -c 'import os; from pathlib import Path; from nfl_coaching_impact.ask import AnalyticalService; AnalyticalService.from_directory(Path(os.environ["ASK_DATA_DIR"]))'
```

Run it as a build/start gate after checksum verification. No artifact-store URL, credential,
new downloader or Render change was introduced here. A manual runtime upload is not durable:
[Render Free services](https://render.com/docs/free) have ephemeral filesystems and cannot
attach persistent disks. Make the bundle part of each deployment's build output; do not rely
on an ad hoc runtime copy. The free tier also has cold starts and resource limits; local checks
are not a Render memory/load benchmark or uptime guarantee.

Without `ASK_DATA_DIR`, the API can start and `POST /ask` returns a sanitized 503. Missing,
corrupt or code-incompatible snapshots also produce a sanitized 503; paths are not exposed.
The frontend retries transient network/503 errors twice with three-second delays and offers
retry feedback. Retries cannot fix a permanently missing snapshot. A healthy database can
therefore coexist with a broken Ask page, making the separate smoke gate essential.

**No C19/C20 migration or production DB reload is required.** Existing historical serving
routes still require the previously approved publication and schema through migration
`0005_coaching_completeness`; they are not rebuilt from Ask. Their live state was not queried.
The C19 bundle has its own version/lineage and is not relabeled as a DB `load_id`.

## Local release validation

| Check | Result |
|---|---|
| C20 focused tests before integration | 32 passed |
| Ask backend/provenance/schema/refusal tests | 40 passed |
| Frontend unit/component suite | 89 passed; includes 15 Statistics, 26 NetworkPage, 20 graph-transform, six graph-component and five AskPage tests |
| Real local Ask browser tests | 6 passed across desktop, tablet and mobile; real snapshot/API responses |
| Disposable PostgreSQL/API behavior | 46 passed, including migrations, publication rollback, pagination, views and explorer contracts |
| Required exact-question HTTP checks | Four safe refusals with alternatives; C16 lookup, OpenAPI and allowed/disallowed CORS preflight passed |
| TypeScript / ESLint / Prettier | Passed |
| Frontend production build | Passed, compiled with the public production API origin; includes lazy-loaded Ask route |
| Ruff / Python formatting / compilation / diff | Passed; 167 Python files formatted |

The local DB runner explicitly removed `DATABASE_URL` and `TEST_DATABASE_URL`, created its own
disposable server, and cleaned it up. No test connected to Neon. Initial sandbox restrictions
on process inspection/socket binding were resolved with permission for local execution; they
were not counted as skipped tests. This release run skipped none of its selected tests. The
unchanged opt-in external source suites and model-refitting suite were not rerun: this closeout
fits no model. The immediately preceding C20 full offline result remains 412 passed/51 opt-in
skips and is not presented as a fresh closeout run. Existing Starlette/httpx and browser color
environment warnings did not fail validation. No deployment or provider setting was changed.

The Ask browser server intentionally had no database connection: `/versions` returned 503
while `/ask` served the verified snapshot. Database-backed endpoints were exercised separately
by the 46 PostgreSQL/API tests; the six browser checks are not claimed as a full-site live test.

## Reopen conditions

C15 needs approved historical preseason team-assignment/context evidence with adequate
coverage. C17 needs that evidence plus a predeclared model that improves future prediction
and generalizes across changed environments. More data alone does not reverse its failed
test. C18 can resume only after a defensible out-of-sample environment-response mechanism
and multi-year transition assumptions have been established; it remains unimplemented.

C20 requires approved, reproducible college QB histories, canonical mappings and defensible
entry dates. CFBD authenticated private research or another source clearing reuse/provenance
requirements could reopen the source gate. Then college/draft models must earn support through
chronological evaluation and calibrated uncertainty. None of these research projects starts here.
