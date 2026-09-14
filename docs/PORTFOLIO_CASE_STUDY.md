# From football question to inspectable evidence

## The problem

A good quarterback season is not, by itself, evidence of good coaching. Player history,
roster construction, overlapping staff duties and schedule can all complicate attribution.
This project asks **“Does performance follow the coach?”** while keeping that distinction visible.

The result is a quarterback analytics application covering 2010–2025, with 1999–2009 used
only as training warm-up. It connects reproducible data pipelines, statistical research,
database integrity and an accessible interface. It does not claim a causal coaching score.

## What to inspect

| Product question                              | Implementation                                                                               | Evidence                                                                                                           |
| --------------------------------------------- | -------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| Did the QB exceed a preseason expectation?    | Actual EPA/dropback minus out-of-sample expected EPA/dropback; separate QB-team-season rows  | [Expected-performance methodology](../METHODOLOGY.md), [model card](../MODEL_CARD.md)                              |
| Who held which role, and when?                | Canonical identities, assignment intervals, citations and explicit provisional/shared states | [Coaching evidence](CHECKPOINT_4_REPORT.md), [data dictionary](../DATA_DICTIONARY.md)                              |
| Can the same result be rebuilt?               | Content-addressed artifacts, recorded input hashes and deterministic publication             | [Architecture](ARCHITECTURE.md)                                                                                    |
| Can a failed load corrupt the published app?  | Transactional loading, integrity constraints and publication rollback tests                  | [Serving implementation](../src/nfl_coaching_impact/serving.py), [checkpoint-seven report](CHECKPOINT_7_REPORT.md) |
| Can a keyboard user explore the graph?        | Equivalent relationship cards, canonical selection, focus actions and URL restoration        | [Frontend](../frontend/README.md), [browser tests](../frontend/e2e/checkpoint-eight.spec.ts)                       |
| Will the system invent an unsupported answer? | Ask reads approved records and explicitly refuses unsupported estimates                      | [Ask contract](CHECKPOINT_19_ASK_ANYTHING.md), [tests](../tests/test_checkpoint_nineteen_ask.py)                   |

## A short product tour

Start with **Baker Mayfield's profile**. His 2022 Carolina and Los Angeles rows illustrate
why player-season alone is an unsafe analytical join. PAE belongs to a QB-team-season;
missing values stay unavailable, and eligibility remains distinct from reliability.

Next inspect **Houston, 2020** in Relationship Explorer. The timeline and relationship cards
expose role changes, assignment evidence and shared play-calling. Connections to a common
team-season establish context, not proof that every quarterback was coached during every week.

Finally, in a **configured local Ask instance**, compare a historical lookup with a team-transfer
question. Approved records carry versions, uncertainty and limitations. Unsupported scenarios
receive an explanation rather than a plausible-looking number.

## Research results that shaped the product

- Historical PAE is a descriptive comparison against a preseason model, not a player grade.
- The calibrated one-year EPA experiment is **research-ready with limitations** and team-independent. Forward PAE is not supported.
- Player × Scheme Fit lacked adequate historical as-of team-assignment coverage for the intended estimation.
- The subsequent conditional scenario experiment did not improve out-of-sample prediction. A career counterfactual simulator was therefore withheld.
- There is no approved universal Coach Effect, fit score or rookie projection model.

These are different outcomes: insufficient data, a tested model that fails, and an implementation
withheld because a prerequisite failed. The [Phase II closeout](PHASE_II_CLOSEOUT.md) records
the distinction and the supporting results. This portfolio pass changes none of them.

## Visual and interaction design

The interface uses a charcoal workstation palette, restrained orange actions, green/gold chart
series, flat panels and tabular numerals. Compact default columns keep comparisons readable;
expanded metrics remain available. Small graphs have a compact canvas, and mobile filters use
two columns while search fields retain their full width.

Color is not the sole evidence channel: signs, text labels, dashed/provisional relationships,
citations and keyboard-accessible cards carry the same meaning. Tests cover desktop, tablet
and mobile behavior; automated accessibility checks complement, rather than replace, manual review.

## Release and data boundaries

The redesign and portfolio pass are approved for release, not yet certified as deployed.
The public site may show the earlier release. Ask also requires its
approved private snapshot; a functioning historical database alone is insufficient.

Source code uses the MIT License. Third-party data remains subject to its original terms.
The approved [PFR audit](PFR_FEASIBILITY_AUDIT.md) remains **PERMISSION REQUIRED BEFORE INGESTION**.
No PFR collection, new model, database migration or deployment is part of this pass.
