"""Deterministic analytical routing and explanations, with no LLM or new estimates."""

from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict
from difflib import SequenceMatcher
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .ask_data import CONTRACT, code_identity, digest, json_bytes


class Intent(StrEnum):
    QB_HISTORY = "QB_HISTORY"
    QB_PROFILE = "QB_PROFILE"
    QB_PROJECTION = "QB_PROJECTION"
    COACH_HISTORY = "COACH_HISTORY"
    COACH_QB_RELATIONSHIP = "COACH_QB_RELATIONSHIP"
    TEAM_SCHEME = "TEAM_SCHEME"
    PCAE_RESEARCH = "PCAE_RESEARCH"
    PLAYER_TEAM_SCENARIO = "PLAYER_TEAM_SCENARIO"
    CAREER_COUNTERFACTUAL = "CAREER_COUNTERFACTUAL"
    ROOKIE_PROJECTION = "ROOKIE_PROJECTION"
    COACH_EFFECT = "COACH_EFFECT"
    UNKNOWN = "UNKNOWN"


class Status(StrEnum):
    SUPPORTED = "SUPPORTED"
    NOT_SUPPORTED = "NOT_SUPPORTED"
    NOT_YET_SUPPORTED = "NOT_YET_SUPPORTED"
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
    NARROW_SCOPE = "NARROW_SCOPE"


class AskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    question: str = Field(min_length=3, max_length=1000)


class Entity(BaseModel):
    kind: str
    id: str
    name: str


class AskResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contract_version: str = CONTRACT
    intent: Intent
    entities: list[Entity] = Field(default_factory=list)
    season: int | None = None
    requested_metric: str | None = None
    status: Status
    data_version: str
    model_version: str | None = None
    metrics: list[dict[str, Any]] = Field(default_factory=list)
    uncertainty: list[dict[str, Any]] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    source_artifacts: list[dict[str, str]] = Field(default_factory=list)
    candidates: list[Entity] = Field(default_factory=list)
    reason: str | None = None
    available_alternative: str | None = None
    explanation: str = ""


REFUSALS = {
    Intent.PLAYER_TEAM_SCENARIO: (
        Status.NOT_SUPPORTED,
        "Checkpoint 17 found no validated Player × Scheme environment-response model.",
        "Show the QB's team-independent projection and the team's historical scheme separately.",
    ),
    Intent.CAREER_COUNTERFACTUAL: (
        Status.NOT_SUPPORTED,
        "Checkpoint 18 is not ready; no validated multi-year environment-response model exists.",
        "Explore the player's actual historical team-season records.",
    ),
    Intent.ROOKIE_PROJECTION: (
        Status.NOT_YET_SUPPORTED,
        "Checkpoint 20 has not implemented or validated college-to-NFL or rookie projections.",
        "Explore established NFL quarterback history or the approved C16 research projections.",
    ),
    Intent.COACH_EFFECT: (
        Status.NOT_SUPPORTED,
        "Checkpoint 12 approved no composite Coach Effect. HC Q is not identifiable; "
        "OC, QB Coach and Play Caller Q remain exploratory, not causal improvement estimates.",
        "Show verified staff history or separate research-ready PCAE decision-value evidence.",
    ),
}


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    return " ".join(re.findall(r"[a-z0-9]+", value))


def contains(text: str, phrase: str) -> bool:
    return bool(phrase) and f" {phrase} " in f" {text} "


def route(question: str) -> Intent:
    q = normalize(question)
    # Unsupported capabilities always win over supported words in a compound request.
    if re.search(
        r"\b(what if|had been|would have|instead|alternate|counterfactual)\b", q
    ) and re.search(r"\b(drafted|career|draft|history)\b", q):
        return Intent.CAREER_COUNTERFACTUAL
    if re.search(
        r"\b(coach effect|caused|causal|make quarterbacks|make qbs|improvement number)\b", q
    ) or (
        re.search(r"\b(how much|effect|impact|improve|better)\b", q)
        and re.search(r"\b(coach|coaching|quarterbacks|qbs)\b", q)
    ):
        return Intent.COACH_EFFECT
    if re.search(r"\b(rookie|college|ncaa|nfl draft|in the nfl|college to nfl)\b", q) and re.search(
        r"\b(project|projection|predict|forecast|will|next season|next year)\b", q
    ):
        return Intent.ROOKIE_PROJECTION
    if re.search(
        r"\b(what would|what if|scenario|transfer|team switch|fit with|fit in|under a different)\b",
        q,
    ):
        return Intent.PLAYER_TEAM_SCENARIO
    if re.search(r"\b(pcae|call value|play calling decision|decision value)\b", q):
        return Intent.PCAE_RESEARCH
    if re.search(
        r"\b(project|projects|projection|predict|prediction|forecast|"
        r"next season|next year|will perform|how will)\b",
        q,
    ):
        return Intent.QB_PROJECTION
    if re.search(
        r"\b(played under|played for|worked with|coached by|which qbs|which quarterbacks)\b", q
    ):
        return Intent.COACH_QB_RELATIONSHIP
    if re.search(r"\b(coach|coaching|staff)\b", q):
        return Intent.COACH_HISTORY
    if re.search(r"\b(scheme|offense|offence|teams|team)\b", q):
        return Intent.TEAM_SCHEME
    if re.search(
        r"\b(style|profile|type of quarterback|mobile|mobility|deep|scramble|shotgun)\b", q
    ):
        return Intent.QB_PROFILE
    if re.search(
        r"\b(perform|performance|history|season|epa|pae|cpoe|stats|statistics|yards|touchdowns)\b",
        q,
    ):
        return Intent.QB_HISTORY
    return Intent.UNKNOWN


def explain(result: AskResponse) -> str:
    """Future explanation adapter seam: input is already-resolved evidence, never a model prompt."""
    if result.status != Status.SUPPORTED:
        return " ".join(v for v in (result.reason, result.available_alternative) if v)
    descriptions = {
        Intent.QB_HISTORY: "Historical regular-season QB-team-season observations. PAE is actual "
        "EPA/dropback minus the original out-of-sample expectation; missing "
        "values stay unavailable.",
        Intent.QB_PROFILE: "Entering-season Player State, not a current roster or a new ability "
        "score. "
        "Recent traits describe the recorded historical window. Conditional "
        "splits remain contextual.",
        Intent.QB_PROJECTION: "TEAM-INDEPENDENT RESEARCH PROJECTION. Frozen C16 EPA-only "
        "estimate for 2026, with no destination team, coach, playing-time or "
        "active-roster assumption.",
        Intent.TEAM_SCHEME: "Observed historical team behavior, not causal coach ownership or a "
        "forecast. "
        "Rates retain their source denominators; unavailable features are not zero.",
        Intent.COACH_HISTORY: "Source-backed staff assignments with their recorded interval "
        "certainty. "
        "A season designation does not prove weekly tenure or individual "
        "play-calling responsibility.",
        Intent.COACH_QB_RELATIONSHIP: "Verified same-team-season coaching context, not proof "
        "of exact weekly QB-coach overlap or a causal coaching effect.",
        Intent.PCAE_RESEARCH: "PCAE is a separate RESEARCH-READY observational play-calling "
        "decision-value measure. Only explicitly verified, non-shared intervals are shown. "
        "It is not a universal Coach Effect or a coach ranking.",
    }
    return descriptions[result.intent]


class AnalyticalService:
    def __init__(self, bundle: dict, version: str):
        self.bundle = bundle
        self.version = version
        self.entities = bundle["entities"]
        self.names = {r["id"]: r["name"] for r in self.entities}
        self.index: dict[str, dict[str, list[dict]]] = {}
        for table, key in (
            ("history", "player_id"),
            ("states", "player_id"),
            ("profiles", "player_id"),
            ("projections", "player_id"),
            ("assignments", "coach_id"),
            ("pcae", "coach_id"),
        ):
            groups: dict[str, list[dict]] = defaultdict(list)
            for row in bundle[table]:
                groups[row[key]].append(row)
            self.index[table] = groups

    @classmethod
    def from_directory(cls, directory: Path) -> AnalyticalService:
        manifest = json.loads((directory / "MANIFEST.json").read_bytes())
        content = (directory / "analytical_bundle.json").read_bytes()
        identity = manifest["identity"]
        version = "c19-" + digest(json_bytes(identity))[:16]
        if (
            manifest["contract"] != CONTRACT
            or version != manifest["data_version"]
            or digest(content) != identity["bundle_sha256"]
            or digest(content) != manifest["output_checksums"]["analytical_bundle.json"]
        ):
            raise ValueError("invalid C19 analytical bundle")
        code = code_identity()
        if identity["code"] != code:
            raise ValueError("C19 code changed; rebuild the analytical snapshot")
        return cls(json.loads(content), version)

    def resolve(self, question: str, kind: str) -> list[Entity]:
        text = normalize(question)
        entities = [r for r in self.entities if r["kind"] == kind]
        ids = [r for r in entities if contains(text, normalize(r["id"]))]
        if ids:
            return [Entity(**{k: r[k] for k in ("kind", "id", "name")}) for r in ids]
        matches = []
        for row in entities:
            labels = [row["name"], *row["aliases"]]
            if kind in {"qb", "coach"}:
                labels.append(row["name"].split()[-1])
            matched = [
                normalize(label)
                for label in labels
                if len(normalize(label)) >= 3 and contains(text, normalize(label))
            ]
            if matched:
                matches.append((max(matched, key=len), row))
        if matches:
            return [
                Entity(**{k: row[k] for k in ("kind", "id", "name")})
                for name, row in matches
                if not any(name != other and contains(other, name) for other, _ in matches)
            ]
        return []

    def suggestions(self, question: str, kind: str) -> list[Entity]:
        # Fuzzy names suggest clarification only; never authorize a numerical lookup.
        tokens = normalize(question).split()
        phrases = [" ".join(tokens[i : i + 2]) for i in range(len(tokens) - 1)]
        scores = []
        for row in self.entities:
            if row["kind"] != kind:
                continue
            score = max(
                (SequenceMatcher(None, p, normalize(row["name"])).ratio() for p in phrases),
                default=0,
            )
            if score >= 0.8:
                scores.append((score, row))
        return [
            Entity(**{k: row[k] for k in ("kind", "id", "name")})
            for _, row in sorted(scores, key=lambda v: (-v[0], v[1]["id"]))[:5]
        ]

    def answer(self, question: str) -> AskResponse:
        question = AskRequest(question=question).question
        intent = route(question)
        result = AskResponse(intent=intent, status=Status.SUPPORTED, data_version=self.version)
        years = sorted(set(map(int, re.findall(r"\b(?:19|20)\d{2}\b", question))))
        if len(years) > 1:
            return self._clarify(
                result, "Ask about one season at a time, or omit the season for history."
            )
        result.season = years[0] if years else None
        q = normalize(question)
        metric_aliases = {
            "cpoe": "cpoe",
            "pae": "performance_above_expectation",
            "epa": "epa_per_dropback",
            "shotgun": "shotgun_rate",
            "deep": "target_depth_deep_rate",
            "mobile": "scramble_rate",
            "mobility": "scramble_rate",
            "scramble": "scramble_rate",
            "no huddle": "no_huddle_rate",
            "yards": "passing_yards",
            "touchdowns": "passing_touchdowns",
            "td": "passing_touchdowns",
            "sack": "sack_rate",
            "success": "success_rate",
        }
        result.requested_metric = next(
            (value for key, value in metric_aliases.items() if contains(q, key)), None
        )
        if intent in REFUSALS:
            for entity_kind in ("qb", "coach", "team"):
                resolved = self.resolve(question, entity_kind)
                if len(resolved) == 1:
                    result.entities.extend(resolved)
                elif resolved:
                    result.candidates.extend(resolved)
            result.status, result.reason, result.available_alternative = REFUSALS[intent]
            return self._finish(result)
        kind = (
            "coach"
            if intent in {Intent.COACH_HISTORY, Intent.COACH_QB_RELATIONSHIP, Intent.PCAE_RESEARCH}
            else "team"
            if intent == Intent.TEAM_SCHEME
            else "qb"
        )
        candidates = self.resolve(question, kind)
        # A name-only coach-history request may omit the word 'coach'.
        if intent in {Intent.QB_HISTORY, Intent.UNKNOWN} and not candidates:
            coaches = self.resolve(question, "coach")
            if coaches and "history" in q:
                result.intent, intent, kind, candidates = (
                    Intent.COACH_HISTORY,
                    Intent.COACH_HISTORY,
                    "coach",
                    coaches,
                )
        # An unrecognized destination-qualified projection must fail closed, not silently
        # substitute the team-independent answer to a transfer question.
        if intent == Intent.QB_PROJECTION and (
            self.resolve(question, "team")
            or (
                re.search(r"\b(under|coach|coached|coaching|with)\b", q)
                and self.resolve(question, "coach")
            )
        ):
            result.intent = Intent.PLAYER_TEAM_SCENARIO
            result.status, result.reason, result.available_alternative = REFUSALS[result.intent]
            return self._finish(result)
        if intent == Intent.UNKNOWN:
            return self._clarify(
                result,
                "Choose QB history, QB style, team scheme, coach history, PCAE, "
                "or the approved 2026 team-independent projection.",
            )
        league_scheme = intent == Intent.TEAM_SCHEME and contains(q, "teams") and not candidates
        if len(candidates) != 1 and not league_scheme:
            result.candidates = candidates or self.suggestions(question, kind)
            return self._clarify(
                result, "Name a single canonical " + kind + "; confirm a candidate if ambiguous."
            )
        result.entities = candidates
        entity_id = candidates[0].id if candidates else ""
        if intent == Intent.QB_HISTORY:
            rows = self._lookup("history", entity_id, result.season)
            result.metrics = rows
            self._sources(result, "history", "pae", "supplemental")
            result.uncertainty = [
                {
                    k: r[k]
                    for k in (
                        "player_id",
                        "team_id",
                        "season",
                        "prediction_std_error",
                        "prediction_interval_low",
                        "prediction_interval_high",
                        "reliability",
                    )
                }
                for r in rows
            ]
            result.limitations = [
                "Intervals are the original expectation uncertainty, not a newly fitted "
                "PAE interval.",
                "Multi-team seasons remain separate; no averaging of stint rates.",
            ]
        elif intent == Intent.QB_PROFILE:
            result.season = result.season if result.season is not None else 2025
            result.metrics = self._lookup("profiles", entity_id, result.season, "target_season")
            if result.requested_metric:
                wanted = "recent_" + result.requested_metric
                result.metrics = [r for r in result.metrics if r["feature_name"] == wanted]
            result.uncertainty = self._lookup("states", entity_id, result.season, "target_season")
            self._sources(result, "profiles", "states", "profile_registry")
            result.limitations = [
                "C14 states cover entering 2010–2025. Default is entering 2025, not a "
                "live profile.",
                "Small-sample estimates remain null; raw observations and reliability "
                "are shown separately.",
                "No arbitrary style grade; conditioned performance is not an inherent "
                "player trait.",
            ]
        elif intent == Intent.QB_PROJECTION:
            result.season = result.season if result.season is not None else 2026
            if result.season != 2026 or result.requested_metric not in {None, "epa_per_dropback"}:
                result.status, result.reason = (
                    Status.NOT_SUPPORTED,
                    "Only frozen 2026 EPA projections are approved; no forward PAE or other "
                    "outcome.",
                )
                result.available_alternative = (
                    "Ask for the approved 2026 team-independent EPA projection "
                    "or historical QB performance."
                )
                return self._finish(result)
            result.metrics = self._lookup("projections", entity_id, 2026, "target_season")
            self._sources(result, "projections")
            result.limitations = [
                "57 approved research candidates only; not an active-roster forecast.",
                "Historical residual bands do not guarantee future coverage or exchangeability.",
            ]
            result.uncertainty = [
                {k: r[k] for k in r if k.startswith(("lower_", "upper_", "radius_", "interval_"))}
                for r in result.metrics
            ]
        elif intent == Intent.TEAM_SCHEME:
            result.season = result.season if result.season is not None else 2025
            result.metrics = [
                r
                for r in self.bundle["scheme"]
                if r["season"] == result.season
                and (not entity_id or r["team_id"] == entity_id)
                and (not result.requested_metric or r["feature_name"] == result.requested_metric)
            ]
            if league_scheme and not result.requested_metric:
                return self._clarify(
                    result, "Specify a measurable scheme tendency, such as shotgun rate."
                )
            if league_scheme:
                result.metrics = sorted(
                    result.metrics,
                    key=lambda r: (r["raw_value"] is None, -(r["raw_value"] or 0), r["team_id"]),
                )
            self._sources(result, "scheme")
            result.limitations = [
                "Observed team-season scheme, not a target-team forecast or causal "
                "coach attribute.",
                "Source coverage and sample sizes are feature-specific; default season is 2025.",
            ]
        elif intent in {Intent.COACH_HISTORY, Intent.COACH_QB_RELATIONSHIP}:
            assignments = [
                r
                for r in self._lookup("assignments", entity_id, result.season)
                if r["verification_status"] == "verified"
            ]
            result.metrics = assignments
            self._sources(result, "assignments")
            result.limitations = [
                "Only verified assignments; absent roles do not imply the coach had no role.",
                "Formal OC/QB titles use the serving Eleven-B overlay. PCAE has a "
                "separately versioned C12 evidence snapshot.",
            ]
            if intent == Intent.COACH_QB_RELATIONSHIP:
                result.metrics = []
                self._sources(result, "history", "pae")
                for assignment in assignments:
                    for row in self.bundle["history"]:
                        if (row["team_id"], row["season"]) == (
                            assignment["team_id"],
                            assignment["season"],
                        ):
                            result.metrics.append(
                                {
                                    **row,
                                    **assignment,
                                    "relationship_semantics": "same_team_season_context",
                                }
                            )
                result.limitations.append(
                    "QB-team-season facts do not establish exact weekly overlap with this "
                    "assignment."
                )
        elif intent == Intent.PCAE_RESEARCH:
            result.metrics = self._lookup("pcae", entity_id, result.season)
            self._sources(result, "pcae")
            result.limitations = [
                "RESEARCH-READY separately; no universal Coach Effect, fixed blend or ranking.",
                "Only verified non-shared caller intervals; incomplete and nonrandom "
                "historical coverage.",
                "No coach-interval confidence interval was published in this source; "
                "uncertainty remains unavailable.",
                "PCAE is average CallValue minus the same-season league average; it is not QB PAE.",
            ]
            result.uncertainty = [{"interval": None, "reason": "SOURCE_NOT_AVAILABLE"}]
        return self._finish(result)

    def _lookup(
        self, table: str, entity_id: str, season: int | None, column="season"
    ) -> list[dict]:
        return [
            dict(r)
            for r in self.index[table].get(entity_id, [])
            if season is None or r[column] == season
        ]

    def _sources(self, result: AskResponse, *names: str) -> None:
        result.source_artifacts.extend(self.bundle["sources"][n] for n in names)

    def _clarify(self, result: AskResponse, reason: str) -> AskResponse:
        result.status, result.reason = Status.CLARIFICATION_REQUIRED, reason
        return self._finish(result)

    def _finish(self, result: AskResponse) -> AskResponse:
        if len(result.metrics) > 400:
            result.status, result.reason = (
                Status.NARROW_SCOPE,
                "More than 400 records match. Specify a single season; no partial "
                "result is returned.",
            )
            result.metrics = []
            result.uncertainty = []
        if result.status != Status.SUPPORTED:
            result.metrics = []
            result.uncertainty = []
        if result.status == Status.SUPPORTED and not result.metrics:
            result.status = Status.DATA_UNAVAILABLE
            result.reason = (
                "No approved record exists for this entity, season and metric. No "
                "fallback estimate was created."
            )
        result.metrics = [dict(row) for row in result.metrics]
        for row in result.metrics:
            for key, label in (
                ("player_id", "quarterback_name"),
                ("team_id", "team_name"),
                ("coach_id", "coach_name"),
            ):
                if key in row and label not in row:
                    row[label] = self.names.get(row[key])
        models = {r.get("model_version") for r in result.metrics if r.get("model_version")}
        result.model_version = next(iter(models)) if len(models) == 1 else None
        result.explanation = explain(result)
        return result
