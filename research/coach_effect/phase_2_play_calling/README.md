# Phase 2 — Play calling / PCAE

`analysis.py` provides the expected-call classifier, separate expected pass/run EPA regressions,
decision-value scoring, interval-safe play-caller attribution, league-centered PCAE,
2024-to-2025 repeatability, and empirical reliability/shrinkage helpers.

The model is trained on 2022–2024 and evaluated on 2025. Call Value is expected EPA of the
chosen play type minus expected EPA of the alternative. The actual outcome of an individual
play is used only for aggregate validation; it is never part of that play's decision score.

The attribution function fails when a play has no explicitly sourced weekly/in-season
play-caller interval or has an unsupported overlap. A formal OC title is not evidence that a
coach called plays. The current production manual data is not comprehensive enough to rerun the
historical 32-team exploratory result, so a future reproduction must supply a separately audited
play-caller input rather than infer assignments.
