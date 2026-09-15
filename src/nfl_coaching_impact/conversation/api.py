"""Additive FastAPI route for deterministic Ask Anything v2."""

from functools import lru_cache

from fastapi import APIRouter

from nfl_coaching_impact.ask import AnalyticalService
from nfl_coaching_impact.ask_api import analytical_service

from .contracts import AskV2Request, AskV2Response
from .evidence import EvidenceService
from .service import stage_c_response

router = APIRouter()


@lru_cache(maxsize=1)
def _cached_evidence(service: AnalyticalService) -> EvidenceService:
    return EvidenceService(service)


def evidence_service(service: AnalyticalService) -> EvidenceService:
    return _cached_evidence(service)


@router.post("/ask/v2", response_model=AskV2Response, tags=["Ask Anything"])
def ask_v2(
    request: AskV2Request,
) -> AskV2Response:
    # Resolve the frozen analytical service only after FastAPI validates the public body.
    # Invalid bodies therefore remain ordinary 422 responses even when data is unavailable.
    return stage_c_response(request, evidence_service(analytical_service()))
