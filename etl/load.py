"""
load.py — Bulk upsert clean DataFrames into PostgreSQL.

THE RULE OF LOAD:
  By the time data reaches this module it is already clean and validated.
  Load's only job is to get it into the database efficiently and safely.
  Always upsert — never assume a clean table. Always verify — never
  assume the insert succeeded.
"""

import logging
import psycopg2.extras as extras
import pandas as pd
from sqlalchemy import text

from etl.config import get_engine, CHUNK_SIZE

logger = logging.getLogger(__name__)


def _bulk_upsert(conn, query: str, df: pd.DataFrame, chunk_size: int = CHUNK_SIZE) -> int:
    """
    Execute a bulk upsert query in chunks using psycopg2 execute_values.
    Args:
        conn:       raw psycopg2 connection (from engine.raw_connection())
        query:      SQL INSERT ... ON CONFLICT string with %s placeholder
        df:         clean DataFrame to insert
        chunk_size: rows per batch

    Returns:
        Total rows processed
    """
    rows = [tuple(row) for row in df.itertuples(index=False)]
    total = 0

    with conn.cursor() as cur:
        for i in range(0, len(rows), chunk_size):
            chunk = rows[i : i + chunk_size]
            extras.execute_values(cur, query, chunk)
            total += len(chunk)
            logger.info("  Loaded %d / %d rows", total, len(rows))

    conn.commit()
    return total


def load_icd10_codes(df: pd.DataFrame) -> None:
    """
    Upsert ICD-10 reference codes into the icd10_codes table.
    If a code already exists, update its description and category.
    """
    logger.info("Loading %d ICD-10 codes...", len(df))
    engine = get_engine()

    query = """
        INSERT INTO icd10_codes (code, description, category, chapter, chapter_code)
        VALUES %s
        ON CONFLICT (code) DO UPDATE SET
            description  = EXCLUDED.description,
            category     = EXCLUDED.category,
            chapter      = EXCLUDED.chapter,
            chapter_code = EXCLUDED.chapter_code
    """

    conn = engine.raw_connection()
    try:
        total = _bulk_upsert(conn, query, df)
        logger.info("ICD-10 load complete: %d rows upserted", total)
    except Exception as e:
        conn.rollback()
        logger.error("ICD-10 load failed, transaction rolled back: %s", e)
        raise
    finally:
        conn.close()


def load_demo_aggregates(df: pd.DataFrame) -> None:
    #Upsert CDC mortality data into the demo_aggregates table.

    insert_df = df.drop(columns=["cause_name"])

    logger.info("Loading %d demo_aggregates...", len(insert_df))
    engine = get_engine()

    query = """
        INSERT INTO demo_aggregates (icd10_code, state, age_group, sex, race, payer_type, year, case_count)
        VALUES %s
        ON CONFLICT (icd10_code, state, age_group, sex, race, payer_type, year) DO UPDATE SET
            case_count  = EXCLUDED.case_count,
            computed_at = NOW()
    """


    conn = engine.raw_connection()
    try:
        total = _bulk_upsert(conn, query, insert_df)
        logger.info("demo_aggregates load complete: %d rows upserted", total)
    except Exception as e:
        conn.rollback()
        logger.error("demo_aggregates load failed, transaction rolled back: %s", e)
        raise
    finally:
        conn.close()



def verify_load(engine=None) -> None:
    if engine is None:
        engine = get_engine()

    with engine.connect() as conn:
        # row counts
        count_icd10 = conn.execute(text("SELECT COUNT(*) FROM icd10_codes")).scalar()
        count_agg   = conn.execute(text("SELECT COUNT(*) FROM demo_aggregates")).scalar()

        logger.info("icd10_codes rows:     %d", count_icd10)
        logger.info("demo_aggregates rows: %d", count_agg)

        # sample rows
        sample = conn.execute(text("""
            SELECT icd10_code, state, year, case_count
            FROM demo_aggregates
            LIMIT 5
        """)).fetchall()

        logger.info("demo_aggregates sample:")
        for row in sample:
            logger.info("  %s", row)