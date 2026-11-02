"""Death counts from demo_aggregates.

CDC WONDER rows are state and year totals. The ETL stores sex, race, age_group,
and payer_type as the literal "all", and keeps only the first code of each cause
range so it can reference icd10_codes. Filtering those demographic columns only
matches when the caller passes "all" or leaves them off.
"""

import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.cache import cache_get, cache_set, make_cache_key
from api.dependencies import get_current_user, get_db
from api.models import (
    ChapterSummary,
    MortalityRecord,
    MortalityTrend,
    PaginatedResponse,
    StateRanking,
    TokenData,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Mortality Analytics"])

_RECORD_FILTERS = ("icd10_code", "state", "year", "sex", "race", "age_group")


def _record_where(filters: dict) -> tuple[str, dict]:
    """Only supplied filters become equality checks. Column names come from the fixed list above."""
    clauses = []
    params = {}
    for name in _RECORD_FILTERS:
        value = filters.get(name)
        if value is not None:
            clauses.append(f"{name} = :{name}")
            params[name] = value
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return where, params


def _load_cached(route: str, params: dict, model):
    hit = cache_get(make_cache_key(route, params))
    if hit is None:
        return None
    return [model(**row) for row in hit]


def _store(route: str, params: dict, rows: list) -> list:
    cache_set(make_cache_key(route, params), [row.model_dump() for row in rows])
    return rows


@router.get("/records", response_model=PaginatedResponse, summary="List mortality aggregate rows")
def list_records(
    icd10_code: str | None = Query(default=None),
    state: str | None = Query(default=None, description="Two-letter state abbreviation"),
    year: int | None = Query(default=None, ge=1900, le=2100),
    sex: str | None = Query(default=None),
    race: str | None = Query(default=None),
    age_group: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
):
    # Record search is not cached; each filter combination would be its own key.
    filters = {
        "icd10_code": icd10_code,
        "state": state,
        "year": year,
        "sex": sex,
        "race": race,
        "age_group": age_group,
    }
    where, params = _record_where(filters)
    logger.info("User '%s' listed mortality records %s", current_user.username, params)

    total = db.execute(text(f"SELECT COUNT(*) FROM demo_aggregates {where}"), params).scalar()
    rows = db.execute(
        text(f"""
            SELECT icd10_code, state, year, case_count, age_group, sex, race, payer_type
            FROM demo_aggregates
            {where}
            ORDER BY year, state, icd10_code
            LIMIT :limit OFFSET :offset
        """),
        {**params, "limit": size, "offset": (page - 1) * size},
    ).fetchall()
    return PaginatedResponse(
        total=total or 0,
        page=page,
        size=size,
        data=[MortalityRecord(**row._mapping) for row in rows],
    )


@router.get("/trends", response_model=list[MortalityTrend], summary="Year-over-year deaths for one cause")
def mortality_trends(
    icd10_code: str = Query(description="Code stored on demo_aggregates"),
    state: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
):
    params = {"icd10_code": icd10_code, "state": state}
    logger.info("User '%s' requested mortality trends %s", current_user.username, params)
    cached = _load_cached("mortality:trends", params, MortalityTrend)
    if cached is not None:
        return cached

    where = "WHERE a.icd10_code = :icd10_code"
    query_params = {"icd10_code": icd10_code}
    if state:
        where += " AND a.state = :state"
        query_params["state"] = state

    rows = db.execute(
        text(f"""
            SELECT
                a.year,
                SUM(a.case_count)::int AS case_count,
                MAX(i.description) AS cause_name
            FROM demo_aggregates a
            LEFT JOIN icd10_codes i ON i.code = a.icd10_code
            {where}
            GROUP BY a.year
            ORDER BY a.year
        """),
        query_params,
    ).fetchall()
    return _store("mortality:trends", params, [MortalityTrend(**row._mapping) for row in rows])


@router.get("/states", response_model=list[StateRanking], summary="Rank states for one cause and year")
def state_rankings(
    icd10_code: str = Query(description="Code stored on demo_aggregates"),
    year: int = Query(ge=1900, le=2100),
    db: Session = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
):
    params = {"icd10_code": icd10_code, "year": year}
    logger.info("User '%s' requested state rankings %s", current_user.username, params)
    cached = _load_cached("mortality:states", params, StateRanking)
    if cached is not None:
        return cached

    rows = db.execute(
        text("""
            SELECT
                state,
                SUM(case_count)::int AS case_count,
                year,
                icd10_code
            FROM demo_aggregates
            WHERE icd10_code = :icd10_code
              AND year = :year
              AND state IS NOT NULL
            GROUP BY state, year, icd10_code
            ORDER BY case_count DESC, state
        """),
        params,
    ).fetchall()
    return _store("mortality:states", params, [StateRanking(**row._mapping) for row in rows])


@router.get("/chapters", response_model=list[ChapterSummary], summary="Deaths grouped by ICD-10 chapter")
def chapter_summary(
    year: int = Query(ge=1900, le=2100),
    db: Session = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
):
    # Inner join drops aggregate rows whose code never landed in icd10_codes.
    params = {"year": year}
    logger.info("User '%s' requested chapter summary for %s", current_user.username, year)
    cached = _load_cached("mortality:chapters", params, ChapterSummary)
    if cached is not None:
        return cached

    rows = db.execute(
        text("""
            SELECT
                i.chapter,
                SUM(a.case_count)::int AS total_deaths,
                a.year
            FROM demo_aggregates a
            JOIN icd10_codes i ON i.code = a.icd10_code
            WHERE a.year = :year
              AND i.chapter IS NOT NULL
            GROUP BY i.chapter, a.year
            ORDER BY total_deaths DESC, i.chapter
        """),
        params,
    ).fetchall()
    return _store("mortality:chapters", params, [ChapterSummary(**row._mapping) for row in rows])
