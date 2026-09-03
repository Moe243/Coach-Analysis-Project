# Phase 1 — QB development / PAE

`analysis.py` calculates PAE, constructs consecutive QB-season transitions, and estimates the
normal year-to-year movement used to create an exploratory QB-development signal. It can test
new-OC transitions and stricter same-QB/same-team/same-head-coach comparisons without treating
one transition as a stable coach effect.

`qb_transition_analysis.sql` preserves the SQL contract for joining PAE to interval-aware coach
assignments. A team-season with multiple OC or head-coach intervals is kept out of the
full-season transition experiment rather than silently collapsed.
