"""Response shapes. These are what callers see, not the database tables."""

from typing import Optional

from pydantic import BaseModel, Field


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    """Claims read off a JWT. Not returned by any route."""

    username: Optional[str] = None
    role: Optional[str] = None


class ICD10Code(BaseModel):
    code: str
    description: str
    category: Optional[str] = None
    chapter: Optional[str] = None
    chapter_code: Optional[str] = None


class ICD10Chapter(BaseModel):
    chapter: str
    chapter_code: Optional[str] = None
    code_count: int = Field(description="Billable codes in this chapter")


class ICD10Category(BaseModel):
    category: str
    description: str = Field(description="Description of the first code in this category")
    chapter: Optional[str] = None
    code_count: int


class MortalityRecord(BaseModel):
    """One demo_aggregates row: deaths for a cause, state, and year."""

    icd10_code: str
    state: Optional[str] = None
    year: int
    case_count: int
    age_group: Optional[str] = None
    sex: Optional[str] = None
    race: Optional[str] = None
    payer_type: Optional[str] = None


class MortalityTrend(BaseModel):
    year: int
    case_count: int
    cause_name: Optional[str] = None


class StateRanking(BaseModel):
    state: str
    case_count: int
    year: int
    icd10_code: str


class ChapterSummary(BaseModel):
    chapter: str
    total_deaths: int
    year: int


class PaginatedResponse(BaseModel):
    """List wrapper so page metadata can be added without breaking clients."""

    total: int = Field(description="Rows matching the filters")
    page: int = Field(description="Current page, starting at 1")
    size: int = Field(description="Rows per page")
    data: list = Field(description="Rows for this page")
