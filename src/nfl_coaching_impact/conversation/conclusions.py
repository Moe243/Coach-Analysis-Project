"""Backend-owned conclusion permissions and grounded proposition construction."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from .contracts import (
    ConclusionPermission,
    EvidencePackage,
    EvidenceRecord,
    GroundedProposition,
)
from .enums import (
    ConclusionKind,
    EvidenceKind,
    PermissionDecision,
    QuestionType,
)
from .registries import SCHEME_FEATURE_UNITS, feature_display_name
from .serialization import canonical_json_bytes


def values(record: EvidenceRecord) -> dict[str, Any]:
    return {item.name: item.value for item in record.values}


def number(value: float | int | None, digits: int = 3) -> str:
    return "unavailable" if value is None else f"{value:.{digits}f}"


def percent(value: float | int | None) -> str:
    return "unavailable" if value is None else f"{100 * value:.1f}%"


def possessive(value: str) -> str:
    return value + ("'" if value.casefold().endswith("s") else "'s")


def metric_display_name(metric: str) -> str:
    return {
        "cpoe": "CPOE",
        "epa_per_dropback": "EPA/dropback",
        "performance_above_expectation": "PAE",
    }.get(metric, feature_display_name(metric))


def metric_unit(metric: str) -> str | None:
    return {
        "epa_per_dropback": "epa_per_dropback",
        "expected_epa_per_dropback": "epa_per_dropback",
        "performance_above_expectation": "epa_per_dropback",
        "success_rate": "rate",
        "sack_rate": "rate",
        "cpoe": "percentage_points",
        "dropbacks": "count",
    }.get(metric)


@dataclass(frozen=True, slots=True)
class ConclusionResult:
    propositions: tuple[GroundedProposition, ...]
    permissions: tuple[ConclusionPermission, ...]


class ConclusionEngine:
    """Permit narrow claims from evidence; deny causal and predictive-fit claims."""

    permissions = (
        ConclusionPermission(
            permission_id="permission_historical",
            kind=ConclusionKind.HISTORICAL_FACT,
            decision=PermissionDecision.ALLOWED,
            reason_code="direct_source_evidence",
            explanation="Direct historical claims may use the cited evidence fields.",
        ),
        ConclusionPermission(
            permission_id="permission_descriptive",
            kind=ConclusionKind.DESCRIPTIVE_COMPARISON,
            decision=PermissionDecision.ALLOWED_WITH_LIMITATIONS,
            reason_code="same_metric_only",
            explanation="Only directly compatible measurements may be compared.",
        ),
        ConclusionPermission(
            permission_id="permission_role",
            kind=ConclusionKind.VERIFIED_ROLE_ATTRIBUTION,
            decision=PermissionDecision.ALLOWED,
            reason_code="verified_assignment_only",
            explanation="Role attribution requires a verified cited assignment.",
        ),
        ConclusionPermission(
            permission_id="permission_development",
            kind=ConclusionKind.DEVELOPMENT_QUALITY,
            decision=PermissionDecision.DENIED,
            reason_code="development_not_identified",
            explanation="The evidence does not identify causal QB-development quality.",
        ),
        ConclusionPermission(
            permission_id="permission_alignment",
            kind=ConclusionKind.PLAYER_SCHEME_DESCRIPTIVE_ALIGNMENT,
            decision=PermissionDecision.ALLOWED_WITH_LIMITATIONS,
            reason_code="registered_dimensions_only",
            explanation="Only registry-approved tendencies may be aligned descriptively.",
        ),
        ConclusionPermission(
            permission_id="permission_numerical_comparison",
            kind=ConclusionKind.NUMERICAL_COMPARISON_WINNER,
            decision=PermissionDecision.ALLOWED_WITH_LIMITATIONS,
            reason_code="same_metric_direct_subtraction_only",
            explanation=(
                "A numerical difference is permitted only for the same registered metric, "
                "unit, and season; it is not an overall quality winner."
            ),
            comparison_winner_allowed=True,
        ),
        ConclusionPermission(
            permission_id="permission_predictive_fit",
            kind=ConclusionKind.PREDICTIVE_FIT,
            decision=PermissionDecision.DENIED,
            reason_code="c17_not_supported",
            explanation="C17 did not validate destination-team predictive fit.",
        ),
        ConclusionPermission(
            permission_id="permission_causal",
            kind=ConclusionKind.CAUSAL,
            decision=PermissionDecision.DENIED,
            reason_code="causation_not_identified",
            explanation="Observational evidence cannot establish causation.",
        ),
    )

    def derive(
        self,
        question_type: QuestionType,
        package: EvidencePackage,
        requested_metric: str | None,
    ) -> ConclusionResult:
        propositions: list[GroundedProposition] = []
        evidence = package.evidence
        history_metric = requested_metric if metric_unit(requested_metric or "") else None
        scheme_metric = requested_metric if requested_metric in SCHEME_FEATURE_UNITS else None
        if question_type in {
            QuestionType.QB_HISTORY,
            QuestionType.COMPARISON,
            QuestionType.CAREER_COUNTERFACTUAL,
        }:
            propositions.extend(self._history(evidence, history_metric))
        if question_type is QuestionType.QB_PROFILE:
            propositions.extend(self._profiles(evidence, requested_metric))
        if question_type in {
            QuestionType.TEAM_SCHEME,
            QuestionType.COMPARISON,
            QuestionType.CAREER_COUNTERFACTUAL,
        }:
            propositions.extend(self._scheme(evidence, scheme_metric))
        propositions.extend(self._roles(evidence))
        propositions.extend(self._contexts(evidence))
        propositions.extend(self._context_summaries(evidence))
        propositions.extend(self._pcae(evidence))
        propositions.extend(self._projections(evidence))
        propositions.extend(self._alignments(evidence))
        if question_type in {QuestionType.COMPARISON, QuestionType.COACH_EFFECT}:
            entity_order = {
                entity.id: index for index, entity in enumerate(package.resolved_entities)
            }
            propositions.extend(self._metric_comparisons(evidence, requested_metric, entity_order))
            role_comparison = self._role_comparison(evidence)
            if role_comparison is not None:
                propositions.append(role_comparison)
        unique = {item.proposition_id: item for item in propositions}
        ordered = tuple(
            sorted(unique.values(), key=lambda item: (-item.importance, item.proposition_id))[:12]
        )
        permission_ids = {item.permission_id for item in ordered}
        has_coach = any(entity.kind.value == "coach" for entity in package.resolved_entities)
        if question_type is QuestionType.COACH_EFFECT or (
            question_type is QuestionType.COMPARISON and has_coach
        ):
            permission_ids.update({"permission_development", "permission_causal"})
        if question_type in {
            QuestionType.PLAYER_TEAM_SCENARIO,
            QuestionType.PLAYER_SCHEME_ALIGNMENT,
        }:
            permission_ids.add("permission_predictive_fit")
        permissions = tuple(
            permission
            for permission in self.permissions
            if permission.permission_id in permission_ids
        )
        return ConclusionResult(ordered, permissions)

    def _metric_comparisons(
        self,
        evidence: tuple[EvidenceRecord, ...],
        requested_metric: str | None,
        entity_order: dict[str, int],
    ) -> list[GroundedProposition]:
        result = []
        for kind, value_key, name_key in (
            (EvidenceKind.QB_HISTORY, requested_metric or "epa_per_dropback", None),
            (EvidenceKind.TEAM_SCHEME, "raw_value", "feature_name"),
        ):
            records = [record for record in evidence if record.kind is kind]
            if name_key:
                records = [
                    record
                    for record in records
                    if requested_metric is None or values(record)[name_key] == requested_metric
                ]
            grouped: dict[tuple[int | None, str], list[EvidenceRecord]] = {}
            for record in records:
                fields = values(record)
                metric = fields[name_key] if name_key else value_key
                if fields.get(value_key) is not None:
                    grouped.setdefault((record.season, metric), []).append(record)
            for (season, metric), pair in grouped.items():
                if len(pair) != 2:
                    continue
                pair.sort(
                    key=lambda record: entity_order.get(record.entities[0].id, len(entity_order))
                )
                first, second = pair
                first_fields, second_fields = values(first), values(second)
                first_entity = first.entities[0]
                second_entity = second.entities[0]
                difference = first_fields[value_key] - second_fields[value_key]
                unit = first_fields.get("unit") or metric_unit(metric)
                renderer = percent if unit in {"rate", "rate_difference"} else number
                statement = (
                    f"{first_entity.display_name} was {renderer(first_fields[value_key])} and "
                    f"{second_entity.display_name} was {renderer(second_fields[value_key])} for "
                    f"{metric.replace('_', ' ')} in {season}; the direct difference was "
                    f"{renderer(difference)}."
                )
                result.append(
                    self.proposition(
                        kind=ConclusionKind.DESCRIPTIVE_COMPARISON,
                        permission_id="permission_numerical_comparison",
                        statement=statement,
                        evidence=(first, second),
                        predicate="same_metric_descriptive_comparison",
                        metric=metric,
                        value=difference,
                        unit=unit,
                        season=season,
                        qualifier=(
                            "Direct same-season, same-metric comparison; not a quality score."
                        ),
                        operation_id="subtract_compatible_metric_values",
                        importance=99,
                    )
                )
        return result

    def proposition(
        self,
        *,
        kind: ConclusionKind,
        permission_id: str,
        statement: str,
        evidence: tuple[EvidenceRecord, ...],
        predicate: str,
        subject: str | None = None,
        metric: str | None = None,
        value: str | int | float | bool | None = None,
        unit: str | None = None,
        season: int | None = None,
        qualifier: str | None = None,
        operation_id: str | None = None,
        importance: int,
    ) -> GroundedProposition:
        evidence_ids = tuple(record.evidence_id for record in evidence[:8])
        identity = {
            "kind": kind.value,
            "predicate": predicate,
            "metric": metric,
            "value": value,
            "season": season,
            "evidence_ids": evidence_ids,
            "operation_id": operation_id,
        }
        proposition_id = (
            "proposition_" + hashlib.sha256(canonical_json_bytes(identity)).hexdigest()[:20]
        )
        uncertainty_id = next(
            (record.uncertainty_id for record in evidence if record.uncertainty_id), None
        )
        return GroundedProposition(
            proposition_id=proposition_id,
            kind=kind,
            statement=statement,
            evidence_ids=evidence_ids,
            permission_id=permission_id,
            uncertainty_id=uncertainty_id,
            subject=subject,
            predicate=predicate,
            metric=metric,
            value=value,
            unit=unit,
            season=season,
            qualifier=qualifier,
            operation_id=operation_id,
            importance=importance,
        )

    def _history(
        self, evidence: tuple[EvidenceRecord, ...], requested_metric: str | None
    ) -> list[GroundedProposition]:
        result = []
        for record in evidence:
            if record.kind is not EvidenceKind.QB_HISTORY:
                continue
            fields = values(record)
            player = next(entity for entity in record.entities if entity.kind.value == "qb")
            team = next(entity for entity in record.entities if entity.kind.value == "team")
            metric = requested_metric or "epa_per_dropback"
            if fields.get(metric) is None:
                continue
            unit = metric_unit(metric)
            rendered_value = percent(fields[metric]) if unit == "rate" else number(fields[metric])
            statement = (
                f"{player.display_name} recorded {rendered_value} "
                f"{metric_display_name(metric)} for {team.display_name} in {record.season} "
                f"across {fields['dropbacks']} dropbacks."
            )
            if (
                metric == "epa_per_dropback"
                and fields.get("performance_above_expectation") is not None
            ):
                pae = fields["performance_above_expectation"]
                if pae > 0:
                    interpretation = f"outperformed it by {number(pae)} EPA/dropback"
                elif pae < 0:
                    interpretation = f"finished {number(abs(pae))} EPA/dropback below it"
                else:
                    interpretation = "matched it"
                statement += (
                    f" The preseason expectation was "
                    f"{number(fields['expected_epa_per_dropback'])}; {player.display_name} "
                    f"{interpretation} (PAE {number(pae)})."
                )
            result.append(
                self.proposition(
                    kind=ConclusionKind.HISTORICAL_FACT,
                    permission_id="permission_historical",
                    statement=statement,
                    evidence=(record,),
                    subject=player.display_name,
                    predicate="historical_qb_performance",
                    metric=metric,
                    value=fields[metric],
                    unit=unit,
                    season=record.season,
                    qualifier=(
                        f"{fields['dropbacks']} dropbacks; {fields['reliability']} reliability"
                    ),
                    importance=95,
                )
            )
        return result

    def _profiles(
        self, evidence: tuple[EvidenceRecord, ...], requested_metric: str | None
    ) -> list[GroundedProposition]:
        result = []
        for record in evidence:
            if record.kind is not EvidenceKind.QB_PROFILE:
                continue
            fields = values(record)
            feature = fields.get("feature_name")
            if feature is None or fields.get("feature_value") is None:
                continue
            if requested_metric and not feature.endswith(requested_metric):
                continue
            player = record.entities[0]
            value = fields["feature_value"]
            rendered = percent(value) if fields.get("unit") == "rate" else number(value)
            result.append(
                self.proposition(
                    kind=ConclusionKind.HISTORICAL_FACT,
                    permission_id="permission_historical",
                    statement=(
                        f"{player.display_name}'s entering-{record.season} profile recorded "
                        f"{feature_display_name(feature)} at {rendered}."
                    ),
                    evidence=(record,),
                    subject=player.display_name,
                    predicate="entering_season_profile",
                    metric=feature,
                    value=value,
                    unit=fields.get("unit"),
                    season=record.season,
                    qualifier=(
                        f"{fields.get('feature_category')} feature; "
                        f"{fields.get('reliability')} reliability"
                    ),
                    importance=90 if feature == "recent_scramble_rate" else 65,
                )
            )
        return result

    def _scheme(
        self, evidence: tuple[EvidenceRecord, ...], requested_metric: str | None
    ) -> list[GroundedProposition]:
        result = []
        for record in evidence:
            if record.kind is not EvidenceKind.TEAM_SCHEME:
                continue
            fields = values(record)
            if requested_metric and fields["feature_name"] != requested_metric:
                continue
            if fields["raw_value"] is None:
                continue
            team = record.entities[0]
            rendered = (
                percent(fields["raw_value"])
                if fields["unit"] in {"rate", "rate_difference"}
                else number(fields["raw_value"])
            )
            result.append(
                self.proposition(
                    kind=ConclusionKind.HISTORICAL_FACT,
                    permission_id="permission_historical",
                    statement=(
                        f"{possessive(team.display_name)} {record.season} "
                        f"{feature_display_name(fields['feature_name'])} was {rendered}."
                    ),
                    evidence=(record,),
                    subject=team.display_name,
                    predicate="historical_team_scheme",
                    metric=fields["feature_name"],
                    value=fields["raw_value"],
                    unit=fields["unit"],
                    season=record.season,
                    qualifier="Observed team-season behavior; not causal coach ownership.",
                    importance=80,
                )
            )
        return result

    def _roles(self, evidence: tuple[EvidenceRecord, ...]) -> list[GroundedProposition]:
        result = []
        for record in evidence:
            if record.kind is not EvidenceKind.COACH_ASSIGNMENT:
                continue
            fields = values(record)
            coach = next(entity for entity in record.entities if entity.kind.value == "coach")
            team = next(entity for entity in record.entities if entity.kind.value == "team")
            result.append(
                self.proposition(
                    kind=ConclusionKind.VERIFIED_ROLE_ATTRIBUTION,
                    permission_id="permission_role",
                    statement=(
                        f"{coach.display_name} had a verified "
                        f"{fields['role'].replace('_', ' ')} assignment with "
                        f"{team.display_name} in {record.season} "
                        f"(weeks {fields['start_week']}–{fields['end_week']}; "
                        f"{fields['interval_basis']})."
                    ),
                    evidence=(record,),
                    subject=coach.display_name,
                    predicate="verified_role_attribution",
                    metric="role",
                    value=fields["role"],
                    season=record.season,
                    qualifier="Verified source-backed assignment.",
                    importance=85,
                )
            )
        return result

    def _contexts(self, evidence: tuple[EvidenceRecord, ...]) -> list[GroundedProposition]:
        result = []
        for record in evidence:
            if record.kind is not EvidenceKind.COACH_QB_CONTEXT:
                continue
            coach = next(entity for entity in record.entities if entity.kind.value == "coach")
            qb = next(entity for entity in record.entities if entity.kind.value == "qb")
            result.append(
                self.proposition(
                    kind=ConclusionKind.HISTORICAL_FACT,
                    permission_id="permission_historical",
                    statement=(
                        f"{qb.display_name} and {coach.display_name} share verified "
                        f"same-team-season context in {record.season}."
                    ),
                    evidence=(record,),
                    subject=qb.display_name,
                    predicate="same_team_season_context",
                    season=record.season,
                    qualifier="This does not establish exact weekly QB-coach exposure.",
                    importance=88,
                )
            )
        return result

    def _context_summaries(self, evidence: tuple[EvidenceRecord, ...]) -> list[GroundedProposition]:
        result = []
        for record in evidence:
            if record.kind is not EvidenceKind.SUMMARY:
                continue
            fields = values(record)
            if "distinct_qb_team_seasons" not in fields:
                continue
            coach = next(
                (entity for entity in record.entities if entity.kind.value == "coach"), None
            )
            if coach is None:
                continue
            count = fields["distinct_qb_team_seasons"]
            if not fields.get("young_filter_applied"):
                result.append(
                    self.proposition(
                        kind=ConclusionKind.HISTORICAL_FACT,
                        permission_id="permission_historical",
                        statement=(
                            f"{coach.display_name} has {count} distinct verified "
                            "same-team-season QB context observations in the selected scope."
                        ),
                        evidence=(record,),
                        subject=coach.display_name,
                        predicate="qb_context_summary",
                        metric="distinct_qb_team_seasons",
                        value=count,
                        qualifier=(
                            "Descriptive same-team-season context; not exact weekly exposure "
                            "or development quality."
                        ),
                        importance=97,
                    )
                )
                continue
            missing = fields["missing_age_excluded_count"]
            missing_label = "observation" if missing == 1 else "observations"
            missing_verb = "was" if missing == 1 else "were"
            result.append(
                self.proposition(
                    kind=ConclusionKind.HISTORICAL_FACT,
                    permission_id="permission_historical",
                    statement=(
                        f"{coach.display_name} has {count} distinct QB-team-season context "
                        f"observations with age under 25 at season start; {missing} "
                        f"missing-age {missing_label} {missing_verb} excluded."
                    ),
                    evidence=(record,),
                    subject=coach.display_name,
                    predicate="young_qb_context_summary",
                    metric="distinct_qb_team_seasons",
                    value=count,
                    qualifier="Descriptive same-team-season context; not development quality.",
                    importance=97,
                )
            )
        return result

    def _pcae(self, evidence: tuple[EvidenceRecord, ...]) -> list[GroundedProposition]:
        result = []
        for record in evidence:
            if record.kind is not EvidenceKind.PCAE:
                continue
            fields = values(record)
            coach = next(entity for entity in record.entities if entity.kind.value == "coach")
            result.append(
                self.proposition(
                    kind=ConclusionKind.HISTORICAL_FACT,
                    permission_id="permission_historical",
                    statement=(
                        f"{coach.display_name}'s research-only PCAE was "
                        f"{number(fields['pcae'])} for the verified weeks "
                        f"{fields['start_week']}–{fields['end_week']} interval "
                        f"in {record.season}."
                    ),
                    evidence=(record,),
                    subject=coach.display_name,
                    predicate="observational_pcae",
                    metric="pcae",
                    value=fields["pcae"],
                    unit="call_value_difference",
                    season=record.season,
                    qualifier="Observational evidence; not QB development impact.",
                    importance=60,
                )
            )
        return result

    def _projections(self, evidence: tuple[EvidenceRecord, ...]) -> list[GroundedProposition]:
        result = []
        for record in evidence:
            if record.kind is not EvidenceKind.QB_PROJECTION:
                continue
            fields = values(record)
            player = record.entities[0]
            result.append(
                self.proposition(
                    kind=ConclusionKind.HISTORICAL_FACT,
                    permission_id="permission_historical",
                    statement=(
                        f"The approved team-independent research model projects "
                        f"{player.display_name} "
                        f"at {number(fields['prediction'])} EPA/dropback in 2026, with a "
                        f"published 95% historical-residual band of "
                        f"{number(fields['lower_95'])} to {number(fields['upper_95'])}."
                    ),
                    evidence=(record,),
                    subject=player.display_name,
                    predicate="team_independent_epa_projection",
                    metric="epa_per_dropback",
                    value=fields["prediction"],
                    unit="epa_per_dropback",
                    season=2026,
                    qualifier="No destination-team, playing-time, roster, or forward-PAE claim.",
                    importance=100,
                )
            )
        return result

    def _alignments(self, evidence: tuple[EvidenceRecord, ...]) -> list[GroundedProposition]:
        result = []
        for record in evidence:
            if record.kind is not EvidenceKind.PLAYER_SCHEME_ALIGNMENT:
                continue
            fields = values(record)
            player = next(entity for entity in record.entities if entity.kind.value == "qb")
            team = next(entity for entity in record.entities if entity.kind.value == "team")
            renderer = percent if fields["comparison_unit"] == "rate" else number
            result.append(
                self.proposition(
                    kind=ConclusionKind.PLAYER_SCHEME_DESCRIPTIVE_ALIGNMENT,
                    permission_id="permission_alignment",
                    statement=(
                        f"{player.display_name}'s measured "
                        f"{feature_display_name(fields['player_feature'])} was "
                        f"{renderer(fields['player_value'])}; {possessive(team.display_name)} "
                        f"historical {feature_display_name(fields['scheme_feature'])} was "
                        f"{renderer(fields['scheme_value'])}."
                    ),
                    evidence=(record,),
                    subject=player.display_name,
                    predicate="descriptive_player_scheme_alignment",
                    metric=fields["scheme_feature"],
                    value=fields["scheme_value"],
                    unit=fields["comparison_unit"],
                    season=record.season,
                    qualifier="Comparable measured tendencies only; not predictive fit.",
                    importance=82,
                )
            )
        return result

    def _role_comparison(self, evidence: tuple[EvidenceRecord, ...]) -> GroundedProposition | None:
        roles: dict[str, set[str]] = {}
        records: dict[str, list[EvidenceRecord]] = {}
        for record in evidence:
            if record.kind is not EvidenceKind.SUMMARY:
                continue
            fields = values(record)
            coach = next(
                (entity for entity in record.entities if entity.kind.value == "coach"), None
            )
            if coach is None:
                continue
            records.setdefault(coach.display_name, []).append(record)
            if "verified_roles" in fields:
                roles[coach.display_name] = {
                    role for role in str(fields["verified_roles"]).split("|") if role
                }
        if len(roles) == 2:
            return self._render_role_comparison(roles, records)
        for record in evidence:
            if record.kind is not EvidenceKind.COACH_ASSIGNMENT:
                continue
            fields = values(record)
            coach = next(entity for entity in record.entities if entity.kind.value == "coach")
            roles.setdefault(coach.display_name, set()).add(str(fields["role"]))
            records.setdefault(coach.display_name, []).append(record)
        return self._render_role_comparison(roles, records)

    def _render_role_comparison(
        self,
        roles: dict[str, set[str]],
        records: dict[str, list[EvidenceRecord]],
    ) -> GroundedProposition | None:
        if len(roles) != 2:
            return None
        names = list(roles)
        direct = {"play_caller", "offensive_coordinator", "quarterbacks_coach"}
        first = roles[names[0]] & direct
        second = roles[names[1]] & direct
        if bool(first) == bool(second):
            statement = (
                "The verified role evidence does not establish a uniquely clearer direct "
                "offensive/QB attribution between the two coaches."
            )
            outcome = "mixed_verified_role_evidence"
        else:
            leader = names[0] if first else names[1]
            statement = (
                f"{leader} has clearer directly verified offensive/QB-role attribution in "
                "the available comparison evidence; this is not proof of better QB development."
            )
            outcome = "clearer_direct_offensive_attribution"
        all_records = tuple(record for name in names for record in records[name])
        return self.proposition(
            kind=ConclusionKind.DESCRIPTIVE_COMPARISON,
            permission_id="permission_descriptive",
            statement=statement,
            evidence=all_records,
            predicate="verified_role_evidence_comparison",
            metric="role_coverage",
            value=outcome,
            qualifier="Role attribution only; development quality and causation are denied.",
            importance=98,
        )
