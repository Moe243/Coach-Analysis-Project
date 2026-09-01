# Checkpoint eight report

Date: 2026-08-31
Status: Relationship Explorer approved after final integrity review

## Outcome

Checkpoint eight now includes the responsive React/TypeScript product and the full Relationship Explorer. The earlier six interface corrections and API `v1.2` foundation remain intact. Phase 2 evolves `/network` into four bounded, URL-backed views—Coach Journey, QB Journey, Team History, and Full Network—without changing football metrics, PAE, coach-impact models, ranking suppression, database schemas, or serving publications.

The current analytical identities remain:

- Historical data version `c3-f6c1aa118ff43b90`
- Expected-performance data version `c5-8fd5d1aba2598c59`
- Expected-performance model `expected-performance-8fd5d1aba2598c59`
- Coach-impact data version `c6-400a5b474aa37a35`
- Coach-impact model `coach-impact-400a5b474aa37a35`
- API contract `api-v1.2`

Checkpoint Nine has not begun. No authentication, deployment, PFR ingestion, PFR scraper, fabricated data, or new analytical claim was added.

## Reused architecture

The implementation retains React Router, TanStack Query, the typed cancellation-aware API client, route-level lazy loading, dynamic Cytoscape loading, canonical profile links, existing status badges, shared loading/error/empty states, responsive page structure, selection class semantics, and non-causal interpretation language.

The frontend requests one authoritative `GET /relationships/explorer` response for the selected bounded scope. It does not rebuild relationship meaning from legacy staff edges and does not issue N+1 PAE requests. Coach and QB option lists reuse the existing paginated serving endpoints with infinite stale time.

## Relationship Explorer architecture

Canonical node grains are:

- Coach: one `coach_id`, node ID `coach:<coach_id>`
- Quarterback: one GSIS `player_id`, node ID `qb:<player_id>`
- Team-Season: one `(team_id, season)`, node ID `team-season:<team_id>:<season>`

Authoritative relationship grains are:

- Coach assignment: one source-backed `assignment_key` interval
- QB result: one `(player_id, team_id, season)`

The pure `buildRelationshipGraph` transformation deduplicates identical IDs defensively, applies truthful client display filters, produces Cytoscape elements, builds node-to-relationship indexes, and assigns explicit deterministic positions. It never recalculates PAE. Missing actual/expected/PAE values remain `null` and display as unavailable.

Coach-only role, interim, shared-duty, verification, and provisional controls affect coaching assignments. They do not remove independently sourced QB-team-season facts in Team History or team-anchored Full Network. QB qualification, minimum-dropback, and PAE-range controls affect QB facts only. Hiding an entity type is an explicit presentation choice.

## Four modes

### Coach Journey

One canonical coach is followed across the selected range. Assignment keys remain separate across teams, seasons, roles, and in-season intervals. Connected QB-team-season results show actual EPA/dropback, expected EPA/dropback, PAE, dropbacks, eligibility, reliability, and publication/model versions. The layout is chronological and never randomized.

### QB Journey

One canonical QB is followed across every returned team-season. Multi-team same-season results remain separate. PAE stays attached to the full `(load_id, player_id, team_id, season)` key. Connected coaching rows are described as team-season context unless the backend establishes stronger interval evidence; the UI never claims exact weekly QB-coach exposure.

### Team History

The selected team is displayed in chronological season lanes. Distinct assignment keys preserve head-coach, offensive-coordinator, play-caller, and QB-coach changes, including interval basis, weeks, interim, shared, retained, verification, confidence, provisional status, and citation availability. Authoritative QB facts remain visible when coach filters remove every assignment.

### Full Network

Full Network starts from a coach, QB, or team and uses the same bounded server contract. It is limited to five seasons, 1,000 nodes, and 2,000 relationships. Stable type columns replace randomized force positioning. A server HTTP 413 produces a complete error state with instructions to narrow scope; no partial graph or misleading completeness claim is rendered.

## URL, selection, and accessible interaction

Supported URL state includes mode, canonical coach/QB/team anchor, Full Network anchor type, start/end season, role set, evidence status, provisional setting, entity visibility, QB eligibility/dropback/PAE filters, interim/shared filters, selected node, and focused node. Reloading or copying a supported URL reconstructs the same meaningful explorer state.

Selecting a node highlights the selected entity, direct neighbors, and connecting edges while fading unrelated elements. The selection is reapplied when Cytoscape reconstructs and is cleared only if the node is no longer visible. Focus opens the selected canonical coach/QB journey or one-season Team History; Reset clears view filters and selection without widening the anchor; Back restores the preceding meaningful in-memory focus state.

The relationship list is an equivalent keyboard surface, not a fallback summary. Entity cards and relationship cards expose the same canonical IDs, assignment keys, roles, intervals, evidence/status fields, citation availability, QB metrics, PAE, eligibility, reliability, and version information. Select, Focus, Reset, and Back are available without Cytoscape or tooltips.

## Responsive and performance behavior

Desktop uses left-to-right chronological lanes. Tablet compresses controls and the graph/detail split without removing the semantic cards. Mobile transposes deterministic graph positions into top-to-bottom lanes, stacks controls and actions, moves detail context ahead of the constrained graph, and leaves the accessible relationship representation fully usable. Browser inspection confirmed no horizontal overflow at the tested desktop, tablet, and mobile viewports.

The graph transformer is memoized from the response, filter state, and compact breakpoint. Lookup queries are cached, Cytoscape remains in its own dynamic production chunk, equivalent rerenders receive stable positions, and client code does not bypass server caps or repeatedly fetch full history.

## Validation results

### Frontend

- 53/53 Vitest unit and component tests passed across eight files.
- 33/33 Playwright journeys passed across desktop, tablet, and mobile Chromium projects.
- TypeScript project checking passed.
- ESLint passed with zero warnings.
- Prettier verification passed.
- Production build passed.
- Two independent production builds were byte-identical.
- Final production assets: main JavaScript 292.18 kB (93.36 kB gzip), Relationship Explorer page 26.16 kB (7.87 kB gzip), lazy Cytoscape 443.04 kB (141.98 kB gzip), and CSS 26.27 kB (5.88 kB gzip).

Frontend regressions cover canonical coach/QB continuity across years and teams; multi-team same-season QB grain; complete-key PAE; missing PAE; year ranges; distinct in-season assignments and roles; interim/shared/verified/provisional states; independent QB preservation; duplicate defense; stable desktop/compact positions; selected/connected/faded graph classes; selection reconstruction and clearing; Focus/Reset/Back; URL restoration; accessible actions and metadata; keyboard behavior; HTTP 413 completeness; non-causal language; and existing Statistics/QB/coach behavior.

Playwright uses deterministic relationship responses for the four new explorer modes while retaining the real local publication for existing Statistics and profile journeys. This isolates frontend mode/layout behavior from the older long-running local API process; authoritative API `v1.2` behavior is separately exercised against a clean PostgreSQL publication below.

### Python, PostgreSQL, API, and network

- Offline Python discovery: 116 tests total; 74 passed and 42 intentionally skipped.
- The 42 offline skips were 40 separately callable PostgreSQL/API tests and two opt-in network tests. They are not reported as passes in the offline result.
- Disposable PostgreSQL/API behavior: 40/40 passed.
- Opt-in network integration: 2/2 passed, covering nflverse boundary assets and the coaching citation/content registry.
- Ruff lint passed.
- Ruff formatting verification passed for 55 Python files.
- Git whitespace/diff checks passed.

The PostgreSQL/API tests prove bounded/anchor validation, empty responses, genuine 1,001-node and 2,001-relationship HTTP 413 behavior, canonical coach/QB identity, independent QB scope under coach filters, complete-key multi-team PAE, assignment interval/evidence preservation, missing PAE, stable ordering, publication/version identity, and duplicate-free nodes and relationships. Existing migration, atomic load, rollback, manual-byte identity, exposure lineage, pagination, warm-up exclusion, and API-label tests also remain green.

## Files changed

- Backend/API foundation: `src/nfl_coaching_impact/api.py`, `src/nfl_coaching_impact/serving.py`
- PostgreSQL/API tests: `tests/test_checkpoint_seven.py`
- Frontend route and shell: `frontend/src/App.tsx`, `frontend/src/components/AppShell.tsx`, `frontend/src/pages/NetworkPage.tsx`, `frontend/src/pages/StatisticsPage.tsx`
- Graph behavior: `frontend/src/components/NetworkGraph.tsx`, `frontend/src/components/networkSelection.ts`, `frontend/src/lib/relationshipGraph.ts`
- Frontend contracts/styles: `frontend/src/api/contracts.ts`, `frontend/src/styles.css`
- Frontend fixtures/tests/E2E: `frontend/src/components/NetworkGraph.test.ts`, `frontend/src/lib/relationshipGraph.test.ts`, `frontend/src/pages/NetworkPage.test.tsx`, `frontend/src/pages/StatisticsPage.test.tsx`, `frontend/src/test/fixtures.ts`, `frontend/e2e/checkpoint-eight.spec.ts`
- Documentation: `README.md`, `frontend/README.md`, `docs/ARCHITECTURE.md`, `METHODOLOGY.md`, `DATA_DICTIONARY.md`, `LIMITATIONS.md`, and this report

## Known limitations

- A Coach–Team-Season–QB path establishes same-team-season context, not exact weekly overlap, mentorship, influence, or causation.
- Full Network is intentionally anchored, capped, and limited to five seasons; it is not a bulk export or an all-history force graph.
- Dense valid scopes may require narrower role/evidence/year filters. The UI does not show a partial graph after HTTP 413.
- Focus history is intentionally session-local. The focused and selected canonical IDs survive in the URL, but a copied URL does not fabricate an earlier Back stack.
- Cytoscape is visually constrained on small screens; the metadata-complete semantic explorer is the authoritative accessible equivalent.
- The application remains local and unauthenticated. Deployment, production reverse-proxy hardening, cross-browser device-lab coverage, and portfolio polish remain deferred.
- PFR remains `PERMISSION REQUIRED BEFORE INGESTION`. No direct PFR collection, scraper, production data, or automated ingestion was introduced.
- All prior public-data, expected-performance, coach-identification, suppression, and non-causal limitations continue to apply.

## Remaining checkpoint-eight defects

The final integrity review corrected two P2 findings before approval: a stale single-season graph description in `LIMITATIONS.md`, and an API mapping that could mix the QB-stat actual EPA value with a PAE artifact's expected/PAE pair if publication inputs drifted. Relationship responses now use the internally constrained PAE actual/expected/PAE triplet when PAE is available and retain the QB-stat actual only when PAE is unavailable. A behavioral PostgreSQL regression proves the displayed arithmetic remains coherent.

No known approval-blocking Checkpoint Eight defect remains after the completed test, integration, deterministic-build, and responsive QA passes.

## Exact next phase

Checkpoint Nine remains unstarted and requires separate explicit approval. PFR remains `PERMISSION REQUIRED BEFORE INGESTION`; no ingestion or automated collection is authorized.
