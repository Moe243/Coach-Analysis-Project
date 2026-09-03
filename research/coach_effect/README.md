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
