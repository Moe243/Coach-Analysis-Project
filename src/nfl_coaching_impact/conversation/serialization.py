"""Canonical JSON used for v2 contract identities and deterministic tests."""

from __future__ import annotations

import dataclasses
import json
import math
from collections.abc import Mapping, Set
from enum import Enum
from typing import Any

from pydantic import BaseModel


def _json_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _json_value(value.model_dump(mode="json", exclude_none=False))
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _json_value(dataclasses.asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("canonical contracts require finite numerical values")
        return value
    if value is None or isinstance(value, str | int | bool):
        return value
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("canonical contract mapping keys must be strings")
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, Set):
        normalized = [_json_value(item) for item in value]
        return sorted(
            normalized,
            key=lambda item: json.dumps(
                item, sort_keys=True, ensure_ascii=True, allow_nan=False, separators=(",", ":")
            ),
        )
    if isinstance(value, tuple | list):
        # Ordered contract collections remain ordered. Models normalize only fields
        # whose contracts explicitly define them as unordered.
        return [_json_value(item) for item in value]
    raise TypeError(f"unsupported canonical contract value: {type(value).__name__}")


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize a contract value without timestamps, platform state, or unstable ordering."""
    normalized = _json_value(value)
    return (
        json.dumps(
            normalized,
            sort_keys=True,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("ascii")
