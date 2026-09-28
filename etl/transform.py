"""
transform.py — Clean, normalize, and validate raw DataFrames.

THE RULE OF TRANSFORM:
  Every row that exits this module must be safe to insert into the database.
  That means:
    - Column names match the schema exactly
    - Data types are correct (dates are dates, ints are ints)
    - Categorical values are standardized (no mixed case, no synonyms)
    - Rows that can't be salvaged are dropped and logged — never silently passed through
    - Foreign key values (like icd10_code) exist in their reference table

DESIGN PATTERN — each transformer follows the same structure:
  1. Rename columns to match schema
  2. Drop rows missing required (NOT NULL) fields
  3. Standardize / parse values
  4. Validate against reference data
  5. Return clean DataFrame + log a summary
"""

import logging
import pandas as pd
from etl.extract import extract_cdc_mortality

logger = logging.getLogger(__name__)


# ── Shared utilities ──────────────────────────────────────────────────────────

def _log_drop(df_before: pd.DataFrame, df_after: pd.DataFrame, reason: str) -> None:
    """Log how many rows were dropped and why."""
    dropped = len(df_before) - len(df_after)
    if dropped > 0:
        logger.warning("Dropped %d rows — %s", dropped, reason)


def standardize_sex(value: str) -> str | None:
    """
    Normalize sex field to a consistent set of values.

    WHY THIS EXISTS:
      CDC files use 'M'/'F', CMS uses 'Male'/'Female', synthetic data might
      use 'male'/'female'. Your schema stores one format. This function is
      the single place that mapping lives.
    """
    if pd.isna(value):
        return None
    mapping = {
        "m": "male", "male": "male", "1": "male",
        "f": "female", "female": "female", "2": "female",
    }
    return mapping.get(str(value).strip().lower(), "unknown")


def standardize_race(value: str) -> str | None:
    """
    Normalize race to CDC race/ethnicity categories.
    CDC mortality files encode race as numeric codes.
    """
    if pd.isna(value):
        return None
    mapping = {
        "1": "american_indian_alaska_native",
        "2": "asian_pacific_islander",
        "3": "black",
        "4": "white",
        "5": "hispanic",          # Note: CDC treats this inconsistently across datasets
        "white": "white",
        "black": "black",
        "asian": "asian_pacific_islander",
        "american indian or alaska native": "american_indian_alaska_native",
    }
    return mapping.get(str(value).strip().lower(), "other_unknown")


def assign_age_group(age: int | None) -> str | None:
    """
    Convert a numeric age into the age group buckets used in demo_aggregates.

    WHY BUCKETS?
      Individual ages in aggregate data are often suppressed for privacy
      (a county with 2 deaths aged 34 could identify people). Age groups
      are the standard CDC reporting unit and what our schema stores.
    """
    if age is None or pd.isna(age):
        return None
    age = int(age)
    if age < 18:   return "0-17"
    if age < 35:   return "18-34"
    if age < 45:   return "35-44"
    if age < 55:   return "45-54"
    if age < 65:   return "55-64"
    return "65+"


# ── ICD-10 code transformer ───────────────────────────────────────────────────
# This one is written for you as the reference implementation.
# Read it carefully — your mortality transformer should follow the same pattern.

# ICD-10 chapter ranges: maps code prefix → (chapter_code, chapter_name)
# The ICD-10 system organizes codes into chapters by letter prefix.
# e.g. all 'J' codes are respiratory diseases.
ICD10_CHAPTERS = [
    ("A", "B",  "A00-B99", "Certain infectious and parasitic diseases"),
    ("C", "D4", "C00-D49", "Neoplasms"),
    ("D5","D8", "D50-D89", "Diseases of blood and blood-forming organs"),
    ("E", "E",  "E00-E89", "Endocrine, nutritional and metabolic diseases"),
    ("F", "F",  "F01-F99", "Mental, behavioural and neurodevelopmental disorders"),
    ("G", "G",  "G00-G99", "Diseases of the nervous system"),
    ("H0","H5", "H00-H59", "Diseases of the eye and adnexa"),
    ("H6","H9", "H60-H95", "Diseases of the ear and mastoid process"),
    ("I", "I",  "I00-I99", "Diseases of the circulatory system"),
    ("J", "J",  "J00-J99", "Diseases of the respiratory system"),
    ("K", "K",  "K00-K95", "Diseases of the digestive system"),
    ("L", "L",  "L00-L99", "Diseases of the skin and subcutaneous tissue"),
    ("M", "M",  "M00-M99", "Diseases of the musculoskeletal system"),
    ("N", "N",  "N00-N99", "Diseases of the genitourinary system"),
    ("O", "O",  "O00-O9A", "Pregnancy, childbirth and the puerperium"),
    ("P", "P",  "P00-P96", "Conditions originating in the perinatal period"),
    ("Q", "Q",  "Q00-Q99", "Congenital malformations"),
    ("R", "R",  "R00-R99", "Symptoms and signs not classified elsewhere"),
    ("S", "T",  "S00-T98", "Injury, poisoning, and external causes"),
    ("V", "Y",  "V00-Y99", "External causes of morbidity"),
    ("Z", "Z",  "Z00-Z99", "Factors influencing health status"),
    ("U", "U",  "U00-U85", "Codes for special purposes"),
]


def _get_icd10_chapter(code: str) -> tuple[str | None, str | None]:
    """Return (chapter_code, chapter_name) for a given ICD-10 code."""
    if not code or len(code) < 1:
        return None, None
    prefix = code[:2].upper()
    first  = code[0].upper()
    for start, end, chapter_code, chapter_name in ICD10_CHAPTERS:
        if start <= prefix <= end or start[0] <= first <= end[0]:
            return chapter_code, chapter_name
    return None, "Unclassified"


def transform_icd10_codes(df_raw: pd.DataFrame) -> pd.DataFrame:
    """
    Transform the raw CMS ICD-10 extract into a DataFrame ready for
    the icd10_codes table.

    Input columns (from extract.py):  [code, description]
    Output columns (match schema):     [code, description, category, chapter, chapter_code]

    Steps:
      1. Drop rows with null/empty codes
      2. Strip whitespace from codes and descriptions
      3. Derive category from the first 3 characters of the code
         (ICD-10 categories are the 3-character parent — J18 is the category
          for J18.9 "Pneumonia, unspecified")
      4. Assign chapter from the ICD10_CHAPTERS lookup above
      5. Remove duplicates (CMS files occasionally have duplicate codes)
    """
    logger.info("Transforming ICD-10 codes: %d input rows", len(df_raw))
    df = df_raw.copy()

    # drop rows missing either required field
    before = df.copy()
    df = df.dropna(subset=["code", "description"])
    df = df[df["code"].str.strip() != ""]
    _log_drop(before, df, "missing code or description")

    # strip whitespace
    df["code"]        = df["code"].str.strip().str.upper()
    df["description"] = df["description"].str.strip()

    # derive category (first 3 chars of code)
    # J18.9 → category = "J18"
    df["category"] = df["code"].str[:3]

    # assign chapter via lookup
    chapters = df["code"].apply(_get_icd10_chapter)
    df["chapter_code"] = [c[0] for c in chapters]
    df["chapter"]      = [c[1] for c in chapters]

    # deduplicate on code (keep first occurrence)
    before = df.copy()
    df = df.drop_duplicates(subset=["code"], keep="first")
    _log_drop(before, df, "duplicate ICD-10 codes")

    # Reorder columns to match schema exactly
    df = df[["code", "description", "category", "chapter", "chapter_code"]]

    logger.info("ICD-10 transform complete: %d clean rows", len(df))
    return df


# ── CDC Mortality transformer ────────────────────────────────────

# US state name to abbreviation lookup
STATE_ABBREV = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR",
    "California": "CA", "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE",
    "Florida": "FL", "Georgia": "GA", "Hawaii": "HI", "Idaho": "ID",
    "Illinois": "IL", "Indiana": "IN", "Iowa": "IA", "Kansas": "KS",
    "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD",
    "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN", "Mississippi": "MS",
    "Missouri": "MO", "Montana": "MT", "Nebraska": "NE", "Nevada": "NV",
    "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY",
    "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK",
    "Oregon": "OR", "Pennsylvania": "PA", "Rhode Island": "RI",
    "South Carolina": "SC", "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX",
    "Utah": "UT", "Vermont": "VT", "Virginia": "VA", "Washington": "WA",
    "West Virginia": "WV", "Wisconsin": "WI", "Wyoming": "WY",
    "District of Columbia": "DC",
}


"""
    Transform the raw CDC mortality DataFrame into rows ready for demo_aggregates.
    Input:  Raw CDC WONDER CSV as DataFrame (all string columns)
    Output: DataFrame with columns matching demo_aggregates schema
"""
def transform_cdc_mortality(df_raw: pd.DataFrame) -> pd.DataFrame:

    logger.info("Transforming CDC mortality data: %d input rows", len(df_raw))
    df = df_raw.copy()

    # keep only state-level data
    before = df.copy()
    df = df[df["State"] != "United States"]
    _log_drop(before, df, "national rollup rows (State == 'United States')")

    # drop rows with no ICD-10 code in the cause name (e.g. 'All Causes')
    before = df.copy()
    df = df[df["113 Cause Name"].str.contains(r"\(", na=False)]
    _log_drop(before, df, "rows with no ICD-10 code in cause name")

    # extract ICD-10 code range from the last parenthetical in cause name
    df["icd10_code"] = df["113 Cause Name"].str.extract(r"\(([^)]+)\)$")

    # rename columns to match schema
    df = df.rename(columns={
        "State":      "state",
        "Deaths":     "case_count",
        "Year":       "year",
        "Cause Name": "cause_name",
    })

    # convert types
    df[["case_count", "year"]] = df[["case_count", "year"]].astype(int)

    # drop columns not needed in the schema
    df = df.drop(columns=["113 Cause Name", "Age-adjusted Death Rate"])

    # strip leading asterisk — CDC uses * to annotate mid-year code additions
    df["icd10_code"] = df["icd10_code"].str.lstrip("*")

    # extract first code from ranges for FK compatibility with icd10_codes table
    df["icd10_code"] = (
        df["icd10_code"]
        .str.split(",").str[0]
        .str.split("-").str[0]
    )

    # map full state names to 2-letter abbreviations, returns NaN for any key not in STATE_ABBREV
    df["state"] = df["state"].map(STATE_ABBREV)

    # warn if any states failed to map
    unmapped = df["state"].isna().sum()
    if unmapped > 0:
        logger.warning("%d rows have unmapped state values", unmapped)

    # add demographic columns not present in this dataset
    df["sex"]        = "all"
    df["race"]       = "all"
    df["age_group"]  = "all"
    df["payer_type"] = "all"

    # reset index after row drops so index is clean
    df.reset_index(drop=True, inplace=True)

    # reorder columns to match demo_aggregates schema
    df = df[
        [
            "icd10_code",
            "state",
            "age_group",
            "sex",
            "race",
            "payer_type",
            "year",
            "case_count",
            "cause_name",
        ]
    ]

    logger.info("CDC mortality transform complete: %d clean rows", len(df))
    return df

