# Offensive Scheme Feature Dictionary

Status: Prompt 8 research-only foundation
Research version: `c12-data-250e540b7de79385`
Observed grain: one `team_id`–`season`
Analysis seasons: 2010–2025

This dictionary defines observed team offensive behavior. It does not assign equal ownership to
the head coach, offensive coordinator, quarterbacks coach, or play caller. Coach associations
preserve the source-backed assignment interval, but most fingerprints remain full team-season
context rather than exact weekly behavior.

## Source and missingness contract

- nflverse play-by-play provides structured run/pass choices, shotgun, no-huddle, `xpass`,
  `pass_oe`, air yards, pass location, scramble, situation, EPA, and success fields for 2010–2025.
- nflverse participation provides structured `offense_personnel` and `offense_formation` for
  2016–2025. The encoded personnel field is parsed; play-description text is never parsed.
- nflverse FTN charting provides explicit motion, play action, RPO, screen, and QB-location fields
  for 2022–2025.
- Values before a source's first season remain null. No historical personnel, formation, motion,
  play-action, RPO, or screen values are backfilled.
- Raw counts/rates and within-season z-scores are both retained. Z-scores are retrospective era
  controls, not as-of predictive features.
- The authoritative row-level definitions, hashes, denominators, and missingness are in
  `scheme_feature_availability.csv` and `team_season_scheme_fingerprints.csv` under the ignored
  Prompt 8 output.

## Personnel

The first digit is the count of running backs and fullbacks; the second is the tight-end count.
Fullbacks therefore count as backs. The parser accepts only structured offensive position tokens,
rejects defensive/special-teams or unknown-position contamination, and requires a plausible total
of at most five RB/FB/TE/WR skill players. It does not infer formations.

Observed groups are `00`, `01`, `02`, `03`, `04`, `10`, `11`, `12`, `13`, `14`, `20`, `21`,
`22`, `23`, `30`, `31`, `32`, `40`, and `41`. All remain `DESCRIPTIVE`: rare groups keep their
zero-inclusive team-season rates and raw denominators, but no exact grouping is promoted into a
future model by Prompt 8.

Personnel families are overlapping descriptive summaries:

| Feature | Explicit definition |
|---|---|
| `personnel_family_11_rate` | exactly one back and one tight end |
| `personnel_family_multiple_te_rate` | at least two tight ends |
| `personnel_family_multiple_back_rate` | at least two RB/FB players |
| `personnel_family_spread_rate` | at most one back, at most one tight end, and at least three WRs |
| `personnel_family_heavy_rate` | at least two backs or at least two tight ends |
| `personnel_family_empty_backfield_rate` | zero backs in the structured personnel grouping |

These families overlap intentionally; they are not exhaustive mutually exclusive buckets.

## Formation and alignment

| Feature family | Definition | Coverage/status |
|---|---|---|
| PBP shotgun | explicit `shotgun = 1` among eligible run/pass plays | 2010–2025, `CORE` |
| Participation formation | exact source values: Shotgun, Under Center, Pistol, Empty, Singleback, I Form, Jumbo, Wildcat | 2016–2025, `DESCRIPTIVE` |
| FTN QB location | exact `S`, `U`, or `P` codes | 2022–2025, `EXPERIMENTAL` |

Under center is never computed as “not shotgun.” Pistol and empty are never inferred from
personnel or pass tendency.

## Pre-snap and mechanics

Motion, play action, RPO, and screen rates use only explicit FTN flags. All are `EXPERIMENTAL`
because the approved structured history is 2022–2025. No play text or air-yard proxy is used.
No-huddle rate uses the explicit PBP flag for 2010–2025 and is `CORE`.

## Pass/run tendency

- `pass_rate`: pass plays divided by eligible run/pass scrimmage plays, excluding two-point tries
  and kneels.
- `expected_pass_rate`: mean nflverse `xpass` on available eligible plays. This is a retrospective
  source field and is not reused as a purported preseason feature.
- `proe_mean`: mean nflverse `pass_oe` on available eligible plays.
- `early_down_pass_rate`: pass rate on first and second down.
- `neutral_pass_rate`: pass rate on first/second down with score differential from -7 through +7
  and more than 120 seconds remaining.

The neutral definition was chosen before portability results were inspected. Prompt 8 performs no
predictive standardization or final model fitting.

## QB usage and pass style

- Target depth: short is at most 9 air yards, intermediate is 10–19, and deep is 20 or more.
- Air-yards summaries retain mean, median, and 90th percentile.
- Pass-location rates use explicit left, middle, and right source categories.
- Scramble rate uses only `qb_scramble = 1`; kneels are excluded.
- Designed-QB-run usage is `UNAVAILABLE`. It is not inferred from non-scramble rushes, player
  identity, or play text.

## Situational tendency

- Red zone uses `yardline_100 <= 20` and reports pass and rush choice separately.
- Third down reports pass tendency and average intended air yards.
- Fourth-down go rate uses pass/run versus pass/run/punt/field-goal plays. It describes team
  behavior and is not automatically owned by the play caller because decision authority is not
  established. Fourth-down pass rate is conditional on choosing an offensive run/pass play.

## Outcome context

EPA and success measures are written to `outcome_profiles.csv`, separate from scheme choices.
They include overall, pass, rush, deep-pass, and scramble outcomes. They are performance
descriptors, not automatically scheme features or coach effects.

## Feature statuses

The current audit contains 12 `CORE`, 53 `DESCRIPTIVE`, 7 `EXPERIMENTAL`, and 1 `UNAVAILABLE`
entries. `CORE` means sufficiently broad, deterministic retrospective coverage—not proof that a
feature belongs in a final Coach Effect equation. Correlations are documented without automatic
feature removal in `scheme_feature_correlations.csv`.
