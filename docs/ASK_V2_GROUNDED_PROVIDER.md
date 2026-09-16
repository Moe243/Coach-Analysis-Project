# Ask v2 grounded-provider development contract

Stage D adds an optional interpretation and presentation layer around the deterministic Ask v2
engine. OpenAI and Groq are supported provider adapters, but neither is configured or enabled in
production. The deterministic backend remains the entity, evidence, calculation, answerability,
and scientific-policy authority.

The implementation uses the pinned OpenAI Python SDK and the Responses API with strict Pydantic
Structured Outputs. Groq uses that SDK through Groq's code-owned OpenAI-compatible endpoint,
`https://api.groq.com/openai/v1`; no Groq SDK or arbitrary endpoint setting is needed. Every
request sets `store=False`, disables background and streaming operation, supplies no tools, and
caps output tokens and timeouts. Application logic permits at most two provider calls: one planner
call and one synthesizer call. Ordinary tests use injected fakes and never require a credential or
network request.

## Provider selection and opt-in configuration

`ASK_V2_PROVIDER` accepts only `none`, `openai`, or `groq`; its default is `none`. An invalid value
fails closed. When the variable is present it has absolute precedence. When it is absent, the legacy
`ASK_V2_OPENAI_ENABLED` setting retains its existing behavior, avoiding a silent OpenAI deployment
regression. In every case `ASK_V2_EXTERNAL_SHARING_ENABLED=true` is independently required.

Groq additionally requires:

- `GROQ_API_KEY=<server-side secret>`
- `ASK_V2_GROQ_PLANNER_MODEL=openai/gpt-oss-120b`
- `ASK_V2_GROQ_SYNTHESIZER_MODEL=openai/gpt-oss-20b`

Both configured Groq models must be one of the explicitly supported GPT-OSS strict-Structured-
Output models. The planner and synthesizer use `low` reasoning effort. These roles interpret and
organize already bounded information; they do not perform football modeling. Free-tier availability
and limits are controlled by Groq and may change. A quota or rate-limit failure never removes the
deterministic product.

OpenAI's legacy opt-in settings remain:

- `ASK_V2_OPENAI_ENABLED=true`
- `OPENAI_API_KEY=<server-side secret>`
- `ASK_V2_PLANNER_MODEL=<explicit model ID>`
- `ASK_V2_SYNTHESIZER_MODEL=<explicit model ID>`

Optional bounded controls are `ASK_V2_PLANNER_TIMEOUT_SECONDS` (default 12, maximum 20),
`ASK_V2_SYNTHESIZER_TIMEOUT_SECONDS` (default 18, maximum 20),
`ASK_V2_TOTAL_TIMEOUT_SECONDS` (default 30, maximum 40),
`ASK_V2_PLANNER_MAX_OUTPUT_TOKENS` (default 600, range 128–1,000), and
`ASK_V2_SYNTHESIZER_MAX_OUTPUT_TOKENS` (default 800, range 128–1,500). The two per-call timeouts
must fit within the total deadline. A key alone never enables sharing, and model IDs are never
selected implicitly. Invalid or incomplete configuration uses deterministic mode.
Provider calls also pass through a four-slot non-blocking server concurrency gate; saturation
falls back immediately instead of turning the API into an unbounded paid-model proxy.

Secrets stay in server environment variables and never use a `VITE_` name. The API never returns
the key, provider error body,
private timeout settings, organization/project identifiers, or provider headers. Deployment,
provider billing, rate-limit policy, and production credentials remain unconfigured.

## External-data boundary

The planner receives only the current question, bounded prior **user** questions, canonical IDs
already present in client context, optional bounded season context, and the closed question/task
vocabulary. It receives no statistics, evidence bundle, snapshot, source URL, file path, database
connection, credential, or prior assistant prose.

The synthesizer receives a compact package of backend-resolved entities, backend-owned
answerability, approved propositions, the evidence values referenced by those propositions,
uncertainty, conclusion permissions, required limitations, unsupported portions, and offered
follow-ups. Source URLs, citations, hashes, raw tables, paths, credentials, and the frozen snapshot
never leave the server. The canonical provider payload cannot exceed 48 KiB.

## Grounding and fallback

Planner output is untrusted. The backend validates its strict schema, re-resolves every mention,
rejects entities absent from the user's bounded context, enforces the requested season, authorizes
each allowlisted task, retrieves evidence itself, and applies the frozen C12/C15/C16/C17/C18/C20
policies.

The synthesizer cannot author prose or numbers. It can select and order backend-generated
proposition IDs, evidence IDs, limitations, unsupported portions, and follow-ups. The server renders
the final words and numeric formatting. Post-synthesis validation rejects unknown or mismatched
references, denied permissions, omitted limitations, omitted unsupported portions, invented
follow-ups, or any extra field that could carry a new fact or conclusion.

Configuration disablement, invalid credentials, unavailable models, provider errors, timeouts,
HTTP 429 rate limits, refusals, malformed output,
oversized payloads, or grounding rejection return the complete deterministic Stage C response.
Invalid provider text is never mixed into that fallback. Public `answer_mode` is `grounded_ai` only
after both provider outputs pass validation; otherwise it is `deterministic`.

Response metadata keeps the Ask contract, evidence reducer, deterministic planner, analytical data
and analytical-model versions separate from the external planner/synthesizer implementation and
configured model identifiers. A provider model identifier is never presented as an analytical
football-model version.

Operational logs contain categories and bounded counts/latency only. They do not contain API keys,
prompts, transcripts, evidence payloads, source material, environment dumps, or raw provider
errors.

## Groq protocol contract

The Groq adapters use the Responses endpoint with Pydantic schemas converted by the OpenAI SDK to
strict JSON Schema. All object fields are required by the existing contracts and objects reject
additional properties. The two selected GPT-OSS models support strict Structured Outputs. Requests
explicitly provide an empty tool list and `tool_choice="none"`; browser search, code execution,
function calling, file search, and MCP are never enabled. Planner output still passes backend entity
resolution and task authorization. Synthesizer output still passes the same proposition, evidence,
number, permission, limitation, and unsupported-output checks as OpenAI output.

No live Groq smoke runs in normal tests or CI. A real-key smoke requires a separately authorized,
explicit manual step. Production remains deterministic until a later deployment review approves
provider configuration.

Current protocol decisions were checked against Groq's official documentation for the
[OpenAI-compatible API](https://console.groq.com/docs/openai),
[Responses API](https://console.groq.com/docs/responses-api),
[Structured Outputs](https://console.groq.com/docs/structured-outputs),
[reasoning controls](https://console.groq.com/docs/reasoning), and
[rate limits](https://console.groq.com/docs/rate-limits). Provider capabilities and limits remain
external service behavior and must be revalidated before production enablement.
