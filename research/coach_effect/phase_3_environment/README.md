# Phase 3 — Environment controls

`analysis.py` compares environment-only and environment-plus-PCAE linear specifications,
reports standardized descriptive coefficients, and performs leave-one-team-out validation.

Environment variables are controls and sensitivity inputs, not positive Coach Effect
components. The intended final exploratory inputs are prior team EPA, preseason expected QB EPA,
an opening-roster supporting-cast measure, and leave-each-offense-out opponent strength. The
supporting-cast correction excludes cut, practice/development squad, and reserve players from
the Week 1 active/inactive roster scope. Same-season offensive outcomes are never used as
preseason inputs.
