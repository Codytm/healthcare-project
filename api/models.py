"""
models.py — Pydantic response models for the HealthTrack API.

WHAT THIS FILE IS:
  Every endpoint in this API returns JSON. These classes define exactly
  what shape that JSON takes. Think of them as contracts between your
  API and whoever is consuming it.

WHY SEPARATE MODELS FROM DATABASE TABLES?
  Your database schema and your API responses are not the same thing.
  The database has internal fields (created_at, source_system, raw IDs)
  that callers don't need to see. Pydantic models let you choose exactly
  what gets exposed. This is called a DTO — Data Transfer Object.

HOW FASTAPI USES THESE:
  When you annotate a route with response_model=MortalityRecord, FastAPI:
    1. Takes whatever your function returns
    2. Validates it against MortalityRecord
    3. Strips any extra fields not in the model
    4. Serializes it to JSON
  If validation fails, FastAPI raises a 500 before the bad data leaves
  your server. You find out immediately in development.

HOW TO READ THESE CLASSES:
  Each field is:    field_name: type = default_or_description
  Optional[x]  means the field can be null — maps to nullable DB columns
  list[x]      means an array of x in the JSON response
"""

from pydantic import BaseModel, Field
from typing import Optional


# ── Token / Auth models ───────────────────────────────────────────────────────

class Token(BaseModel):
    """Returned by POST /auth/login on success."""
    access_token: str
    token_type: str = "bearer"   # always "bearer" — tells clients how to send it


class TokenData(BaseModel):
    """
    The decoded contents of a JWT payload.
    Used internally — never returned directly to clients.
    """
    username: Optional[str] = None


# ── ICD-10 reference models ───────────────────────────────────────────────────

class ICD10Code(BaseModel):
    """A single ICD-10 code with its description and classification."""
    code:         str
    description:  str
    category:     Optional[str] = None
    chapter:      Optional[str] = None
    chapter_code: Optional[str] = None

    class Config:
        # tells Pydantic to read data from object attributes as well as dicts
        # needed when SQLAlchemy row objects are passed directly
        from_attributes = True


class ICD10Chapter(BaseModel):
    """A unique ICD-10 chapter with its code range."""
    chapter:      str
    chapter_code: Optional[str] = None
    code_count:   int = Field(description="Number of billable codes in this chapter")


class ICD10Category(BaseModel):
    """A 3-character ICD-10 category grouping billable codes."""
    category:    str
    description: str = Field(description="Description of the first code in this category")
    chapter:     Optional[str] = None
    code_count:  int


# ── Mortality / aggregate models ──────────────────────────────────────────────

class MortalityRecord(BaseModel):
    """
    A single row from demo_aggregates.
    Represents death counts for one cause/state/year combination.
    """
    icd10_code:  str
    state:       Optional[str] = None
    year:        int
    case_count:  int
    age_group:   Optional[str] = None
    sex:         Optional[str] = None
    race:        Optional[str] = None
    payer_type:  Optional[str] = None

    class Config:
        from_attributes = True


class MortalityTrend(BaseModel):
    """
    Year-over-year death counts for a single cause.
    Used by the trends endpoint to power time-series charts.
    """
    year:        int
    case_count:  int
    cause_name:  Optional[str] = None


class StateRanking(BaseModel):
    """
    A state's death count for a given cause and year.
    Used by the state comparison endpoint.
    """
    state:       str
    case_count:  int
    year:        int
    icd10_code:  str


class ChapterSummary(BaseModel):
    """
    Total deaths grouped by ICD-10 chapter for a given year.
    Powers the chapter breakdown chart on the dashboard.
    """
    chapter:      str
    total_deaths: int
    year:         int


# ── Shared pagination wrapper ─────────────────────────────────────────────────
# WHY A WRAPPER?
#   Returning a bare list from an API is an anti-pattern. If you later need
#   to add metadata (total count, page number, filters applied), you'd have
#   to break every client. Wrapping in an object from day one means you can
#   add fields without breaking existing consumers.

class PaginatedResponse(BaseModel):
    """Generic wrapper for list responses."""
    total:   int = Field(description="Total records matching the query")
    page:    int = Field(description="Current page number (1-indexed)")
    size:    int = Field(description="Records per page")
    data:    list  = Field(description="The records for this page")
