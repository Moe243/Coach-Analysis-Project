# QB State Feature Dictionary

Contract versions: `qb-style-profile-v1`, `qb-player-state-v1`, and `qb-asof-universe-v1`

The machine-readable authority is `qb_feature_registry.csv` in the current ignored Checkpoint 14
output. All state features are known by August 31 and have a source season earlier than the target
season.

## Grains

| Artifact | Grain |
|---|---|
| QB stint profile | player, team, season, feature, profile version |
| QB-season profile | player, season, feature, profile version |
| State universe | player, target season, universe version |
| Player State | player, target season, state version |
| State feature | player, target season, feature, state version |
| Evaluation link | player, team, season, evaluation version |

## Interpretation

- `preseason_ability_estimate_epa_per_db` is a shrunk cumulative historical EPA baseline. It is
  not a latent ability score.
- `recent_epa_per_dropback` is prior-season performance and remains distinct from the preseason
  estimate.
- `recent_observed_pae` is prior-season actual EPA/dropback minus its out-of-sample expected
  EPA/dropback. It is conditional and is never reconstructed from a target-season outcome.
- Style features retain explicit depth, location, formation, situation, and mobility denominators.
- Designed runs and under-center performance are unavailable rather than inferred.

## Sample and uncertainty

Raw values remain in profile artifacts. A state value is null below its registered opportunity
threshold. Qualified rates use empirical Beta-binomial shrinkage; qualified continuous means use
normal-normal shrinkage. `shrinkage_weight` measures how much the estimate reflects the player
rather than the historical prior: at least 0.75 is high reliability, 0.40–0.749 is medium, and
lower values are low. Standard errors and 95% intervals remain feature-specific; there is no
aggregate confidence or 0–100 style score.

The registry status is assigned by predeclared stability and, for conditioned outcomes,
portability checks. `PREDICTIVE_CORE` means suitable for later research consideration, not causal,
environment-free, or already selected by a future prediction model.
