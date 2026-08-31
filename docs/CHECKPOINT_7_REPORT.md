# Checkpoint seven report

Date: 2026-08-30

Status: implemented; awaiting approval

## Outcome

Checkpoint seven adds a reproducible PostgreSQL serving layer and read-only FastAPI API without changing any historical metric, coaching assignment, PAE, or coach-impact model. It loads historical `c3-f6c1aa118ff43b90`, expected performance `c5-8fd5d1aba2598c59`, and coach impact `c6-400a5b474aa37a35` / `coach-impact-400a5b474aa37a35` under schema `checkpoint-7.1`, loader `serving-loader-v2`, and API contract `api-v1.1`.

The deterministic serving load ID is `e6efef76-b0cc-5bb8-ab82-d634bf2cf1d8`. Its manual-input digest is `67c3b4bf0f5179042e3a859535d931cfb3a7290099a7e79f5bba5d967ba56784`.

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
| Source / pipeline manifests | 140 / 4 |

Published view counts are 1,689 QB-season rows, 1,689 PAE rows, 144 coach-impact rows, 1,343 assignment rows, 1,170 network edges, 1,349 citations, and seven review-summary groups. Warm-up QB rows are absent from published views.

## Database design and safety

Alembic revision `0001_checkpoint7` creates immutable load-scoped serving tables from a revision-specific SQL snapshot, so later changes to `db/schema.sql` cannot rewrite migration history. Composite foreign keys enforce player/team/game/season/coach lineage. Deferred behavioral triggers reject exposure rows whose assignment key, coach, team, season, role, weeks, verification, confidence, interval basis, or shared status disagrees with the referenced assignment. Other guards reject overlapping role intervals, require citations for verified assignments, and prevent citation reassignment from orphaning a verified row. Checks preserve interval ordering, exact fractional exposure, PAE arithmetic, uncertainty ordering, and suppression rules.

The loader validates upstream checksums, required columns, null/duplicate business keys, citations, complete exposure-assignment lineage, exposure arithmetic, and every model/data version before writing. Every mutable manual CSV is hashed into the load ID and a stored `manual_inputs` manifest; changing one forces a new publication rather than reusing an old load. All inserts and the `serving_publication` pointer change occur in one transaction. A failed candidate load preserves the previous active publication and removes every partial candidate row. Identical reruns reuse the deterministic load after checking completeness. Independent empty databases produce the same load ID and ordered checksums across all eight analytical views; execution timestamps may legitimately differ.

## API contract

The API supplies health/version, QB list/profile/PAE, coach list/profile/impact, team list, assignments, network nodes/edges, citations, and review summaries. Queries use bound parameters and whitelisted sort expressions. List endpoints use `limit` (1-200), `offset` (nonnegative), `total`, and deterministic total ordering ending in a complete business key. Shared role/status enums return 422 for invalid values. Network edges include both assignments' verification, confidence, shared/provisional, full-interval, and overlap fields and support a both-assignments verification filter. Missing details return 404 and valid no-match list queries return empty pages. The PAE view explicitly joins an analysis-scope QB season, so even an out-of-sample warm-up record remains unpublished.

Every request transaction is PostgreSQL read-only. No credential, local path, cache status, or mutable execution metadata is exposed. Coach-impact responses retain exploratory, identified, ranking-eligibility, and suppression fields. The API does not turn suppressed checkpoint-six estimates into rankings.

Authentication is not implemented. The application is local-development only and must not be exposed publicly.

## Validation

- Disposable PostgreSQL 17 migration and real-data load: passed.
- Legacy PostgreSQL constraint tests: 9 passed.
- Checkpoint-seven PostgreSQL/API tests: 20 passed; with nine legacy PostgreSQL tests, the disposable database suite has 29 passing tests. New adversarial coverage includes manual-input identity changes, complete exposure lineage, immutable migration sourcing, warm-up PAE exclusion, citation reassignment, prior-publication rollback preservation, total pagination ordering, typed role/status filters, network metadata, and all-eight-view clean-load checksums.
- Full offline discovery: 105 tests, 74 passed and 31 integration tests skipped by design. The separately invoked 29 PostgreSQL/API tests and two network tests all passed, so all 105 discovered behaviors passed in their applicable environments.
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
