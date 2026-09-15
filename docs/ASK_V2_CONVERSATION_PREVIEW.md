# Ask Anything 2.0 Conversation Preview

Status: **PREVIEW ONLY**. The existing `/ask` route remains Ask v1. The additive
`/ask/preview` route uses `POST /ask/v2`; no production route migration has occurred.

## Product contract

The preview is answer-first. Each successful exchange shows the direct football answer before
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

## Validation

Run focused preview tests with:

```bash
cd frontend
pnpm vitest run src/api/askV2.test.ts src/lib/askV2.test.ts \
  src/hooks/useAskV2Conversation.test.tsx src/pages/AskPreviewPage.test.tsx
pnpm playwright test e2e/ask-v2-preview.spec.ts
```

The browser suite uses deterministic typed public-response fixtures and does not require or call
OpenAI. It runs across the repository's desktop, tablet, and mobile projects. Ask v1 compatibility
remains covered separately by its existing unit and browser tests.
