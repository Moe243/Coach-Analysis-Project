"""Additive FastAPI route for the staged Ask Anything v2 contract."""

from fastapi import APIRouter

from .contracts import AskV2Request, AskV2Response
from .service import stage_a_response

router = APIRouter()


@router.post("/ask/v2", response_model=AskV2Response, tags=["Ask Anything"])
def ask_v2(request: AskV2Request) -> AskV2Response:
    return stage_a_response(request)
