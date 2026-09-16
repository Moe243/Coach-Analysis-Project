# Ask Anything 2.0 Release Candidate

Status: **LOCAL RELEASE CANDIDATE — NOT DEPLOYED**.

The frontend `/ask` route now renders Ask v2 and calls `POST /ask/v2`. The rollback route
`/ask/legacy` renders the unchanged v1 interface and still calls `POST /ask`. The temporary
`/ask/preview` URL redirects to `/ask`. Backend endpoints were not renamed or replaced.

## Product contract

Ask Anything is answer-first. Each successful exchange shows the direct football answer before
ranked public evidence, comparison or alignment context, material uncertainty, unsupported
portions, supported follow-ups, and expandable methodology and provenance. Backend answerability
and conclusion permissions remain authoritative. Grounded AI may organize approved evidence, but
it cannot introduce a calculation or scientific conclusion; deterministic mode uses the same
analytical authority.

The browser stores conversation state only in component memory. It constructs request context
from successful structured turns, never from assistant prose, and sends at most eight recent user
turns, 8,000 context characters, and eight canonical entity references. Visible older exchanges
may remain after the request context has been bounded. Refresh and **New conversation** clear the
session, and reset cancels an outstanding request.

Clarification candidates use canonical backend IDs in structured context while displaying human
names. Profile and Relationship Explorer links are constructed only from canonical entity IDs.
Null metrics render as unavailable, and rates become percentages only when the public unit says
they are rates. Backend text is rendered literally rather than interpreted as HTML or Markdown.

## Failure behavior

Every turn owns an immutable request snapshot and an abortable lifecycle. A newer submission
cancels an older pending request, preventing late responses from replacing current state.
Transient network, 429, 502, 503, and 504 failures retry within a fixed bound. A final failure
leaves earlier successful turns visible and offers a retry of the same question and context.
Provider failure is not exposed; the backend's deterministic fallback renders normally.

## Scientific capability boundary

- C12 exposes no causal or universal Coach Effect; PCAE remains observational and separate from
  QB PAE.
- C15 Player × Scheme fit remains not estimable/data-limited.
- C16 permits only the frozen 2026 team-independent EPA/dropback projection for approved players;
  forward PAE, touchdowns, yards, probability and coach-specific projections are unsupported.
- C17 destination-team numerical response is not supported. Comparable player/scheme usage may
  be described without forecasting improvement.
- C18 alternate-career simulation is not ready or implemented.
- C20 rookie/college projection remains not estimable/data-limited.

These decisions are backend-owned. Planner output, conversation context, provider synthesis and
frontend rendering cannot change answerability, conclusion permissions, evidence values or
checkpoint status.

## Runtime and rollback

Deterministic mode is complete and requires no OpenAI setting or credential. Optional grounded
presentation remains disabled unless every opt-in provider setting documented in
`ASK_V2_GROUNDED_PROVIDER.md` is valid; invalid or incomplete configuration falls back to the
deterministic response. No production provider has been enabled.

For product rollback, use `/ask/legacy`, which preserves the v1 UI and `POST /ask` contract. A
deployment rollback can revert the local route-migration commit without changing either backend
endpoint or rebuilding the frozen v1 snapshot.

## Validation

Run focused release-candidate tests with:

```bash
cd frontend
pnpm vitest run src/api/askV2.test.ts src/lib/askV2.test.ts \
  src/hooks/useAskV2Conversation.test.tsx src/pages/AskPreviewPage.test.tsx
pnpm playwright test e2e/ask-v2-preview.spec.ts
```

The browser suite uses deterministic typed public-response fixtures and does not require or call
OpenAI. It runs across the repository's desktop, tablet, and mobile projects. Ask v1 compatibility
remains covered separately at `/ask/legacy` by its existing unit and browser tests. This route
migration has not been pushed, merged or deployed.
