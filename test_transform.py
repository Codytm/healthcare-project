# test_transform.py  (add this to .gitignore too)
#.venv\Scripts\Activate.ps1
import pandas as pd
from etl.extract import extract_cdc_mortality
from etl.transform import STATE_ABBREV

# Load once, reuse across checkpoints so you're not re-downloading
df_raw = extract_cdc_mortality()


"""# CHECKPOINT 1 — understand the real data
print("=== ROW COUNT ===")
print(len(df_raw))

print("\n=== ALL COLUMNS ===")
print(df_raw.columns.tolist())

print("\n=== FIRST 10 ROWS ===")
print(df_raw.head(10).to_string())

print("\n=== LAST 5 ROWS ===")
print(df_raw.tail(5).to_string())

print("\n=== DEATHS unique values (all) ===")
print(df_raw["Deaths"].value_counts(dropna=False))

print("\n=== STATE unique values ===")
print(df_raw["State"].value_counts(dropna=False))

print("\n=== 113 Cause Name sample ===")
print(df_raw["113 Cause Name"].unique()[:10])

print("\n=== YEAR unique values ===")
print(df_raw["Year"].unique())
"""

# ====================================================================
# Drop bad rows
df = df_raw.copy()

# TODO 1: Drop rows where State is "United States"
# TODO 2: Drop rows where "113 Cause Name" does not contain "("
#         HINT: pandas Series has a .str.contains() method

# drop rows where the state contains United states
df = df[~df["State"].str.contains("United States", na=False)]

# drop rows where 113 cause name doesn't contain ( meaning no icd10 code present
df = df[df["113 Cause Name"].str.contains(r"\(", na=False)]

print("=== ROWS AFTER DROPPING ===")
print(len(df))
print("\n=== CONFIRM no 'United States' rows remain ===")
print(df[df["State"] == "United States"])
print("\n=== CONFIRM no 'All Causes' rows remain ===")
print(df[df["113 Cause Name"] == "All Causes"])

# ====================================================================
# TODO: Use str.extract() with a regex pattern to pull the content


# grab only the icd10 code from the column, put into new column "icd10_code"
df["icd10_code"] = df["113 Cause Name"].str.extract(r"\(([^)]+)\)$")

print("=== SAMPLE: 113 Cause Name vs extracted icd10_code ===")
print(df[["113 Cause Name", "icd10_code"]].drop_duplicates().head(10).to_string())

print("\n=== ANY NULLS in icd10_code? ===")
print(df["icd10_code"].isna().sum())

# ====================================================================
# TODO 1: Rename the columns listed above using df.rename()
# TODO 2: Convert case_count to int using .astype(int)
# TODO 3: Convert year to int using .astype(int)
# TODO 4: Drop "113 Cause Name" and "Age-adjusted Death Rate"

# rename the columns
df = df.rename(columns={
    "State" : "state",
    "Deaths" : "case_count",
    "Year" : "year",
    "Cause Name" : "cause_name",
})

# convert data types
df[["case_count", "year"]] = df[["case_count", "year"]].astype(int)

# remove unneeded columns
df = df.drop(columns=["113 Cause Name", "Age-adjusted Death Rate"])

print("=== COLUMNS AFTER RENAME ===")
print(df.columns.tolist())

print("\n=== DTYPES ===")
print(df.dtypes)

print("\n=== FIRST 5 ROWS ===")
print(df.head().to_string())

# ====================================================================

# getting rid of the leading asterisk
df["icd10_code"] = df["icd10_code"].str.lstrip("*")

# change the full state name to the abbreviation
df["state"] = df["state"].map(STATE_ABBREV)

# fill in empty attributes not covered in this CDC csv
df["sex"]        = None
df["race"]       = None
df["age_group"]  = None
df["payer_type"] = None


print("\n=== STATE SAMPLE (should be 2-letter) ===")
print(df["state"].value_counts().head(10))

print("\n=== ANY NULLS in state? ===")
print(df["state"].isna().sum())

print("\n=== ICD10 CODE SAMPLE (no leading asterisks) ===")
print(df["icd10_code"].unique())

print("\n=== COLUMNS ===")
print(df.columns.tolist())

# ====================================================================
# TODO 1: Extract the first code from icd10_code ranges

# TODO 2: Reset the index
#         df.reset_index(drop=True, inplace=True)

# TODO 3: Reorder columns to match demo_aggregates schema exactly
#         ["icd10_code", "state", "age_group", "sex", "race",
#          "payer_type", "year", "case_count", "cause_name"]

# extracting the first icd10 code if multiple are present for normalization
df["icd10_code"] = (
    df["icd10_code"]
      .str.split(",").str[0]
      .str.split("-").str[0]
)

# re-indexing the dataframe
df.reset_index(drop=True, inplace=True)

# reordering columns to match schema
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

print("=== FINAL SHAPE ===")
print(df.shape)

print("\n=== FINAL COLUMNS ===")
print(df.columns.tolist())

print("\n=== FINAL DTYPES ===")
print(df.dtypes)

print("\n=== SAMPLE ROWS ===")
print(df.head(10).to_string())

print("\n=== ICD10 CODES (should be single codes now) ===")
print(df["icd10_code"].unique())

print("\n=== NULL CHECK ===")
print(df.isnull().sum())