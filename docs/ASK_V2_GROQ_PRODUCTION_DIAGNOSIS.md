# Groq production fallback diagnosis — 2026-09-16

## Finding and safe state

**Root cause: UNRESOLVED.** The historical production logs cannot establish whether
the provider was eligible, initialized, attempted, rejected remotely, or rejected by
the backend. Do not reactivate sharing to infer the missing evidence.

Read-only Render inspection confirmed current live deployment
`dep-dalbr8uk1f9s73fmero0`, source
`cb4ab4279badca8b4f227a9ea4d8155342fe7238`. `/health` returned HTTP 200 and
`/ask/v2` returned deterministic mode with null planner and synthesizer model metadata.
Saved configuration was inspected without accessing the credential value:

| Setting | Saved state |
| --- | --- |
| ASK_V2_PROVIDER | groq |
| ASK_V2_EXTERNAL_SHARING_ENABLED | false |
| ASK_V2_GROQ_PLANNER_MODEL | openai/gpt-oss-120b |
| ASK_V2_PLANNER_TIMEOUT_SECONDS | 12 |
| ASK_V2_TOTAL_TIMEOUT_SECONDS | 30 |
| ASK_V2_PLANNER_MAX_OUTPUT_TOKENS | 600 |
| GROQ_API_KEY | Configured, masked; runtime presence/nonblank unverified |

A masked environment row is not proof that the running process received a valid,
nonblank credential. No key was revealed, hashed, transmitted, or copied. No Groq
call was made in this diagnosis. Render configuration, deployments, frontend, and
Neon were not changed. Explicit Groq selection prevents the legacy OpenAI path.

## Activation history and local comparison

Render confirms trial deployment `dep-dalbnle7bikc73fnsqvg` succeeded, was triggered
by an environment update, and used the same approved SHA. Its visible log window
includes all four smoke POSTs at 10:56:29–10:56:31 AM CDT. There is no per-process
environment snapshot, provider status, or provider exception/category in those logs.
The earlier save operation recorded sharing true, but this is not historical runtime
readiness proof. Do not treat current saved settings as a historical environment dump.

The approved successful local smoke used the same source revision, provider, planner
model, and sharing true. Current production differs deliberately: sharing false.
Historical production key validity, inherited process settings, and effective call
configuration were not recorded; equivalence to local cannot be asserted. The local
SDK is 3.14.0 and the release lock pins that version, but the logs inspected do not
independently identify the historical runtime's installed SDK. Local/Render host and
network environments differ. None of these differences establishes the failure cause.

## Exact readiness and parsing

`ProviderConfiguration.from_environment()` trims and lowercases the provider selector.
Explicit `none`, `openai`, or `groq` overrides legacy OpenAI settings; invalid/blank
explicit selectors fail closed. If absent, legacy `ASK_V2_OPENAI_ENABLED` applies.
Sharing is trimmed/lowercased: true/1/yes/on enable; false/0/no/off/blank/absent
disable; unrecognized values invalidate configuration.

| Groq prerequisites | Configuration ready | SDK invocation |
| --- | --- | --- |
| Valid Groq selector, sharing true, valid key/model/numerics | yes | If client initializes and concurrency/payload checks pass |
| Sharing false, blank, or absent | no | never |
| Missing/invalid key | no | never |
| Missing/unsupported planner model | no | never |
| Invalid numeric controls or planner timeout greater than total | no | never |
| No synthesizer model or invalid unused synthesis controls | unaffected | Planner-only remains eligible |
| Eligible config but client import/construction fails | yes, runtime no | never |
| Runtime eligible but four-slot gate saturated | yes | never |

Key validation requires `gsk_` followed by at least 16 permitted alphanumeric/underscore/
hyphen characters. This checks shape, not authentication. Planner model allowlist:
`openai/gpt-oss-120b`, `openai/gpt-oss-20b`. Planner timeout range 1–20s, total 1–40s,
planner output 128–1,000 tokens; defaults 12/30/600. **A Groq synthesizer is not
required**, in either configuration readiness or runtime readiness.

## Offline request compatibility audit

An actual pinned OpenAI SDK client with `httpx.MockTransport` captured the outgoing
JSON without network or real credentials. It made one mocked POST to
`https://api.groq.com/openai/v1/responses`. Production and successful local adapter
construction use this same source path; historical server-side acceptance is unknown.

| Wire field | Audit |
| --- | --- |
| model / instructions / input | Documented Responses fields; configured GPT-OSS planner |
| text.format | SDK converts Pydantic to json_schema, strict true, named ProviderPlanDraft |
| reasoning | effort medium; documented Responses object, not a flat chat parameter |
| max_output_tokens | 600, documented; includes reasoning and visible output |
| stream | false; no streaming |
| tools / tool_choice | [] / none; tool invocation disabled, none documented |
| parallel_tool_calls | false, documented |
| background | false is sent; not listed in the current request reference, acceptance unproven |
| store | false is sent, NOT omitted by the SDK; documentation conflicts |

`previous_response_id`, `truncation`, `include`, `safety_identifier`, `prompt_cache_key`,
and reusable `prompt` are absent. `timeout` is a client control, not a JSON field.
`text_format` is converted to the wire schema, not sent under that Python argument name.
All schema objects require every property and set `additionalProperties:false`; the
schema uses definitions/references, enums, arrays, bounded strings/arrays, and ordinary
object primitives. The existing realistic mocked response parses successfully. Actual
model/schema acceptance during the failed trial is not observable.

The [Responses overview](https://console.groq.com/docs/responses-api) lists `store`
as unsupported. The [API reference](https://console.groq.com/docs/api-reference)
explicitly accepts false/null. This explains why the overview alone does not prove
that `store:false` causes HTTP 400. Successful prior local requests used the same
construction; the offline capture disproves the hypothesis that the SDK silently
omitted it. Do not invent a definitive explanation for differing remote behavior.
The [Structured Outputs guide](https://console.groq.com/docs/structured-outputs)
supports GPT-OSS strict schemas and excludes streaming/tool use; none is requested.
Do not equate an empty tools list with executing tools.

## Smoke traces and candidate causes

All four saved failed-trial response objects are **exactly JSON-equivalent** to their
saved provider-disabled baselines, including versions and metadata. This is an object
comparison, not a claim about HTTP transport byte encoding. Local diagnosis reused
those baselines rather than repeating production queries with sharing enabled.

Reid/Tomlin's deterministic analysis cannot authorize the surname-only coach lookup,
so it asks for a more specific entity and returns no coaches. The orchestrator builds
this fallback first. Every readiness, initialization, transport, parsing, translation,
authorization, or deadline failure can return that exact object. Thus this response
does not distinguish “no draft” from “rejected draft.” The successful local planner
draft could use backend-only unique-surname normalization; no equivalent production
draft is available for inspection.

The Kyler/Minnesota descriptive answer, Allen 2026 team-independent C16 projection,
and Mahomes/Chicago refusal also came back as their complete baseline objects. Useful
deterministic content is not evidence of successful Groq planning. None has a causal,
Coach Effect, destination forecast, or forward-PAE upgrade.

| Candidate cause | Classification / evidence |
| --- | --- |
| Provider never ready/called | POSSIBLE; readiness/init paths were silent |
| Missing/invalid runtime key | POSSIBLE; masked configured row is not runtime/auth proof |
| Bad selector/sharing parsing | RULED OUT for inspected saved strings; historical runtime unverified |
| Missing runtime planner model | POSSIBLE historically; correct model saved now |
| Accidental synthesizer requirement | RULED OUT; source and offline regression prove planner-only readiness |
| Invalid credentials / 401 | POSSIBLE; no upstream status recorded |
| Model permission/access / 403 | POSSIBLE; no access evidence |
| Incompatible request / 400 | POSSIBLE; store docs conflict and background acceptance unproven |
| Rate limit / 429 | POSSIBLE; no upstream status recorded |
| DNS/TLS/connection/5xx | POSSIBLE; no transport exception recorded |
| Provider timeout | POSSIBLE; ordinary 12-second expiry is not supported by the sub-3-second timings |
| Structured parse failure | POSSIBLE; offline strict schema/SDK parsing works, live result absent |
| Semantic draft rejection | POSSIBLE; failure returns exact same fallback |
| Entity/task translation rejection | POSSIBLE; failure returns exact same fallback |

The 2.57/0.50/0.40/0.39s latencies are compatible with an immediate remote error or
local rejection as well as config fallback plus cold initialization. They are clues,
not proof of network attempts. No root-cause candidate is CONFIRMED or LIKELY on the
available evidence. Root-path HEAD/GET 404s in startup logs are not Groq HTTP 404s.

## Safe observability patch — isolated review only

Old orchestration emits application-logger INFO events, but default Uvicorn setup
does not enable application/root INFO and its standard message formatter does not
serialize `extra` fields. Readiness and initialization failures returned without any
event. Provider exceptions also collapsed 400/401/403/5xx into provider_unavailable;
attempted was incorrectly hard-coded true even before the SDK/concurrency gate.

The patch adds a dedicated non-propagating INFO logger with compact JSON to stderr.
It does not alter root/SDK logging or the public health/Ask contracts. Runtime creation
records selected provider, sharing, key-present boolean, configured-model boolean,
configuration validity/readiness and runtime readiness. No startup/application hooks
or production configuration changes are required; events occur on request handling.

Invocation-start/completion events record closed phase/component, attempted, success,
coarse category, validated numeric HTTP status/family, bounded model identity, and
SDK-call elapsed milliseconds. `attempted=true` means SDK provider invocation began,
not proof that an HTTP packet reached Groq. Saturation, payload failure and readiness
fallback record false. Translation and authorization phases distinguish backend
rejection from request/parse failures. OpenAI planner and synthesizer have separate
attempts and timers. No question, prior question, prompt, draft, evidence, ID, key,
header, raw exception, body, or arbitrary extra field is accepted by the emitter.

Validation: 266 passed, zero failed/skipped, across telemetry (33), Groq (50), draft
(49), OpenAI Stage D (71), and adversarial/fallback Stage F (63) tests. Includes
actual SDK offline wire capture, invalid status/model redaction, safe initialization
failure, saturated/disabled non-attempts, semantic/parse separation, deterministic
fallback equality, and a subprocess with production Uvicorn/root WARNING logging.
Ruff, formatting (five files), Python compilation, diff and scoped secret checks passed.

**Next action:** review the isolated safe telemetry patch while keeping sharing false.
No provider reactivation, deployment, configuration correction, or live synthetic
Groq diagnostic is authorized by this diagnosis.
