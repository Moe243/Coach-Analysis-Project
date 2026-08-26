"""Machine-readable data-quality checks for checkpoint two."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import polars as pl

from .errors import DataQualityError


@dataclass(frozen=True)
class QualityCheck:
    name: str
    status: str
    severity: str
    failure_count: int
    details: str


class QualityReport:
    def __init__(self) -> None:
        self.checks: list[QualityCheck] = []

    def record(
        self,
        name: str,
        passed: bool,
        *,
        failure_count: int = 0,
        details: str = "",
        severity: str = "error",
    ) -> None:
        self.checks.append(
            QualityCheck(
                name=name,
                status="pass" if passed else "fail",
                severity=severity,
                failure_count=failure_count,
                details=details,
            )
        )
        if not passed and severity == "error":
            raise DataQualityError(f"{name}: {details} (failures={failure_count})")

    def warn(self, name: str, count: int, details: str) -> None:
        self.checks.append(
            QualityCheck(
                name=name,
                status="warning" if count else "pass",
                severity="warning",
                failure_count=count,
                details=details,
            )
        )

    def frame(self) -> pl.DataFrame:
        return pl.DataFrame([asdict(check) for check in self.checks])
