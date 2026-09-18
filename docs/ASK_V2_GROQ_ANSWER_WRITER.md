# Groq 120B grounded answer writer — isolated candidate

This candidate adds a language layer, not a scientific model. It starts from
`b39b0dbabd1329a27cdbad748ede4f2ea8bdc9ad` on
`codex/ask-v2-groq-answer-writer`. Production activation is **not** part of this work.
External sharing remains disabled in the example configuration; Render and Neon are
untouched. A bounded local live smoke requires separate authorization after review.

## Flow and authority

1. Compute and retain the authoritative deterministic Ask 2.1 response.
2. When provider configuration and external sharing are ready, Groq interprets the
   bounded request through the existing untrusted draft schema.
3. The backend resolves canonical entities, binds seasons/tasks, retrieves evidence,
   and applies scientific conclusion permissions. Rejected plans fall back atomically.
4. Reduce that authorized result to a provider-neutral `ApprovedAnswerBrief`.
5. Groq returns strict phrase-ID `CompositionPlan`; the backend validates and renders it.
6. Replace only answer prose, answer mode and provider-version metadata on success.
   Evidence, propositions, answerability, permissions, uncertainty, entities,
   limitations and follow-ups remain backend-owned and unchanged.

The planner and writer use **only `openai/gpt-oss-120b`**, at most one call each.
There are no retries or repair calls. No 20B model, additional SDK, arbitrary base URL,
tools, retrieval access or hidden reasoning output is accepted. The pinned existing
OpenAI-compatible Responses SDK uses the code-owned Groq endpoint. OpenAI's separate
selection-only synthesis path and the frozen v1 snapshot identity remain unchanged.

## Exact writer input

The backend retains a provider-neutral `ApprovedAnswerBrief`: authorized propositions,
entities, measurements, years, applicable mandatory caveats and scientific permissions.
Its hard caps remain 24 supports, 64 measurements and eight mandatory caveats.
The compact writer wire catalog contains backend intent/topic, word budget, required
support IDs and approved phrase records (ID, owner support ID, kind, complete text).
Each support has at most three natural variants; current reusable families have one
or two. Unknown families retain the exact approved fact. Canonical entity plumbing,
duplicate measurement records and technical original variants need not be retransmitted.
Phrase hashes bind complete support, exact text, measurements, resolved entities and
question type; years/team/stints remain in their authorized prose. Both internal brief
and actual wire catalog must fit 48 KiB. Nothing is truncated.

No source URLs, raw evidence tables, provenance, SQL, paths, credentials, telemetry,
publication IDs or previous assistant prose enter this writer input. Private phrase
and support IDs are never rendered publicly. Conversation stays in the existing
bounded planner/context interface, not writer evidence.

## Strict output and validation

`CompositionPlan` contains one to three paragraphs, each with one to eight items and
at most sixteen items overall. Each item has only `phrase_id` and an enum connector.
There is no text, notes, reasoning, custom wording, calculation or other escape hatch.
The backend selects exact phrase text by ID. Unknown/out-of-context IDs, missing
primary fact or required caveat, duplicate phrases/supports (even alternate variants),
extra fields, excessive paragraphs/items and empty paragraphs fail atomically.
The raw Responses output is also checked for duplicate JSON keys (including nested
and escaped keys) and agreement with the SDK-parsed result; last-value-wins ambiguity
is rejected without logging or retaining the raw response.

The current implementation uses **composition planning**, not factual paraphrase.
The writer chooses facts, variants, ordering, commonality/contrast lead, optional
definition, paragraph grouping and limitation placement. The first item must be a
proposition with no connector. The primary support must appear but need not lead.
Connectors are `none`, `continuation` (Also), `contrast` (However), `comparison`
(Meanwhile), and `limitation_transition` (For context; only before a caveat). No causal
connector or provider-written transition is allowed. Answers are ordinary natural
prose in one to three short paragraphs, normally 60–180 words, less when sufficient.
Backend-authored natural variants cover historical EPA/expectation/PAE, verified role
history, role-evidence comparisons, descriptive player/scheme comparisons and
team-independent projections; other facts keep their approved wording.
The legacy `WriterResult` text schema remains internal defense in depth: backend-generated
fact/caveat sentences still pass its complete-clause, exact numeric, entity, polarity,
causal and predictive checks. It is no longer accepted from the Groq writer. The final
word budget includes rendered connectors. Resolved brief identities disambiguate former
QBs who later became coaches with the same display name (e.g. Scott Tolzien); the global
catalog still detects unrelated names. No scientific or entity-resolution rules change.

This conservative gate binds numbers to metric labels, entities, years, units, polarity
and intervals. It rejects swapped actual/expected values, attaching one stint's numbers
to another, invented grades/rankings, unseen names (including names absent from the
catalog), causal upgrades and unsupported predictions. Decimal normalization permits
a leading positive sign, a Unicode minus for an already-negative value and
`%`/`percent` typography, not new rounding or calculations. Unmatched arithmetic and
Unicode unit/sign symbols remain tokens rather than disappearing as punctuation;
they cannot reverse a sign or silently turn EPA/PAE into a percentage.
Missing values never become zero. Mandatory caveats must contain complete approved
text: citing a caveat ID while replacing its warning fails. Ordinary negated caveats
such as “not causal” or “no forward PAE” are valid, not global banned-word violations.

C16 language must remain explicitly team-independent with its approved historical
residual band. C15 fit, C17 destination predictions, C18 alternate-career simulations,
C20 rookie forecasts, forward PAE and composite Coach Effect remain unsupported.
Same-team-season coaching context never becomes exact weekly exposure or development
credit. Unconstrained provider paraphrases, even plausible ones, always fail the private schema.

## Failure, timeouts and diagnostics

Every planner/writer timeout, malformed response, HTTP failure, refusal, overflow or
validation failure returns the **exact original deterministic response**, including
null provider-model metadata. No partial writer prose or provider error reaches users.

Defaults/recommended initial budget: planner 12 seconds, writer 18 seconds, total
30 seconds (hard configuration ceiling 40). The writer receives the smaller remaining
budget; total time is checked before dispatch and after validation. SDK requests have
bounded timeouts and retries disabled. Output limits reuse the existing planner 600 /
synthesizer 800 token settings, with configurable ceilings 1,000 / 1,500. For a later
authorized live smoke, 1,500 writer output tokens may be useful for ID-rich comparisons;
no production values are changed here. Truncation is a failure, never partial success.

Best-effort diagnostics add `component=writer`, `phase=writer_validation`, bounded
validation outcome and fallback boolean to existing provider/model/attempt/success/
HTTP-status/latency fields. Validation categories are `writer_valid`,
`unknown_support_id`, `unapproved_number`, `unapproved_entity`, `missing_limitation`,
`causal_violation`, `predictive_violation`, `schema_invalid`, `unsupported_sentence`,
and `too_long`. Existing timeout/authentication/permission/rate-limit/server/transport
categories remain. No prompt, question, answer, evidence, raw exception/body, key,
header, DB URL or path is logged. Broken loggers/formatters cannot change responses.

## Historical initial implementation gate and measurements

Golden coverage includes Allen 2022, Reid/Tomlin, Kyler/Minnesota, Allen's 2026 research
projection, McCarthy offensive-role continuation, Rodgers 2011 → 2012 → coaching
history, and Reid/Tomlin → Why → McVay. Mocked provider responses are validated against
the real frozen analytical bundle; this is **not a live Groq quality/latency claim**.

Representative serialized brief sizes and approximate tokens (characters divided by
four, **not measured Groq tokenizer counts**, excluding schema/instructions):

| Flow | Bytes | Approximate tokens |
| --- | ---: | ---: |
| Allen 2022 | 2,629 | 657 |
| Reid/Tomlin | 4,910 | 1,227 |
| Kyler/Minnesota | 4,995 | 1,248 |
| Allen 2026 | 2,096 | 524 |
| McCarthy | 4,962 | 1,240 |
| Rodgers 2011 | 2,675 | 668 |

On this machine, median warm construction was about 0.09–0.25 ms and validation
0.24–0.56 ms over 25 repetitions per flow, excluding evidence retrieval/provider time.
Name matching uses a bounded cached snapshot matcher. Cold compilation is not included
in these warm measurements. The existing answer area, Key numbers, caveats and Keep
Exploring are preserved; the metric explainer recognizes both `EPA/dropback` and
`EPA per dropback` so natural unit wording cannot hide the explanation.

Independent review reproduced a blocking numeric-typography bypass in the initial
candidate: Unicode minus and percent symbols were discarded by phrase normalization.
The corrective regression cases cover sign/unit substitutions, double negation,
arithmetic symbols and atomic fallback. The review also added shorter approved
comparison/caveat wording without removing any mandatory restriction, and repaired
the metric-explainer detection described above.

Historical independent review gate on 2026-09-17: 661 backend Ask/provider/context/release/C19 tests,
66 targeted frontend Ask/API/context/exploration tests and 21 mocked browser tests
across desktop/tablet/mobile passed, with no failures or skips. Browser checks include
accessibility and page-overflow assertions. TypeScript, ESLint, Prettier, Ruff, Python
formatting/compilation, the local production frontend build and diff checks passed.
Playwright emitted only the existing `NO_COLOR`/`FORCE_COLOR` environment warning.
Sandbox cache-access failures were rerun with approval; they were not skipped tests.
No live provider calls were made.

Offline examples improve concise statistical and role wording; the value of another
model call for comparisons remains modest and unproven live. Before merge, a separately
authorized bounded local smoke should assess Allen 2022, Reid/Tomlin, Kyler/Minnesota
and Allen 2026 for grounding acceptance, readability, tokens and total latency. This
does not authorize production sharing or activation.

## Historical corrective round following the first live smoke

The first smoke used eight requests. All four planners succeeded; Allen 2022's writer
validated, Reid/Tomlin's writer returned HTTP 400 and the other two writers returned
HTTP 429. Failures returned exact deterministic responses. Allen's accepted prose did
not materially improve presentation. These are not successful full writer-quality tests.

Structural diagnosis found identical static strict output schemas for Allen and
Reid/Tomlin: 1,481 serialized bytes, SHA-256
`e006c9d4c217e60b5b899fe74a31221b656a836eaf7d9d232205bbfbe170364c`.
There are no dynamic ID enums. Every object forbids extras and requires all properties.
Model, endpoint, reasoning and output limit were identical. The difference was input and
prospective output complexity: Reid/Tomlin had 11 supports/seven mandatory caveat IDs,
versus Allen's four supports/two IDs. The old telemetry retained no error code/parameter.
It cannot prove unsupported schema, truncation or any other specific cause of the 400.

Corrections keep the same schema/model/reasoning/timeout/token configuration:

- Natural variants combine actual/expected EPA, PAE and dropbacks without inventing
  grades. Exact source decimals are preserved, not rounded. The writer still chooses
  useful facts, ordering, wording, definitions and paragraph grouping.
- Presentation applicability is backend-owned. Complete player/team/year facts preserve
  grain. Interval-method notes need not be recited when no uncertainty interval is
  discussed. PCAE warnings remain mandatory when PCAE facts appear, not for role-only
  comparisons. Unknown caveats always remain; original response/policy never changes.
- Applicable restrictions are translated, deduplicated only when equivalent, and grouped
  into mandatory paragraphs. Causal-development, destination-prediction, team-independent
  scope, missingness, preseason timing, bounded evidence and exact-week warnings remain.
- The wire brief transmits natural variants without repeating the technical original.
  Backend validation retains original facts and complete approved alternatives.
- Groq 400/429 diagnostics allowlist structured error type/code/parameter; unknown values
  become null. No message/failed-generation/raw body/exception is logged. A separate
  local-only helper captures numeric quota/reset metadata without waiting or retrying.

Writer wire sizes, excluding instructions and the unchanged schema:

| Flow | Before bytes | After bytes |
| --- | ---: | ---: |
| Allen 2022 | 2,629 | 1,849 |
| Reid/Tomlin | 4,910 | 3,219 |
| Kyler/Minnesota | 4,995 | 3,801 |
| Allen 2026 | 2,096 | 1,833 |
| McCarthy history | 4,962 | 4,253 |

All planner fields are consumed by translation/resolution/context guards; none was
removed. Prior 300–555 output-token counts do not establish avoidable draft content;
reasoning effort remains unchanged. Writer prose normally targets about 60–180 words;
short supported historical answers need not be padded.

### Future paced four-question smoke — not run in this task

Use the same four questions, at most eight calls, no retries/repairs. Start distinct
two-call questions at least 90 seconds apart when reliable reset metadata is absent.
When numeric Retry-After/reset metadata is available, wait that duration plus five
seconds and at least 90 seconds before the next distinct question. Stop the session on
429; never repeat it. Daily quota exhaustion needs a later session, not minute pacing.
Application 429 behavior remains immediate deterministic fallback, with no waiting.

Groq documents organization-level RPM/RPD/TPM/TPD limits and numeric quota headers:
[rate-limit documentation](https://console.groq.com/docs/rate-limits).
The prior smoke did not retain quota/reset metadata, so its exact limiter is unknown.
Eight burst requests and at least 7,300 reported tokens are consistent with token limits,
not proof of one; three failed writers reported no usage.

Offline corrective gate: 690 backend tests passed, zero failures/skips, including five
quality goldens, the exact SDK Reid/Tomlin schema test, closed diagnostics, mandatory
restriction preservation and SDK-level no-retry writer-429 fallback. Frontend Ask/API
regressions: 66 passed, zero failures/skips. TypeScript, ESLint, Prettier, Ruff, Python
formatting/compilation, production frontend build and diff checks passed. Dependency
cache permission failures were rerun with approval, not counted as skipped tests.
Any live diagnostic remains bounded to one planner and one writer request only.

### Authorized two-call diagnostic — corrective gate failed

Exactly two additional local requests were made, without retries: one Reid/Tomlin
planner and one writer, both using `openai/gpt-oss-120b`. Both returned HTTP 200 and
parsed schemas. The writer failed the unchanged complete-clause grounding validator
with bounded category `unsupported_sentence`. The user response exactly matched the
original deterministic answer, with null planner/writer model metadata. Rejected raw
prose was not logged, reported or saved. No prompt rewrite or gate relaxation followed.

Planner latency was 1.657 seconds; writer latency 1.914 seconds; total 3.649 seconds.
Provider-reported usage: planner 940 input/495 output tokens; writer 1,582 input/739
output tokens; 3,756 combined. This confirms current request transport/schema parsing
works, not the precise cause of the earlier 400 or validated live writer quality.

Safe quota headers reported an 8,000-token limit, with 6,742 then 4,842 tokens remaining
and reset durations of 9.435 then 23.685 seconds. Request headers reported a 1,000 limit
with 999 then 998 remaining. This supports token-pressure plausibility for the prior
burst, but cannot retrospectively establish which quota caused its 429s. No rate-limit
response occurred in this diagnostic and no Retry-After value was supplied.

That historical corrective round failed its live gate and left its eight intended
corrections uncommitted. Main, Render, Neon, OpenAI and production sharing were untouched.
It motivated the separately authorized composition-only corrective round below; the
rejected wording itself is unknown and no exact offending sentence is asserted.

## Historical composition corrective round — offline only

Private writer implementation identity is now
`ask-v2-stage-d/groq-composition-writer-v2-responses-3.14`; analytical versions and
the frozen Ask snapshot are unchanged. Existing natural phrase families, caveat
applicability, safe bounded diagnostics and no-retry protections are retained.
Two distinct valid plans are tested for historical performance, role comparison,
player/team descriptive alignment and team-independent projection: variants, ordering,
paragraph grouping and limitation placement change without changing approved facts.
McCarthy offensive-role continuation and Rodgers 2011 → 2012 → coaching context use
the real frozen deterministic bundle. Provider call count in this task is **zero**.
Live accepted composition quality still requires a separately authorized paced smoke.

Current representative wire sizes (canonical JSON; excludes instructions/schema):

| Flow | Previous reduced prose brief bytes | Composition catalog bytes |
| --- | ---: | ---: |
| Allen 2022 | 1,849 | 955 |
| Reid/Tomlin | 3,219 | 2,326 |
| Kyler/Minnesota | 3,801 | 2,764 |
| Allen 2026 | 1,833 | 1,021 |

Offline product goldens: Allen 2022, Reid/Tomlin, Kyler/Minnesota, Allen 2026,
McCarthy offensive-role continuation and Rodgers follow-ups all **PASS**. Reid/Tomlin
includes both documented environments and the non-causal limitation; Allen 2022 has
no irrelevant caveat. Projection retains the team-independent scope and original band.
Adversarial plans for wrong entity/season/measurement/limitation, unknown connectors,
missing primary support/caveats, duplicate phrase/support variants, text escape hatches,
empty/excessive paragraphs/items and malformed structure fail closed. Top-level, nested
and escaped duplicate JSON keys also fail. HTTP 400/429/5xx and timeout fallback remain
atomic; SDK-level 429 coverage confirms one request and no retries.

Final gate: **728 backend passes**, **66 frontend Ask/API passes**, zero failures/skips.
Backend includes Ask/context/release/C19, OpenAI Stage D, Groq provider, writer,
composition, diagnostics and broken logger/formatter regressions. TypeScript, ESLint,
Prettier, Ruff, Python formatting (104 files), compilation, production frontend build
and `git diff --check` pass. A frontend dependency-cache permission startup failure was
resolved with narrowly granted cache access, not skipped or counted as a test pass.
No frontend source, analytical pipeline/model, frozen snapshot, database/migration,
production configuration or deployment file changed. No live Groq/OpenAI calls occurred;
Render and Neon were not accessed. The future paced smoke plan above remains required.

## Historical descriptive-scenario composition polish

The subsequent paced smoke accepted all four planner/writer compositions without
fallback, retry or 429. Its product gate failed only for Kyler/Minnesota: fragmented
rate comparisons were interrupted by two mandatory passages totaling 68 words, with
repeated “For context” introductions. This is a presentation defect, not unsupported
scientific evidence or a provider transport defect.

Private writer identity is now
`ask-v2-stage-d/groq-composition-writer-v2.1-responses-3.14`. Reusable descriptive
phrases are complete player-first/team-first sentences. “Higher than”, “lower than”
and “the same as” describe the exact approved rates using Decimal comparisons; they
do not infer similarity thresholds, suitability, improvement or predictive fit.
No metric, analytical model, scientific permission or frozen snapshot changes.

Only `PLAYER_TEAM_SCENARIO` combines the complete known six-warning bundle into one
33-word mandatory phrase: limited coverage, preseason/not-live history, unavailable
missing measurements, no coaching causation, no predictive fit and no forecast of
performance/improvement with another team. Consolidation requires all six known
meanings; partial bundles and additional/unknown warnings are retained. The original
backend response and its limitations remain unchanged. Other question types,
including the Reid/Tomlin development limitation, are not shortened.

Scenario wire rules require at least two approved factual points when two are
available, all facts before caveats, and `none` for caveat connectors. The backend
enforces the same bounds, preventing interruption and repeated introductions without
fixing the chosen facts, variants, ordering or paragraph grouping. Groq still chooses
composition; the existing strict phrase-ID schema and all grounding/fallback checks
remain. No connector with new factual or causal meaning was added.

Kyler/Minnesota's canonical wire catalog is **2,481 bytes**, versus **2,764 bytes**
before polish (excluding instructions/schema). Multiple two-/four-point, player-/team-
first offline goldens pass. Extra-warning, partial-bundle, exact-direction, interrupted-
facts, prefixed-caveat and predictive-prose attack regressions are included.

The final live check requires separate completion after the offline fix commit:
exactly one Kyler/Minnesota question, one planner and one writer call, no retry or
repair, with the prior safe reset/pacing honored. No production activation is included.

Offline gate: **746 backend tests passed**, **66 frontend Ask tests passed**, with
zero failures/skips. TypeScript, ESLint, Prettier, Ruff, Python formatting (104 files),
compilation, production frontend build and `git diff --check` pass. Allen 2022,
Reid/Tomlin, Allen 2026, McCarthy and Rodgers goldens remain grounded and pass.
The live result is intentionally not asserted by this offline commit.

## Current connector-only polish

The subsequent single-question smoke passed planner/writer HTTP 200, parsing,
composition validation and grounding with unchanged backend authority. Product
quality still failed: two consecutive comparisons began with “Also,”. No additional
request or repair followed that failed check.

The renderer now has three backend-owned neutral surfaces per non-empty connector
class. It remembers the preceding two clauses across paragraph boundaries and
unprefixed clauses, choosing the first surface not used in that window. Selection
remains deterministic and within the provider-selected semantic class; continuation
is never changed into contrast or causation for variety. The `none` connector stays
empty. Facts, phrase IDs, scientific limitations, validation and word-budget checks
remain unchanged. Repetition is reduced without provider-authored transition text.

Private writer implementation identity is
`ask-v2-stage-d/groq-composition-writer-v2.2-responses-3.14`; the approved 120B model,
planner identity, schema, instructions and wire catalog do not change. Kyler's wire
catalog remains **2,481 bytes**. Regressions cover consecutive/near-adjacent repetition,
paragraph boundaries, mixed classes, neutral wording, deterministic output and the
exact last live deep/short/scramble connector pattern. The prior extra-warning,
predictive-prose, context and causal defenses remain in force.

The final authorized live check must occur only after this offline fix is committed
and provider reset requirements are satisfied: one planner and one writer for the
Kyler/Minnesota question, no retry/repair, with no production activation.

Offline gate: **757 backend tests passed**, including **66 composition tests**,
and **66 frontend Ask tests passed**, with zero failures/skips. TypeScript, ESLint,
Prettier, Ruff, Python formatting (104 files), compilation, production build and
`git diff --check` pass. All six product goldens remain grounded and pass; the final
live result is not asserted by this offline commit.
