# Ask Anything 2.1 — connected exploration

Ask presents a concise answer, optional permitted key numbers, up to four meaningful
Keep Exploring actions (exactly four when available), and a short natural limitation.
Internal evidence, permissions, uncertainty and versions remain in the API; they are
not public answer panels. Ask also suppresses the application version footer.
Key numbers use permitted single-measurement propositions, not internal coverage
counts or two-sided comparison values that could be mislabeled as a player's metric.
Comparison values remain in the approved prose with their correct player/team labels.
If multiple team stints produce the same unqualified player-season metric, Key numbers
omits that metric rather than selecting one team's value or inventing an aggregate.

## Navigation and context

Actions come from a deterministic allowlist of existing routes and canonical resolved
entities, not free-form provider URLs. QB and coach journeys use `/network` with the
existing `qb_journey` and `coach_journey` modes. Team context uses `team_history`.
Multi-entity exploration uses bounded `full_network` with `anchor=all`, a selected
canonical node and at most eight `highlights`. The server remains authoritative for
the five-season, node and relationship limits. Historical destinations stay within
2010–2025 even when the answer discusses a 2026 projection. Entities are visible only
where their recorded history exists; navigation does not manufacture relationships.

Statistics uses its existing name-search `player` and optional `season` query fields.
It does not introduce a new exact-ID statistics API. Graph URLs retain canonical IDs.
Graph selection highlights the union of the selected entities' supported branches and
fits that context. Manual selection, focus and reset leave multi-selection mode.
Career Tree actions open the complete supported 2010–2025 history; season-specific
Statistics and relationship actions preserve the answer's relevant historical scope.
Player-plus-team exploration shows their separately observed histories, not a fabricated
destination-team stint. Independent team-season highlights retain that context on reload.

Follow-up buttons submit real turns with bounded canonical and season context. Only
user turns, not assistant prose, inform interpretation. A newly named unrelated entity
does not inherit an old question's season. Comparison replacements retain the active
anchor; `Why?` does not erase the previous substantive topic. Relative next/previous
seasons resolve only from a single historical season and only to another historical
season. They cannot reuse or extend the frozen projection into a new forecast.
An explicit short replacement can resolve a unique exact catalog surname; ambiguous
or unknown names require clarification rather than silently keeping the old pair.
Bounded-evidence diagnostics become natural public caveats, not raw status codes.
The conversation lives in application memory for this browser tab. Exploring a route
and returning with browser Back preserves it; reloading or New conversation clears it.
Follow-up buttons ignore immediate duplicate clicks. Generic filler is not added merely
to force four actions when fewer than four meaningful supported candidates exist.
The just-answered question is not offered again as a generated follow-up.
Without an explicit year, two-QB comparisons use their latest shared recorded
analysis season, so retired QBs are not silently scoped to an empty 2025 record.
Explicit years are preserved, including when a participant has no record that year.
This is a same-season measurement comparison, not an all-career quality winner.

QB coaching-history navigation retrieves verified cited assignments on the exact
team-season of each recorded QB stint. “Best seasons” means the three highest recorded
EPA/dropback QB-team-seasons per requested QB with at least 200 dropbacks, within
2010–2025; it is not an all-career or coach ranking. Missing records stay unavailable.
Same-team-season context is not exact weekly exposure or a development/causal effect.

## Future answer-writer design — not enabled

The existing strict `ProviderSynthesisInput` / selection-only proposal seam and backend
grounding validator remain unchanged. No free-form Groq answer writer is implemented
or activated in this change. A future provider-neutral writing brief would contain only
resolved public names, backend-permitted propositions, approved numbers/units/seasons,
mandatory caveats, unsupported portions and allowlisted action candidates. Private
tables, credentials, provenance, hidden reasoning and unapproved results are excluded.

The backend would keep evidence/permission mappings privately and validate every new
public number and concrete entity, mandatory caveats and unchanged answerability.
Causal upgrades, fit scores, destination forecasts, career simulations, forward PAE and
rookie forecasts remain prohibited. Failed writing validation must use deterministic
text. Providers may select/rank valid action IDs but never invent routes. A future Groq
writer may use the same `openai/gpt-oss-120b` model as the planner; this is a design
preference, not a production setting or a new approved scientific capability.

## Original implementation gate

Validation on 2026-09-16 used baseline
`07ec827ca04a16bb8bd0b2cec04767db9ad91f56` and a disposable local PostgreSQL/API
publication with external providers disabled. No production services were changed.

- Backend Ask/release, Stage A–D/F, provider-draft, Groq/OpenAI, telemetry and
  connected-context suites: 515 passed, zero failed or skipped.
- Frontend unit/component suites: 150 passed, zero failed or skipped.
- Playwright: 90 passed, zero failed or skipped across desktop, tablet and mobile;
  includes axe, responsive checks and real deterministic API golden flows.
- TypeScript, ESLint, Prettier, Ruff, Python formatting, compilation and diff checks
  passed. Two independent production builds were byte-identical.

Actual local Rodgers/McCarthy, Reid/Tomlin → Why → McVay, Allen 2022,
Kyler/Minnesota and Rodgers/Favre flows were reviewed. Real destination reload tests
cover QB Journey, Statistics, Team History and multi-entity Full Network.
Regression fixes prevent an unrelated inherited season, ambiguous counterpart reuse,
retired-player loss, public diagnostic leaks and mislabeled comparison numbers.
Routine browser color-environment and temporary build-directory warnings were benign.
The free-form answer writer remains a future design, not implemented or activated.

## Independent product review and corrective gate

The candidate starting at `65edc2a75001ccc6ff0c6b206a81d9e1f0dfe40b` was reviewed
against the actual frozen deterministic local application, not just fixture responses.
Desktop, tablet and mobile views and live local PostgreSQL-backed destinations were
checked with providers and external sharing disabled.

Corrective changes preserve conversation state across route navigation; resolve
historical `Who coached him?` and coach-information follow-ups; explain the verified
role basis of Reid/Tomlin comparisons; retain the complete supported QB Career Tree;
show both independently observed sides of player/team exploration; put the initial
mobile composer above examples; suppress raw API error details and ambiguous
multi-team Key numbers; and prevent immediate duplicate follow-up submission.
Coach exploration uses specific football questions and a bounded quarterback network
instead of a generic fourth filler action. Numerical comparisons keep their approved
values, readable units and explicit same-season (not career-ranking) scope.

The independent final gate consists of 522 backend Ask/release/provider regression
passes, 157 frontend unit/component passes and 90 browser passes across all three
viewports, with zero failures or skips in those final runs. Browser checks include axe,
keyboard operation, overflow, retry, frozen-backend golden answers, contextual turns,
deep-link reload and return navigation. TypeScript, ESLint, Prettier, Ruff, Python
formatting/compilation and diff checks pass. Two clean production builds are
byte-identical. No external-provider smoke was run or claimed.
Intermediate browser runs interrupted by local review-server restarts, active edits
or a Statistics search timing timeout were not counted as passes; the frozen final
run passed all 90 tests without retries or skips.

The Ask answer surface and its connected profile/Explorer destinations contain no
internal IDs or version panels. Provider metadata and raw scientific status codes do
not appear in Ask. Canonical identifiers and version lineage remain in API/URL state,
not public answer or relationship cards. Source links, assignment intervals,
verification/confidence and uncertainty remain visible. The legacy Ask route retains
its frozen research-oriented presentation. No analytical
model, scientific policy, database migration or production configuration changed.

Remaining limitations are deliberate: deterministic prose is structured; coverage
starts in 2010 (earlier Rodgers/Favre Green Bay history is not fabricated); coach
information is limited to available verified project records; and dense Full Network
views still benefit from zoom and the equivalent accessible relationship cards.
No provider answer writer, causal coaching winner or destination forecast is enabled.
