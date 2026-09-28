"""
extract.py — Download and read raw source files into DataFrames.

THE RULE OF EXTRACT:
  Do nothing except acquire the data faithfully.
  No cleaning, no renaming, no validation here.
  If the source is broken, fail loudly and immediately.
  The raw file should always be saveable so you can re-run
  transform without re-downloading.

WHY SAVE RAW FILES TO DISK?
  Network downloads can fail halfway. CDC URLs sometimes change.
  If you transform in memory without saving first, a bug in transform.py
  means you re-download every time you iterate. Raw files are your
  safety checkpoint.
"""

import logging
import requests
import pandas as pd
from pathlib import Path
from tqdm import tqdm

from etl.config import DATA_RAW_DIR, SOURCES

logger = logging.getLogger(__name__)


def download_file(url: str, dest_path: Path, force: bool = False) -> Path:
    """
    Download a file from a URL to dest_path with a progress bar.

    Args:
        url:       Source URL to download from.
        dest_path: Where to save the file locally.
        force:     If False and file already exists, skip download.
                   Set True to force a fresh download.

    Returns:
        Path to the downloaded file.

    WHY STREAM=TRUE?
      Without streaming, requests downloads the entire file into memory
      before writing. A large CDC file can be hundreds of MB. Streaming
      writes chunks to disk as they arrive — safe for any file size.

    WHY CHECK IF FILE EXISTS?
      During development you'll re-run the ETL many times. Skipping the
      download when the file already exists saves time and avoids hammering
      the CDC/CMS servers unnecessarily.
    """
    if dest_path.exists() and not force:
        logger.info("File already exists, skipping download: %s", dest_path.name)
        return dest_path

    logger.info("Downloading: %s", url)
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    response = requests.get(url, stream=True, timeout=60)
    response.raise_for_status()  # raises HTTPError for 4xx/5xx responses

    total_bytes = int(response.headers.get("content-length", 0))

    with open(dest_path, "wb") as f, tqdm(
        total=total_bytes,
        unit="B",
        unit_scale=True,
        desc=dest_path.name,
    ) as progress:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
            progress.update(len(chunk))

    logger.info("Saved to: %s (%.1f MB)", dest_path, dest_path.stat().st_size / 1e6)
    return dest_path


def extract_icd10_codes() -> pd.DataFrame:
    """
    Read the CMS ICD-10-CM file and return a DataFrame of code + description.

    The text file contains one code per line:
        CODE<whitespace>DESCRIPTION
    e.g.:  A000  Cholera due to Vibrio cholerae 01, biovar cholerae

    Returns:
        DataFrame with columns: [code, description]
    """
    icd10_path = DATA_RAW_DIR / "icd10cm_codes.txt"
    if not icd10_path.exists():
        raise FileNotFoundError(
            f"ICD-10 file not found: {icd10_path}"
        )

    logger.info("Reading ICD-10 code file...")
    rows = []

    with open(icd10_path, encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()

            if not line:
                continue

            # First token is the code, rest is the description
            parts = line.split(None, 1)

            if len(parts) == 2:
                rows.append({
                    "code": parts[0].strip(),
                    "description": parts[1].strip(),
                })

    df = pd.DataFrame(rows)
    logger.info("Extracted %d ICD-10 codes", len(df))
    return df


def extract_cdc_mortality() -> pd.DataFrame:
    """
    Download the CDC mortality dataset and return as a raw DataFrame.

    The CDC WONDER mortality file is a CSV. We read it as-is here —
    no renaming, no type conversion. That's transform.py's job.

    Returns:
        Raw DataFrame with CDC's original column names.
    """
    dest = DATA_RAW_DIR / "cdc_mortality.csv"
    download_file(SOURCES["cdc_mortality"], dest)

    logger.info("Reading CDC mortality CSV...")
    # dtype=str reads everything as strings.
    # Reading numbers as strings in extract prevents pandas from silently
    # coercing '001' to 1 or interpreting 'Suppressed' as NaN before we
    # have a chance to handle it deliberately in transform.
    df = pd.read_csv(dest, dtype=str, encoding="utf-8", low_memory=False)
    logger.info(
        "Loaded CDC mortality: %d rows x %d columns", len(df), len(df.columns)
    )
    logger.info("Columns: %s", list(df.columns))
    return df
