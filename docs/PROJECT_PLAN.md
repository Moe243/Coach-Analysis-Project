# Project plan

## Checkpoint one — foundation (complete)

- Feasibility audit and source register
- Metric and modeling specification
- Architecture and PostgreSQL schema
- Manual coaching-data template
- Reproducible source audit and offline contract tests
- No frontend and no fitted rankings

Exit criterion: repository contracts are internally consistent, tests pass, and checkpoint two is explicitly approved.

## Checkpoint two — data foundation vertical slice (complete)

Implement one CLI that ingests 2009 warm-up plus 2010, 2016, 2022, and 2025 boundary seasons; writes Bronze/Silver Parquet; resolves canonical player/team IDs; computes QB game/season metrics; and produces duplicate, unmatched-ID, coverage, and leakage reports.

Exit criterion met: `make vertical-slice` and its offline form are repeatable; dependencies are locked; behavioral fixture tests prove formulas, lineage, cache reuse, and atomic failure; the five official seasons pass cardinality, identity, coverage, and leakage checks. No coach rankings or frontend were created.

## Checkpoint three — full historical ingestion (complete)

Expand validated ingestion to 1999-2025, with 1999-2009 warm-up only and 2010-2025 analysis seasons. Ingest play-by-play, schedules, rosters, player statistics, injuries, depth charts, and snap counts where available; preserve explicit historical gaps; process and publish seasons independently; and assemble complete QB-game and QB-team-season tables only after every season passes.

Exit criterion met: the 140-asset official build passed storage/download preflight, all 27 seasons published independently, the full dataset published atomically, the offline rerun reused checksum-identical outputs, and season-level source/metric/quality summaries report all gaps and warnings. No coaching or modeling work was started.

## Checkpoint four — coaching-data verification (complete)

Build the source-backed coach-team-season-role table for 2010-2025, including assignment intervals, interim/shared/retained flags, citations, conflicts, and coverage reporting.

Exit criterion met after review fixes: all 512 team-seasons are covered by 1,343 assignment rows; 566 verified intervals have citations; 777 provisional assignments and 1,527 unresolved reviews remain explicit; identity, interval, interim, source-content, compound-title, overlap, and PostgreSQL contracts pass. Unsupported play callers remain queued rather than inferred.

## Checkpoint five — expected performance (complete)

Build timing-safe prior/career features, three shrinkage baselines, a tuned Ridge candidate, expanding-window evaluation, out-of-sample predictions, uncertainty, and leakage/stability reports. Validated college/draft data was absent and remains explicitly missing.

Exit criterion met: all 1,689 published PAE rows are out of sample and exclude warm-up seasons; career performance was selected from four candidates using documented accuracy/calibration scoring; opening-week team snapshots prevent midseason-destination leakage; roster experience is separate from prior QB history; complete parameter/source/code/dependency identity controls immutable versions; deterministic clean-rebuild, leakage, arithmetic, cardinality, missingness, and atomic-failure contracts pass.

## Checkpoint six — coach impact (complete)

Build interval-compatible QB-coach exposures; compare no-coach, regularized coach fixed-effect, and empirical-Bayes partial-pooling models; produce QB-season block-bootstrap uncertainty, role-specific sensitivities, overlap diagnostics, and preliminary ranking eligibility/warnings.

Exit criterion met: verified primary estimates include fractional interval exposure and 200-block-bootstrap intervals; provisional/shared/weighting/control/threshold sensitivities remain separate; unsupported QB-coach attribution is suppressed; every rank is preliminary and non-publishable; deterministic clean rebuild and content identity contracts pass.

## Checkpoint seven — application database and API (complete)

Create Alembic migrations, curated PostgreSQL loads, FastAPI search/filter/detail endpoints, pagination, schema validation, and API tests.

Exit criterion implemented: migrations are repeatable; the loader publishes canonical, analytical, provenance, and review facts atomically and idempotently; serving views exclude warm-up output where required; disposable PostgreSQL/API behavior tests pass; and independent clean loads have identical analytical checksums.

## Checkpoint eight — frontend (implemented; pending approval)

Build a responsive React/TypeScript interface with URL-synchronized quarterback, coach, team, season, role, evidence, eligibility, ordering, and metric filters; QB and coach detail routes; source citations; a focused coaching-network graph with a semantic list alternative; and an interpretation guide.

Exit criterion implemented: real checkpoint-seven API flows were exercised at desktop, tablet, and mobile widths; component/API/accessibility tests, lint, formatting, type checking, and the production build pass; loading, empty, error, pagination, deep-link, evidence, uncertainty, and suppression states are covered. Deployment and portfolio packaging remain checkpoint nine work.

## Checkpoint nine — portfolio polish

Add screenshots/GIFs, CI, Docker Compose application workflow, conclusions, employer-oriented README narrative, reproducibility review, and deployment documentation.

Exit criterion: clean-clone setup works and conclusions answer the research question without causal overstatement.
