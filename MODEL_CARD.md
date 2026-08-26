# Model card

Status: design specification; no model has been trained.

## Intended use

The expected-performance model estimates a preseason EPA/dropback expectation for an NFL quarterback-team-season. The coach-impact models estimate partially pooled associations between coaching-role exposure and game-level performance residuals.

Intended users are portfolio reviewers, sports analysts, and football-operations practitioners who will inspect the estimate together with uncertainty and context.

## Out-of-scope uses

- Claiming that a coach caused a player's outcome
- Personnel, employment, contract, or wagering decisions based on rank alone
- Evaluation of non-quarterback position coaches in version one
- In-season prediction using information unavailable at the stated cutoff
- Replacing film review, medical information, or proprietary tracking data

## Training and evaluation population

- Published analysis seasons: 2010-2025 regular seasons
- Warm-up seasons: 1999-2009, used only to train models predicting 2010 onward
- Default displayed sample: quarterback-team-seasons with at least 200 eligible dropbacks
- Smaller samples remain stored and are excluded from default rankings

## Inputs

The expected model may use draft/combine/profile information, age, experience, prior starts, prior performance and usage, prior injuries, team change, and lagged environment features. College features are deferred until the baseline works.

Forbidden expected-model inputs include same-season results, same-season honors, future injuries, future depth charts, and any feature computed with seasons at or after the predicted season.

## Outputs

- Expected EPA/dropback
- Actual EPA/dropback
- QB Performance Above Expectation
- Prediction diagnostics and applicable warning flags
- Role-specific coach association estimates with uncertainty and exposure counts

## Candidate models

1. Elastic Net with season-safe preprocessing; primary and preferred for interpretability.
2. Histogram gradient boosting; challenger.
3. Frequentist mixed-effects models for role-specific coach associations.
4. Crossed-role mixed model as sensitivity analysis, not the default leaderboard.

Bayesian hierarchical modeling is deferred.

## Validation

- Expanding-window outer evaluation by season
- Time-ordered inner tuning
- No random row split across time
- MAE, RMSE, R-squared, calibration intercept and slope
- Stability by season, experience, volume, team change, and missing-feature patterns
- Leakage tests checking every feature's `as_of_season`
- Bootstrap intervals clustered by QB-season for coach effects
- Sensitivity checks for role overlap, threshold choice, and environment controls

## Fairness and subgroup review

The model is not about protected traits and must not infer them. Still, systematic missingness can differ by era, draft status, experience, roster position, and data availability. Performance and calibration will be reported for rookies, veterans, low/high draft capital, team changers, and major data-availability eras.

## Known risks

Selection bias, staff collinearity, survivorship, roster quality, measurement error, unequal samples, and post-treatment adjustment can all distort estimates. See `LIMITATIONS.md`.

## Versioning and release gate

Each model run must store code version, data version, feature version, training cutoff, hyperparameters, evaluation metrics, and artifact URI. No model is publishable until leakage tests pass and its model card is updated with actual results.
