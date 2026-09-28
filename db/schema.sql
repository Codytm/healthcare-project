-- ============================================================
-- HealthTrack Analytics — Database Schema — Cody Musulin
-- PostgreSQL 18
-- ============================================================

-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- enables fuzzy text search on names


-- ============================================================
-- REFERENCE TABLES
-- ============================================================

CREATE TABLE icd10_codes (
    code            VARCHAR(10)  PRIMARY KEY,          -- e.g. 'J18.9'
    description     VARCHAR(255) NOT NULL,              -- e.g. 'Pneumonia, unspecified'
    category        VARCHAR(100),                       -- e.g. 'Pneumonia'
    chapter         VARCHAR(100),                       -- e.g. 'Diseases of the respiratory system'
    chapter_code    VARCHAR(10)                         -- e.g. 'J00-J99'
);

COMMENT ON TABLE icd10_codes IS
  'Reference table for ICD-10-CM codes. Loaded once from CMS ICD-10 release files.';


-- ============================================================
-- CORE ENTITY TABLES
-- ============================================================

CREATE TABLE facilities (
    facility_id     UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
    name            VARCHAR(255) NOT NULL,
    facility_type   VARCHAR(50)  NOT NULL,              -- 'hospital', 'clinic', 'urgent_care'
    street_address  VARCHAR(255),
    city            VARCHAR(100),
    state           CHAR(2)      NOT NULL,
    zip_code        VARCHAR(10),
    created_at      TIMESTAMP    NOT NULL DEFAULT NOW()
);

CREATE TABLE patients (
    patient_id      UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
    first_name      VARCHAR(100),                       -- nullable: de-identified datasets
    last_name       VARCHAR(100),                       -- nullable: de-identified datasets
    date_of_birth   DATE,
    sex             VARCHAR(20),
    race            VARCHAR(50),                        -- CDC race categories
    ethnicity       VARCHAR(50),
    zip_code        VARCHAR(10),
    state           CHAR(2),
    source_system   VARCHAR(50)  NOT NULL DEFAULT 'cdc',-- 'cdc', 'cms', 'synthetic'
    created_at      TIMESTAMP    NOT NULL DEFAULT NOW()
);

COMMENT ON COLUMN patients.source_system IS
  'Tracks which ETL source loaded this patient. Critical for deduplication.';

CREATE TABLE providers (
    provider_id     UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
    npi             VARCHAR(10)  UNIQUE,                -- National Provider Identifier
    full_name       VARCHAR(255),
    specialty       VARCHAR(100),
    facility_id     UUID         REFERENCES facilities(facility_id),
    state           CHAR(2),
    created_at      TIMESTAMP    NOT NULL DEFAULT NOW()
);


-- ============================================================
-- EVENT TABLES
-- ============================================================

CREATE TABLE visits (
    visit_id        UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
    patient_id      UUID         NOT NULL REFERENCES patients(patient_id)  ON DELETE CASCADE,
    provider_id     UUID                  REFERENCES providers(provider_id) ON DELETE SET NULL,
    facility_id     UUID                  REFERENCES facilities(facility_id) ON DELETE SET NULL,
    visit_date      DATE         NOT NULL,
    visit_type      VARCHAR(50),                        -- 'inpatient', 'outpatient', 'emergency'
    payer_type      VARCHAR(50),                        -- 'medicare', 'medicaid', 'private', 'uninsured'
    length_of_stay  INT,                                -- days; NULL for outpatient
    discharge_status VARCHAR(50),
    created_at      TIMESTAMP    NOT NULL DEFAULT NOW()
);

CREATE TABLE diagnoses (
    diagnosis_id    UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
    visit_id        UUID         NOT NULL REFERENCES visits(visit_id) ON DELETE CASCADE,
    icd10_code      VARCHAR(10)  NOT NULL REFERENCES icd10_codes(code),
    is_primary      BOOLEAN      NOT NULL DEFAULT FALSE, -- TRUE = primary dx for this visit
    diagnosis_date  DATE,
    notes           TEXT,
    created_at      TIMESTAMP    NOT NULL DEFAULT NOW()
);

COMMENT ON COLUMN diagnoses.is_primary IS
  'Primary diagnosis = main reason for visit.';

CREATE TABLE procedures (
    procedure_id    UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
    visit_id        UUID         NOT NULL REFERENCES visits(visit_id) ON DELETE CASCADE,
    cpt_code        VARCHAR(10),                        -- Current Procedural Terminology
    description     VARCHAR(255),
    procedure_date  DATE,
    created_at      TIMESTAMP    NOT NULL DEFAULT NOW()
);


-- ============================================================
-- AGGREGATE / REPORTING TABLE
-- ============================================================

CREATE TABLE demo_aggregates (
    agg_id          UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
    icd10_code      VARCHAR(10)  NOT NULL REFERENCES icd10_codes(code),
    state           CHAR(2),
    age_group       VARCHAR(20),                        -- '0-17', '18-34', '35-44', '45-54', '55-64', '65+'
    sex             VARCHAR(20),
    race            VARCHAR(50),
    payer_type      VARCHAR(50),
    year            SMALLINT     NOT NULL,
    case_count      INT          NOT NULL DEFAULT 0,
    visit_count     INT          NOT NULL DEFAULT 0,
    computed_at     TIMESTAMP    NOT NULL DEFAULT NOW(),

    UNIQUE (icd10_code, state, age_group, sex, race, payer_type, year)
);

COMMENT ON TABLE demo_aggregates IS
  'Pre-computed counts by demographic slice. Populated nightly by ETL.
   Dashboard queries this table — never the raw diagnoses table.';


-- ============================================================
-- INDEXES
-- ============================================================

-- Patient lookups
CREATE INDEX idx_patients_state        ON patients(state);
CREATE INDEX idx_patients_zip          ON patients(zip_code);
CREATE INDEX idx_patients_source       ON patients(source_system);
CREATE INDEX idx_patients_name_trgm    ON patients USING gin(last_name gin_trgm_ops);

-- Visit queries
CREATE INDEX idx_visits_patient        ON visits(patient_id);
CREATE INDEX idx_visits_date           ON visits(visit_date);
CREATE INDEX idx_visits_payer          ON visits(payer_type);
CREATE INDEX idx_visits_type           ON visits(visit_type);
CREATE INDEX idx_visits_patient_date   ON visits(patient_id, visit_date DESC);  -- composite: patient timeline

-- Diagnosis queries (most common dashboard queries hit this table)
CREATE INDEX idx_diagnoses_visit       ON diagnoses(visit_id);
CREATE INDEX idx_diagnoses_icd10       ON diagnoses(icd10_code);
CREATE INDEX idx_diagnoses_primary     ON diagnoses(icd10_code) WHERE is_primary = TRUE;  -- partial index

-- Aggregate dashboard queries
CREATE INDEX idx_agg_icd10             ON demo_aggregates(icd10_code);
CREATE INDEX idx_agg_state_year        ON demo_aggregates(state, year);
CREATE INDEX idx_agg_icd10_year        ON demo_aggregates(icd10_code, year);

-- ICD-10 reference lookups
CREATE INDEX idx_icd10_chapter         ON icd10_codes(chapter);
CREATE INDEX idx_icd10_category        ON icd10_codes(category);


-- ============================================================
-- VIEWS  (convenience — used by API layer)
-- ============================================================

CREATE VIEW patient_visit_summary AS
SELECT
    p.patient_id,
    p.state,
    p.sex,
    p.race,
    DATE_PART('year', AGE(p.date_of_birth))  AS age,
    COUNT(v.visit_id)                         AS total_visits,
    MAX(v.visit_date)                         AS last_visit_date,
    MIN(v.visit_date)                         AS first_visit_date
FROM patients p
LEFT JOIN visits v ON p.patient_id = v.patient_id
GROUP BY p.patient_id, p.state, p.sex, p.race, p.date_of_birth;

CREATE VIEW top_diagnoses_by_state AS
SELECT
    i.chapter,
    i.description,
    d.icd10_code,
    p.state,
    COUNT(*)                                  AS diagnosis_count,
    COUNT(*) FILTER (WHERE d.is_primary)      AS primary_count
FROM diagnoses d
JOIN visits    v ON d.visit_id    = v.visit_id
JOIN patients  p ON v.patient_id  = p.patient_id
JOIN icd10_codes i ON d.icd10_code = i.code
GROUP BY i.chapter, i.description, d.icd10_code, p.state;

