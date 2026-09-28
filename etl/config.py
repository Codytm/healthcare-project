"""
config.py — Central configuration for the HealthTrack ETL pipeline.

WHY THIS FILE EXISTS:
  Never hardcode database credentials, file paths, or environment-specific
  settings directly in your code. If you do, you'll accidentally commit a
  password to GitHub, or break the pipeline when moving between machines.

  Instead, all secrets live in a .env file (which is git-ignored), and this
  module reads them into a single Config object the rest of the app imports.

HOW .env WORKS:
  python-dotenv reads a file named .env in your project root at startup.
  A .env file looks like this:

      DB_HOST=localhost
      DB_PORT=5432
      DB_NAME=healthtrack
      DB_USER=postgres
      DB_PASSWORD=yourpassword

  Your code never sees the raw string — it calls os.getenv("DB_HOST").
  On a real server, you'd set these as actual environment variables instead
  of a file. The code doesn't change either way. That's the point.
"""

import os
import logging
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError

ICD10_YEAR = "2025"

# ── Locate project root and load .env ────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env")


# ── Directory paths ───────────────────────────────────────────────────────────
# Using pathlib.Path instead of raw strings means this works on Windows,
# Mac, and Linux without you changing anything (no backslash/forward-slash issues)
DATA_RAW_DIR       = PROJECT_ROOT / "data" / "raw"
DATA_PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
LOG_DIR            = PROJECT_ROOT / "logs"

# Ensure directories exist at import time
DATA_RAW_DIR.mkdir(parents=True, exist_ok=True)
DATA_PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)


# ── Logging setup ─────────────────────────────────────────────────────────────
# Configured once here so every module that imports config gets consistent
# log formatting. Logs go to both console AND a file simultaneously.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(),                                  # console
        logging.FileHandler(LOG_DIR / "etl.log", encoding="utf-8"),  # file
    ],
)
logger = logging.getLogger(__name__)


# ── Database configuration ────────────────────────────────────────────────────
DB_CONFIG = {
    "host":     os.getenv("DB_HOST", "localhost"),
    "port":     int(os.getenv("DB_PORT", 5432)),
    "dbname":   os.getenv("DB_NAME", "healthtrack"),
    "user":     os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", ""),
}

# SQLAlchemy connection string format:
#   postgresql+psycopg2://user:password@host:port/dbname
DB_URL = (
    f"postgresql+psycopg2://{DB_CONFIG['user']}:{DB_CONFIG['password']}"
    f"@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['dbname']}"
)


def get_engine():
    """
    Returns a SQLAlchemy engine with connection pooling.

    WHY A FUNCTION instead of a module-level engine?
      If config.py is imported but the DB isn't running yet, a module-level
      engine would fail at import time and crash the whole app. A function
      fails only when called — so you can import config safely and connect
      only when you actually need the database.
    """
    try:
        engine = create_engine(
            DB_URL,
            pool_size=5,        # keep 5 connections open and ready
            max_overflow=10,    # allow up to 10 extra under heavy load
            pool_timeout=30,    # wait up to 30s for a free connection
            pool_pre_ping=True, # test connections before use (handles restarts)
        )
        # Test the connection immediately so failures are obvious
        with engine.connect() as conn:
            logger.info("Database connection established: %s/%s",
                        DB_CONFIG["host"], DB_CONFIG["dbname"])
        return engine
    except OperationalError as e:
        logger.error("Could not connect to database: %s", e)
        raise


# ── Source data URLs ──────────────────────────────────────────────────────────
# Centralised here so if a URL changes you fix it in one place.
SOURCES = {
    # CDC Wonder compressed mortality
    "cdc_mortality": (
        "https://data.cdc.gov/api/views/bi63-dtpu/rows.csv?accessType=DOWNLOAD"
    ),
}

# ── ETL behaviour constants ───────────────────────────────────────────────────
CHUNK_SIZE   = 10_000   # rows processed per batch during load
LOG_EVERY    = 50_000   # log progress every N rows during transform
