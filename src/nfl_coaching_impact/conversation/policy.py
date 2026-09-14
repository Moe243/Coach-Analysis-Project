"""Frozen scientific conclusions inherited by Ask v2 from approved checkpoints."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from types import MappingProxyType

from .serialization import canonical_json_bytes


@dataclass(frozen=True, slots=True)
class ScientificPolicy:
    checkpoint: str
    status: str
    permitted_use: str
    prohibited_use: str


_POLICIES = {
    "C12_COACH_EFFECT": ScientificPolicy(
        checkpoint="C12",
        status="NO_COMPOSITE_COACH_EFFECT",
        permitted_use="Verified assignments and separately labeled observational PCAE evidence.",
        prohibited_use="Causal Coach Effect, universal coach ranking, or inferred role ownership.",
    ),
    "C15_PLAYER_SCHEME_FIT": ScientificPolicy(
        checkpoint="C15",
        status="NOT ESTIMABLE / DATA-LIMITED",
        permitted_use="Descriptive player and scheme tendencies kept separate.",
        prohibited_use="A fit score or predictive player-by-scheme contribution.",
    ),
    "C16_EPA_PROJECTION": ScientificPolicy(
        checkpoint="C16",
        status="RESEARCH-READY WITH LIMITATIONS",
        permitted_use="Team-independent EPA research projection with published uncertainty.",
        prohibited_use=(
            "Destination-team, coach, playing-time, active-roster, or forward-PAE claims."
        ),
    ),
    "C17_SCENARIO": ScientificPolicy(
        checkpoint="C17",
        status="NOT SUPPORTED",
        permitted_use="Descriptive comparison of measured player and historical scheme tendencies.",
        prohibited_use=(
            "Numerical destination-team scenario or predicted scheme-driven improvement."
        ),
    ),
    "C18_COUNTERFACTUAL": ScientificPolicy(
        checkpoint="C18",
        status="NOT READY / NOT IMPLEMENTED",
        permitted_use="Historical facts from actual observed careers.",
        prohibited_use="Career counterfactual simulation or alternate-history numerical output.",
    ),
    "C20_ROOKIE_PROJECTION": ScientificPolicy(
        checkpoint="C20",
        status="NOT ESTIMABLE / DATA-LIMITED",
        permitted_use="Documented draft and historical evidence without an NFL projection.",
        prohibited_use="College-to-NFL or rookie performance projection.",
    ),
}

SCIENTIFIC_POLICIES = MappingProxyType(_POLICIES)
SCIENTIFIC_POLICY_VERSION = (
    "ask-policy-"
    + hashlib.sha256(
        canonical_json_bytes({key: asdict(value) for key, value in sorted(_POLICIES.items())})
    ).hexdigest()[:16]
)
