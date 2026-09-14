"""Temporary Stage A behavior; analytical execution begins in later stages."""

from __future__ import annotations

from .contracts import AskV2Request, AskV2Response, stage_a_versions
from .enums import Answerability, AnswerMode, ReasonCode


def stage_a_response(_request: AskV2Request) -> AskV2Response:
    return AskV2Response(
        answerability=Answerability.NOT_SUPPORTED,
        answer_mode=AnswerMode.DETERMINISTIC,
        reason_code=ReasonCode.IMPLEMENTATION_NOT_AVAILABLE_YET,
        answer=(
            "Ask v2 analytical execution is not yet enabled in this staged implementation. "
            "No analytical evidence or model result has been produced."
        ),
        versions=stage_a_versions(),
    )
