"""Additive Ask API, independently versioned from the existing DB publication."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from .ask import AnalyticalService, AskRequest, AskResponse

router = APIRouter()


@lru_cache(maxsize=1)
def _load(directory: str) -> AnalyticalService:
    return AnalyticalService.from_directory(Path(directory))


def analytical_service() -> AnalyticalService:
    # No user-supplied path, database URL, source URL, SQL, Python, or LLM tool invocation.
    directory = os.environ.get("ASK_DATA_DIR")
    if not directory:
        raise HTTPException(503, "Ask Anything analytical snapshot is not configured")
    try:
        return _load(directory)
    except (OSError, ValueError, KeyError, TypeError):
        raise HTTPException(
            503, "Ask Anything analytical snapshot is unavailable or incompatible"
        ) from None


@router.post("/ask", response_model=AskResponse, tags=["Ask Anything"])
def ask(
    request: AskRequest, service: Annotated[AnalyticalService, Depends(analytical_service)]
) -> AskResponse:
    return service.answer(request.question)
