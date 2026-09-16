"""Canonical resolution over the immutable C19 entity catalog."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from difflib import SequenceMatcher

from .contracts import CanonicalEntityReference, EntityResolution, ResolvedEntity
from .enums import EntityKind, ResolutionStatus


class UnknownCanonicalEntity(ValueError):
    """Raised when a syntactically valid client reference is absent from the snapshot."""


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    return " ".join(re.findall(r"[a-z0-9]+", value))


class EntityResolver:
    """Resolve exact names/aliases/IDs; partial and fuzzy input only produces candidates."""

    def __init__(self, entities: list[dict]):
        self._by_key: dict[tuple[EntityKind, str], ResolvedEntity] = {}
        self._exact_labels: dict[tuple[EntityKind, str], list[ResolvedEntity]] = {}
        self._candidate_labels: dict[EntityKind, list[tuple[str, ResolvedEntity]]] = {
            kind: [] for kind in EntityKind
        }
        for row in entities:
            kind = EntityKind(row["kind"])
            entity = ResolvedEntity(kind=kind, id=row["id"], display_name=row["name"])
            self._by_key[(kind, entity.id)] = entity
            exact_labels = {normalize(entity.display_name)}
            exact_labels.update(normalize(alias) for alias in row.get("aliases", []) if alias)
            for label in sorted(exact_labels):
                self._exact_labels.setdefault((kind, label), []).append(entity)
                if len(label) >= 3:
                    self._candidate_labels[kind].append((label, entity))
            if kind in {EntityKind.QB, EntityKind.COACH}:
                name_parts = normalize(entity.display_name).split()
                first_name = name_parts[0]
                surname = name_parts[-1]
                if len(first_name) >= 3:
                    self._candidate_labels[kind].append((first_name, entity))
                if len(surname) >= 3:
                    self._candidate_labels[kind].append((surname, entity))
        for entities_for_label in self._exact_labels.values():
            entities_for_label.sort(key=lambda entity: entity.id)
        for kind in EntityKind:
            self._candidate_labels[kind].sort(key=lambda item: (item[0], item[1].id))

    def require(self, reference: CanonicalEntityReference) -> ResolvedEntity:
        entity = self._by_key.get((reference.kind, reference.id))
        if entity is None:
            raise UnknownCanonicalEntity(
                f"canonical {reference.kind.value} is not present in the analytical snapshot"
            )
        return entity

    def require_id(self, kind: EntityKind, entity_id: str) -> ResolvedEntity:
        return self.require(CanonicalEntityReference(kind=kind, id=entity_id))

    def revalidate_context(
        self, references: Iterable[CanonicalEntityReference]
    ) -> tuple[ResolvedEntity, ...]:
        resolved = {
            reference.kind.value + ":" + reference.id: self.require(reference)
            for reference in references
        }
        return tuple(resolved[key] for key in sorted(resolved))

    def resolve(self, kind: EntityKind, mention: str) -> EntityResolution:
        cleaned = mention.strip()
        direct = self._by_key.get((kind, cleaned))
        if direct is not None:
            return self._exact(cleaned, kind, direct)

        label = normalize(cleaned)
        exact = self._deduplicate(self._exact_labels.get((kind, label), []))
        if len(exact) == 1:
            return self._exact(cleaned, kind, exact[0])
        if len(exact) > 1:
            return self._ambiguous(cleaned, kind, exact)

        partial = self._deduplicate(
            entity
            for candidate_label, entity in self._candidate_labels[kind]
            if label and (label == candidate_label or f" {label} " in f" {candidate_label} ")
        )
        if partial:
            return self._ambiguous(cleaned, kind, partial)

        fuzzy_scores: dict[str, tuple[float, ResolvedEntity]] = {}
        for candidate_label, entity in self._candidate_labels[kind]:
            score = SequenceMatcher(None, label, candidate_label).ratio()
            if score >= 0.8 and score > fuzzy_scores.get(entity.id, (0.0, entity))[0]:
                fuzzy_scores[entity.id] = (score, entity)
        candidates = [
            entity
            for _, entity in sorted(fuzzy_scores.values(), key=lambda item: (-item[0], item[1].id))[
                :5
            ]
        ]
        if candidates:
            return self._ambiguous(cleaned, kind, candidates)
        return EntityResolution(
            mention=cleaned,
            kind=kind,
            status=ResolutionStatus.NOT_FOUND,
            lookup_authorized=False,
        )

    def resolve_many(
        self, mentions: Iterable[tuple[EntityKind, str]]
    ) -> tuple[EntityResolution, ...]:
        results: list[EntityResolution] = []
        seen: set[tuple[EntityKind, str]] = set()
        for kind, mention in mentions:
            result = self.resolve(kind, mention)
            if result.lookup_authorized:
                key = (kind, result.resolved[0].id)
                if key in seen:
                    continue
                seen.add(key)
            results.append(result)
        return tuple(results)

    @staticmethod
    def _deduplicate(entities: Iterable[ResolvedEntity]) -> list[ResolvedEntity]:
        return list({entity.id: entity for entity in entities}.values())

    @staticmethod
    def _exact(mention: str, kind: EntityKind, entity: ResolvedEntity) -> EntityResolution:
        return EntityResolution(
            mention=mention,
            kind=kind,
            status=ResolutionStatus.EXACT,
            resolved=(entity,),
            lookup_authorized=True,
        )

    @staticmethod
    def _ambiguous(
        mention: str, kind: EntityKind, candidates: Iterable[ResolvedEntity]
    ) -> EntityResolution:
        unique = sorted({entity.id: entity for entity in candidates}.values(), key=lambda e: e.id)
        return EntityResolution(
            mention=mention,
            kind=kind,
            status=ResolutionStatus.AMBIGUOUS,
            candidates=tuple(unique[:5]),
            lookup_authorized=False,
        )
