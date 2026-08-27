# Data layout

- `processed/vertical_slice/<data_version>/bronze/`: byte-identical upstream Parquet for one atomic checkpoint-two build; ignored by Git.
- `processed/vertical_slice/<data_version>/silver/`: validated canonical and metric Parquet; ignored by Git.
- `processed/vertical_slice/LATEST`: local pointer to the most recently published immutable version; ignored by Git.
- `processed/historical/seasons/season=<season>/<season_version>/`: independently validated checkpoint-three Silver artifacts and checksums; ignored by Git.
- `processed/historical/<data_version>/bronze/`: byte-identical 1999-2025 source assets for one atomic full-history build; ignored by Git.
- `processed/historical/<data_version>/silver/`: canonical identities, complete QB facts, partitioned contextual sources, coverage, season summaries, and quality results; ignored by Git.
- `processed/historical/LATEST`: local pointer updated only after the complete historical build passes; ignored by Git.
- `processed/historical/EXECUTION_LOG.json`: mutable run evidence outside content-addressed outputs; timestamps, cache/retrieval status, preflight facts, and reuse status may legitimately differ between executions.
- `.cache/nfl_coaching_impact/`: verified download cache and retrieval metadata; located at the repository root and ignored by Git.
- `raw/`: reserved for later full-history immutable source storage; ignored by Git.
- `interim/`: normalized intermediate tables; ignored by Git.
- `processed/`: validated analytical Parquet outputs; ignored by Git.
- `external/`: restricted or user-supplied local inputs; ignored by Git.
- `manual/`: small, source-backed human-verified inputs; templates and permitted facts may be committed.

Checkpoint four commits only compact coaching facts in `manual/`: canonical coach identities, assignment intervals, normalized citations, role definitions, source-book URLs/digests, and an explicit review queue. `interval_basis` distinguishes head coaches observed on game weeks from OC/QB-coach season designations in preseason staff books. Raw NFL PDFs and team media guides remain uncommitted.

Never place credentials in this tree. Never commit raw CFBD responses, nflverse bulk files, third-party media guides, database dumps, or model artifacts.

A failed run removes only its unpublished staging directory. For historical ingestion, a season failure cannot alter already completed immutable season versions and never updates the full-history `LATEST` pointer.

Each successful version includes `OUTPUT_CHECKSUMS.json`. Reuse fails loudly if a listed output is missing, has a different byte size, or fails its SHA-256 check.
