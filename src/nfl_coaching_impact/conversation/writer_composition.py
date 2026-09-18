"""Untrusted composition instructions; factual language remains backend-owned."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from enum import StrEnum

from pydantic import Field, ValidationError, model_validator

from .answer_writer import (
    ApprovedAnswerBrief,
    BriefSupportKind,
    WriterRejected,
    WriterResult,
    WriterSentence,
    validate_writer_result,
)
from .contracts import ContractModel
from .enums import QuestionType
from .providers import WriterValidationCategory
from .serialization import canonical_json_bytes


class Connector(StrEnum):
    NONE = "none"
    CONTINUATION = "continuation"
    CONTRAST = "contrast"
    COMPARISON = "comparison"
    LIMITATION_TRANSITION = "limitation_transition"


_CONNECTORS = {
    Connector.NONE: ("",),
    Connector.CONTINUATION: ("Also, ", "Additionally, ", "In addition, "),
    Connector.CONTRAST: ("However, ", "In contrast, ", "By contrast, "),
    Connector.COMPARISON: ("Meanwhile, ", "For comparison, ", "By comparison, "),
    Connector.LIMITATION_TRANSITION: (
        "For context, ",
        "To put that in context, ",
        "For perspective, ",
    ),
}


def _render_composition(plan: CompositionPlan, by_id: Mapping[str, ApprovedPhrase]) -> str:
    """Vary surfaces within their class, never facts or connector semantics.

    Remember the preceding two clauses across paragraph boundaries, including
    unprefixed clauses. Three equivalent surfaces prevent adjacent/near-adjacent
    repetition without randomness, provider prose or changing semantic class.
    """
    recent: list[str] = []
    paragraphs = []
    for paragraph in plan.paragraphs:
        clauses = []
        for item in paragraph.items:
            variants = _CONNECTORS[item.connector]
            surface = next((text for text in variants if text not in recent), variants[0])
            clauses.append(surface + by_id[item.phrase_id].text)
            recent = [*recent[-1:], surface]
        paragraphs.append(" ".join(clauses))
    return "\n\n".join(paragraphs)


class CompositionItem(ContractModel):
    phrase_id: str = Field(pattern=r"^phrase_[0-9a-f]{16}$")
    connector: Connector


class CompositionParagraph(ContractModel):
    items: tuple[CompositionItem, ...] = Field(min_length=1, max_length=8)


class CompositionPlan(ContractModel):
    paragraphs: tuple[CompositionParagraph, ...] = Field(min_length=1, max_length=3)

    @model_validator(mode="after")
    def bounded_unique_items(self):
        items = [item for paragraph in self.paragraphs for item in paragraph.items]
        if len(items) > 16 or len({item.phrase_id for item in items}) != len(items):
            raise ValueError("composition must contain at most 16 unique phrases")
        if items[0].connector is not Connector.NONE:
            raise ValueError("the answer must not begin with a connective")
        return self


class ApprovedPhrase(ContractModel):
    phrase_id: str
    support_id: str
    kind: BriefSupportKind
    text: str
    entity_ids: tuple[str, ...]
    measurement_ids: tuple[str, ...]


def approved_phrases(brief: ApprovedAnswerBrief) -> tuple[ApprovedPhrase, ...]:
    """Bind each variant to its exact backend fact, values and entity/season scope."""
    phrases = []
    for support in brief.supports:
        measurements = tuple(m for m in brief.measurements if m.support_id == support.support_id)
        for text in dict.fromkeys(support.phrasings or (support.text,)):
            identity = canonical_json_bytes(
                {
                    "support": support,
                    "text": text,
                    "measurements": measurements,
                    "entities": brief.entities,
                    "question_type": brief.question_type,
                }
            )
            phrases.append(
                ApprovedPhrase(
                    phrase_id="phrase_" + hashlib.sha256(identity).hexdigest()[:16],
                    support_id=support.support_id,
                    kind=support.kind,
                    text=text,
                    entity_ids=support.entity_ids,
                    measurement_ids=tuple(m.measurement_id for m in measurements),
                )
            )
    return tuple(phrases)


def composition_provider_input(brief: ApprovedAnswerBrief) -> dict:
    """Compact wire catalog; IDs select prose, never confer analytical authority."""
    phrases = approved_phrases(brief)
    payload = {
        "question_type": brief.question_type,
        "topic": brief.topic,
        "maximum_words": brief.maximum_words,
        "required_fact": brief.supports[0].support_id,
        "required_limitations": brief.required_limitation_ids,
        "phrases": [
            {"phrase_id": p.phrase_id, "support_id": p.support_id, "kind": p.kind, "text": p.text}
            for p in phrases
        ],
    }
    if brief.question_type is QuestionType.PLAYER_TEAM_SCENARIO:
        payload["composition_rules"] = {
            "facts_before_limitations": True,
            "minimum_facts": min(
                2, sum(s.kind is BriefSupportKind.PROPOSITION for s in brief.supports)
            ),
            "limitation_connector": Connector.NONE,
        }
    return payload


def validate_composition(
    untrusted: object, brief: ApprovedAnswerBrief, *, catalog: Mapping[str, str]
) -> str:
    """Validate atomically and render only exact approved phrases and safe connectors."""
    try:
        plan = CompositionPlan.model_validate(untrusted)
    except ValidationError as error:
        raise WriterRejected(
            WriterValidationCategory.SCHEMA_INVALID, "invalid composition schema"
        ) from error
    by_id = {phrase.phrase_id: phrase for phrase in approved_phrases(brief)}
    items = [item for paragraph in plan.paragraphs for item in paragraph.items]
    if any(item.phrase_id not in by_id for item in items):
        raise WriterRejected(
            WriterValidationCategory.UNKNOWN_SUPPORT_ID, "unknown or out-of-context approved phrase"
        )
    chosen = [by_id[item.phrase_id] for item in items]
    if len({p.support_id for p in chosen}) != len(chosen):
        raise WriterRejected(
            WriterValidationCategory.UNKNOWN_SUPPORT_ID,
            "repeated support through different variants",
        )
    facts = [p for p in chosen if p.kind is not BriefSupportKind.LIMITATION]
    limitations = [p for p in chosen if p.kind is BriefSupportKind.LIMITATION]
    if not facts or len(facts) > 8 or chosen[0].kind is not BriefSupportKind.PROPOSITION:
        raise WriterRejected(
            WriterValidationCategory.SCHEMA_INVALID,
            "composition must lead with a fact and contain at most eight facts",
        )
    if brief.question_type is QuestionType.PLAYER_TEAM_SCENARIO:
        available = sum(s.kind is BriefSupportKind.PROPOSITION for s in brief.supports)
        actual = sum(p.kind is BriefSupportKind.PROPOSITION for p in facts)
        first_limit = next(
            (i for i, p in enumerate(chosen) if p.kind is BriefSupportKind.LIMITATION), len(chosen)
        )
        if (
            actual < min(2, available)
            or any(p.kind is not BriefSupportKind.LIMITATION for p in chosen[first_limit:])
            or any(
                item.connector is not Connector.NONE
                for item, p in zip(items, chosen, strict=True)
                if p.kind is BriefSupportKind.LIMITATION
            )
        ):
            raise WriterRejected(
                WriterValidationCategory.SCHEMA_INVALID,
                "scenario needs useful comparisons before unprefixed caveats",
            )
    for item, phrase in zip(items, chosen, strict=True):
        if item.connector is Connector.LIMITATION_TRANSITION and (
            phrase.kind is not BriefSupportKind.LIMITATION
        ):
            raise WriterRejected(
                WriterValidationCategory.SCHEMA_INVALID,
                "limitation connector requires a limitation",
            )

    def sentence(phrases):
        return WriterSentence(
            text=" ".join(p.text for p in phrases),
            support_ids=tuple(p.support_id for p in phrases),
            entity_ids=tuple(dict.fromkeys(e for p in phrases for e in p.entity_ids)),
            measurement_ids=tuple(dict.fromkeys(m for p in phrases for m in p.measurement_ids)),
        )

    # Preserve the numeric/entity/polarity/causal/predictive defenses. The legacy
    # text schema is internal here, never accepted from the composition provider.
    # A former QB may later be a coach with the same display name (Scott
    # Tolzien). Prefer the canonical identity resolved in this backend brief,
    # not the global single-name alias map's last-value-wins identity. Keep
    # the rest of the catalog to detect any unrelated football names.
    resolved_catalog = dict(catalog)
    for entity in brief.entities:
        resolved_catalog[entity.display_name.casefold()] = entity.id
    validate_writer_result(
        WriterResult(
            sentences=tuple(sentence((p,)) for p in facts),
            limitation=sentence(limitations) if limitations else None,
            used_support_ids=tuple(p.support_id for p in chosen),
            used_measurement_ids=tuple(dict.fromkeys(m for p in chosen for m in p.measurement_ids)),
        ),
        brief,
        catalog=resolved_catalog,
    )
    answer = _render_composition(plan, by_id)
    if len(answer.split()) > brief.maximum_words:
        raise WriterRejected(
            WriterValidationCategory.TOO_LONG, "composition exceeds the complete answer word budget"
        )
    return answer
