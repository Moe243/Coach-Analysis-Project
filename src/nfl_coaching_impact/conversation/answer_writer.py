"""Provider-neutral answer brief, strict writer contract, and fail-closed validation."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Mapping
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from functools import lru_cache

from pydantic import Field, ValidationError, model_validator

from .contracts import (
    ContractModel,
    Identifier,
    ReasonText,
    ResolvedEntity,
    ShortText,
)
from .enums import (
    Answerability,
    ConclusionKind,
    PermissionDecision,
    QuestionType,
)
from .orchestration import AuthoritativeResult
from .providers import WriterValidationCategory
from .serialization import canonical_json_bytes

MAX_WRITER_SUPPORTS = 24
MAX_WRITER_MEASUREMENTS = 64
MAX_WRITER_SENTENCES = 8
MAX_WRITER_WORDS = 220

_NUMBER = re.compile(r"(?<![A-Za-z0-9])[-+]?\d[\d,]*(?:\.\d+)?%?")


class BriefSupportKind(StrEnum):
    PROPOSITION = "proposition"
    LIMITATION = "limitation"
    DEFINITION = "definition"


class ApprovedAnswerSupport(ContractModel):
    support_id: Identifier
    kind: BriefSupportKind
    text: ReasonText
    entity_ids: tuple[str, ...] = Field(default=(), max_length=8)
    phrasings: tuple[ReasonText, ...] = Field(default=(), max_length=3)


class ApprovedMeasurement(ContractModel):
    measurement_id: Identifier
    support_id: Identifier
    canonical_value: str = Field(pattern=r"^-?(?:0|[1-9]\d*)(?:\.\d+)?$")
    display_value: ShortText
    unit: ShortText


class ApprovedAnswerBrief(ContractModel):
    """The only analytical material a natural-language writer may receive."""

    question_type: QuestionType
    topic: ReasonText
    answerability: Answerability
    entities: tuple[ResolvedEntity, ...] = Field(default=(), max_length=8)
    supports: tuple[ApprovedAnswerSupport, ...] = Field(
        min_length=1, max_length=MAX_WRITER_SUPPORTS
    )
    measurements: tuple[ApprovedMeasurement, ...] = Field(
        default=(), max_length=MAX_WRITER_MEASUREMENTS
    )
    required_limitation_ids: tuple[Identifier, ...] = Field(default=(), max_length=8)
    causal_conclusion_allowed: bool
    predictive_fit_allowed: bool
    team_independent_projection_allowed: bool
    maximum_words: int = Field(default=180, ge=40, le=MAX_WRITER_WORDS)

    @model_validator(mode="after")
    def validate_references(self):
        support_ids = {item.support_id for item in self.supports}
        if len(support_ids) != len(self.supports):
            raise ValueError("answer brief support IDs must be unique")
        if not set(self.required_limitation_ids) <= support_ids:
            raise ValueError("required limitation is absent from the answer brief")
        if len(set(self.required_limitation_ids)) != len(self.required_limitation_ids):
            raise ValueError("required limitation IDs must be unique")
        if self.supports[0].kind is not BriefSupportKind.PROPOSITION:
            raise ValueError("the brief must lead with an approved answer proposition")
        if any(
            item.support_id in self.required_limitation_ids
            and item.kind is not BriefSupportKind.LIMITATION
            for item in self.supports
        ):
            raise ValueError("required limitation must reference a limitation support")
        entity_ids = {item.id for item in self.entities}
        if len(entity_ids) != len(self.entities) or any(
            not set(item.entity_ids) <= entity_ids for item in self.supports
        ):
            raise ValueError("answer brief entities must be unique and references resolved")
        measurement_ids = {item.measurement_id for item in self.measurements}
        if len(measurement_ids) != len(self.measurements):
            raise ValueError("answer brief measurement IDs must be unique")
        if any(item.support_id not in support_ids for item in self.measurements):
            raise ValueError("answer brief measurement references unknown support")
        for item in self.supports:
            for text in (item.text, *item.phrasings):
                if re.search(
                    r"://|/(?:Users|home|private)/|\bC\d{2}\b|"
                    r"\b(?:player_id|team_id|load_id|source_url|publication_id)\b",
                    text,
                ):
                    raise ValueError(
                        "answer brief must not transmit private or technical source text"
                    )
        return self


class WriterSentence(ContractModel):
    text: str = Field(min_length=1, max_length=1_600)
    support_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=8)
    measurement_ids: tuple[Identifier, ...] = Field(default=(), max_length=16)
    entity_ids: tuple[str, ...] = Field(default=(), max_length=8)

    @model_validator(mode="after")
    def validate_unique_references(self):
        for values in (self.support_ids, self.measurement_ids, self.entity_ids):
            if len(values) != len(set(values)):
                raise ValueError("writer sentence references must be unique")
        return self


class WriterResult(ContractModel):
    """Strict private provider output; internal identifiers never reach the public answer."""

    sentences: tuple[WriterSentence, ...] = Field(min_length=1, max_length=MAX_WRITER_SENTENCES)
    limitation: WriterSentence | None = None
    used_support_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=24)
    used_measurement_ids: tuple[Identifier, ...] = Field(default=(), max_length=64)

    @model_validator(mode="after")
    def validate_unique_usage(self):
        if len(self.used_support_ids) != len(set(self.used_support_ids)):
            raise ValueError("used support IDs must be unique")
        if len(self.used_measurement_ids) != len(set(self.used_measurement_ids)):
            raise ValueError("used measurement IDs must be unique")
        return self


class WriterRejected(ValueError):
    def __init__(self, category: WriterValidationCategory, message: str):
        super().__init__(message)
        self.category = category


def _numeric_tokens(text: str) -> tuple[str, ...]:
    return tuple(match.group(0) for match in _NUMBER.finditer(text))


def _canonical_number(value: str) -> str:
    cleaned = value.replace(",", "").rstrip("%").lstrip("+")
    try:
        number = Decimal(cleaned)
    except InvalidOperation as error:  # pragma: no cover - regex pre-validates values
        raise ValueError("invalid numeric token") from error
    if not number.is_finite():
        raise ValueError("non-finite numeric token")
    normalized = format(number.normalize(), "f")
    return "0" if normalized in {"-0", ""} else normalized


def _measurement(
    support_id: str,
    token: str,
    index: int,
    *,
    unit: str = "number",
) -> ApprovedMeasurement:
    canonical = _canonical_number(token)
    if token.endswith("%"):
        unit = "percent"
    identity = canonical_json_bytes(
        {"support_id": support_id, "canonical_value": canonical, "index": index}
    )
    return ApprovedMeasurement(
        measurement_id="m_" + hashlib.sha256(identity).hexdigest()[:12],
        support_id=support_id,
        canonical_value=canonical,
        display_value=token,
        unit=unit,
    )


def _support_measurements(support: ApprovedAnswerSupport) -> tuple[ApprovedMeasurement, ...]:
    seen: set[str] = set()
    result = []
    for match in _NUMBER.finditer(support.text):
        token = match[0]
        canonical = _canonical_number(token)
        if canonical in seen:
            continue
        seen.add(canonical)
        before = support.text[max(0, match.start() - 40) : match.start()]
        after = support.text[match.end() : match.end() + 40]
        unit = "number"
        if re.match(r"\s+(?:EPA/dropback|EPA per dropback)\b", after):
            unit = "EPA/dropback"
        elif re.match(r"\s+dropbacks\b", after):
            unit = "dropbacks"
        elif re.search(r"\b(?:in|entering)\s+$", before) and re.fullmatch(r"20\d{2}", token):
            unit = "season"
        result.append(_measurement(support.support_id, token, len(result), unit=unit))
    return tuple(result)


def _permission_allowed(result: AuthoritativeResult, kind: ConclusionKind) -> bool:
    return any(
        item.kind is kind and item.decision is not PermissionDecision.DENIED
        for item in result.conclusions.permissions
    )


def _public_limitation(text: str) -> str:
    """Translate backend caveats, never remove their scientific restrictions."""
    if text.startswith("BOUNDED_SCOPE:"):
        return "This is a bounded historical summary, not a review of every individual record."
    translations = {
        "Multi-team seasons remain separate at player_id + team_id + season.": (
            "A quarterback's results with different teams in the same season remain separate."
        ),
        "QB performance samples are distinct player_id + team_id + season observations.": (
            "Quarterback samples are separate player, team and season records."
        ),
        "PCAE is observational research evidence, not QB PAE or a universal Coach Effect.": (
            "Play-calling evidence is observational; it is not quarterback performance "
            "or an overall coaching grade."
        ),
        "PCAE, verified roles, QB context, and scheme remain distinct evidence families.": (
            "Play-calling decisions, documented roles, quarterback history and offensive "
            "tendencies are different kinds of evidence."
        ),
        "Player State is entering-season evidence, not current or live performance.": (
            "The player profile describes entering-season history, not current or live performance."
        ),
        "The destination-team research does not support a prediction or improvement adjustment.": (
            "Historical comparisons cannot reliably predict performance "
            "or improvement with a different team."
        ),
        "Historical scheme is observed team-season behavior, not causal coach ownership.": (
            "Historical offensive tendencies describe team-season behavior, "
            "not what a coach caused."
        ),
        "Alignment compares declared compatible tendencies only; it is not a fit score.": (
            "These comparisons describe measured tendencies; they are not a predictive fit rating."
        ),
        "No coach-interval confidence interval was published.": (
            "There is no published uncertainty interval for an individual coach's assignment."
        ),
        (
            "Only verified non-shared caller intervals are present; "
            "coverage is incomplete and nonrandom."
        ): (
            "The play-calling evidence covers only verified, non-shared assignments "
            "and is incomplete and nonrandom."
        ),
        "Expectation intervals are not newly fitted PAE intervals.": (
            "The expectation's uncertainty interval is not a separate uncertainty interval "
            "for performance above expectation."
        ),
        "Season-level intervals are not converted into weekly certainty.": (
            "A season-level assignment does not establish exact weekly coaching exposure."
        ),
    }
    return translations.get(text, text)


def _public_phrasings(predicate: str, text: str) -> tuple[str, ...]:
    """Backend-owned factual clauses; free paraphrase cannot be verified by IDs alone.

    The language layer can choose, reorder and combine these clauses. Complete-clause
    matching keeps metric labels, entities, polarity and contextual years bound to facts.
    """
    phrasings = [text]
    if predicate == "historical_qb_performance":
        match = re.fullmatch(
            r"(.+?) recorded ([-\d.]+) EPA/dropback for (.+?) in (\d{4}) across "
            r"(\d+) dropbacks\. The preseason expectation was ([-\d.]+); .+? "
            r"(outperformed|underperformed) it by ([-\d.]+) EPA/dropback \(PAE ([-\d.]+)\)\.",
            text,
        )
        if match:
            name, actual, team, year, volume, expected, direction, delta, pae = match.groups()
            phrasings.append(
                f"{name} {direction} his preseason expectation in {year} with {team}: "
                f"{actual} EPA per dropback against an expected {expected}, "
                f"leaving a {pae} PAE across {volume} dropbacks."
            )
            phrasings.append(
                f"With {team} in {year}, {name} produced {actual} EPA per dropback "
                f"against a preseason expectation of {expected}. His PAE was {pae} "
                f"across {volume} dropbacks."
            )
    elif predicate == "team_independent_epa_projection":
        match = re.fullmatch(
            r"The approved team-independent research model projects (.+?) at ([-\d.]+) "
            r"EPA/dropback in (\d{4}), with a published (\d+)% historical-residual "
            r"band of ([-\d.]+) to ([-\d.]+)\.",
            text,
        )
        if match:
            name, estimate, year, coverage, lower, upper = match.groups()
            phrasings.append(
                f"{name}'s team-independent {year} research projection is {estimate} "
                f"EPA per dropback, with a {coverage}% historical-residual band "
                f"from {lower} to {upper}."
            )
    elif predicate == "verified_role_attribution":
        match = re.fullmatch(
            r"(.+?) had a verified (.+?) assignment with (.+?) in (\d{4}) "
            r"\(weeks (\d+)[–-](\d+); recorded assignment interval\)\.",
            text,
        )
        if match:
            name, role, team, year, start, end = match.groups()
            phrasings.append(
                f"{name} served in a verified {role} role with {team} in {year}, "
                f"with a recorded assignment covering weeks {start}–{end}."
            )
    return tuple(phrasings)


def approved_answer_brief(result: AuthoritativeResult) -> ApprovedAnswerBrief:
    """Reduce authorized analysis to the minimum bounded language-layer payload."""
    propositions = result.conclusions.propositions[:4]
    evidence_by_id = {item.evidence_id: item for item in result.package.evidence}
    entities: dict[tuple[str, str], ResolvedEntity] = {
        (item.kind.value, item.id): item for item in result.response.entities
    }
    supports: list[ApprovedAnswerSupport] = []
    for proposition in propositions:
        linked_entities = {
            (entity.kind.value, entity.id): entity
            for evidence_id in proposition.evidence_ids
            for entity in (
                evidence_by_id[evidence_id].entities if evidence_id in evidence_by_id else ()
            )
        }
        entities.update(linked_entities)
        supports.append(
            ApprovedAnswerSupport(
                support_id=proposition.proposition_id,
                kind=BriefSupportKind.PROPOSITION,
                text=proposition.statement,
                entity_ids=tuple(
                    sorted(
                        entity.id
                        for entity in linked_entities.values()
                        if entity.display_name.casefold() in proposition.statement.casefold()
                    )
                ),
                phrasings=_public_phrasings(proposition.predicate, proposition.statement),
            )
        )

    required_limitations: list[str] = []
    for index, text in enumerate(result.response.limitations, start=1):
        support_id = f"limitation_{index}"
        supports.append(
            ApprovedAnswerSupport(
                support_id=support_id,
                kind=BriefSupportKind.LIMITATION,
                text=_public_limitation(text),
            )
        )
        required_limitations.append(support_id)
    for index, portion in enumerate(result.response.unsupported_portions, start=1):
        support_id = f"unsupported_{index}"
        supports.append(
            ApprovedAnswerSupport(
                support_id=support_id,
                kind=BriefSupportKind.LIMITATION,
                text=portion.explanation,
            )
        )
        required_limitations.append(support_id)

    if any(
        support.kind is BriefSupportKind.PROPOSITION and "PAE" in support.text
        for support in supports
    ):
        supports.append(
            ApprovedAnswerSupport(
                support_id="definition_pae",
                kind=BriefSupportKind.DEFINITION,
                text=(
                    "Performance Above Expectation (PAE) is actual EPA per dropback minus "
                    "the preseason expected EPA per dropback."
                ),
            )
        )

    measurements = tuple(
        measurement for support in supports for measurement in _support_measurements(support)
    )
    selected_entities = tuple(
        sorted(entities.values(), key=lambda item: (item.kind.value, item.id))
    )
    topic_names = ", ".join(item.display_name for item in selected_entities)
    topic = result.plan.proposal.question_type.value.replace("_", " ").title()
    if topic_names:
        topic = f"{topic}: {topic_names}"
    return ApprovedAnswerBrief(
        question_type=result.plan.proposal.question_type,
        topic=topic,
        answerability=result.response.answerability,
        entities=selected_entities,
        supports=tuple(supports),
        measurements=measurements,
        required_limitation_ids=tuple(required_limitations),
        causal_conclusion_allowed=_permission_allowed(result, ConclusionKind.CAUSAL),
        predictive_fit_allowed=_permission_allowed(result, ConclusionKind.PREDICTIVE_FIT),
        team_independent_projection_allowed=(
            result.plan.proposal.question_type is QuestionType.QB_PROJECTION
            and any(item.predicate == "team_independent_epa_projection" for item in propositions)
        ),
    )


def entity_catalog(rows: Iterable[Mapping[str, object]]) -> dict[str, str]:
    """Build a normalized full-name/alias catalog for unapproved-entity detection."""
    result: dict[str, str] = {}
    for row in rows:
        entity_id = str(row["id"])
        labels = [str(row["name"]), *(str(item) for item in row.get("aliases", ()) if item)]
        for label in labels:
            if len(label.split()) >= 2:
                result[label.casefold()] = entity_id
    return result


@lru_cache(maxsize=2)
def _catalog_pattern(labels: tuple[str, ...]) -> re.Pattern:
    # A single bounded snapshot-name matcher avoids recompiling hundreds of regexes
    # for each sentence. Longer aliases win when labels overlap.
    alternatives = "|".join(
        re.escape(label) for label in sorted(labels, key=lambda x: (-len(x), x))
    )
    return re.compile(rf"(?<![A-Za-z0-9])(?:{alternatives or '(?!)'})(?![A-Za-z0-9])")


_CAUSAL = re.compile(
    r"(?i)\b(?:caused|made\s+\w+(?:\s+\w+)?\s+(?:better|elite)|"
    r"developed\s+\w+(?:\s+\w+)?\s+into|improved\s+(?:him|her|them)|"
    r"responsible\s+for\s+(?:his|her|their)\s+success|elevated\s+(?:his|her|their)\s+career|"
    r"turned\s+(?:him|her|them)\s+into|resulted\s+in\s+better\s+quarterback\s+play)\b"
)
_PREDICTIVE = re.compile(
    r"(?i)(?:\bwill\s+improve\b|\bwould\s+(?:produce|post|average|improve)\b|"
    r"\bexpected\s+to\s+improve\s+by\b|\b\d+(?:\.\d+)?%\s+chance\b|"
    r"\bfit\s+score\b|\b\d+(?:\.\d+)?\s*/\s*10\s+fit\b|"
    r"\blikely\s+destination\s+outcome\b|\b(?:future|projected)\s+PAE\b)"
)


def _reject(
    category: WriterValidationCategory,
    message: str,
) -> None:
    raise WriterRejected(category, message)


def _phrase_tokens(text: str) -> tuple[str, ...]:
    """Allow punctuation, sign and percent typography, never arbitrary rounding/units."""
    text = re.sub(r"\bpercent\b", "%", text, flags=re.I)
    text = re.sub(r"(?<=\d)\s+%", "%", text)
    text = _NUMBER.sub(
        lambda match: (
            " value"
            + _canonical_number(match[0]).replace("-", "negative").replace(".", "point")
            + ("percent" if match[0].endswith("%") else "number")
            + " "
        ),
        text,
    )
    return tuple(re.findall(r"[a-z0-9]+", text.casefold()))


_JOINERS = tuple(
    _phrase_tokens(text)
    for text in (
        "and",
        "also",
        "in addition",
        "for context",
        "however",
        "",
        "meanwhile",
    )
)


def _validate_phrases(sentence: WriterSentence, supports: Mapping[str, ApprovedAnswerSupport]):
    """Recognize only complete approved clauses plus non-factual joining language.

    IDs alone are not entailment. This deliberately conservative grammar rejects novel
    facts, swapped metric labels, unseen proper names and caveat reversals, even when
    all cited IDs and individual numeric values happen to be valid.
    """
    tokens = _phrase_tokens(sentence.text)
    candidates = [
        (support.support_id, _phrase_tokens(phrase))
        for support_id in sentence.support_ids
        for support in (supports[support_id],)
        for phrase in (support.phrasings or (support.text,))
    ]
    pending = [(0, frozenset())]
    visited = set()
    while pending:
        index, used = pending.pop()
        if (index, used) in visited:
            continue
        visited.add((index, used))
        if index == len(tokens) and used == frozenset(sentence.support_ids):
            return
        for support_id, phrase in candidates:
            if support_id in used:
                continue
            for joiner in _JOINERS if used else ((),):
                combined = (*joiner, *phrase)
                if tokens[index : index + len(combined)] == combined:
                    pending.append((index + len(combined), used | {support_id}))
    if _CAUSAL.search(sentence.text):
        _reject(WriterValidationCategory.CAUSAL_VIOLATION, "unapproved causal language")
    if _PREDICTIVE.search(sentence.text):
        _reject(WriterValidationCategory.PREDICTIVE_VIOLATION, "unapproved predictive language")
    _reject(WriterValidationCategory.UNSUPPORTED_SENTENCE, "unapproved factual phrasing")


def _validate_sentence(
    sentence: WriterSentence,
    *,
    support_by_id: Mapping[str, ApprovedAnswerSupport],
    measurement_by_id: Mapping[str, ApprovedMeasurement],
    allowed_entity_ids: set[str],
    catalog: Mapping[str, str],
) -> None:
    if any(item not in support_by_id for item in sentence.support_ids):
        _reject(WriterValidationCategory.UNKNOWN_SUPPORT_ID, "unknown answer support")
    if any(item not in measurement_by_id for item in sentence.measurement_ids):
        _reject(WriterValidationCategory.UNAPPROVED_NUMBER, "unknown approved measurement")
    if any(item not in allowed_entity_ids for item in sentence.entity_ids):
        _reject(WriterValidationCategory.UNAPPROVED_ENTITY, "unapproved entity reference")

    support_set = set(sentence.support_ids)
    selected_measurements = [measurement_by_id[item] for item in sentence.measurement_ids]
    if any(item.support_id not in support_set for item in selected_measurements):
        _reject(
            WriterValidationCategory.UNAPPROVED_NUMBER,
            "measurement is not attached to the sentence support",
        )
    approved_values = {item.canonical_value for item in selected_measurements}
    observed_values = {_canonical_number(item) for item in _numeric_tokens(sentence.text)}
    if observed_values != approved_values:
        _reject(
            WriterValidationCategory.UNAPPROVED_NUMBER,
            "writer number does not exactly match the approved brief",
        )

    detected_entities = {
        catalog[match[0]]
        for match in _catalog_pattern(tuple(catalog)).finditer(sentence.text.casefold())
    }
    if detected_entities != set(sentence.entity_ids):
        _reject(
            WriterValidationCategory.UNAPPROVED_ENTITY,
            "writer entity mapping does not match the approved text",
        )
    _validate_phrases(sentence, support_by_id)


def validate_writer_result(
    untrusted: object,
    brief: ApprovedAnswerBrief,
    *,
    catalog: Mapping[str, str],
) -> WriterResult:
    """Validate untrusted prose without accepting provider-owned scientific decisions."""
    try:
        result = WriterResult.model_validate(untrusted)
    except ValidationError as error:
        raise WriterRejected(
            WriterValidationCategory.SCHEMA_INVALID,
            "writer output does not match the strict schema",
        ) from error

    support_by_id = {item.support_id: item for item in brief.supports}
    measurement_by_id = {item.measurement_id: item for item in brief.measurements}
    allowed_entity_ids = {item.id for item in brief.entities}
    all_sentences = (*result.sentences, *((result.limitation,) if result.limitation else ()))
    for sentence in all_sentences:
        _validate_sentence(
            sentence,
            support_by_id=support_by_id,
            measurement_by_id=measurement_by_id,
            allowed_entity_ids=allowed_entity_ids,
            catalog=catalog,
        )

    used_support = {item for sentence in all_sentences for item in sentence.support_ids}
    used_measurements = {item for sentence in all_sentences for item in sentence.measurement_ids}
    if used_support != set(result.used_support_ids) or used_measurements != set(
        result.used_measurement_ids
    ):
        _reject(
            WriterValidationCategory.UNKNOWN_SUPPORT_ID,
            "writer usage summary does not match sentence-level support",
        )
    primary_support = brief.supports[0].support_id
    if primary_support not in {item for part in result.sentences for item in part.support_ids}:
        _reject(WriterValidationCategory.UNKNOWN_SUPPORT_ID, "primary answer fact was omitted")
    if sum(len(part.support_ids) for part in all_sentences) != len(used_support):
        _reject(WriterValidationCategory.UNKNOWN_SUPPORT_ID, "duplicate factual support")

    required = set(brief.required_limitation_ids)
    limitation_support = set(result.limitation.support_ids) if result.limitation else set()
    if not required <= limitation_support:
        _reject(
            WriterValidationCategory.MISSING_LIMITATION,
            "writer omitted a mandatory scientific limitation",
        )

    answer = render_writer_answer(result)
    if len(answer.split()) > min(brief.maximum_words, MAX_WRITER_WORDS):
        _reject(WriterValidationCategory.TOO_LONG, "writer answer exceeds the word budget")
    # Full approved-clause matching above checks polarity, not a blanket word ban:
    # "not causal" and "no future PAE" are valid mandatory caveats.
    if brief.question_type is QuestionType.PLAYER_TEAM_SCENARIO:
        limitation = result.limitation.text if result.limitation else ""
        if not re.search(
            r"(?i)\b(?:cannot|does not|not a prediction|not predictive)\b",
            limitation,
        ):
            _reject(
                WriterValidationCategory.MISSING_LIMITATION,
                "scenario answer omitted the destination-prediction limitation",
            )
    if brief.team_independent_projection_allowed:
        if "team-independent" not in answer.casefold():
            _reject(
                WriterValidationCategory.PREDICTIVE_VIOLATION,
                "projection answer omitted team-independent scope",
            )
    return result


def render_writer_answer(result: WriterResult) -> str:
    lead = " ".join(" ".join(sentence.text.split()) for sentence in result.sentences)
    return (
        lead
        if result.limitation is None
        else lead + "\n\n" + " ".join(result.limitation.text.split())
    )
