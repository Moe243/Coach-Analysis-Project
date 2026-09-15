# Ask v2 grounded-provider development contract

Stage D adds an optional interpretation and presentation layer around the deterministic Ask v2
engine. It is development-only and is not configured or enabled in production. The deterministic
backend remains the entity, evidence, calculation, answerability, and scientific-policy authority.

The implementation uses the official OpenAI Python SDK `3.14.0` and the Responses API with strict
Pydantic Structured Outputs. Every request sets `store=False`, disables background and streaming
operation, supplies no tools, and caps output tokens and timeouts. Application logic permits at
most two provider calls: one planner call and one synthesizer call. Ordinary tests use injected
fakes and never require a credential or network request.

## Opt-in configuration

All five required settings must be present and valid before either provider is called:

- `ASK_V2_OPENAI_ENABLED=true`
- `ASK_V2_EXTERNAL_SHARING_ENABLED=true`
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

Secrets stay in server environment variables. The API never returns the key, provider error body,
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

Configuration disablement, provider errors, timeouts, rate limits, refusals, malformed output,
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
