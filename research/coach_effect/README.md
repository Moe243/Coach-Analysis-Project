# Coach Effect research

This directory preserves the deterministic research methods behind the proposed Coach Effect
framework. It is intentionally outside `src/`, `backend/`, database migrations, and frontend
code. Generated files belong under the ignored `research/coach_effect/outputs/` directory and
must never be loaded into production serving tables.

The four phases are:

1. [`phase_1_qb_effect`](phase_1_qb_effect/README.md): leakage-safe PAE and QB-transition tests.
2. [`phase_2_play_calling`](phase_2_play_calling/README.md): expected calls, expected pass/run
   EPA, decision value, PCAE, repeatability, and reliability.
3. [`phase_3_environment`](phase_3_environment/README.md): environment controls and
   leave-one-team-out validation.
4. [`phase_4_coach_effect`](phase_4_coach_effect/README.md): PAE/PCAE residualization and the
   unweighted conceptual framework.

The code consumes explicit input paths and does not silently fall back to production outputs.
Research findings are exploratory associations, not causal estimates or production rankings.
See [the research narrative](../../docs/COACH_EFFECT_RESEARCH.md),
[methodology](../../docs/COACH_EFFECT_METHODOLOGY.md), and
[model card](../../docs/COACH_EFFECT_MODEL_CARD.md).

## Production gate

Production Coach Effect implementation is blocked until offensive coordinator, quarterbacks
coach, and play-caller assignments are comprehensively verified. Play-caller records require
explicit evidence and weekly or in-season intervals wherever duties changed or were shared.

Checkpoint Eleven-B is run with
`make PYTHON=.venv/bin/python checkpoint-eleven-b`. It writes only ignored,
content-addressed evidence/PCAE diagnostics under `outputs/checkpoint_11b/`, including the
unresolved-caller queue, season attribution, PAE joinability, and repeatability readiness. It does
not estimate Coach Effect weights or publish rankings.

Checkpoint Twelve is run with `make PYTHON=.venv/bin/python checkpoint-twelve`. It compares
research-only Coach Effect candidates through strict rolling-origin validation, coach portability,
deterministic placebos, environment sensitivity, empirical-Bayes diagnostics, and a gated Scheme
analysis. Outputs are written only to ignored, content-addressed directories under
`outputs/checkpoint_12/`. The current evidence does not authorize a production equation, score, or
ranking.

The independent adversarial review is run with
`make PYTHON=.venv/bin/python checkpoint-twelve-review`. It rebuilds the core grains, refits the
candidate models, audits chronology and variance, expands approved scheme features, and writes a
separate content-addressed review under `outputs/checkpoint_12_review/`. Candidate A is preserved.

Prompt 8 historical data expansion is run with
`make PYTHON=.venv/bin/python checkpoint-twelve-data-expansion` after the official nflverse
participation and FTN source caches have been captured once. It preserves the 512-cell caller
matrix, overlays only source-backed research intervals, rebuilds PCAE only for newly qualifying
verified intervals with the unchanged method, and produces source-hashed team-season scheme
profiles plus portability and readiness diagnostics. All outputs remain ignored, research-only,
non-ranking artifacts under `outputs/checkpoint_12_data_expansion/`.

Prompt 9 is run with
`make PYTHON=.venv/bin/python checkpoint-twelve-play-caller-verification`. It audits the frozen
high-value queue in three deterministic batches, accepts only explicit source-backed calling
intervals, excludes shared or provisional duties from individual PCAE, and refreshes attribution
availability without changing PAE, Q, PCAE, CallValue, or Scheme methodology. Its ignored outputs
live under `outputs/checkpoint_12_play_caller_verification/`; no Coach Effect equation or ranking is
fit.

Prompt 10 is run with
`make PYTHON=.venv/bin/python checkpoint-twelve-final-play-caller-evidence`. It closes the bounded
public-source research sprint by reviewing all 28 highly recoverable cells, all 27 possibly
recoverable cells, five known shared/ambiguous cells, and 15 statistically prioritized archival
cells. Full-season verification requires explicit in-game caller evidence plus a defensible
continuity record; game-specific evidence remains bounded. Its ignored, content-addressed outputs
live under `outputs/checkpoint_12_final_play_caller_evidence/`. The sprint refreshes only
verified, non-shared PCAE attribution with the unchanged Prompt 8 method and does not fit a Coach
Effect equation, select weights or shrinkage, or create a ranking.

Prompt 11 is run with
`make PYTHON=.venv/bin/python checkpoint-twelve-coverage-gate-review`. It reviews the historical
50% play-caller cell gate against full-cell, bounded-interval, play-weighted, temporal-fold,
selection, and cluster-resampling evidence. It changes no verification status and fits no final
Coach Effect equation, weight, shrinkage method, score, or ranking. Its content-addressed outputs
remain ignored under `outputs/checkpoint_12_coverage_gate_review/`.

Prompt 12 is run with
`make PYTHON=.venv/bin/python checkpoint-twelve-final-research`. It freezes the Prompt 10/11
evidence state, compares Models 0–6 on the independently selected 2021–2025 folds, audits
role-specific Q and verified non-shared PCAE, tests shrinkage, context, missingness, placebos, and
the limited prior-scheme challenger, and writes only ignored content-addressed outputs under
`outputs/checkpoint_12_final_research/`. The final research decision retains Q and PCAE as
separate research signals; it approves no composite, fixed weights, score, ranking, production
change, Phase II work, or Ask Anything implementation.
