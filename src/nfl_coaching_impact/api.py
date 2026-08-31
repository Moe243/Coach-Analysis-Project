"""Read-only FastAPI surface for the checkpoint-seven PostgreSQL publication."""

from __future__ import annotations

import os
from contextlib import contextmanager
from enum import StrEnum
from typing import Annotated, Any, Literal

import psycopg
from fastapi import FastAPI, HTTPException, Query
from psycopg.rows import dict_row
from pydantic import BaseModel, ConfigDict

from .serving import API_CONTRACT_VERSION, SCHEMA_VERSION


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class Page(ApiModel):
    items: list[dict[str, Any]]
    total: int
    limit: int
    offset: int


class Health(ApiModel):
    status: str
    database: str
    api_contract_version: str


class Versions(ApiModel):
    load_id: str
    schema_version: str
    loader_version: str
    api_contract_version: str
    historical_data_version: str
    expected_data_version: str
    expected_model_version: str
    coach_data_version: str
    coach_model_version: str


class CoachRole(StrEnum):
    HEAD_COACH = "head_coach"
    OFFENSIVE_COORDINATOR = "offensive_coordinator"
    PLAY_CALLER = "play_caller"
    QUARTERBACKS_COACH = "quarterbacks_coach"


class VerificationStatus(StrEnum):
    UNVERIFIED = "unverified"
    PROVISIONAL = "provisional"
    VERIFIED = "verified"
    CONFLICTING = "conflicting"


class ReviewStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


app = FastAPI(
    title="NFL Coaching Impact Engine API",
    version=API_CONTRACT_VERSION,
    description=(
        "Read-only access to versioned QB, PAE, coaching-assignment, and exploratory "
        "coach-impact outputs. Suppression and identification labels are preserved."
    ),
)


def _database_url() -> str:
    value = os.environ.get("DATABASE_URL")
    if not value:
        raise HTTPException(status_code=503, detail="DATABASE_URL is not configured")
    return value


@contextmanager
def _connection():
    with psycopg.connect(_database_url(), row_factory=dict_row) as connection:
        with connection.transaction():
            connection.execute("SET TRANSACTION READ ONLY")
            yield connection


def _page(
    source: str,
    *,
    clauses: list[str],
    params: list[Any],
    order: str,
    limit: int,
    offset: int,
) -> Page:
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    with _connection() as connection:
        total = connection.execute(
            f"SELECT count(*) AS total FROM {source}{where}", params
        ).fetchone()["total"]
        rows = connection.execute(
            f"SELECT * FROM {source}{where} ORDER BY {order} LIMIT %s OFFSET %s",
            [*params, limit, offset],
        ).fetchall()
    return Page(items=rows, total=total, limit=limit, offset=offset)


Limit = Annotated[int, Query(ge=1, le=200)]
Offset = Annotated[int, Query(ge=0)]


@app.get("/health", response_model=Health)
def health() -> Health:
    with _connection() as connection:
        connection.execute("SELECT 1")
    return Health(status="ok", database="available", api_contract_version=API_CONTRACT_VERSION)


@app.get("/versions", response_model=Versions)
def versions() -> Versions:
    with _connection() as connection:
        row = connection.execute(
            "SELECT l.load_id::text, l.schema_version, l.loader_version, "
            "l.api_contract_version, l.historical_data_version, l.expected_data_version, "
            "l.expected_model_version, l.coach_data_version, l.coach_model_version "
            "FROM serving_loads l JOIN serving_publication p ON p.load_id = l.load_id"
        ).fetchone()
    if not row:
        raise HTTPException(status_code=503, detail="No serving publication is available")
    return Versions(**row)


@app.get("/qbs", response_model=Page)
def qbs(
    search: str | None = None,
    team_id: str | None = None,
    season: int | None = Query(None, ge=2010, le=2025),
    eligible: bool | None = None,
    sort: Literal["name", "season", "dropbacks", "epa"] = "name",
    limit: Limit = 50,
    offset: Offset = 0,
) -> Page:
    clauses, params = [], []
    if search:
        clauses.append("display_name ILIKE %s")
        params.append(f"%{search}%")
    if team_id:
        clauses.append("team_id = %s")
        params.append(team_id)
    if season is not None:
        clauses.append("season = %s")
        params.append(season)
    if eligible is not None:
        clauses.append("qualifies_default = %s")
        params.append(eligible)
    orders = {
        "name": "display_name, season DESC, team_id, player_id",
        "season": "season DESC, display_name, team_id, player_id",
        "dropbacks": "dropbacks DESC, display_name, season DESC, team_id, player_id",
        "epa": "epa_per_dropback DESC NULLS LAST, display_name, season DESC, team_id, player_id",
    }
    return _page(
        "api_qb_statistics",
        clauses=clauses,
        params=params,
        order=orders[sort],
        limit=limit,
        offset=offset,
    )


@app.get("/qbs/{player_id}")
def qb_profile(player_id: str) -> dict[str, Any]:
    with _connection() as connection:
        player = connection.execute(
            "SELECT player_id, display_name, position, payload FROM serving_players p "
            "JOIN serving_publication pub ON pub.load_id = p.load_id WHERE player_id = %s",
            (player_id,),
        ).fetchone()
        seasons = connection.execute(
            "SELECT * FROM api_qb_statistics WHERE player_id = %s ORDER BY season, team_id",
            (player_id,),
        ).fetchall()
    if not player or not seasons:
        raise HTTPException(status_code=404, detail="Quarterback not found")
    return {"player": player, "seasons": seasons}


@app.get("/qbs/{player_id}/pae", response_model=Page)
def qb_pae(player_id: str, limit: Limit = 50, offset: Offset = 0) -> Page:
    result = _page(
        "api_qb_pae",
        clauses=["player_id = %s"],
        params=[player_id],
        order="season, team_id, player_id",
        limit=limit,
        offset=offset,
    )
    if result.total == 0:
        raise HTTPException(status_code=404, detail="No published PAE found for quarterback")
    return result


@app.get("/coaches", response_model=Page)
def coaches(
    search: str | None = None,
    role: CoachRole | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
) -> Page:
    clauses, params = [], []
    if search:
        clauses.append("canonical_name ILIKE %s")
        params.append(f"%{search}%")
    if role:
        clauses.append("role::text = %s")
        params.append(role.value)
    return _page(
        "(SELECT DISTINCT load_id, coach_id, canonical_name, role "
        "FROM api_coaching_assignments) AS coaches",
        clauses=clauses,
        params=params,
        order="canonical_name, role, coach_id",
        limit=limit,
        offset=offset,
    )


@app.get("/coaches/{coach_id}")
def coach_profile(coach_id: str) -> dict[str, Any]:
    with _connection() as connection:
        coach = connection.execute(
            "SELECT coach_id, canonical_name FROM serving_coaches c "
            "JOIN serving_publication p ON p.load_id = c.load_id WHERE coach_id = %s",
            (coach_id,),
        ).fetchone()
        history = connection.execute(
            "SELECT * FROM api_coaching_assignments WHERE coach_id = %s "
            "ORDER BY season, start_week, role",
            (coach_id,),
        ).fetchall()
    if not coach:
        raise HTTPException(status_code=404, detail="Coach not found")
    return {"coach": coach, "role_history": history}


@app.get("/coach-impact", response_model=Page)
def coach_impact(
    role: CoachRole | None = None,
    eligible: bool | None = None,
    min_exposure: float | None = Query(None, ge=0),
    sort: Literal["name", "effect", "exposure"] = "name",
    limit: Limit = 50,
    offset: Offset = 0,
) -> Page:
    clauses, params = [], []
    if role:
        clauses.append("role::text = %s")
        params.append(role.value)
    if eligible is not None:
        clauses.append("rank_eligible = %s")
        params.append(eligible)
    if min_exposure is not None:
        clauses.append("verified_dropbacks >= %s")
        params.append(min_exposure)
    orders = {
        "name": "canonical_name, role, coach_id",
        "effect": "estimated_effect DESC NULLS LAST, canonical_name, role, coach_id",
        "exposure": "verified_dropbacks DESC, canonical_name, role, coach_id",
    }
    return _page(
        "api_coach_impact",
        clauses=clauses,
        params=params,
        order=orders[sort],
        limit=limit,
        offset=offset,
    )


@app.get("/teams", response_model=Page)
def teams(search: str | None = None, limit: Limit = 50, offset: Offset = 0) -> Page:
    clauses, params = [], []
    if search:
        clauses.append("(team_name ILIKE %s OR team_abbr ILIKE %s)")
        params.extend([f"%{search}%", f"%{search}%"])
    return _page(
        "(SELECT t.* FROM serving_teams t JOIN serving_publication p "
        "ON p.load_id = t.load_id) AS teams",
        clauses=clauses,
        params=params,
        order="team_name, team_id",
        limit=limit,
        offset=offset,
    )


@app.get("/assignments", response_model=Page)
def assignments(
    coach_id: str | None = None,
    team_id: str | None = None,
    season: int | None = Query(None, ge=2010, le=2025),
    role: CoachRole | None = None,
    verification_status: VerificationStatus | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
) -> Page:
    values = {
        "coach_id": coach_id,
        "team_id": team_id,
        "season": season,
        "role::text": role.value if role else None,
        "verification_status::text": verification_status.value if verification_status else None,
    }
    clauses = [f"{column} = %s" for column, value in values.items() if value is not None]
    params = [value for value in values.values() if value is not None]
    return _page(
        "api_coaching_assignments",
        clauses=clauses,
        params=params,
        order="season DESC, team_id, role, start_week, end_week, assignment_key",
        limit=limit,
        offset=offset,
    )


@app.get("/network/nodes", response_model=Page)
def network_nodes(limit: Limit = 50, offset: Offset = 0) -> Page:
    return _page(
        "(SELECT DISTINCT load_id, coach_id, canonical_name "
        "FROM api_coaching_assignments) AS nodes",
        clauses=[],
        params=[],
        order="canonical_name, coach_id",
        limit=limit,
        offset=offset,
    )


@app.get("/network/edges", response_model=Page)
def network_edges(
    season: int | None = Query(None, ge=2010, le=2025),
    team_id: str | None = None,
    verification_status: VerificationStatus | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
) -> Page:
    clauses, params = [], []
    if season is not None:
        clauses.append("season = %s")
        params.append(season)
    if team_id:
        clauses.append("team_id = %s")
        params.append(team_id)
    if verification_status is not None:
        clauses.append(
            "source_verification_status::text = %s AND target_verification_status::text = %s"
        )
        params.extend([verification_status.value, verification_status.value])
    return _page(
        "api_coaching_network_edges",
        clauses=clauses,
        params=params,
        order=(
            "season, team_id, source_coach_id, target_coach_id, source_role, target_role, "
            "source_assignment_key, target_assignment_key"
        ),
        limit=limit,
        offset=offset,
    )


@app.get("/citations", response_model=Page)
def citations(
    coach_id: str | None = None,
    team_id: str | None = None,
    season: int | None = Query(None, ge=2010, le=2025),
    limit: Limit = 50,
    offset: Offset = 0,
) -> Page:
    values = {"coach_id": coach_id, "team_id": team_id, "season": season}
    clauses = [f"{column} = %s" for column, value in values.items() if value is not None]
    params = [value for value in values.values() if value is not None]
    return _page(
        "api_source_citations",
        clauses=clauses,
        params=params,
        order="season DESC, team_id, role, assignment_key, source_url",
        limit=limit,
        offset=offset,
    )


@app.get("/review-queue/summary", response_model=Page)
def review_summary(
    status: ReviewStatus | None = None,
    role: CoachRole | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
) -> Page:
    values = {
        "review_status": status.value if status else None,
        "role::text": role.value if role else None,
    }
    clauses = [f"{column} = %s" for column, value in values.items() if value is not None]
    params = [value for value in values.values() if value is not None]
    return _page(
        "api_review_queue_summary",
        clauses=clauses,
        params=params,
        order="review_status, role, issue_type, load_id",
        limit=limit,
        offset=offset,
    )


@app.get("/schema-version")
def schema_version() -> dict[str, str]:
    return {"schema_version": SCHEMA_VERSION}
