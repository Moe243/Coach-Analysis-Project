# Ask Anything 2.1 — connected exploration

Ask presents a concise answer, optional permitted key numbers, up to four meaningful
Keep Exploring actions (exactly four when available), and a short natural limitation.
Internal evidence, permissions, uncertainty and versions remain in the API; they are
not public answer panels. Ask also suppresses the application version footer.
Key numbers use permitted single-measurement propositions, not internal coverage
counts or two-sided comparison values that could be mislabeled as a player's metric.
Comparison values remain in the approved prose with their correct player/team labels.

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

Follow-up buttons submit real turns with bounded canonical and season context. Only
user turns, not assistant prose, inform interpretation. A newly named unrelated entity
does not inherit an old question's season. Comparison replacements retain the active
anchor; `Why?` does not erase the previous substantive topic. Relative next/previous
seasons resolve only from a single historical season and only to another historical
season. They cannot reuse or extend the frozen projection into a new forecast.
An explicit short replacement can resolve a unique exact catalog surname; ambiguous
or unknown names require clarification rather than silently keeping the old pair.
Bounded-evidence diagnostics become natural public caveats, not raw status codes.
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

## Validation and product review

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
