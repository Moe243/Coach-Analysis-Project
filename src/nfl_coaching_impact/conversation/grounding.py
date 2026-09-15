"""Compact provider payload construction and fail-closed grounded rendering."""

from __future__ import annotations

from pydantic import ValidationError

from .contracts import (
    AskV2Response,
    GroundedSynthesisProposal,
    ProviderEvidenceRecord,
    ProviderFollowUp,
    ProviderLimitation,
    ProviderSynthesisInput,
    ProviderUnsupportedPortion,
    PublicEvidencePoint,
)
from .enums import AnswerMode, PermissionDecision, SynthesisSectionKind, SynthesisStyle
from .orchestration import AuthoritativeResult
from .providers import MAX_PROVIDER_PAYLOAD_BYTES, ProviderPayloadTooLarge
from .serialization import canonical_json_bytes


class GroundingRejected(ValueError):
    """A structured provider selection violated backend-owned grounding rules."""


_STYLE_INTRO = {
    SynthesisStyle.CONCISE: "The clearest answer from the approved evidence is:",
    SynthesisStyle.EXPLANATORY: "Here is what the approved evidence supports:",
    SynthesisStyle.COMPARATIVE: "The most defensible comparison is:",
    SynthesisStyle.CONTEXTUAL: "In the context available to this project:",
}

_SECTION_HEADING = {
    SynthesisSectionKind.KEY_EVIDENCE: "Key evidence",
    SynthesisSectionKind.CONTEXT: "Context",
    SynthesisSectionKind.UNCERTAINTY: "Uncertainty",
}


def provider_synthesis_input(question: str, result: AuthoritativeResult) -> ProviderSynthesisInput:
    """Remove source material and retain only compact authorized analytical units."""
    referenced = {
        evidence_id
        for proposition in result.conclusions.propositions
        for evidence_id in proposition.evidence_ids
    }
    compact_evidence = tuple(
        ProviderEvidenceRecord(
            evidence_id=record.evidence_id,
            kind=record.kind,
            summary=record.summary,
            entities=record.entities,
            season=record.season,
            values=record.values,
            uncertainty_id=record.uncertainty_id,
            operation_id=record.operation_id,
        )
        for record in result.package.evidence
        if record.evidence_id in referenced
    )
    payload = ProviderSynthesisInput(
        question=question,
        answerability=result.response.answerability,
        entities=result.response.entities,
        propositions=result.conclusions.propositions,
        evidence=compact_evidence,
        permissions=result.conclusions.permissions,
        uncertainty=result.response.uncertainty,
        limitations=tuple(
            ProviderLimitation(limitation_id=f"limitation_{index}", text=text)
            for index, text in enumerate(result.response.limitations, start=1)
        ),
        unsupported=tuple(
            ProviderUnsupportedPortion(unsupported_id=f"unsupported_{index}", portion=portion)
            for index, portion in enumerate(result.response.unsupported_portions, start=1)
        ),
        followups=tuple(
            ProviderFollowUp(followup_id=f"followup_{index}", followup=followup)
            for index, followup in enumerate(result.response.follow_ups, start=1)
        ),
    )
    if len(canonical_json_bytes(payload)) > MAX_PROVIDER_PAYLOAD_BYTES:
        raise ProviderPayloadTooLarge("provider synthesis payload exceeds 48 KiB")
    return payload


def validate_synthesis(
    untrusted: object, payload: ProviderSynthesisInput
) -> GroundedSynthesisProposal:
    try:
        proposal = GroundedSynthesisProposal.model_validate(untrusted)
    except ValidationError as error:
        raise GroundingRejected("synthesis output does not match the strict schema") from error

    propositions = {item.proposition_id: item for item in payload.propositions}
    evidence = {item.evidence_id: item for item in payload.evidence}
    permissions = {item.permission_id: item for item in payload.permissions}
    limitation_ids = {item.limitation_id for item in payload.limitations}
    unsupported_ids = {item.unsupported_id for item in payload.unsupported}
    followup_ids = {item.followup_id for item in payload.followups}
    selected_ids = [
        *proposal.direct_proposition_ids,
        *(item for section in proposal.sections for item in section.proposition_ids),
    ]
    if any(item not in propositions for item in selected_ids):
        raise GroundingRejected("synthesis references an unknown proposition")
    if any(item not in evidence for item in proposal.evidence_ids):
        raise GroundingRejected("synthesis references unknown evidence")
    if set(proposal.limitation_ids) != limitation_ids:
        raise GroundingRejected("synthesis omitted or invented a required limitation")
    if set(proposal.unsupported_ids) != unsupported_ids:
        raise GroundingRejected("synthesis omitted or invented an unsupported portion")
    if not set(proposal.followup_ids) <= followup_ids:
        raise GroundingRejected("synthesis invented an unsupported follow-up")

    selected_evidence = {
        evidence_id for item in selected_ids for evidence_id in propositions[item].evidence_ids
    }
    if not set(proposal.evidence_ids) <= selected_evidence:
        raise GroundingRejected("evidence is not attached to a selected proposition")
    if selected_evidence and not proposal.evidence_ids:
        raise GroundingRejected("grounded synthesis omitted supporting evidence")
    for item in selected_ids:
        permission = permissions.get(propositions[item].permission_id)
        if permission is None or permission.decision is PermissionDecision.DENIED:
            raise GroundingRejected("synthesis selected a proposition without permission")
    return proposal


def render_grounded_response(
    result: AuthoritativeResult,
    payload: ProviderSynthesisInput,
    proposal: GroundedSynthesisProposal,
    *,
    planner_implementation_version: str,
    planner_model_version: str,
    synthesizer_implementation_version: str,
    synthesizer_model_version: str,
):
    """Render only server-authored proposition text and server-authored qualifications."""
    propositions = {item.proposition_id: item for item in payload.propositions}
    evidence = {item.evidence_id: item for item in payload.evidence}
    limitations = {item.limitation_id: item.text for item in payload.limitations}
    unsupported = {item.unsupported_id: item.portion for item in payload.unsupported}
    followups = {item.followup_id: item.followup for item in payload.followups}

    paragraphs = [_STYLE_INTRO[proposal.style]]
    paragraphs.append(
        " ".join(propositions[item].statement for item in proposal.direct_proposition_ids)
    )
    for section in proposal.sections:
        text = " ".join(propositions[item].statement for item in section.proposition_ids)
        paragraphs.append(f"{_SECTION_HEADING[section.kind]}: {text}")
    qualifiers = tuple(
        dict.fromkeys(
            propositions[item].qualifier
            for item in [
                *proposal.direct_proposition_ids,
                *(claim for section in proposal.sections for claim in section.proposition_ids),
            ]
            if propositions[item].qualifier
        )
    )
    if qualifiers:
        paragraphs.append("Qualification: " + " ".join(qualifiers))
    if any("usage feature" in qualifier.lower() for qualifier in qualifiers):
        paragraphs.append("This describes usage, not its efficiency or a player grade.")
    if proposal.unsupported_ids:
        paragraphs.append(
            "Not supported: "
            + " ".join(unsupported[item].explanation for item in proposal.unsupported_ids)
        )
    answer = "\n\n".join(paragraphs)
    versions = result.response.versions.model_copy(
        update={
            "planner_implementation_version": planner_implementation_version,
            "planner_model_version": planner_model_version,
            "synthesizer_implementation_version": synthesizer_implementation_version,
            "synthesizer_model_version": synthesizer_model_version,
            "answer_mode": AnswerMode.GROUNDED_AI,
        }
    )
    return AskV2Response.model_validate(
        {
            **result.response.model_dump(mode="python"),
            "answer_mode": AnswerMode.GROUNDED_AI,
            "answer": answer,
            "evidence": tuple(
                PublicEvidencePoint(
                    rank=index,
                    evidence_id=evidence_id,
                    summary=evidence[evidence_id].summary,
                )
                for index, evidence_id in enumerate(proposal.evidence_ids, start=1)
            ),
            "limitations": tuple(limitations[item] for item in proposal.limitation_ids),
            "unsupported_portions": tuple(unsupported[item] for item in proposal.unsupported_ids),
            "follow_ups": tuple(followups[item] for item in proposal.followup_ids),
            "versions": versions,
        }
    )
