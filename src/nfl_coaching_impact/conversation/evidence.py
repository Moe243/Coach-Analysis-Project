"""Deterministic evidence reducers over the immutable C19 analytical service."""

from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from nfl_coaching_impact.ask import AnalyticalService

from .contracts import (
    ApprovedTask,
    EvidencePackage,
    EvidenceRecord,
    EvidenceValue,
    PublicVersionMetadata,
    ResolvedEntity,
    SeasonContext,
    SourceReference,
    UncertaintyRepresentation,
    contract_schema_sha256,
)
from .enums import (
    AnalyticalTask,
    Answerability,
    AnswerMode,
    EntityKind,
    EvidenceKind,
    FeatureCategory,
    Reliability,
)
from .policy import SCIENTIFIC_POLICY_VERSION
from .registries import (
    EVIDENCE_REDUCER_VERSION,
    FEATURE_COMPATIBILITY,
    PLAYER_FEATURE_DEFINITIONS,
    SCHEME_FEATURE_UNITS,
    feature_display_name,
)
from .resolution import EntityResolver
from .serialization import canonical_json_bytes


@dataclass(frozen=True, slots=True)
class RankedEvidence:
    priority: int
    record: EvidenceRecord


@dataclass(frozen=True, slots=True)
class ReducerResult:
    ranked: tuple[RankedEvidence, ...] = ()
    uncertainty: tuple[UncertaintyRepresentation, ...] = ()
    limitations: tuple[str, ...] = ()
    model_versions: tuple[str, ...] = ()

    @property
    def records(self) -> tuple[EvidenceRecord, ...]:
        return tuple(item.record for item in self.ranked)

    @classmethod
    def combine(cls, *results: ReducerResult) -> ReducerResult:
        ranked_by_id: dict[str, RankedEvidence] = {}
        uncertainty_by_id: dict[str, UncertaintyRepresentation] = {}
        limitations: set[str] = set()
        models: set[str] = set()
        for result in results:
            for item in result.ranked:
                existing = ranked_by_id.get(item.record.evidence_id)
                if existing is None or item.priority < existing.priority:
                    ranked_by_id[item.record.evidence_id] = item
            uncertainty_by_id.update({item.uncertainty_id: item for item in result.uncertainty})
            limitations.update(result.limitations)
            models.update(result.model_versions)
        return cls(
            ranked=tuple(
                sorted(
                    ranked_by_id.values(),
                    key=lambda item: (item.priority, item.record.evidence_id),
                )
            ),
            uncertainty=tuple(uncertainty_by_id[key] for key in sorted(uncertainty_by_id)),
            limitations=tuple(sorted(limitations)),
            model_versions=tuple(sorted(models)),
        )


class EvidenceService:
    """A reference-index layer; source rows remain owned by one AnalyticalService."""

    def __init__(self, analytical: AnalyticalService):
        self.analytical = analytical
        self.bundle = analytical.bundle
        self.resolver = EntityResolver(analytical.entities)
        self._history_team_season = self._index("history", ("team_id", "season"))
        self._profiles = self._index("profiles", ("player_id", "target_season"))
        self._states = self._index("states", ("player_id", "target_season"))
        self._scheme = self._index("scheme", ("team_id", "season"))
        self._assignments_team_season = self._index("assignments", ("team_id", "season"))
        self._projections = self._index("projections", ("player_id", "target_season"))
        self._validate_bundle_contract()

    def _index(
        self, table: str, fields: tuple[str, ...]
    ) -> dict[tuple[Any, ...], tuple[dict, ...]]:
        grouped: dict[tuple[Any, ...], list[dict]] = defaultdict(list)
        for row in self.bundle[table]:
            grouped[tuple(row[field] for field in fields)].append(row)
        return {key: tuple(values) for key, values in grouped.items()}

    def _validate_bundle_contract(self) -> None:
        self._require_unique("history", ("player_id", "team_id", "season"))
        self._require_unique("states", ("player_id", "target_season"))
        self._require_unique("profiles", ("player_id", "target_season", "feature_name"))
        self._require_unique("scheme", ("team_id", "season", "feature_name"))
        self._require_unique("assignments", ("assignment_key",))
        self._require_unique("pcae", ("coach_id", "team_id", "season", "start_week", "end_week"))
        self._require_unique("projections", ("player_id", "target_season"))
        unknown_profiles = {
            row["feature_name"] for row in self.bundle["profiles"]
        } - PLAYER_FEATURE_DEFINITIONS.keys()
        unknown_scheme = {
            row["feature_name"] for row in self.bundle["scheme"]
        } - SCHEME_FEATURE_UNITS.keys()
        if unknown_profiles or unknown_scheme:
            raise ValueError("analytical bundle contains an unregistered evidence feature")
        for row in self.bundle["history"]:
            pae = row["performance_above_expectation"]
            if pae is not None and not math.isclose(
                row["epa_per_dropback"] - row["expected_epa_per_dropback"],
                pae,
                abs_tol=1e-12,
            ):
                raise ValueError("historical PAE arithmetic does not reconcile")
        for row in self.bundle["pcae"]:
            if (
                row["verification_status"] != "verified"
                or row["is_shared"]
                or not row["research_only"]
                or row["production_ranking"]
            ):
                raise ValueError("PCAE bundle violates the approved research-only contract")
            if not math.isclose(
                row["average_call_value"] - row["league_average_call_value"],
                row["pcae"],
                abs_tol=2e-10,
            ):
                raise ValueError("PCAE arithmetic does not reconcile")

    def _require_unique(self, table: str, fields: tuple[str, ...]) -> None:
        keys = [tuple(row[field] for field in fields) for row in self.bundle[table]]
        if any(value is None for key in keys for value in key) or len(keys) != len(set(keys)):
            raise ValueError(f"invalid {table} evidence grain: {fields}")

    def _entity(self, kind: EntityKind, entity_id: str) -> ResolvedEntity:
        return self.resolver.require_id(kind, entity_id)

    def _source(
        self, name: str, row_key: str, citation: dict[str, Any] | None = None
    ) -> SourceReference:
        source = self.bundle["sources"][name]
        citation = citation or {}
        return SourceReference(
            artifact=source["artifact"],
            data_version=source["data_version"],
            source_sha256=source["sha256"],
            row_key=row_key,
            source_url=citation.get("source_url"),
            source_title=citation.get("source_title"),
            source_type=citation.get("source_type"),
            source_accessed_at=citation.get("source_accessed_at"),
            evidence_locator=citation.get("evidence_locator"),
            evidence_note=citation.get("evidence_note"),
        )

    @staticmethod
    def _values(**values: Any) -> tuple[EvidenceValue, ...]:
        return tuple(EvidenceValue(name=name, value=value) for name, value in values.items())

    def _record(
        self,
        *,
        priority: int,
        kind: EvidenceKind,
        grain: str,
        summary: str,
        entities: Iterable[ResolvedEntity] = (),
        season: int | None = None,
        values: tuple[EvidenceValue, ...] = (),
        sources: Iterable[SourceReference] = (),
        uncertainty_id: str | None = None,
        operation_id: str | None = None,
        sample_count: int | None = None,
        source_evidence_ids: Iterable[str] = (),
    ) -> RankedEvidence:
        canonical_entities = tuple(
            sorted(entities, key=lambda entity: (entity.kind.value, entity.id))
        )
        canonical_sources = tuple(
            sorted(
                sources,
                key=lambda source: (
                    source.artifact,
                    source.data_version,
                    source.row_key or "",
                    source.source_url or "",
                ),
            )
        )
        source_ids = tuple(sorted(set(source_evidence_ids)))
        identity = {
            "reducer_version": EVIDENCE_REDUCER_VERSION,
            "kind": kind.value,
            "grain": grain,
            "entities": [(entity.kind.value, entity.id) for entity in canonical_entities],
            "season": season,
            "values": [(value.name, value.value, value.unit) for value in values],
            "sources": [
                (source.artifact, source.data_version, source.source_sha256, source.row_key)
                for source in canonical_sources
            ],
            "uncertainty_id": uncertainty_id,
            "operation_id": operation_id,
            "sample_count": sample_count,
            "source_evidence_ids": source_ids,
        }
        evidence_id = "evidence_" + hashlib.sha256(canonical_json_bytes(identity)).hexdigest()[:24]
        return RankedEvidence(
            priority=priority,
            record=EvidenceRecord(
                evidence_id=evidence_id,
                kind=kind,
                summary=summary,
                entities=canonical_entities,
                season=season,
                values=values,
                sources=canonical_sources,
                uncertainty_id=uncertainty_id,
                operation_id=operation_id,
                sample_count=sample_count,
                source_evidence_ids=source_ids[:32],
            ),
        )

    @staticmethod
    def _uncertainty_id(grain: str, values: dict[str, Any]) -> str:
        return (
            "uncertainty_"
            + hashlib.sha256(
                canonical_json_bytes(
                    {"reducer_version": EVIDENCE_REDUCER_VERSION, "grain": grain, **values}
                )
            ).hexdigest()[:24]
        )

    def _history_evidence(
        self, row: dict, priority: int = 20
    ) -> tuple[RankedEvidence, tuple[UncertaintyRepresentation, ...]]:
        player = self._entity(EntityKind.QB, row["player_id"])
        team = self._entity(EntityKind.TEAM, row["team_id"])
        key = f"{row['player_id']}|{row['team_id']}|{row['season']}"
        uncertainty: tuple[UncertaintyRepresentation, ...] = ()
        uncertainty_id = None
        if any(
            row[field] is not None
            for field in (
                "prediction_std_error",
                "prediction_interval_low",
                "prediction_interval_high",
            )
        ):
            fields = {
                "standard_error": row["prediction_std_error"],
                "lower": row["prediction_interval_low"],
                "upper": row["prediction_interval_high"],
            }
            uncertainty_id = self._uncertainty_id("qb_history|" + key, fields)
            uncertainty = (
                UncertaintyRepresentation(
                    uncertainty_id=uncertainty_id,
                    method="original_preseason_expectation_uncertainty",
                    standard_error=fields["standard_error"],
                    lower=fields["lower"],
                    upper=fields["upper"],
                    confidence_level=0.95,
                    reliability=Reliability(str(row["reliability"]).upper()),
                    explanation=(
                        "Original expectation uncertainty; this is not a newly fitted PAE interval."
                    ),
                ),
            )
        record = self._record(
            priority=priority,
            kind=EvidenceKind.QB_HISTORY,
            grain="player_id|team_id|season|" + key,
            summary=(
                f"QB team-season performance for {player.display_name} with "
                f"{team.display_name} in {row['season']}."
            ),
            entities=(player, team),
            season=row["season"],
            values=self._values(
                dropbacks=row["dropbacks"],
                starts=row["starts"],
                epa_per_dropback=row["epa_per_dropback"],
                expected_epa_per_dropback=row["expected_epa_per_dropback"],
                performance_above_expectation=row["performance_above_expectation"],
                cpoe=row["cpoe"],
                success_rate=row["success_rate"],
                sack_rate=row["sack_rate"],
                qualifies_default=row["qualifies_default"],
                eligibility_status=row["eligibility_status"],
                reliability=row["reliability"],
                is_out_of_sample=row["is_out_of_sample"],
                metric_version=row["metric_version"],
                model_version=row["model_version"],
            ),
            sources=(
                self._source("history", key),
                self._source("pae", key),
                self._source("supplemental", key),
            ),
            uncertainty_id=uncertainty_id,
        )
        return record, uncertainty

    def qb_history(self, player_id: str, season: int | None = None) -> ReducerResult:
        self._entity(EntityKind.QB, player_id)
        rows = sorted(
            (
                row
                for row in self.analytical.index["history"].get(player_id, ())
                if season is None or row["season"] == season
            ),
            key=lambda row: (row["season"], row["team_id"]),
        )
        ranked: list[RankedEvidence] = []
        uncertainty: list[UncertaintyRepresentation] = []
        models: set[str] = set()
        for row in rows:
            item, row_uncertainty = self._history_evidence(row)
            ranked.append(item)
            uncertainty.extend(row_uncertainty)
            if row["model_version"]:
                models.add(row["model_version"])
        return ReducerResult(
            ranked=tuple(ranked),
            uncertainty=tuple(uncertainty),
            limitations=(
                "Multi-team seasons remain separate at player_id + team_id + season.",
                "Expectation intervals are not newly fitted PAE intervals.",
            ),
            model_versions=tuple(sorted(models)),
        )

    def _state_evidence(
        self, row: dict
    ) -> tuple[RankedEvidence, tuple[UncertaintyRepresentation, ...]]:
        player = self._entity(EntityKind.QB, row["player_id"])
        key = f"{row['player_id']}|{row['target_season']}"
        fields = {
            "standard_error": row["preseason_ability_standard_error"],
            "lower": row["preseason_ability_interval_low"],
            "upper": row["preseason_ability_interval_high"],
        }
        uncertainty_id = None
        uncertainty: tuple[UncertaintyRepresentation, ...] = ()
        if any(value is not None for value in fields.values()):
            uncertainty_id = self._uncertainty_id("player_state|" + key, fields)
            uncertainty = (
                UncertaintyRepresentation(
                    uncertainty_id=uncertainty_id,
                    method="checkpoint_14_preseason_ability_uncertainty",
                    standard_error=fields["standard_error"],
                    lower=fields["lower"],
                    upper=fields["upper"],
                    confidence_level=0.95,
                    reliability=Reliability(row["preseason_ability_reliability"]),
                    explanation="Entering-season preseason ability uncertainty.",
                ),
            )
        return (
            self._record(
                priority=8,
                kind=EvidenceKind.QB_PROFILE,
                grain="player_id|target_season|" + key,
                summary=(
                    f"Entering-season Player State for {player.display_name} "
                    f"in {row['target_season']}."
                ),
                entities=(player,),
                season=row["target_season"],
                values=self._values(
                    as_of_date=row["as_of_date"],
                    maximum_source_season=row["maximum_source_season"],
                    age_at_season_start=row["age_at_season_start"],
                    is_rookie=row["is_rookie"],
                    nfl_experience=row["nfl_experience"],
                    nfl_experience_status=row["nfl_experience_status"],
                    prior_dropbacks=row["prior_dropbacks"],
                    prior_starts=row["prior_starts"],
                    career_dropbacks=row["career_dropbacks"],
                    career_starts=row["career_starts"],
                    preseason_ability_estimate_epa_per_db=row[
                        "preseason_ability_estimate_epa_per_db"
                    ],
                    preseason_ability_reliability=row["preseason_ability_reliability"],
                    state_completeness=row["state_completeness"],
                    state_status=row["state_status"],
                    state_version=row["state_version"],
                ),
                sources=(self._source("states", key),),
                uncertainty_id=uncertainty_id,
            ),
            uncertainty,
        )

    def _profile_evidence(
        self, row: dict
    ) -> tuple[RankedEvidence, tuple[UncertaintyRepresentation, ...]]:
        definition = PLAYER_FEATURE_DEFINITIONS[row["feature_name"]]
        if row["source_season"] is not None and row["source_season"] >= row["target_season"]:
            raise ValueError("Player State evidence reaches the target or a future season")
        player = self._entity(EntityKind.QB, row["player_id"])
        key = f"{row['player_id']}|{row['target_season']}|{row['feature_name']}"
        fields = {
            "standard_error": row["estimate_standard_error"],
            "lower": row["interval_low"],
            "upper": row["interval_high"],
        }
        uncertainty_id = None
        uncertainty: tuple[UncertaintyRepresentation, ...] = ()
        if any(value is not None for value in fields.values()):
            uncertainty_id = self._uncertainty_id("qb_profile|" + key, fields)
            uncertainty = (
                UncertaintyRepresentation(
                    uncertainty_id=uncertainty_id,
                    method=row["estimate_type"] or "source_method_unavailable",
                    standard_error=fields["standard_error"],
                    lower=fields["lower"],
                    upper=fields["upper"],
                    confidence_level=0.95,
                    reliability=Reliability(row["reliability"]),
                    explanation=(
                        "Entering-season estimate uncertainty is retained from the Player State "
                        "research."
                    ),
                ),
            )
        return (
            self._record(
                priority=10 if definition.category is FeatureCategory.USAGE else 15,
                kind=EvidenceKind.QB_PROFILE,
                grain="player_id|target_season|feature_name|" + key,
                summary=(
                    f"Entering-season {definition.category.value.lower()} measurement: "
                    f"{feature_display_name(row['feature_name'])} for {player.display_name}."
                ),
                entities=(player,),
                season=row["target_season"],
                values=self._values(
                    feature_name=row["feature_name"],
                    feature_category=definition.category.value,
                    feature_value=row["feature_value"],
                    raw_value=row["raw_value"],
                    unit=definition.unit,
                    as_of_date=row["as_of_date"],
                    source_season=row["source_season"],
                    observation_start_season=row["observation_start_season"],
                    observation_end_season=row["observation_end_season"],
                    sample_size=row["sample_size"],
                    denominator=row["denominator"],
                    qualified=row["qualified"],
                    reliability=row["reliability"],
                    feature_status=row["feature_status"],
                    missingness_reason=row["missingness_reason"],
                ),
                sources=(
                    self._source("profiles", key),
                    self._source("profile_registry", row["feature_name"]),
                ),
                uncertainty_id=uncertainty_id,
            ),
            uncertainty,
        )

    def qb_profile(
        self,
        player_id: str,
        target_season: int | None = None,
        feature_names: Iterable[str] | None = None,
    ) -> ReducerResult:
        self._entity(EntityKind.QB, player_id)
        available = sorted(
            {row["target_season"] for row in self.analytical.index["profiles"].get(player_id, ())}
        )
        if target_season is None and available:
            target_season = available[-1]
        requested = None if feature_names is None else set(feature_names)
        if requested is not None and not requested <= PLAYER_FEATURE_DEFINITIONS.keys():
            raise ValueError("requested player feature is not registered")
        rows = sorted(
            (
                row
                for row in self._profiles.get((player_id, target_season), ())
                if requested is None or row["feature_name"] in requested
            ),
            key=lambda row: row["feature_name"],
        )
        ranked: list[RankedEvidence] = []
        uncertainty: list[UncertaintyRepresentation] = []
        state_rows = self._states.get((player_id, target_season), ())
        if len(state_rows) == 1:
            state, state_uncertainty = self._state_evidence(state_rows[0])
            ranked.append(state)
            uncertainty.extend(state_uncertainty)
        for row in rows:
            item, row_uncertainty = self._profile_evidence(row)
            ranked.append(item)
            uncertainty.extend(row_uncertainty)
        return ReducerResult(
            ranked=tuple(sorted(ranked, key=lambda item: (item.priority, item.record.evidence_id))),
            uncertainty=tuple(sorted(uncertainty, key=lambda item: item.uncertainty_id)),
            limitations=(
                "Player State is entering-season evidence, not current or live performance.",
                "Usage, efficiency, contextual splits, state, and uncertainty remain distinct.",
            ),
        )

    def _scheme_evidence(self, row: dict, priority: int = 20) -> RankedEvidence:
        team = self._entity(EntityKind.TEAM, row["team_id"])
        key = f"{row['team_id']}|{row['season']}|{row['feature_name']}"
        return self._record(
            priority=priority,
            kind=EvidenceKind.TEAM_SCHEME,
            grain="team_id|season|feature_name|" + key,
            summary=(
                f"Observed {feature_display_name(row['feature_name'])} for "
                f"{team.display_name} in {row['season']}."
            ),
            entities=(team,),
            season=row["season"],
            values=self._values(
                feature_name=row["feature_name"],
                raw_value=row["raw_value"],
                unit=SCHEME_FEATURE_UNITS[row["feature_name"]],
                feature_sample_size=row["feature_sample_size"],
                feature_status=row["feature_status"],
                missingness_reason=row["missingness_reason"],
                source_dataset=row["source_dataset"],
                source_covered=row["source_covered"],
                causal_coach_ownership=False,
            ),
            sources=(self._source("scheme", key),),
        )

    def team_scheme(
        self,
        team_id: str,
        season: int | None = None,
        feature_names: Iterable[str] | None = None,
    ) -> ReducerResult:
        self._entity(EntityKind.TEAM, team_id)
        available = sorted(
            {row["season"] for row in self.bundle["scheme"] if row["team_id"] == team_id}
        )
        if season is None and available:
            season = available[-1]
        requested = None if feature_names is None else set(feature_names)
        if requested is not None and not requested <= SCHEME_FEATURE_UNITS.keys():
            raise ValueError("requested scheme feature is not registered")
        rows = sorted(
            (
                row
                for row in self._scheme.get((team_id, season), ())
                if requested is None or row["feature_name"] in requested
            ),
            key=lambda row: row["feature_name"],
        )
        return ReducerResult(
            ranked=tuple(self._scheme_evidence(row) for row in rows),
            limitations=(
                "Historical scheme is observed team-season behavior, not causal coach ownership.",
                "Missing scheme values remain unavailable and are never league-average filled.",
            ),
        )

    def _assignment_evidence(self, row: dict) -> RankedEvidence:
        coach = self._entity(EntityKind.COACH, row["coach_id"])
        team = self._entity(EntityKind.TEAM, row["team_id"])
        if row["verification_status"] != "verified":
            raise ValueError("unverified assignment cannot become approved assignment evidence")
        if not row["citations"]:
            raise ValueError("verified assignment evidence requires a citation")
        sources = tuple(
            self._source("assignments", row["assignment_key"], citation)
            for citation in row["citations"]
        )
        role_priority = {
            "play_caller": 5,
            "offensive_coordinator": 6,
            "quarterbacks_coach": 7,
            "head_coach": 8,
        }
        return self._record(
            priority=role_priority.get(row["role"], 9),
            kind=EvidenceKind.COACH_ASSIGNMENT,
            grain="assignment_key|" + row["assignment_key"],
            summary=(
                f"Verified {row['role']} assignment for {coach.display_name} with "
                f"{team.display_name} in {row['season']}."
            ),
            entities=(coach, team),
            season=row["season"],
            values=self._values(
                assignment_key=row["assignment_key"],
                role=row["role"],
                start_week=row["start_week"],
                end_week=row["end_week"],
                interval_basis=row["interval_basis"],
                verification_status=row["verification_status"],
                confidence_level=row["confidence_level"],
                is_shared=row["is_shared"],
                is_interim=row["is_interim"],
                is_retained=row["is_retained"],
                is_provisional=row["is_provisional"],
            ),
            sources=sources,
        )

    def coach_assignments(self, coach_id: str, season: int | None = None) -> ReducerResult:
        self._entity(EntityKind.COACH, coach_id)
        rows = sorted(
            (
                row
                for row in self.analytical.index["assignments"].get(coach_id, ())
                if row["verification_status"] == "verified"
                and (season is None or row["season"] == season)
            ),
            key=lambda row: row["assignment_key"],
        )
        return ReducerResult(
            ranked=tuple(self._assignment_evidence(row) for row in rows),
            limitations=(
                "Only verified source-backed assignments enter approved evidence.",
                "Season-level intervals are not converted into weekly certainty.",
                "Play-calling responsibility is never inferred from an OC title.",
            ),
        )

    def qb_coaching_context(
        self, player_id: str, season: int | None = None, *, best_seasons: bool = False
    ) -> ReducerResult:
        """Bounded factual navigation context; no coach effect or exposure is inferred."""
        self._entity(EntityKind.QB, player_id)
        rows = [
            row
            for row in self.analytical.index["history"].get(player_id, ())
            if (season is None or row["season"] == season)
            and (not best_seasons or row["qualifies_default"])
            and row["epa_per_dropback"] is not None
        ]
        rows.sort(
            key=lambda row: (
                -row["epa_per_dropback"] if best_seasons else -row["season"],
                -row["season"],
                row["team_id"],
            )
        )
        ranked = []
        uncertainty = []
        models = set()
        for row in rows[:3]:
            history, intervals = self._history_evidence(row)
            ranked.append(history)
            uncertainty.extend(intervals)
            if row["model_version"]:
                models.add(row["model_version"])
            for assignment in self._assignments_team_season.get(
                (row["team_id"], row["season"]), ()
            ):
                if assignment["verification_status"] == "verified":
                    ranked.append(self._assignment_evidence(assignment))
        return ReducerResult(
            ranked=tuple(ranked),
            uncertainty=tuple(uncertainty),
            model_versions=tuple(sorted(models)),
            limitations=(
                "Coaching context means a verified assignment in the same team-season, "
                "not exact weekly QB exposure or proof of causation.",
                "Only the three strongest recorded qualifying QB-team-seasons by EPA/dropback "
                "are selected; qualifying means at least 200 dropbacks."
                if best_seasons
                else "Only the three most recent recorded QB-team-seasons are shown.",
                "Historical coverage is 2010–2025; this is not an all-career ranking.",
            ),
        )

    def coach_qb_context(
        self,
        coach_id: str,
        season: int | None = None,
        *,
        young_only: bool = False,
    ) -> ReducerResult:
        coach = self._entity(EntityKind.COACH, coach_id)
        assignment_rows = sorted(
            (
                row
                for row in self.analytical.index["assignments"].get(coach_id, ())
                if row["verification_status"] == "verified"
                and (season is None or row["season"] == season)
            ),
            key=lambda row: row["assignment_key"],
        )
        assignments = tuple(self._assignment_evidence(row) for row in assignment_rows)
        assignment_ids_by_team_season: dict[tuple[str, int], list[str]] = defaultdict(list)
        assignment_keys_by_team_season: dict[tuple[str, int], list[str]] = defaultdict(list)
        for row, item in zip(assignment_rows, assignments, strict=True):
            team_season = (row["team_id"], row["season"])
            assignment_ids_by_team_season[team_season].append(item.record.evidence_id)
            assignment_keys_by_team_season[team_season].append(row["assignment_key"])
        sample_rows: dict[tuple[str, str, int], dict] = {}
        missing_age_count = 0
        age_excluded_count = 0
        for team_season in assignment_ids_by_team_season:
            for row in self._history_team_season.get(team_season, ()):
                state_rows = self._states.get((row["player_id"], row["season"]), ())
                age = state_rows[0]["age_at_season_start"] if len(state_rows) == 1 else None
                if young_only and age is None:
                    missing_age_count += 1
                    continue
                if young_only and age >= 25:
                    age_excluded_count += 1
                    continue
                row = {**row, "age_at_season_start": age}
                sample_rows[(row["player_id"], row["team_id"], row["season"])] = row
        contexts: list[RankedEvidence] = []
        models: set[str] = set()
        for key in sorted(sample_rows):
            row = sample_rows[key]
            qb = self._entity(EntityKind.QB, row["player_id"])
            team = self._entity(EntityKind.TEAM, row["team_id"])
            team_season = (row["team_id"], row["season"])
            assignment_ids = assignment_ids_by_team_season[team_season]
            assignment_keys = assignment_keys_by_team_season[team_season]
            contexts.append(
                self._record(
                    priority=12,
                    kind=EvidenceKind.COACH_QB_CONTEXT,
                    grain="player_id|team_id|season|coach_id|"
                    + "|".join(map(str, (*key, coach_id))),
                    summary=(
                        f"Verified same-team-season context for {coach.display_name} and "
                        f"{qb.display_name} with {team.display_name} in {row['season']}."
                    ),
                    entities=(coach, qb, team),
                    season=row["season"],
                    values=self._values(
                        analytical_sample_key="|".join(map(str, key)),
                        dropbacks=row["dropbacks"],
                        epa_per_dropback=row["epa_per_dropback"],
                        expected_epa_per_dropback=row["expected_epa_per_dropback"],
                        performance_above_expectation=row["performance_above_expectation"],
                        age_at_season_start=row["age_at_season_start"],
                        relationship_semantics="same_team_season_context",
                        exact_weekly_overlap=False,
                        verified_role_count=len(assignment_ids),
                    ),
                    sources=(
                        self._source("history", "|".join(map(str, key))),
                        self._source("pae", "|".join(map(str, key))),
                        self._source("assignments", "|".join(sorted(assignment_keys))),
                    ),
                    source_evidence_ids=assignment_ids,
                )
            )
            if row["model_version"]:
                models.add(row["model_version"])
        source_ids = [item.record.evidence_id for item in (*assignments, *contexts)]
        key_digest = hashlib.sha256(canonical_json_bytes(sorted(sample_rows))).hexdigest()
        summary = self._record(
            priority=3,
            kind=EvidenceKind.SUMMARY,
            grain=f"coach_context_summary|{coach_id}|{season or 'all'}",
            summary=f"Distinct verified coaching-context coverage for {coach.display_name}.",
            entities=(coach,),
            season=season,
            values=self._values(
                distinct_qb_team_seasons=len(sample_rows),
                verified_assignment_count=len(assignments),
                verified_roles="|".join(sorted({row["role"] for row in assignment_rows})),
                relationship_semantics="same_team_season_context",
                exact_weekly_overlap=False,
                young_filter_applied=young_only,
                young_definition="age_under_25_at_season_start" if young_only else None,
                missing_age_excluded_count=missing_age_count,
                age_25_or_older_excluded_count=age_excluded_count,
                source_key_sha256=key_digest,
            ),
            sources=(self._source("assignments", f"coach|{coach_id}|{season or 'all'}"),),
            operation_id="count_distinct_qb_team_seasons",
            sample_count=len(sample_rows),
            source_evidence_ids=source_ids,
        )
        return ReducerResult(
            ranked=(summary, *assignments, *contexts),
            limitations=tuple(
                item
                for item in (
                    "QB performance samples are distinct player_id + team_id + season "
                    "observations.",
                    "Role assignments remain separate evidence and do not multiply QB samples.",
                    "Same-team-season context does not establish exact weekly QB exposure.",
                    (
                        "Young quarterback means age under 25 at season start; missing ages are "
                        f"excluded ({missing_age_count} observations)."
                        if young_only
                        else None
                    ),
                )
                if item is not None
            ),
            model_versions=tuple(sorted(models)),
        )

    def _pcae_evidence(self, row: dict) -> RankedEvidence:
        coach = self._entity(EntityKind.COACH, row["coach_id"])
        team = self._entity(EntityKind.TEAM, row["team_id"])
        key = "|".join(
            map(
                str,
                (
                    row["coach_id"],
                    row["team_id"],
                    row["season"],
                    row["start_week"],
                    row["end_week"],
                ),
            )
        )
        return self._record(
            priority=30,
            kind=EvidenceKind.PCAE,
            grain="coach_id|team_id|season|start_week|end_week|" + key,
            summary=(
                f"Research-only PCAE interval for {coach.display_name} with "
                f"{team.display_name} in {row['season']}."
            ),
            entities=(coach, team),
            season=row["season"],
            values=self._values(
                start_week=row["start_week"],
                end_week=row["end_week"],
                attributed_play_count=row["attributed_play_count"],
                eligible_play_count=row["eligible_play_count"],
                average_call_value=row["average_call_value"],
                league_average_call_value=row["league_average_call_value"],
                pcae=row["pcae"],
                verification_status=row["verification_status"],
                confidence_level=row["confidence_level"],
                is_shared=row["is_shared"],
                research_only=row["research_only"],
                production_ranking=row["production_ranking"],
                ranking_output=row["ranking_output"],
                model_version=row["model_version"],
                play_eligibility_version=row["play_eligibility_version"],
            ),
            sources=(self._source("pcae", key),),
        )

    def pcae(self, coach_id: str, season: int | None = None) -> ReducerResult:
        self._entity(EntityKind.COACH, coach_id)
        rows = sorted(
            (
                row
                for row in self.analytical.index["pcae"].get(coach_id, ())
                if season is None or row["season"] == season
            ),
            key=lambda row: (row["season"], row["team_id"], row["start_week"], row["end_week"]),
        )
        return ReducerResult(
            ranked=tuple(self._pcae_evidence(row) for row in rows),
            limitations=(
                "PCAE is observational research evidence, not QB PAE or a universal Coach Effect.",
                "Only verified non-shared caller intervals are present; coverage is "
                "incomplete and nonrandom.",
                "No coach-interval confidence interval was published.",
            ),
            model_versions=tuple(sorted({row["model_version"] for row in rows})),
        )

    def projection(self, player_id: str, target_season: int = 2026) -> ReducerResult:
        player = self._entity(EntityKind.QB, player_id)
        if target_season != 2026:
            return ReducerResult(
                limitations=("Only the frozen 2026 team-independent EPA projection is approved.",)
            )
        rows = self._projections.get((player_id, target_season), ())
        if not rows:
            return ReducerResult(
                limitations=(
                    "The player is absent from the fixed 57-candidate projection artifact.",
                )
            )
        row = rows[0]
        key = f"{player_id}|{target_season}"
        uncertainty_id = self._uncertainty_id(
            "qb_projection|" + key,
            {"lower": row["lower_95"], "upper": row["upper_95"]},
        )
        uncertainty = UncertaintyRepresentation(
            uncertainty_id=uncertainty_id,
            method=row["interval_method"],
            lower=row["lower_95"],
            upper=row["upper_95"],
            confidence_level=0.95,
            reliability=Reliability.UNAVAILABLE,
            explanation=(
                "Published historical-residual band; no categorical reliability label was supplied."
            ),
        )
        record = self._record(
            priority=35,
            kind=EvidenceKind.QB_PROJECTION,
            grain="player_id|target_season|" + key,
            summary=(
                f"Frozen team-independent 2026 EPA research projection for {player.display_name}."
            ),
            entities=(player,),
            season=target_season,
            values=self._values(
                prediction=row["prediction"],
                outcome=row["outcome"],
                lower_50=row["lower_50"],
                upper_50=row["upper_50"],
                lower_80=row["lower_80"],
                upper_80=row["upper_80"],
                lower_95=row["lower_95"],
                upper_95=row["upper_95"],
                as_of_date=row["as_of_date"],
                model_status=row["model_status"],
                model_version=row["model_version"],
                data_version=row["data_version"],
                active_roster_claim=row["active_roster_claim"],
                team_independent=True,
            ),
            sources=(self._source("projections", key),),
            uncertainty_id=uncertainty_id,
        )
        return ReducerResult(
            ranked=(record,),
            uncertainty=(uncertainty,),
            limitations=(
                "Projection is team-independent and makes no destination, coach, "
                "playing-time, or roster claim.",
                "No forward PAE, yards, touchdowns, interceptions, or team-specific "
                "improvement is approved.",
            ),
            model_versions=(row["model_version"],),
        )

    def compare_qbs(
        self, first_player_id: str, second_player_id: str, season: int
    ) -> ReducerResult:
        first = self.qb_history(first_player_id, season)
        second = self.qb_history(second_player_id, season)
        first_keys = {
            value.name
            for record in first.records
            for value in record.values
            if value.value is not None
        }
        second_keys = {
            value.name
            for record in second.records
            for value in record.values
            if value.value is not None
        }
        comparable = sorted(
            (first_keys & second_keys)
            & {
                "dropbacks",
                "epa_per_dropback",
                "expected_epa_per_dropback",
                "performance_above_expectation",
                "cpoe",
                "success_rate",
                "sack_rate",
            }
        )
        entities = (
            self._entity(EntityKind.QB, first_player_id),
            self._entity(EntityKind.QB, second_player_id),
        )
        source_ids = [record.evidence_id for record in (*first.records, *second.records)]
        summary = self._record(
            priority=2,
            kind=EvidenceKind.SUMMARY,
            grain=f"qb_comparison|{first_player_id}|{second_player_id}|{season}",
            summary="Comparable historical QB evidence fields for the selected season.",
            entities=entities,
            season=season,
            values=self._values(
                comparable_metric_count=len(comparable),
                comparable_metrics="|".join(comparable),
                winner_selected=False,
            ),
            sources=(self._source("history", f"comparison|{season}"),),
            operation_id="intersect_nonmissing_metric_names",
            sample_count=len(first.records) + len(second.records),
            source_evidence_ids=source_ids,
        )
        return ReducerResult.combine(
            ReducerResult(ranked=(summary,)),
            first,
            second,
        )

    def compare_teams_scheme(
        self, first_team_id: str, second_team_id: str, season: int
    ) -> ReducerResult:
        first_rows = {
            row["feature_name"]: row for row in self._scheme.get((first_team_id, season), ())
        }
        second_rows = {
            row["feature_name"]: row for row in self._scheme.get((second_team_id, season), ())
        }
        shared = sorted(first_rows.keys() & second_rows.keys())
        ranked: list[RankedEvidence] = []
        for feature in shared:
            ranked.extend(
                (
                    self._scheme_evidence(first_rows[feature], priority=15),
                    self._scheme_evidence(second_rows[feature], priority=15),
                )
            )
        return ReducerResult(
            ranked=tuple(ranked),
            limitations=(
                "Only identical registered scheme features from the same season are aligned.",
                "No causal coach ownership or future scheme claim is produced.",
            ),
        )

    def player_team_alignment(
        self,
        player_id: str,
        team_id: str,
        player_target_season: int,
        team_scheme_season: int,
        *,
        include_projection: bool = False,
    ) -> ReducerResult:
        player = self._entity(EntityKind.QB, player_id)
        team = self._entity(EntityKind.TEAM, team_id)
        profile_rows = {
            row["feature_name"]: row
            for row in self._profiles.get((player_id, player_target_season), ())
        }
        scheme_rows = {
            row["feature_name"]: row for row in self._scheme.get((team_id, team_scheme_season), ())
        }
        ranked: list[RankedEvidence] = []
        uncertainty: list[UncertaintyRepresentation] = []
        for mapping in FEATURE_COMPATIBILITY:
            profile = profile_rows.get(mapping.player_feature)
            scheme = scheme_rows.get(mapping.scheme_feature)
            if profile is None or scheme is None:
                continue
            player_item, player_uncertainty = self._profile_evidence(profile)
            scheme_item = self._scheme_evidence(scheme)
            ranked.extend((player_item, scheme_item))
            uncertainty.extend(player_uncertainty)
            if profile["feature_value"] is None or scheme["raw_value"] is None:
                continue
            key = (
                f"{player_id}|{player_target_season}|{team_id}|{team_scheme_season}|"
                f"{mapping.player_feature}|{mapping.scheme_feature}"
            )
            ranked.append(
                self._record(
                    priority=5,
                    kind=EvidenceKind.PLAYER_SCHEME_ALIGNMENT,
                    grain="descriptive_alignment|" + key,
                    summary=(
                        f"Comparable measured {mapping.semantic_label} for "
                        f"{player.display_name} and {team.display_name}."
                    ),
                    entities=(player, team),
                    season=team_scheme_season,
                    values=self._values(
                        player_target_season=player_target_season,
                        team_scheme_season=team_scheme_season,
                        player_feature=mapping.player_feature,
                        scheme_feature=mapping.scheme_feature,
                        player_value=profile["feature_value"],
                        scheme_value=scheme["raw_value"],
                        comparison_unit=mapping.comparison_unit,
                        higher_higher_is_similar_usage=mapping.higher_higher_is_similar_usage,
                        descriptive_only=True,
                    ),
                    sources=(*player_item.record.sources, *scheme_item.record.sources),
                    uncertainty_id=player_item.record.uncertainty_id,
                    source_evidence_ids=(
                        player_item.record.evidence_id,
                        scheme_item.record.evidence_id,
                    ),
                )
            )
        result = ReducerResult(
            ranked=tuple(ranked),
            uncertainty=tuple(uncertainty),
            limitations=(
                "Alignment compares declared compatible tendencies only; it is not a fit score.",
                (
                    "The destination-team research does not support a prediction or "
                    "improvement adjustment."
                ),
            ),
        )
        if include_projection:
            result = ReducerResult.combine(result, self.projection(player_id, 2026))
        return ReducerResult.combine(result)

    def compare_coaches(
        self,
        first_coach_id: str,
        second_coach_id: str,
        season: int | None = None,
        *,
        young_only: bool = False,
    ) -> ReducerResult:
        results = []
        for coach_id in (first_coach_id, second_coach_id):
            context = self.coach_qb_context(coach_id, season, young_only=young_only)
            pcae = self.pcae(coach_id, season)
            coach = self._entity(EntityKind.COACH, coach_id)
            pcae_records = [
                item.record for item in pcae.ranked if item.record.kind is EvidenceKind.PCAE
            ]
            pcae_summary = self._record(
                priority=4,
                kind=EvidenceKind.SUMMARY,
                grain=f"coach_pcae_summary|{coach_id}|{season or 'all'}",
                summary=f"Research-only PCAE coverage for {coach.display_name}.",
                entities=(coach,),
                season=season,
                values=self._values(
                    pcae_interval_count=len(pcae_records),
                    pcae_available=bool(pcae_records),
                    research_only=True,
                    production_ranking=False,
                ),
                sources=(self._source("pcae", f"coach|{coach_id}|{season or 'all'}"),),
                operation_id="count_pcae_intervals",
                sample_count=len(pcae_records),
                source_evidence_ids=[item.evidence_id for item in pcae_records],
            )
            results.extend(
                (
                    context,
                    pcae,
                    ReducerResult(ranked=(pcae_summary,)),
                )
            )
        return ReducerResult.combine(
            *results,
            ReducerResult(
                limitations=(
                    "Stage B organizes evidence and does not select a better coach or developer.",
                    "PCAE, verified roles, QB context, and scheme remain distinct "
                    "evidence families.",
                )
            ),
        )

    def package(
        self,
        task: AnalyticalTask,
        result: ReducerResult,
        entities: Sequence[ResolvedEntity],
        seasons: SeasonContext | None = None,
    ) -> EvidencePackage:
        unique = {item.record.evidence_id: item for item in result.ranked}
        ordered = sorted(unique.values(), key=lambda item: (item.priority, item.record.evidence_id))
        limitations = set(result.limitations)
        answerability = Answerability.SUPPORTED if ordered else Answerability.DATA_UNAVAILABLE
        if len(ordered) > 32:
            full_ids = [item.record.evidence_id for item in ordered]
            omitted = len(ordered) - 31
            scope = self._record(
                priority=0,
                kind=EvidenceKind.LIMITATION,
                grain=f"bounded_scope|{task.value}|{len(ordered)}",
                summary=(
                    "The evidence request exceeds the compact package boundary; narrow the scope."
                ),
                entities=entities,
                values=self._values(
                    total_evidence_records=len(ordered),
                    retained_evidence_records=31,
                    omitted_evidence_records=omitted,
                    partial_package=True,
                    source_key_sha256=hashlib.sha256(canonical_json_bytes(full_ids)).hexdigest(),
                ),
                operation_id="deterministic_evidence_boundary",
                sample_count=len(ordered),
                source_evidence_ids=full_ids,
            )
            ordered = [scope, *ordered[:31]]
            limitations.add(
                f"BOUNDED_SCOPE: {omitted} evidence records are not represented; only retained "
                "evidence and complete aggregate summaries may support a conclusion. Narrow the "
                "request for record-level review."
            )
            answerability = Answerability.PARTIALLY_SUPPORTED
        versions = PublicVersionMetadata(
            contract_schema_sha256=contract_schema_sha256(),
            scientific_policy_version=SCIENTIFIC_POLICY_VERSION,
            analytical_data_version=self.analytical.version,
            analytical_model_versions=tuple(sorted(set(result.model_versions))),
            evidence_reducer_version=EVIDENCE_REDUCER_VERSION,
            planner_implementation_version="not-implemented",
            synthesizer_implementation_version="not-implemented",
            answer_mode=AnswerMode.DETERMINISTIC,
        )
        retained_uncertainty_ids = {
            item.record.uncertainty_id for item in ordered if item.record.uncertainty_id is not None
        }
        return EvidencePackage(
            answerability=answerability,
            resolved_entities=tuple(entities),
            approved_tasks=(
                ApprovedTask(
                    task_id="task_1",
                    task=task,
                    entities=tuple(entities),
                    seasons=seasons,
                    authorization_reason="Selected from the backend analytical task allowlist.",
                ),
            ),
            evidence=tuple(item.record for item in ordered),
            uncertainty=tuple(
                item
                for item in result.uncertainty
                if item.uncertainty_id in retained_uncertainty_ids
            ),
            limitations=tuple(sorted(limitations)),
            versions=versions,
        )
