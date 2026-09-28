# test_transform.py — end to end smoke test for the transform stage
from etl.extract import extract_cdc_mortality
from etl.transform import transform_cdc_mortality

# Step 1 — extract
df_raw = extract_cdc_mortality()

# Step 2 — transform
df_clean = transform_cdc_mortality(df_raw)

# Step 3 — inspect output
print("\n=== FINAL SHAPE ===")
print(df_clean.shape)

print("\n=== COLUMNS ===")
print(df_clean.columns.tolist())

print("\n=== DTYPES ===")
print(df_clean.dtypes)

print("\n=== SAMPLE ROWS ===")
print(df_clean.head(10).to_string())

print("\n=== NULL CHECK ===")
print(df_clean.isnull().sum())

print("\n=== UNIQUE ICD10 CODES ===")
print(df_clean["icd10_code"].unique())