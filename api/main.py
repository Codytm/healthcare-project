"""
main.py — FastAPI application entry point.

THIS FILE'S ONLY JOBS:
  1. Create the FastAPI app instance
  2. Configure middleware
  3. Register routers
  4. Define startup/shutdown events

It should contain no business logic and no database queries.
All of that lives in routers/.

HOW TO RUN:
  uvicorn api.main:app --reload --port 8000

  `api.main` = the module path (api/main.py)
  `app`      = the FastAPI instance defined below
  `--reload` = restart server on code changes (development only)

THEN VISIT:
  http://localhost:8000/docs   — interactive API documentation
  http://localhost:8000/redoc  — alternative documentation UI
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import icd10, mortality, auth

logger = logging.getLogger(__name__)


# ── Lifespan — startup and shutdown events ────────────────────────────────────
# WHY LIFESPAN INSTEAD OF @app.on_event("startup")?
#   The lifespan pattern is the modern FastAPI approach. The code before
#   `yield` runs on startup, the code after runs on shutdown.
#   This is where you'd warm up a cache, verify DB connectivity,
#   or load ML models into memory once rather than per-request.

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("HealthTrack API starting up...")
    yield
    logger.info("HealthTrack API shutting down...")


# ── App instance ──────────────────────────────────────────────────────────────
app = FastAPI(
    title="HealthTrack Analytics API",
    description=(
        "REST API for querying CDC mortality data, ICD-10 diagnoses, "
        "and demographic health trends. Built with FastAPI and PostgreSQL."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",     # Swagger UI
    redoc_url="/redoc",   # ReDoc UI
)


# ── CORS Middleware ───────────────────────────────────────────────────────────
# WHAT IS CORS?
#   Browsers block JavaScript from making requests to a different domain
#   than the page was loaded from. This is a security feature called the
#   Same-Origin Policy. CORS (Cross-Origin Resource Sharing) is the
#   mechanism that lets your API tell browsers "it's okay, allow requests
#   from these origins."
#
#   If your dashboard is at localhost:3000 and your API is at localhost:8000,
#   without CORS the browser blocks every API call. With CORS configured
#   correctly, the browser allows them.
#
# IN PRODUCTION: replace "*" with your actual frontend domain.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        # all origins — restrict this in production
    allow_credentials=True,
    allow_methods=["*"],        # GET, POST, PUT, DELETE etc.
    allow_headers=["*"],        # Authorization, Content-Type etc.
)


# ── Router registration ───────────────────────────────────────────────────────
# prefix= sets the URL prefix for all routes in that router.
# tags=   groups routes in the /docs UI under a named section.

app.include_router(auth.router,     prefix="/auth",     tags=["Authentication"])
app.include_router(icd10.router,    prefix="/icd10",    tags=["ICD-10 Reference"])
app.include_router(mortality.router,prefix="/mortality",tags=["Mortality Analytics"])


# ── Health check ──────────────────────────────────────────────────────────────
# A simple unauthenticated endpoint that returns 200 if the server is running.
# Load balancers and monitoring tools ping this to check service health.
# It's the one endpoint that should never require auth.
@app.get("/health", tags=["System"])
def health_check():
    return {"status": "ok", "service": "HealthTrack Analytics API"}
