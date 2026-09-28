import logging
from etl.extract import extract_icd10_codes
from etl.extract import extract_cdc_mortality
from etl.transform import transform_icd10_codes
from etl.transform import transform_cdc_mortality
from etl.load import load_icd10_codes
from etl.load import load_demo_aggregates
from etl.load import verify_load

logger = logging.getLogger(__name__)

if __name__ == "__main__":

    logger.info("Pipeline Start")

    # get icd10 data
    df_icd10_raw   = extract_icd10_codes()
    df_icd10_clean = transform_icd10_codes(df_icd10_raw)
    load_icd10_codes(df_icd10_clean)

    # get cdc data
    df_mortality_raw   = extract_cdc_mortality()
    df_mortality_clean = transform_cdc_mortality(df_mortality_raw)
    load_demo_aggregates(df_mortality_clean)

    # verify
    verify_load()

    logger.info("Pipeline Complete")