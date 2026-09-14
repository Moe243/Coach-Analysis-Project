"""Strict request, planner, evidence, and response contracts for Ask Anything v2."""

from __future__ import annotations

import hashlib
import re
from typing import Annotated, Any, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from .enums import (
    AnalyticalTask,
    Answerability,
    AnswerMode,
    ConclusionKind,
    ContextDependency,
    ConversationRole,
    EntityKind,
    EvidenceKind,
    PermissionDecision,
    QuestionType,
    ReasonCode,
    Reliability,
    RequestedOutput,
    ResolutionStatus,
)
from .policy import SCIENTIFIC_POLICY_VERSION
from .serialization import canonical_json_bytes

ASK_V2_CONTRACT_VERSION = "ask-v2"
STAGE_A_IMPLEMENTATION_VERSION = "ask-v2-stage-a"
MIN_SEASON = 2010
MAX_SEASON = 2026

ShortText = Annotated[str, StringConstraints(min_length=1, max_length=200, strip_whitespace=True)]
ReasonText = Annotated[str, StringConstraints(min_length=1, max_length=500, strip_whitespace=True)]
Identifier = Annotated[
    str,
    StringConstraints(pattern=r"^[a-z][a-z0-9_-]{0,99}$", strip_whitespace=True),
]
ScalarValue = str | int | float | bool | None


class ContractModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        allow_inf_nan=False,
    )


class ConversationTurn(ContractModel):
    role: ConversationRole
    content: str = Field(min_length=1, max_length=8_000)


class CanonicalEntityReference(ContractModel):
    kind: EntityKind
    id: str = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_identifier(self) -> Self:
        patterns = {
            EntityKind.QB: r"^(?:00-\d{7}|[A-Z]{3}\d{6})$",
            EntityKind.COACH: r"^coach-[a-z0-9]+(?:-[a-z0-9]+)*$",
            EntityKind.TEAM: r"^team_[a-z0-9]+$",
        }
        if not re.fullmatch(patterns[self.kind], self.id):
            raise ValueError(f"invalid canonical {self.kind.value} identifier")
        return self


class SeasonContext(ContractModel):
    start_season: int = Field(ge=MIN_SEASON, le=MAX_SEASON)
    end_season: int = Field(ge=MIN_SEASON, le=MAX_SEASON)

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        if self.start_season > self.end_season:
            raise ValueError("start_season must not exceed end_season")
        return self


class ConversationContext(ContractModel):
    turns: tuple[ConversationTurn, ...] = Field(default=(), max_length=8)
    entities: tuple[CanonicalEntityReference, ...] = Field(default=(), max_length=8)
    seasons: SeasonContext | None = None

    @model_validator(mode="after")
    def validate_and_normalize(self) -> Self:
        if sum(len(turn.content) for turn in self.turns) > 8_000:
            raise ValueError("conversation context exceeds 8000 characters")
        keys = [(entity.kind.value, entity.id) for entity in self.entities]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate canonical entity reference")
        object.__setattr__(
            self,
            "entities",
            tuple(sorted(self.entities, key=lambda entity: (entity.kind.value, entity.id))),
        )
        return self


class AskV2Request(ContractModel):
    question: str = Field(min_length=3, max_length=1_000)
    context: ConversationContext = Field(default_factory=ConversationContext)


class ResolvedEntity(CanonicalEntityReference):
    display_name: ShortText


class EntityResolution(ContractModel):
    mention: ShortText
    kind: EntityKind
    status: ResolutionStatus
    resolved: tuple[ResolvedEntity, ...] = Field(default=(), max_length=8)
    candidates: tuple[ResolvedEntity, ...] = Field(default=(), max_length=5)
    lookup_authorized: bool

    @model_validator(mode="after")
    def validate_resolution(self) -> Self:
        if self.lookup_authorized != (self.status is ResolutionStatus.EXACT):
            raise ValueError("only exact resolution may authorize analytical lookup")
        if self.status is ResolutionStatus.EXACT and len(self.resolved) != 1:
            raise ValueError("exact resolution requires one canonical entity")
        if self.status is not ResolutionStatus.EXACT and self.resolved:
            raise ValueError("non-exact resolution cannot contain an authorized entity")
        if self.status is ResolutionStatus.AMBIGUOUS and not self.candidates:
            raise ValueError("ambiguous resolution requires candidates")
        return self


_UNSAFE_ENTITY_MENTION = re.compile(
    r"(?i)(?:[a-z][a-z0-9+.-]*://|\bwww\.|(?:^|\s)[~/\\]|\$\(|`|\r|\n)"
)


class PlannerEntityProposal(ContractModel):
    kind: EntityKind
    mention: str = Field(min_length=1, max_length=100)
    canonical_id_hint: CanonicalEntityReference | None = None

    @field_validator("mention")
    @classmethod
    def reject_executable_or_location_like_mentions(cls, value: str) -> str:
        if _UNSAFE_ENTITY_MENTION.search(value):
            raise ValueError("entity mention may not contain a URL, path, or executable syntax")
        return value

    @model_validator(mode="after")
    def validate_hint_kind(self) -> Self:
        if self.canonical_id_hint and self.canonical_id_hint.kind is not self.kind:
            raise ValueError("canonical_id_hint kind does not match entity proposal kind")
        return self


class AnalyticalTaskProposal(ContractModel):
    task: AnalyticalTask
    entity_indexes: tuple[int, ...] = Field(default=(), max_length=8)
    seasons: SeasonContext | None = None

    @field_validator("entity_indexes")
    @classmethod
    def validate_entity_indexes(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        if any(index < 0 or index > 7 for index in value):
            raise ValueError("planner entity index is outside the bounded proposal")
        if len(value) != len(set(value)):
            raise ValueError("duplicate planner entity index")
        return value


class PlannerProposal(ContractModel):
    question_type: QuestionType
    entities: tuple[PlannerEntityProposal, ...] = Field(default=(), max_length=8)
    tasks: tuple[AnalyticalTaskProposal, ...] = Field(default=(), max_length=12)
    requested_outputs: tuple[RequestedOutput, ...] = Field(default=(), max_length=5)
    context_dependencies: tuple[ContextDependency, ...] = Field(default=(), max_length=4)

    @model_validator(mode="after")
    def validate_and_normalize(self) -> Self:
        for task in self.tasks:
            if any(index >= len(self.entities) for index in task.entity_indexes):
                raise ValueError("planner task references an absent entity proposal")
        object.__setattr__(
            self,
            "requested_outputs",
            tuple(sorted(set(self.requested_outputs), key=lambda item: item.value)),
        )
        object.__setattr__(
            self,
            "context_dependencies",
            tuple(sorted(set(self.context_dependencies), key=lambda item: item.value)),
        )
        return self


class ApprovedTask(ContractModel):
    task_id: Identifier
    task: AnalyticalTask
    entities: tuple[CanonicalEntityReference, ...] = Field(default=(), max_length=8)
    seasons: SeasonContext | None = None
    authorization_reason: ReasonText


class RejectedTask(ContractModel):
    task_id: Identifier
    task: AnalyticalTask
    reason_code: ReasonCode
    explanation: ReasonText


class EvidenceValue(ContractModel):
    name: Identifier
    value: ScalarValue
    unit: ShortText | None = None


class SourceReference(ContractModel):
    artifact: ShortText
    data_version: ShortText
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    row_key: ShortText | None = None
    source_url: str | None = Field(default=None, max_length=2_000)
    source_title: ShortText | None = None
    source_type: ShortText | None = None
    source_accessed_at: ShortText | None = None
    evidence_locator: ReasonText | None = None
    evidence_note: ReasonText | None = None


class EvidenceRecord(ContractModel):
    evidence_id: Identifier
    kind: EvidenceKind
    summary: ReasonText
    entities: tuple[ResolvedEntity, ...] = Field(default=(), max_length=8)
    season: int | None = Field(default=None, ge=MIN_SEASON, le=MAX_SEASON)
    values: tuple[EvidenceValue, ...] = Field(default=(), max_length=16)
    sources: tuple[SourceReference, ...] = Field(default=(), max_length=4)
    uncertainty_id: Identifier | None = None
    operation_id: Identifier | None = None
    sample_count: int | None = Field(default=None, ge=0)
    source_evidence_ids: tuple[Identifier, ...] = Field(default=(), max_length=32)


class UncertaintyRepresentation(ContractModel):
    uncertainty_id: Identifier
    method: ShortText
    standard_error: float | None = None
    lower: float | None = None
    upper: float | None = None
    confidence_level: float | None = Field(default=None, gt=0, lt=1)
    reliability: Reliability
    explanation: ReasonText

    @model_validator(mode="after")
    def validate_interval(self) -> Self:
        if self.lower is not None and self.upper is not None and self.lower > self.upper:
            raise ValueError("uncertainty lower bound must not exceed upper bound")
        return self


class ConclusionPermission(ContractModel):
    permission_id: Identifier
    kind: ConclusionKind
    decision: PermissionDecision
    reason_code: Identifier
    explanation: ReasonText
    evidence_ids: tuple[Identifier, ...] = Field(default=(), max_length=8)
    permitted_numeric_fields: tuple[Identifier, ...] = Field(default=(), max_length=12)
    comparison_winner_allowed: bool = False


class GroundedProposition(ContractModel):
    proposition_id: Identifier
    kind: ConclusionKind
    statement: ReasonText
    evidence_ids: tuple[Identifier, ...] = Field(default=(), max_length=8)
    permission_id: Identifier
    uncertainty_id: Identifier | None = None


class UnsupportedRequestedPortion(ContractModel):
    description: ReasonText
    reason_code: ReasonCode
    explanation: ReasonText


class SupportedFollowUp(ContractModel):
    label: ShortText
    question: str = Field(min_length=3, max_length=1_000)


class PublicEvidencePoint(ContractModel):
    rank: int = Field(ge=1, le=5)
    evidence_id: Identifier
    summary: ReasonText


class PublicVersionMetadata(ContractModel):
    ask_contract_version: Literal["ask-v2"] = ASK_V2_CONTRACT_VERSION
    contract_schema_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    scientific_policy_version: str
    analytical_data_version: str | None = None
    analytical_model_versions: tuple[ShortText, ...] = ()
    evidence_reducer_version: str | None = None
    planner_implementation_version: str
    planner_model_version: str | None = None
    synthesizer_implementation_version: str
    synthesizer_model_version: str | None = None
    answer_mode: AnswerMode


class EvidencePackage(ContractModel):
    answerability: Answerability
    resolved_entities: tuple[ResolvedEntity, ...] = Field(default=(), max_length=8)
    approved_tasks: tuple[ApprovedTask, ...] = Field(default=(), max_length=12)
    rejected_tasks: tuple[RejectedTask, ...] = Field(default=(), max_length=12)
    evidence: tuple[EvidenceRecord, ...] = Field(default=(), max_length=32)
    uncertainty: tuple[UncertaintyRepresentation, ...] = Field(default=(), max_length=32)
    propositions: tuple[GroundedProposition, ...] = Field(default=(), max_length=12)
    conclusion_permissions: tuple[ConclusionPermission, ...] = Field(default=(), max_length=8)
    unsupported_portions: tuple[UnsupportedRequestedPortion, ...] = Field(default=(), max_length=8)
    limitations: tuple[ReasonText, ...] = Field(default=(), max_length=12)
    versions: PublicVersionMetadata


class AskV2Response(ContractModel):
    contract_version: Literal["ask-v2"] = ASK_V2_CONTRACT_VERSION
    answerability: Answerability
    answer_mode: AnswerMode
    reason_code: ReasonCode | None = None
    answer: str = Field(min_length=1, max_length=4_000)
    entities: tuple[ResolvedEntity, ...] = Field(default=(), max_length=8)
    evidence: tuple[PublicEvidencePoint, ...] = Field(default=(), max_length=5)
    propositions: tuple[GroundedProposition, ...] = Field(default=(), max_length=12)
    uncertainty: tuple[UncertaintyRepresentation, ...] = Field(default=(), max_length=12)
    unsupported_portions: tuple[UnsupportedRequestedPortion, ...] = Field(default=(), max_length=8)
    follow_ups: tuple[SupportedFollowUp, ...] = Field(default=(), max_length=4)
    versions: PublicVersionMetadata

    @model_validator(mode="after")
    def validate_response_consistency(self) -> Self:
        if self.answer_mode is not self.versions.answer_mode:
            raise ValueError("response and version answer modes must match")
        ranks = [point.rank for point in self.evidence]
        if ranks != list(range(1, len(ranks) + 1)):
            raise ValueError("public evidence ranks must be contiguous and ordered")
        return self


def contract_schema_sha256() -> str:
    schemas: dict[str, Any] = {
        model.__name__: model.model_json_schema()
        for model in (
            AskV2Request,
            PlannerProposal,
            EvidencePackage,
            AskV2Response,
        )
    }
    return hashlib.sha256(canonical_json_bytes(schemas)).hexdigest()


def stage_a_versions() -> PublicVersionMetadata:
    return PublicVersionMetadata(
        contract_schema_sha256=contract_schema_sha256(),
        scientific_policy_version=SCIENTIFIC_POLICY_VERSION,
        planner_implementation_version=STAGE_A_IMPLEMENTATION_VERSION,
        synthesizer_implementation_version=STAGE_A_IMPLEMENTATION_VERSION,
        answer_mode=AnswerMode.DETERMINISTIC,
    )
