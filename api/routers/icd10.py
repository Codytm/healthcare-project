"""ICD-10 reference lookups used to filter the mortality endpoints."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.dependencies import get_current_user, get_db
from api.models import ICD10Category, ICD10Chapter, ICD10Code, TokenData

logger = logging.getLogger(__name__)
router = APIRouter(tags=["ICD-10 Reference"])


@router.get(
    "/chapters",
    response_model=list[ICD10Chapter],
    summary="List all ICD-10 chapters",
)
def list_chapters(
    db: Session = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
):
    logger.info("User '%s' requested ICD-10 chapters", current_user.username)
    rows = db.execute(text("""
        SELECT chapter, chapter_code, COUNT(*) AS code_count
        FROM icd10_codes
        WHERE chapter IS NOT NULL
        GROUP BY chapter, chapter_code
        ORDER BY chapter
    """)).fetchall()

    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No ICD-10 chapters found. Has the ETL pipeline been run?",
        )
    return [ICD10Chapter(**row._mapping) for row in rows]


@router.get(
    "/categories",
    response_model=list[ICD10Category],
    summary="List ICD-10 categories",
)
def list_categories(
    chapter: str | None = Query(default=None, description="Chapter name to filter by"),
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
):
    # Bound :chapter instead of interpolating it, so the filter cannot change the SQL.
    logger.info("User '%s' requested categories, chapter=%s", current_user.username, chapter)
    params = {"limit": limit}
    where = "WHERE c.chapter IS NOT NULL"
    if chapter:
        where += " AND c.chapter = :chapter"
        params["chapter"] = chapter

    rows = db.execute(
        text(f"""
            SELECT
                c.category,
                c.chapter,
                COUNT(*) AS code_count,
                (
                    SELECT description
                    FROM icd10_codes
                    WHERE category = c.category
                    ORDER BY code
                    LIMIT 1
                ) AS description
            FROM icd10_codes c
            {where}
            GROUP BY c.category, c.chapter
            ORDER BY c.category
            LIMIT :limit
        """),
        params,
    ).fetchall()
    return [ICD10Category(**row._mapping) for row in rows]


@router.get(
    "/search",
    response_model=list[ICD10Code],
    summary="Search ICD-10 codes by keyword",
)
def search_codes(
    q: str = Query(min_length=2, description="Matched against the code or description"),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
):
    # ILIKE is a case-insensitive substring match, not fuzzy matching.
    logger.info("User '%s' searching ICD-10: '%s'", current_user.username, q)
    rows = db.execute(
        text("""
            SELECT code, description, category, chapter, chapter_code
            FROM icd10_codes
            WHERE description ILIKE :search_term
               OR code ILIKE :search_term
            ORDER BY code
            LIMIT :limit
        """),
        {"search_term": f"%{q}%", "limit": limit},
    ).fetchall()
    return [ICD10Code(**row._mapping) for row in rows]
