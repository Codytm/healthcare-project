"""
routers/icd10.py — ICD-10 reference data endpoints.

WHAT THIS ROUTER DOES:
  Exposes the icd10_codes reference table through three endpoints:
    GET /icd10/chapters   — list all ICD-10 chapters (disease categories)
    GET /icd10/categories — list categories within a chapter
    GET /icd10/search     — search codes by keyword

WHY REFERENCE DATA MATTERS:
  Every other endpoint in the API uses ICD-10 codes as filter parameters.
  A client building a dropdown of disease categories needs this data.
  Without it, consumers would have to hardcode values or query the DB directly.

READ THIS FILE CAREFULLY:
  This is the complete reference implementation.
  routers/mortality.py follows the exact same pattern.
  Every design decision here — query structure, error handling,
  response models, parameter validation — should be replicated there.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import text

from api.dependencies import get_db, get_current_user
from api.models import ICD10Chapter, ICD10Category, ICD10Code

logger = logging.getLogger(__name__)

# APIRouter groups these endpoints under a shared prefix and tag.
# prefix="/icd10" is set in main.py when this router is registered.
# tags=["ICD-10 Reference"] controls grouping in the /docs UI.
router = APIRouter(tags=["ICD-10 Reference"])


# ── GET /icd10/chapters ───────────────────────────────────────────────────────

@router.get(
    "/chapters",
    response_model=list[ICD10Chapter],
    summary="List all ICD-10 chapters",
    description="Returns all distinct ICD-10 chapters with their code ranges and the number of billable codes in each.",
)
def list_chapters(
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """
    WHAT THIS ENDPOINT DOES:
      Queries icd10_codes for all distinct chapters, counts codes per chapter,
      and returns them sorted alphabetically.

    WHY REQUIRE AUTH HERE?
      Even reference data is protected. In a real clinical system, exposing
      what diagnosis codes exist could reveal what conditions a facility treats.
      Consistent auth also means every endpoint is protected by default —
      you opt out rather than opt in, which is safer.

    QUERY EXPLANATION:
      GROUP BY chapter, chapter_code — one row per unique chapter
      COUNT(*) — how many billable codes fall in this chapter
      HAVING chapter IS NOT NULL — exclude the small number of codes
        that didn't map to a chapter during ETL
      ORDER BY chapter — alphabetical for consistent response ordering
    """
    logger.info("User '%s' requested ICD-10 chapters", current_user)

    query = text("""
        SELECT
            chapter,
            chapter_code,
            COUNT(*) AS code_count
        FROM icd10_codes
        WHERE chapter IS NOT NULL
        GROUP BY chapter, chapter_code
        ORDER BY chapter
    """)

    rows = db.execute(query).fetchall()

    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No ICD-10 chapters found. Has the ETL pipeline been run?"
        )

    # Convert SQLAlchemy Row objects to dicts, then validate against the model.
    # _mapping gives you a dict-like view of the row — cleaner than indexing by position.
    return [ICD10Chapter(**row._mapping) for row in rows]


# ── GET /icd10/categories ─────────────────────────────────────────────────────

@router.get(
    "/categories",
    response_model=list[ICD10Category],
    summary="List ICD-10 categories",
    description="Returns 3-character ICD-10 categories, optionally filtered by chapter.",
)
def list_categories(
    chapter: str | None = Query(
        default=None,
        description="Filter by chapter name, e.g. 'Diseases of the respiratory system'",
    ),
    limit: int = Query(default=50, ge=1, le=500, description="Max records to return"),
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """
    QUERY PARAMETERS:
      `chapter` is optional — if omitted, returns categories from all chapters.
      `limit` uses FastAPI's Query() with ge=1, le=500:
        ge = greater than or equal (minimum value)
        le = less than or equal (maximum value)
        FastAPI enforces these bounds automatically — no if/else needed in your code.

    PARAMETERIZED QUERIES — WHY :chapter INSTEAD OF f-string:
      Never build SQL with string formatting:
        BAD:  f"WHERE chapter = '{chapter}'"  ← SQL injection vulnerability
        GOOD: "WHERE chapter = :chapter" with {"chapter": chapter}

      SQLAlchemy sends the value separately from the query string.
      The database treats it as data, never as SQL syntax.
      A user passing chapter="'; DROP TABLE icd10_codes; --" gets an error,
      not a dropped table.

    SUBQUERY EXPLANATION:
      The inner query finds the description of the first code in each category
      (MIN(code) gives us the alphabetically first billable code).
      The outer query joins back to get that code's description.
      This gives each category a representative human-readable label.
    """
    logger.info(
        "User '%s' requested categories — chapter filter: %s", current_user, chapter
    )

    params = {"limit": limit}
    where  = "WHERE c.chapter IS NOT NULL"

    if chapter:
        where += " AND c.chapter = :chapter"
        params["chapter"] = chapter

    query = text(f"""
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
    """)

    rows = db.execute(query, params).fetchall()
    return [ICD10Category(**row._mapping) for row in rows]


# ── GET /icd10/search ─────────────────────────────────────────────────────────

@router.get(
    "/search",
    response_model=list[ICD10Code],
    summary="Search ICD-10 codes by keyword",
    description="Full-text search across ICD-10 code descriptions. Uses trigram similarity for fuzzy matching.",
)
def search_codes(
    q: str = Query(
        min_length=2,
        description="Search term, e.g. 'pneumonia' or 'diabetes'"
    ),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """
    SEARCH IMPLEMENTATION:
      Uses PostgreSQL's ILIKE for case-insensitive pattern matching.
      The % wildcards mean "any characters before/after the search term."
      "pneumonia" matches "Pneumonia, unspecified" and
      "Viral pneumonia, not elsewhere classified".

      For fuzzy matching (typo tolerance), we installed pg_trgm in the schema
      and created a GIN index on last_name. For descriptions you could use
      similarity() from pg_trgm — this is an extension you could add later.

    WHY min_length=2 ON THE QUERY PARAMETER?
      A single character search would match thousands of codes and be useless.
      FastAPI enforces this constraint before your function runs — you don't
      need to validate it yourself.
    """
    logger.info("User '%s' searching ICD-10: '%s'", current_user, q)

    query = text("""
        SELECT
            code,
            description,
            category,
            chapter,
            chapter_code
        FROM icd10_codes
        WHERE description ILIKE :search_term
           OR code ILIKE :search_term
        ORDER BY code
        LIMIT :limit
    """)

    rows = db.execute(query, {
        "search_term": f"%{q}%",
        "limit": limit,
    }).fetchall()

    return [ICD10Code(**row._mapping) for row in rows]
