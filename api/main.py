"""FastAPI app: middleware, routers, startup seed, and the health check."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.cache import check_redis
from api.dependencies import check_database
from api.routers import admin, auth, icd10, mortality
from api.users import seed_users

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create the analyst and admin accounts before the first request.
    logger.info("HealthTrack API starting up...")
    seed_users()
    yield
    logger.info("HealthTrack API shutting down...")


app = FastAPI(
    title="HealthTrack Analytics API",
    description=(
        "REST API for querying CDC mortality data, ICD-10 diagnoses, "
        "and demographic health trends. Built with FastAPI and PostgreSQL."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# Any origin is allowed until the dashboard has a fixed host.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(icd10.router, prefix="/icd10", tags=["ICD-10 Reference"])
app.include_router(mortality.router, prefix="/mortality", tags=["Mortality Analytics"])
app.include_router(admin.router, prefix="/admin", tags=["Administration"])


@app.get("/health", tags=["System"])
def health_check():
    """Unauthenticated. Redis being down degrades the check; it does not fail it."""
    database = "ok" if check_database() else "down"
    redis_status = "ok" if check_redis() else "down"
    overall = "ok" if database == "ok" and redis_status == "ok" else "degraded"
    return {
        "status": overall,
        "service": "HealthTrack Analytics API",
        "database": database,
        "redis": redis_status,
    }
