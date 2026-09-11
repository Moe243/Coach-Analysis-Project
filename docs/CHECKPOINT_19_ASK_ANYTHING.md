# Checkpoint 19 — Ask Anything

Date: 2026-09-10. Scope: isolated implementation/review; **not deployed**.

Final content version: `c19-62010b4bfffeb4af`. API contract: `ask-v1`.

## Integration and research boundaries

C17 commit `8142227a6d2baef1656f149d6bfe3367ade546e2` was fast-forwarded into
`main` and pushed to `origin/main` after its 18 focused tests passed. Its result
remains **NOT SUPPORTED**: destination environment and interaction terms did not
improve the C16 baseline. C18 remains **NOT READY** and unimplemented.

C19 starts from that commit on `codex/phase2-checkpoint-19-ask-anything`.
It is an interface to approved evidence, not a new analytical model. C20 is
unimplemented and requires a separately approved college/rookie data/model design.
No model, PAE/PCAE formula, database migration, production publication, deployment
configuration, Neon or Render setting changes are part of this checkpoint.

## Architecture

`scripts/run_checkpoint_nineteen.py` captures and validates approved artifacts and
all manual CSV bytes, then atomically publishes a local content-addressed bundle.
The API never builds this bundle on request. It loads the explicitly configured
`ASK_DATA_DIR`, verifies the bundle checksum, manifest/content identity, contract
and relevant code identity, then retains an immutable in-memory snapshot.
Missing, incompatible or tampered snapshots return a sanitized HTTP 503. An
operator must restart the process to activate a replacement snapshot.

`POST /ask` accepts only `{ "question": "..." }`, trimmed to 3–1,000 characters.
The endpoint is read-only despite using POST. The existing explicit CORS origin
allowlist remains; POST is added to GET for JSON preflight. No SQL, source URL,
filesystem path, Python expression or user-selected analytical model is accepted.
The additive `ask-v1` contract is independent of the existing database publication
contract: old statistics/relationship views need no reload or migration.

Processing is deterministic: normalize text → priority-ordered intent rules →
canonical entity/season/metric resolution → approved table lookup → structured
response → fixed explanation template. No LLM, external credentials or paid API
is required. `explain(AskResponse)` is the future explanation adapter boundary;
it cannot select a different model, generate estimates or override a refusal.

### Intents and capability gates

| Intent | Evidence/action |
| --- | --- |
| `QB_HISTORY` | Canonical regular-season QB-team-season facts and OOS PAE, 2010–2025 |
| `QB_PROFILE` | C14 entering-season state features and uncertainty, 2010–2025 |
| `QB_PROJECTION` | Exactly the 57 C16 EPA-only 2026 team-independent research rows |
| `COACH_HISTORY` | Verified source-backed assignments using the Eleven-B formal-title overlay |
| `COACH_QB_RELATIONSHIP` | Assignment × QB-team-season context, not exact weekly exposure |
| `TEAM_SCHEME` | Observed C13 team-season tendencies; an explicit tendency can list all teams |
| `PCAE_RESEARCH` | Frozen C12 verified, non-shared caller interval research evidence |
| `PLAYER_TEAM_SCENARIO` | Refuse: C17 did not validate environment-response estimates |
| `CAREER_COUNTERFACTUAL` | Refuse: C18 has no validated multi-year response mechanism |
| `ROOKIE_PROJECTION` | Refuse: C20 completed its source gate as DATA-LIMITED; no rookie model was implemented or validated |
| `COACH_EFFECT` | Refuse: no composite Coach Effect or causal coach-improvement number |
| `UNKNOWN` | Clarify; no analytical fallback |

Unsupported capability rules precede supported-intent rules. Destination-qualified
projections also refuse rather than silently answer a different, team-independent
question. Forward PAE, other outcomes, years outside 2026, and candidates outside
the frozen 57 receive no new estimate. This is a bounded deterministic vocabulary,
not general natural-language understanding. Complex or unsupported phrasing may
require reformulation. No conversational/pronoun memory is implemented.

### Entity, season and response contracts

Canonical GSIS QB IDs, repository coach IDs and franchise team IDs are retained.
Exact canonical IDs have priority; normalized names, repository coach aliases,
team abbreviations/city/nickname labels and surnames follow. Ambiguous matches
return candidates, never a numerical choice. Near-name fuzzy matches suggest
confirmation only. Selecting a candidate resubmits the same question with its ID.
Multiple explicit seasons require clarification. Historical QB/coach requests
may omit season to inspect history; scheme defaults explicitly to observed 2025;
style defaults explicitly to **entering 2025**, not current or end-2025 ability;
projection defaults explicitly to the frozen 2026 research forecast.

The response includes `contract_version`, `intent`, `entities`, `season`,
`requested_metric`, `status`, `data_version`, nullable `model_version`, `metrics`,
`uncertainty`, `limitations`, logical `source_artifacts` with versions/checksums,
`candidates`, `reason`, `available_alternative`, and `explanation`.
Status is `SUPPORTED`, `NOT_SUPPORTED`, `NOT_YET_SUPPORTED`,
`CLARIFICATION_REQUIRED`, `DATA_UNAVAILABLE`, or `NARROW_SCOPE`.
More than 400 records yields `NARROW_SCOPE` with no partial metrics or uncertainty.
No answer calculation produces a new number: rates, estimates and intervals come
from the approved source rows. Sorting and display rounding are not new estimates.

## Frozen source contracts

| Family | Approved version | Bundle rows |
| --- | --- | ---: |
| Historical + canonical enhancements | `c3-f6c1aa118ff43b90`, `enh-04254065cafd92ba` | 1,187 QB-team-seasons |
| OOS expected performance | `c5-8fd5d1aba2598c59` via canonical enhancement PAE | Exact full-key join |
| C14 | `c14-43283062e788e686` | 8,457 states; 50,787 feature records |
| C13 | `c13-5e3d7a34ea4d1af5` | 6,144 tendency records |
| C16 refinement | `c16r-8c8063c5954e2a22` | 57 projections |
| C12 final caller evidence | `c12-pc-final-cac923f086757e5b` | 287 intervals |
| Validated serving Eleven-B manual snapshot | hash of captured manual inputs | 1,857 assignments before verified-only filtering |

The bundle has 1,119 canonical entity labels. Historical PAE joins on
`player_id, team_id, season` within exact frozen historical/expected versions.
There is no database load ID at this artifact boundary, so no DB publication is
mixed in. There is no player-season-only join and no averaging of stint rates.
Trent Edwards' 2010 Buffalo and Jacksonville records remain separate and preserve
their different PAE values. Missing values remain null. Historical expectation
intervals are not relabeled as newly estimated PAE confidence intervals.

C14 raw values, shrunk estimates, source/history windows, sample sizes,
qualification, missingness, reliability, stability/portability classification and
intervals remain distinct. No new latent ability or 0–100 style grade is created.
C13 scheme answers are observed historical behavior, not preseason forecasts or
causal coach attributes. No C16 prediction acquires a team/coach assumption.

Coaching history reuses the serving completeness validator and formal OC/QB-coach
overlay, not superseded base formal-role rows. Only verified assignments are
returned, with interval basis, citations and shared/interim flags. Retained status
is null where the source overlay does not supply it. QB links preserve assignment
keys and mean only **same-team-season context**. Missing roles are not evidence
that a person held no role. PCAE uses the separately labeled final C12 evidence
snapshot; it is not silently merged into older serving assignments. Its source
contains no caller-interval uncertainty estimate, so that uncertainty is explicitly
unavailable. Incomplete/nonrandom coverage remains a limitation. PCAE is not a
universal Coach Effect, a causal attribution or a coach ranking.

## Determinism and local operation

Run, from the isolated worktree:

```sh
PYTHONPATH=src:. python scripts/run_checkpoint_nineteen.py
```

This creates ignored `data/processed/ask_anything/<c19-version>/` containing
`analytical_bundle.json` and `MANIFEST.json`, plus an atomic parent `LATEST` pointer.
Configure local `ASK_DATA_DIR` to that version directory and run the existing API.
The frontend uses its existing `VITE_API_BASE_URL` and sends JSON to `/ask`.
There are no new secrets or external-LLM environment variables.

Version identity includes the exact captured input bytes, frozen source versions,
router/builder/endpoint and reused validator/constants source hashes, Python,
Polars, Pydantic, JSON serialization settings and final bundle checksum.
Existing version directories cannot be overwritten with different contents.
Two real CLI builds into independent roots must have identical versions,
manifests and bundle bytes. Source artifacts and source manifests are never edited.

## Frontend

The `/ask` page is a lazy-loaded additional navigation tab. Existing Statistics
and Relationship Explorer implementations are unchanged. A labeled question form,
supported examples, canonical clarification buttons, response/status explanation,
readable metric cards, optional full source fields, uncertainty and provenance
sections make the evidence inspectable. Nulls display as `Unavailable`; query
failures display errors rather than sample data. Two bounded automatic retries
cover retryable API/network failures; explicit retry resubmits the failed question.
Each displayed answer retains the submitted question, preventing edited input from
masquerading as the answer's request. New requests clear stale answers.

## Examples from the approved artifacts

- Josh Allen 2022: EPA/DB `0.23669382413196524`, expected
  `0.12208120500548975`, PAE `0.1146126191264755`.
- Lamar Jackson entering 2025 recent scramble rate: raw `0.08518518518518518`,
  shrunk `0.08077328160849609`, reliability `HIGH`; historical window is explicit.
- Miami 2024 observed average air yards: `6.3219761499`.
- Josh Allen 2026: **TEAM-INDEPENDENT RESEARCH PROJECTION**, EPA/DB
  `0.12002145080037831`; historical residual 80% band
  `[-0.07339268585363214, 0.31343558745438876]`, not guaranteed future coverage.
- Andy Reid 2024 PCAE: `0.0155738523`, separate research-only decision value.
- Kyler Murray in Minnesota: `NOT_SUPPORTED`, no metrics; offer projection and
  destination history separately without combining them.
- Mahomes drafted by Chicago: `NOT_SUPPORTED`; Fernando Mendoza NFL projection:
  `NOT_YET_SUPPORTED`; universal Reid QB-improvement score: `NOT_SUPPORTED`.

## Validation and closeout

Completed focused validation:

- C17 integration gate: **18 passed**.
- Final C19 backend/API/artifact tests: **40 passed**. These cover all intent families,
  refusal contracts, projection/PAE identity, multi-team grains, state timing, nulls,
  ambiguity/canonical confirmation, source capture/tampering, deterministic snapshots,
  real FastAPI requests, cross-origin POST preflight and sanitized errors.
- Existing local PostgreSQL/API behavior suite: **46 passed** on a disposable local
  server, including migrations, atomic rollback, idempotency, serving identity,
  full-key PAE, all Relationship Explorer modes and API filtering. Production URLs
  were removed from the test environment. The first sandboxed launch was blocked
  by process inspection; the permissioned local-only rerun passed.
- Frontend unit/components: **89 passed**, including existing Statistics,
  Relationship Explorer, QB/coach detail, selection and URL behavior.
- C19 real-API Playwright: **6 passed** across desktop, tablet and mobile, repeated
  on the final snapshot. Numerical responses were not mocked. Checks cover canonical
  clarification, history, projection, refusal, provenance and no horizontal overflow.
- TypeScript, ESLint, Prettier, Ruff, Python formatting, Python compilation and
  production frontend build: **passed**. Copied ignored dependency caches were used;
  the pnpm dependency auto-install check was disabled for local browser tests only.
- Two separate real CLI builds into independent output roots produced the same
  final version and byte-identical `MANIFEST.json` and `analytical_bundle.json`.

Review corrections included allowing POST through the still-restricted CORS
allowlist, preserving ambiguity between different canonical names, refusing explicit
coach-qualified forecasts without misclassifying a QB's surname as coach context,
and clearing all analytical payloads on narrowing/refusal. No unresolved model
or data-contract defect is being deferred as a fabricated fallback.

Full offline regression: **373 passed, 51 intentionally skipped**, one upstream
Starlette/httpx deprecation warning, in 1,205.57 seconds. This run collected the
initial 33 C19 cases; the final expanded **40-case** focused suite was run afterward
and passed on the final code. No skipped test is counted as a pass.

The 51 offline skips comprise 46 database-dependent tests (all separately passed
on the disposable local PostgreSQL server) and five opt-in remote-source/network
tests. The five remote-source tests were **not rerun**: C19 makes no source-ingestion,
source-evidence or network-collection change. Legacy participation/FTN regression
inputs were checksum-verified and seeded into the existing library's memory cache
for offline execution; no assertion was bypassed or source downloaded.

**C19 STATUS: COMPLETE — isolated review commit.** The review commit contains code,
tests and documentation only; ignored analytical/dependency outputs remain local.
No C19 merge/push or deployment occurred. C18 is NOT READY and unimplemented. C20
is not implementation-ready under this checkpoint; it needs its own approved
rookie/college data and modeling specification and remains unimplemented.
