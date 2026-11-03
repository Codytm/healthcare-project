# HealthTrack Analytics

HealthTrack is a small public-health analytics stack. It models clinical concepts the way a health dataset actually works — ICD-10 codes, visits, and demographic slices — and serves them through the kind of backend used in production: a normalized database, an ETL job, an authenticated API, a cache, and Docker.

The subject matter comes from a biomedical background. The implementation is software engineering practice: schema design, data loading, and an API other people can query.

Public CDC and CMS files do not include patient records. The schema has tables for patients, visits, and diagnoses, and the data that is loaded today is ICD-10 reference codes plus state- and year-level death counts.

## What is built

**Database.** [db/schema.sql](db/schema.sql) is a PostgreSQL schema for facilities, patients, providers, visits, diagnoses, procedures, and ICD-10 codes. `demo_aggregates` holds precomputed death counts so dashboard-style queries do not scan raw events. Indexes cover the common lookups, including a trigram index for patient names.

**ETL.** [etl/pipeline.py](etl/pipeline.py) downloads CDC WONDER mortality data, reads a local CMS ICD-10 file, cleans both, and upserts them. Cause ranges are stored as their first ICD-10 code so they can reference `icd10_codes`. This file has no age, sex, or race split, so those columns are stored as `"all"`.

**API.** FastAPI exposes ICD-10 chapter, category, and code search, plus paginated mortality rows, year-over-year trends, state rankings, and deaths by chapter. OpenAPI docs are at `/docs`.

Login issues a JWT with an `analyst` or `admin` role. Analysts can read. Admins can also clear the Redis cache. Trends, state rankings, and chapter summaries are cached for five minutes. If Redis is down, those reads still hit Postgres. `GET /health` reports the API, the database, and Redis separately.

**Local stack.** [docker-compose.yml](docker-compose.yml) runs Postgres, Redis, and the API. Postgres is published on host port **5433** so it does not collide with a database already listening on 5432. Inside Compose, the API uses the hostname `postgres`.

## Run it

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Fill in `.env`. It is gitignored. `JWT_SECRET_KEY`, `ANALYST_PASSWORD`, and `ADMIN_PASSWORD` are required for login. Generate a secret with:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Start the stack, then load data into the Compose database:

```bash
docker compose up --build
```

In another terminal, point the ETL at that database and run it. The ICD-10 source file must already be at `data/raw/icd10cm_codes.txt`. The CDC file is downloaded if it is missing.

```bash
# .env for this run: DB_HOST=localhost  DB_PORT=5433
python -m etl.pipeline
```

Open http://localhost:8000/docs and log in as `analyst` or `admin` with the passwords from `.env`.

`pytest` uses whatever database `.env` points at. A mortality test skips when `demo_aggregates` is empty.

## Next

A small dashboard on these endpoints: prevalence over time, chapter breakdowns, a state view, and filters on the mortality search. After that, tighter CORS, rate limiting, and a free-tier deploy of this same Compose stack, with the environment variables set on the host.
