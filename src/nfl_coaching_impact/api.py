"""Read-only FastAPI surface for the checkpoint-seven PostgreSQL publication."""

from __future__ import annotations

import os
from contextlib import contextmanager
from enum import StrEnum
from typing import Annotated, Any, Literal

import psycopg
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from psycopg import sql
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
    enhancement_data_version: str


class RelationshipCitation(ApiModel):
    source_url: str
    source_title: str | None
    source_type: str | None
    source_accessed_at: str
    evidence_locator: str | None
    evidence_note: str | None


class CoachRelationshipNode(ApiModel):
    node_id: str
    node_type: Literal["coach"]
    coach_id: str
    canonical_name: str


class QuarterbackRelationshipNode(ApiModel):
    node_id: str
    node_type: Literal["quarterback"]
    player_id: str
    display_name: str


class TeamSeasonRelationshipNode(ApiModel):
    node_id: str
    node_type: Literal["team_season"]
    team_id: str
    team_abbr: str
    team_name: str
    season: int


RelationshipNode = CoachRelationshipNode | QuarterbackRelationshipNode | TeamSeasonRelationshipNode


class CoachAssignmentRelationship(ApiModel):
    relationship_id: str
    relationship_type: Literal["coach_assignment"]
    source_node_id: str
    target_node_id: str
    assignment_key: str
    coach_id: str
    team_id: str
    season: int
    role: str
    start_week: int
    end_week: int
    interval_basis: str
    verification_status: str
    confidence_level: str
    is_shared: bool
    is_interim: bool
    is_retained: bool
    is_provisional: bool
    citations: list[RelationshipCitation]
    publication_version: str


class QbTeamSeasonRelationship(ApiModel):
    relationship_id: str
    relationship_type: Literal["qb_team_season"]
    source_node_id: str
    target_node_id: str
    player_id: str
    team_id: str
    season: int
    dropbacks: int
    actual_epa_per_dropback: float | None
    expected_epa_per_dropback: float | None
    performance_above_expectation: float | None
    qualifies_default: bool
    eligibility_status: str | None
    reliability: str | None
    is_out_of_sample: bool | None
    metric_version: str
    model_version: str | None
    historical_data_version: str
    expected_data_version: str | None
    publication_version: str


Relationship = CoachAssignmentRelationship | QbTeamSeasonRelationship


class RelationshipQuery(ApiModel):
    mode: str
    coach_id: str | None
    player_id: str | None
    team_id: str | None
    start_season: int
    end_season: int
    role: str | None
    verification_status: str | None
    include_provisional: bool


class RelationshipSemantics(ApiModel):
    coach_assignment: str
    qb_team_season: str
    coach_qb_context: str
    exact_weekly_overlap: bool


class RelationshipExplorerResponse(ApiModel):
    query: RelationshipQuery
    versions: Versions
    semantics: RelationshipSemantics
    nodes: list[RelationshipNode]
    relationships: list[Relationship]
    node_count: int
    relationship_count: int
    max_nodes: int
    max_relationships: int


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


class RelationshipMode(StrEnum):
    COACH_JOURNEY = "coach_journey"
    QB_JOURNEY = "qb_journey"
    TEAM_HISTORY = "team_history"
    FULL_NETWORK = "full_network"


app = FastAPI(
    title="NFL Coaching Impact Engine API",
    version=API_CONTRACT_VERSION,
    description=(
        "Read-only access to versioned QB, PAE, coaching-assignment, and exploratory "
        "coach-impact outputs. Suppression and identification labels are preserved."
    ),
)


def _cors_origins() -> list[str]:
    """Return the explicitly configured browser origins; wildcards are never accepted."""
    origins = [
        origin.strip().rstrip("/")
        for origin in os.environ.get("CORS_ORIGINS", "").split(",")
        if origin.strip()
    ]
    if "*" in origins:
        raise RuntimeError("CORS_ORIGINS must list explicit origins; '*' is not allowed")
    return origins


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["Accept", "Content-Type"],
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
MAX_RELATIONSHIP_NODES = 1_000
MAX_RELATIONSHIPS = 2_000
MAX_FULL_NETWORK_SEASONS = 5


def _active_versions(connection: Any) -> Versions:
    row = connection.execute(
        "SELECT l.load_id::text, l.schema_version, l.loader_version, "
        "l.api_contract_version, l.historical_data_version, l.expected_data_version, "
        "l.expected_model_version, l.coach_data_version, l.coach_model_version, "
        "l.enhancement_data_version "
        "FROM serving_loads l JOIN serving_publication p ON p.load_id = l.load_id"
    ).fetchone()
    if not row:
        raise HTTPException(status_code=503, detail="No serving publication is available")
    versions = Versions(**row)
    if versions.api_contract_version != API_CONTRACT_VERSION:
        raise HTTPException(
            status_code=503,
            detail=(
                "Serving publication API contract does not match the running application; "
                "reload the publication"
            ),
        )
    return versions


@app.get("/health", response_model=Health)
def health() -> Health:
    with _connection() as connection:
        connection.execute("SELECT 1")
    return Health(status="ok", database="available", api_contract_version=API_CONTRACT_VERSION)


@app.get("/versions", response_model=Versions)
def versions() -> Versions:
    with _connection() as connection:
        return _active_versions(connection)


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


@app.get("/coaching/completeness", response_model=Page)
def coaching_completeness(
    team_id: str | None = None,
    season: int | None = Query(None, ge=2010, le=2025),
    role: CoachRole | None = None,
    assignment_status: Literal["verified", "provisional", "conflicting", "missing"] | None = None,
    requires_manual_review: bool | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
) -> Page:
    values = {
        "team_id": team_id,
        "season": season,
        "role::text": role.value if role else None,
        "assignment_status": assignment_status,
        "requires_manual_review": requires_manual_review,
    }
    clauses = [f"{column} = %s" for column, value in values.items() if value is not None]
    params = [value for value in values.values() if value is not None]
    return _page(
        "api_coaching_completeness",
        clauses=clauses,
        params=params,
        order="season DESC, team_id, role",
        limit=limit,
        offset=offset,
    )


@app.get("/environment", response_model=Page)
def inherited_environment(
    team_id: str | None = None,
    season: int | None = Query(None, ge=2010, le=2025),
    limit: Limit = 50,
    offset: Offset = 0,
) -> Page:
    values = {"team_id": team_id, "season": season}
    clauses = [f"{column} = %s" for column, value in values.items() if value is not None]
    params = [value for value in values.values() if value is not None]
    return _page(
        "api_inherited_environment",
        clauses=clauses,
        params=params,
        order="season DESC, team_id",
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


def _relationship_qb_rows(
    connection: Any,
    team_seasons: set[tuple[str, int]],
    *,
    player_id: str | None,
) -> list[dict[str, Any]]:
    if not team_seasons:
        return []
    ordered_scope = sorted(team_seasons, key=lambda item: (item[1], item[0]))
    values = sql.SQL(", ").join(sql.SQL("(%s, %s)") for _ in ordered_scope)
    player_clause = sql.SQL(" AND qs.player_id = %s") if player_id else sql.SQL("")
    query = sql.SQL(
        """
        WITH scope(team_id, season) AS (VALUES {values})
        SELECT qs.load_id::text, qs.player_id, qs.display_name, qs.team_id, qs.season,
               qs.dropbacks, qs.epa_per_dropback, qs.qualifies_default, qs.metric_version,
               t.team_abbr, t.team_name,
               pae.data_version AS expected_data_version,
               pae.model_version, pae.expected_epa_per_dropback,
               pae.actual_epa_per_dropback AS pae_actual_epa_per_dropback,
               pae.performance_above_expectation, pae.eligibility_status,
               pae.reliability, pae.is_out_of_sample
          FROM api_qb_statistics qs
          JOIN scope s ON s.team_id = qs.team_id AND s.season = qs.season
          JOIN serving_teams t ON t.load_id = qs.load_id AND t.team_id = qs.team_id
          LEFT JOIN api_qb_pae pae
            ON pae.load_id = qs.load_id AND pae.player_id = qs.player_id
           AND pae.team_id = qs.team_id AND pae.season = qs.season
         WHERE true {player_clause}
         ORDER BY qs.season, qs.team_id, qs.display_name, qs.player_id
         LIMIT %s
        """
    ).format(values=values, player_clause=player_clause)
    params: list[Any] = [value for item in ordered_scope for value in item]
    if player_id:
        params.append(player_id)
    params.append(MAX_RELATIONSHIPS + 1)
    return connection.execute(query, params).fetchall()


@app.get("/relationships/explorer", response_model=RelationshipExplorerResponse)
def relationship_explorer(
    mode: RelationshipMode,
    coach_id: str | None = None,
    player_id: str | None = None,
    team_id: str | None = None,
    start_season: int = Query(2010, ge=2010, le=2025),
    end_season: int = Query(2025, ge=2010, le=2025),
    role: CoachRole | None = None,
    verification_status: VerificationStatus | None = None,
    include_provisional: bool = False,
) -> RelationshipExplorerResponse:
    """Return a bounded Coach -> Team-Season <- QB evidence graph."""

    if start_season > end_season:
        raise HTTPException(status_code=422, detail="start_season must not exceed end_season")
    if mode == RelationshipMode.COACH_JOURNEY and not coach_id:
        raise HTTPException(status_code=422, detail="coach_journey requires coach_id")
    if mode == RelationshipMode.QB_JOURNEY and not player_id:
        raise HTTPException(status_code=422, detail="qb_journey requires player_id")
    if mode == RelationshipMode.TEAM_HISTORY and not team_id:
        raise HTTPException(status_code=422, detail="team_history requires team_id")
    if mode == RelationshipMode.FULL_NETWORK:
        if not any((coach_id, player_id, team_id)):
            raise HTTPException(
                status_code=422,
                detail="full_network requires coach_id, player_id, or team_id",
            )
        if end_season - start_season + 1 > MAX_FULL_NETWORK_SEASONS:
            raise HTTPException(
                status_code=422,
                detail=f"full_network is limited to {MAX_FULL_NETWORK_SEASONS} seasons",
            )
    if verification_status == VerificationStatus.PROVISIONAL and not include_provisional:
        raise HTTPException(
            status_code=422,
            detail="include_provisional=true is required for provisional relationships",
        )

    clauses = ["a.season BETWEEN %s AND %s"]
    params: list[Any] = [start_season, end_season]
    if coach_id:
        clauses.append("a.coach_id = %s")
        params.append(coach_id)
    if team_id:
        clauses.append("a.team_id = %s")
        params.append(team_id)
    if player_id:
        clauses.append(
            "EXISTS (SELECT 1 FROM api_qb_statistics qs "
            "WHERE qs.player_id = %s AND qs.team_id = a.team_id AND qs.season = a.season)"
        )
        params.append(player_id)
    if role:
        clauses.append("a.role::text = %s")
        params.append(role.value)
    if verification_status:
        clauses.append("a.verification_status::text = %s")
        params.append(verification_status.value)
    if not include_provisional:
        clauses.append("a.verification_status::text <> 'provisional'")

    with _connection() as connection:
        active_versions = _active_versions(connection)
        assignment_rows = connection.execute(
            "SELECT a.* FROM api_coaching_assignments a WHERE "
            + " AND ".join(clauses)
            + " ORDER BY a.season, a.team_id, a.role, a.start_week, a.end_week, "
            "a.assignment_key LIMIT %s",
            [*params, MAX_RELATIONSHIPS + 1],
        ).fetchall()
        if len(assignment_rows) > MAX_RELATIONSHIPS:
            raise HTTPException(
                status_code=413, detail="Relationship scope is too large; narrow it"
            )

        team_seasons = {(row["team_id"], row["season"]) for row in assignment_rows}
        preserve_team_qbs = bool(
            team_id and mode in {RelationshipMode.TEAM_HISTORY, RelationshipMode.FULL_NETWORK}
        )
        if player_id or preserve_team_qbs:
            anchor_clauses = ["season BETWEEN %s AND %s"]
            anchor_params: list[Any] = [start_season, end_season]
            if player_id:
                anchor_clauses.append("player_id = %s")
                anchor_params.append(player_id)
            if team_id:
                anchor_clauses.append("team_id = %s")
                anchor_params.append(team_id)
            anchor_rows = connection.execute(
                "SELECT DISTINCT team_id, season FROM api_qb_statistics WHERE "
                + " AND ".join(anchor_clauses)
                + " ORDER BY season, team_id LIMIT %s",
                [*anchor_params, MAX_RELATIONSHIPS + 1],
            ).fetchall()
            if len(anchor_rows) > MAX_RELATIONSHIPS:
                raise HTTPException(
                    status_code=413, detail="Relationship scope is too large; narrow it"
                )
            team_seasons.update((row["team_id"], row["season"]) for row in anchor_rows)

        qb_rows = _relationship_qb_rows(
            connection,
            team_seasons,
            player_id=player_id,
        )
        if len(qb_rows) > MAX_RELATIONSHIPS:
            raise HTTPException(
                status_code=413, detail="Relationship scope is too large; narrow it"
            )

        assignment_keys = [row["assignment_key"] for row in assignment_rows]
        citation_rows = (
            connection.execute(
                "SELECT * FROM api_source_citations WHERE assignment_key = ANY(%s) "
                "ORDER BY assignment_key, source_url",
                (assignment_keys,),
            ).fetchall()
            if assignment_keys
            else []
        )

    citations: dict[str, list[RelationshipCitation]] = {}
    for row in citation_rows:
        citations.setdefault(row["assignment_key"], []).append(
            RelationshipCitation(
                source_url=row["source_url"],
                source_title=row["source_title"],
                source_type=row["source_type"],
                source_accessed_at=row["source_accessed_at"].isoformat(),
                evidence_locator=row["evidence_locator"],
                evidence_note=row["evidence_note"],
            )
        )

    node_by_id: dict[str, RelationshipNode] = {}
    relationships: list[Relationship] = []
    publication_version = active_versions.load_id
    for row in assignment_rows:
        coach_node_id = f"coach:{row['coach_id']}"
        team_season_node_id = f"team-season:{row['team_id']}:{row['season']}"
        node_by_id[coach_node_id] = CoachRelationshipNode(
            node_id=coach_node_id,
            node_type="coach",
            coach_id=row["coach_id"],
            canonical_name=row["canonical_name"],
        )
        node_by_id[team_season_node_id] = TeamSeasonRelationshipNode(
            node_id=team_season_node_id,
            node_type="team_season",
            team_id=row["team_id"],
            team_abbr=row["team_abbr"],
            team_name=row["team_name"],
            season=row["season"],
        )
        relationships.append(
            CoachAssignmentRelationship(
                relationship_id=row["assignment_key"],
                relationship_type="coach_assignment",
                source_node_id=coach_node_id,
                target_node_id=team_season_node_id,
                assignment_key=row["assignment_key"],
                coach_id=row["coach_id"],
                team_id=row["team_id"],
                season=row["season"],
                role=str(row["role"]),
                start_week=row["start_week"],
                end_week=row["end_week"],
                interval_basis=str(row["interval_basis"]),
                verification_status=str(row["verification_status"]),
                confidence_level=str(row["confidence_level"]),
                is_shared=row["is_shared"],
                is_interim=row["is_interim"],
                is_retained=row["is_retained"],
                is_provisional=str(row["verification_status"]) == "provisional",
                citations=citations.get(row["assignment_key"], []),
                publication_version=publication_version,
            )
        )

    seen_qb_relationships: set[tuple[str, str, int]] = set()
    for row in qb_rows:
        qb_key = (row["player_id"], row["team_id"], row["season"])
        if qb_key in seen_qb_relationships:
            raise HTTPException(status_code=503, detail="Duplicate QB-team-season relationship")
        seen_qb_relationships.add(qb_key)
        qb_node_id = f"qb:{row['player_id']}"
        team_season_node_id = f"team-season:{row['team_id']}:{row['season']}"
        node_by_id[qb_node_id] = QuarterbackRelationshipNode(
            node_id=qb_node_id,
            node_type="quarterback",
            player_id=row["player_id"],
            display_name=row["display_name"],
        )
        node_by_id[team_season_node_id] = TeamSeasonRelationshipNode(
            node_id=team_season_node_id,
            node_type="team_season",
            team_id=row["team_id"],
            team_abbr=row["team_abbr"],
            team_name=row["team_name"],
            season=row["season"],
        )
        relationships.append(
            QbTeamSeasonRelationship(
                relationship_id=(
                    f"qb-team-season:{row['player_id']}:{row['team_id']}:{row['season']}"
                ),
                relationship_type="qb_team_season",
                source_node_id=qb_node_id,
                target_node_id=team_season_node_id,
                player_id=row["player_id"],
                team_id=row["team_id"],
                season=row["season"],
                dropbacks=row["dropbacks"],
                actual_epa_per_dropback=(
                    row["pae_actual_epa_per_dropback"]
                    if row["performance_above_expectation"] is not None
                    else row["epa_per_dropback"]
                ),
                expected_epa_per_dropback=row["expected_epa_per_dropback"],
                performance_above_expectation=row["performance_above_expectation"],
                qualifies_default=row["qualifies_default"],
                eligibility_status=row["eligibility_status"],
                reliability=row["reliability"],
                is_out_of_sample=row["is_out_of_sample"],
                metric_version=row["metric_version"],
                model_version=row["model_version"],
                historical_data_version=active_versions.historical_data_version,
                expected_data_version=row["expected_data_version"],
                publication_version=publication_version,
            )
        )

    nodes = sorted(node_by_id.values(), key=lambda item: (item.node_type, item.node_id))
    relationships.sort(key=lambda item: (item.relationship_type, item.relationship_id))
    if len(nodes) > MAX_RELATIONSHIP_NODES or len(relationships) > MAX_RELATIONSHIPS:
        raise HTTPException(status_code=413, detail="Relationship scope is too large; narrow it")

    return RelationshipExplorerResponse(
        query=RelationshipQuery(
            mode=mode.value,
            coach_id=coach_id,
            player_id=player_id,
            team_id=team_id,
            start_season=start_season,
            end_season=end_season,
            role=role.value if role else None,
            verification_status=verification_status.value if verification_status else None,
            include_provisional=include_provisional,
        ),
        versions=active_versions,
        semantics=RelationshipSemantics(
            coach_assignment=(
                "Source-backed coaching assignment for the stated team-season interval"
            ),
            qb_team_season="Authoritative QB participation/performance for one team-season",
            coach_qb_context=(
                "QB participated for this team-season while the coaching assignment existed "
                "within the same season"
            ),
            exact_weekly_overlap=False,
        ),
        nodes=nodes,
        relationships=relationships,
        node_count=len(nodes),
        relationship_count=len(relationships),
        max_nodes=MAX_RELATIONSHIP_NODES,
        max_relationships=MAX_RELATIONSHIPS,
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
