# Checkpoint seven report

Date: 2026-08-30

Status: implemented; awaiting approval

## Outcome

Checkpoint seven adds a reproducible PostgreSQL serving layer and read-only FastAPI API without changing any historical metric, coaching assignment, PAE, or coach-impact model. It loads historical `c3-f6c1aa118ff43b90`, expected performance `c5-8fd5d1aba2598c59`, and coach impact `c6-400a5b474aa37a35` / `coach-impact-400a5b474aa37a35` under schema `checkpoint-7.0`, loader `serving-loader-v1`, and API contract `api-v1`.

The deterministic serving load ID is `e4984ec4-e17e-5fed-99e4-52390f4d7c72`.

## Loaded rows

| Dataset | Rows |
|---|---:|
| Teams / aliases | 32 / 143 |
| Players / external IDs | 15,930 / 156,578 |
| Games / QB games / QB seasons | 7,276 / 17,255 / 2,899 |
| Published PAE | 1,689 |
| Coaches / assignments / citations | 281 / 1,343 / 1,349 |
| Manual-review items | 1,527 |
| Coach exposures / effects / ranking contracts | 4,308 / 144 / 144 |
| Source / pipeline manifests | 140 / 3 |

Published view counts are 1,689 QB-season rows, 1,689 PAE rows, 144 coach-impact rows, 1,343 assignment rows, 1,170 network edges, 1,349 citations, and seven review-summary groups. Warm-up QB rows are absent from published views.

## Database design and safety

Alembic revision `0001_checkpoint7` creates immutable load-scoped serving tables. Composite foreign keys enforce player/team/game/season/coach lineage. Behavioral triggers reject overlapping non-shared or mixed shared/non-shared role intervals and require citations for verified assignments. Checks preserve interval ordering, exact fractional exposure, PAE arithmetic, uncertainty ordering, and suppression rules.

The loader validates upstream checksums, required columns, null/duplicate business keys, citations, exposure arithmetic, and every model/data version before writing. All inserts and the `serving_publication` pointer change occur in one transaction. Failures roll back without a valid-looking partial publication. Identical reruns reuse the deterministic load after checking completeness. Independent empty databases produce the same load ID and ordered analytical-view checksums; execution timestamps may legitimately differ.

## API contract

The API supplies health/version, QB list/profile/PAE, coach list/profile/impact, team list, assignments, network nodes/edges, citations, and review summaries. Queries use bound parameters and whitelisted sort expressions. List endpoints use `limit` (1-200), `offset` (nonnegative), `total`, and deterministic ordering. Missing details return 404, invalid queries return FastAPI 422 responses, and valid no-match list queries return empty pages.

Every request transaction is PostgreSQL read-only. No credential, local path, cache status, or mutable execution metadata is exposed. Coach-impact responses retain exploratory, identified, ranking-eligibility, and suppression fields. The API does not turn suppressed checkpoint-six estimates into rankings.

Authentication is not implemented. The application is local-development only and must not be exposed publicly.

## Validation

- Disposable PostgreSQL 17 migration and real-data load: passed.
- Legacy PostgreSQL constraint tests: 9 passed.
- Checkpoint-seven PostgreSQL/API tests: 12 passed, including repeatable migrations, idempotency, lineage and fractional-exposure rejection, interval-basis/shared-duty preservation, warm-up filtering, version mismatch rejection, atomic rollback, endpoint behavior, and independent clean-load checksums.
- Full offline discovery: 97 tests, 74 passed and 23 integration tests skipped by design; the separately invoked 21 PostgreSQL/API and two network tests all passed, so every discovered test passed in its applicable environment.
- Ruff, formatting, and `git diff --check`: passed.

Generated PostgreSQL data files, caches, source/model artifacts, secrets, and dumps remain ignored and uncommitted.

## Known limitations

- No authentication, rate limiting, TLS, deployment, or production observability.
- Offset pagination and `ILIKE` search are sufficient for this portfolio dataset but are not a large-scale search design.
- Network routes expose data only; no graph UI or graph inference was built.
- PostgreSQL stores the already exploratory/suppressed checkpoint-six outputs and does not improve causal identification.
- The application requires PostgreSQL; SQLite is intentionally unsupported.

## Exact next checkpoint

Checkpoint eight may build the responsive Next.js frontend against the documented read-only API: QB, coach, and team search/detail views; filters; tables; charts; uncertainty and suppression explanations; and methodology links. It must not change checkpoint-five or checkpoint-six analytical definitions without a separate reviewed model checkpoint.

Stop here for approval before checkpoint eight.
