# Checkpoint Eleven-B report

Date: 2026-09-04
Status: independent adversarial review completed locally; uncommitted; not pushed or deployed

## Scope and evidence standard

Checkpoint Eleven-B audits all 512 team-season cells for head coach, offensive coordinator (OC),
quarterbacks coach (QB coach), and offensive play caller from 2010 through 2025. The coverage
contract distinguishes a verified person from a verified absence of a separately designated formal
role. It also preserves partial, provisional, conflicting, and unresolved states rather than
inventing a person.

A formal staff title is not play-caller evidence. Verified play-caller intervals require source
text establishing play-calling responsibility and defensible weekly boundaries. A
`season_designation` may resolve the person for the coverage matrix, but it is excluded from PCAE
attribution unless its weekly interval is independently bounded. Shared intervals remain shared.

The research overlay does not promote frozen serving assignments or change the deployed database,
API, frontend, PAE/PCAE formulas, Coach Effect logic, rankings, or deployment.

## Recalculated starting and final coverage

The dirty worktree at the start of the adversarial pass recalculated to: 512 HC verified-person
cells; 488 OC verified-person and 24 missing cells; 495 QB-coach verified-person, three partial,
and 14 missing cells; and 133 play-caller verified-person, seven partial, 96 provisional, and 276
manual-review cells.

Final evidence-state coverage is:

| Role | Verified person | Verified no separate role | Partial | Provisional | Unresolved | Total |
|---|---:|---:|---:|---:|---:|---:|
| Head coach | 512 | 0 | 0 | 0 | 0 | 512 |
| Offensive coordinator | 488 | 24 | 0 | 0 | 0 | 512 |
| Quarterbacks coach | 496 | 16 | 0 | 0 | 0 | 512 |
| Play caller | 119 | 0 | 1 | 125 | 267 | 512 |

No OC or QB-coach cell remains unresolved in the research coverage matrix. This does not mutate
the frozen serving layer: the production manual queue still contains its prior season-interval
reviews until a later authorized publication step.

## Corrections from the independent review

False-positive QB-coach assignments were removed for assistant-only titles: Todd Downing
(DET 2010 and 2011), Zac Taylor (MIA 2012), Corey Matthaei (KC 2016 and 2017), Marcus Brady
(IND 2018), and Zac Robinson (LA 2021). Each cell is now represented by source-backed
`verified_no_designated_role` evidence; an assistant-quarterbacks title is not promoted to the
primary quarterbacks-coach role.

False-negative QB-coach assignments were corrected for Al Saunders (LV 2011), Nathaniel Hackett
(BUF 2013), Norv Turner (CLE 2013), and Brian Schottenheimer (JAX 2021). The Jacksonville source is
the official team position-group page, which identifies Schottenheimer as the quarterback position
coach.

The three formerly partial QB-coach cells now preserve mixed evidence without inventing a
successor: Nathaniel Hackett JAX Weeks 1–8 plus verified no separate role Weeks 9–17 (2016); Bill
Lazor CIN Weeks 1–2 plus no separate role Weeks 3–17 (2017); and Byron Leftwich ARI Weeks 1–7 plus
no separate role Weeks 8–17 (2018).

All 24 former OC gaps were converted to `verified_no_designated_role`, not to a guessed person:
ARI/NE 2010; CLE/DAL 2011; HOU 2014; CLE 2016; CLE/HOU/SF 2017; HOU/LA/SF 2018;
ARI/LA/SF 2019; ARI/PHI/SF 2020; ARI 2021; ARI/NE/SF 2022; SF 2023; and SF 2024.

The play-caller audit found 15 previously missed full cells: ARI, BAL, DAL, LV (2010); BAL, DAL,
LV (2011); BAL, DAL, TEN (2012); MIA (2015); and BAL, BUF, JAX, MIN (2016). Sixteen new verified
interval rows express those cells because several contain in-season changes.

The same audit found a material false-positive interval assumption in 2017. ESPN's all-team audit
was published after Week 10 and does not prove Weeks 11–17. Twenty-nine team-seasons now retain
verified evidence only through Week 10 and provisional continuation thereafter. CIN, DEN, and KC
remain fully verified because independent team/league sources bound their changes. NYG is Ben
McAdoo Weeks 1–5, Mike Sullivan Weeks 6–10, and provisional Sullivan Weeks 11–17.

## Play-caller interval audit

The four specifically challenged 2018 changes pass with no gaps or overlaps:

- ARI: Mike McCoy Weeks 1–7; Byron Leftwich Weeks 8–17.
- CLE: Todd Haley Weeks 1–8; Freddie Kitchens Weeks 9–17.
- JAX: Nathaniel Hackett Weeks 1–12; Scott Milanovich Weeks 13–17.
- MIN: John DeFilippo Weeks 1–14; Kevin Stefanski Weeks 15–17.

Other corrected boundaries include BAL 2012 (Cam Cameron 1–14; interim-basis Jim Caldwell 15–17),
TEN 2012 (Chris Palmer 1–12; Dowell Loggains 13–17), MIA 2015 (Bill Lazor 1–12; Zac Taylor
13–17), and the four 2016 changes listed above.

Houston 2020 is unchanged: Tim Kelly is verified Weeks 1–3; Kelly and Bill O'Brien are both shared
in Week 4; Kelly Weeks 5–17 remains provisional. The 62 eligible Week 4 plays are classified
`shared_or_ambiguous_interval` and none is attributed to an individual caller.

## Formal-role and source audit

Relative to `7f0f8d5`, the current overlay adds 216 formal-title rows: 99 OC and 117 QB coach.
Source-family distribution is 182 official-team pages, 20 official-book mirrors, five official
league pages, four official-team media guides, two official releases, two media-guide mirrors, and
one official biography. No purportedly independent triangulation is claimed from derivative copies.

A deterministic 32-row newly verified OC sample and a separate 32-row newly verified QB-coach
sample were checked across every season and source family represented in the samples. Both passed
identity, title, team-season, interval, and source-content review after the assistant-title
corrections above. All 54 detected compound-title rows were audited: explicit combined primary-role
titles expand to each stated role; assistant-quarterbacks titles do not.

All 133 play-caller cells that were verified at the start were rechecked. The 2017 overreach was
downgraded as described above. The formal 2018 four-team sample, transition-year samples, and
2023–2025 samples passed. A simple web search was also performed for every non-fully-verified
play-caller cell; only evidence meeting the explicit-duty and interval standard was promoted.

Canonical identity checks found 299 unique coach IDs, 299 unique normalized names, no assignment-key
duplicates, and no coach ID mapped to conflicting canonical names.

## Final play-caller coverage by season

| Season | Verified | Partial | Provisional | Unresolved |
|---:|---:|---:|---:|---:|
| 2010 | 4 | 0 | 0 | 28 |
| 2011 | 3 | 0 | 0 | 29 |
| 2012 | 3 | 0 | 0 | 29 |
| 2013 | 1 | 0 | 0 | 31 |
| 2014 | 0 | 0 | 0 | 32 |
| 2015 | 1 | 1 | 0 | 30 |
| 2016 | 4 | 0 | 0 | 28 |
| 2017 | 3 | 0 | 29 | 0 |
| 2018 | 4 | 0 | 0 | 28 |
| 2019 | 0 | 0 | 0 | 32 |
| 2020 | 0 | 0 | 32 | 0 |
| 2021 | 0 | 0 | 32 | 0 |
| 2022 | 0 | 0 | 32 | 0 |
| 2023 | 32 | 0 | 0 | 0 |
| 2024 | 32 | 0 | 0 | 0 |
| 2025 | 32 | 0 | 0 | 0 |

The unresolved set is 267 cells: 28 in 2010; 29 each in 2011 and 2012; 31 in 2013; 32 each in
2014 and 2019; 30 in 2015; and 28 each in 2016 and 2018. The single partial cell is Indianapolis
2015. Provisional cells are the 29 post-Week-10 2017 continuations and all 96 cells in 2020–2022.

## Historical PCAE attribution

The PCAE method is unchanged. Models train on strictly prior seasons, and attribution requires one
verified, explicit, non-shared, weekly-bounded play-caller interval. Representative play traces
for 2012, 2013, 2015, 2016, 2017, 2018, 2020, and 2023–2025 all joined to the expected
`assignment_key`, team, season, and week. No offensive coordinator row entered as a substitute.

| Season | Eligible | Attributed | Shared/ambiguous | Unattributed | Rate |
|---:|---:|---:|---:|---:|---:|
| 2010 | 31,894 | 1,000 | 0 | 30,894 | 3.135% |
| 2011 | 32,150 | 1,016 | 0 | 31,134 | 3.160% |
| 2012 | 32,437 | 1,978 | 0 | 30,459 | 6.098% |
| 2013 | 32,850 | 946 | 0 | 31,904 | 2.880% |
| 2014 | 32,325 | 0 | 0 | 32,325 | 0.000% |
| 2015 | 32,503 | 1,470 | 0 | 31,033 | 4.523% |
| 2016 | 32,291 | 4,101 | 0 | 28,190 | 12.700% |
| 2017 | 31,987 | 19,606 | 0 | 12,381 | 61.294% |
| 2018 | 31,751 | 3,889 | 0 | 27,862 | 12.248% |
| 2019 | 32,046 | 0 | 0 | 32,046 | 0.000% |
| 2020 | 32,444 | 160 | 62 | 32,284 | 0.493% |
| 2021 | 33,986 | 0 | 0 | 33,986 | 0.000% |
| 2022 | 33,652 | 0 | 0 | 33,652 | 0.000% |
| 2023 | 33,836 | 33,836 | 0 | 0 | 100.000% |
| 2024 | 33,335 | 33,335 | 0 | 0 | 100.000% |
| 2025 | 32,813 | 32,813 | 0 | 0 | 100.000% |

The artifact contains 173 PCAE interval rows. Its readiness table has 171 coach-season
observations, 93 unique verified callers, 48 repeat callers, 56 consecutive-season pairs, 91
multi-QB callers, 28 multi-team callers, and 30 team-switch observations. These are readiness
diagnostics, not Coach Effect estimates or rankings.

## Reproducibility, validation, and release boundary

Research data version: `c11b-bbf7d43d0e4c4c05`. All mutable manual CSVs, historical PBP assets,
the PAE artifact, dependency versions, and relevant source-code hashes participate in the identity.
Independent empty-directory builds compare the version and every emitted byte.

Final validation passed: 174 offline tests passed with 46 intentional environment-dependent skips;
both opt-in network tests passed; and the complete source validator passed all registered books,
84 assignment-source URLs, 159 Eleven-B evidence URLs, 25 no-role evidence URLs, content-check
contracts, and nonblank overlay/no-role source terms. Ruff lint, Ruff formatting, deterministic
clean-rebuild tests, and `git diff --check` also passed. Generated research outputs remain ignored.

OC and QB-coach research coverage is complete only because verified no-separate-role is an explicit
outcome; it is not a person assignment. Play-caller coverage remains materially incomplete. The
production Coach Effect gate remains closed, the Coach Effect equation remains open, and no effect,
weight, score, or ranking was estimated. Nothing in this worktree has been committed, pushed,
deployed, or written to Neon.
