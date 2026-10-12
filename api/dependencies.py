"""
dependencies.py — Shared dependencies injected into API route functions.

WHAT IS DEPENDENCY INJECTION?
  Instead of each route function setting up its own database connection
  or validating its own token, you declare "I need a database session"
  or "I need a verified user" as function parameters. FastAPI sees those
  declarations and calls the right setup function before your route runs.

  This means:
    - Database sessions are always opened AND closed correctly
    - Auth logic is written once, used everywhere
    - Routes stay focused on their actual job — querying and returning data
    - Testing is easier — you can swap dependencies for mocks

HOW TO USE THESE IN A ROUTE:
  from api.dependencies import get_db, get_current_user

  @router.get("/something")
  def my_route(db: Session = Depends(get_db)):
      # db is a live database session, closed automatically when done
      ...

  @router.get("/protected")
  def protected_route(current_user: str = Depends(get_current_user)):
      # only runs if the JWT token in the request header is valid
      ...
"""

import os
from datetime import datetime, timedelta
from typing import Generator

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from api.models import TokenData

# ── Configuration ─────────────────────────────────────────────────────────────

# SECRET_KEY signs every JWT. If this changes, all existing tokens become invalid.
# In production this must be a long random string from an environment variable.
# Generate one with: python -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY      = os.getenv("JWT_SECRET_KEY", "change-this-in-production")
ALGORITHM       = "HS256"           # HMAC with SHA-256 — standard JWT algorithm
TOKEN_EXPIRE_MINUTES = 30           # tokens expire after 30 minutes of inactivity

# ── Password hashing ──────────────────────────────────────────────────────────
# WHY HASH PASSWORDS?
#   You never store a plain password. If your database is compromised,
#   hashed passwords are useless to an attacker (with a good algorithm).
#   bcrypt is deliberately slow — it makes brute-force attacks impractical.
#
# CryptContext manages the hashing algorithm and handles upgrades gracefully.
# "deprecated='auto'" means old hashes are automatically re-hashed on login
# if you ever switch algorithms in the future.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Check a plain password against a stored hash."""
    return pwd_context.verify(plain_password, hashed_password)


def hash_password(plain_password: str) -> str:
    """Hash a plain password for storage. Never store the plain version."""
    return pwd_context.hash(plain_password)


# ── JWT token creation and verification ───────────────────────────────────────

def create_access_token(data: dict) -> str:
    """
    Create a signed JWT containing `data` as the payload.

    We always add an expiry (`exp`) claim. The jose library checks this
    automatically when decoding — expired tokens are rejected without
    any extra code on your part.
    """
    payload = data.copy()
    expire  = datetime.utcnow() + timedelta(minutes=TOKEN_EXPIRE_MINUTES)
    payload.update({"exp": expire})
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


# ── OAuth2 scheme ─────────────────────────────────────────────────────────────
# OAuth2PasswordBearer tells FastAPI:
#   "tokens come from POST /auth/login"
#   "look for them in the Authorization: Bearer <token> header"
# This also makes the /docs UI show a login button automatically.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_user(token: str = Depends(oauth2_scheme)) -> str:
    """
    Dependency that validates the JWT in the Authorization header.

    FastAPI calls this before any route that declares:
        current_user: str = Depends(get_current_user)

    If the token is missing, expired, or tampered with → 401 Unauthorized.
    If valid → returns the username string to the route function.

    WHY HTTP 401 not 403?
      401 = "I don't know who you are" (missing/invalid credentials)
      403 = "I know who you are but you're not allowed" (insufficient permissions)
      An invalid token is a 401 — we can't establish identity.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
        # WWW-Authenticate header is required by the OAuth2 spec
        # it tells the client what auth scheme to use
    )
    try:
        payload  = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")   # "sub" = subject = who this token is for
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError:
        # JWTError covers: expired tokens, invalid signature, malformed tokens
        raise credentials_exception

    return token_data.username


# ── Database session dependency ───────────────────────────────────────────────

# Build the DB URL from environment variables — same pattern as etl/config.py
_DB_URL = (
    f"postgresql+psycopg2://"
    f"{os.getenv('DB_USER', 'postgres')}:{os.getenv('DB_PASSWORD', '')}"
    f"@{os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', '5432')}"
    f"/{os.getenv('DB_NAME', 'healthtrack')}"
)

# SessionLocal is a factory that produces Session objects.
# autocommit=False means you control when transactions commit.
# autoflush=False means SQLAlchemy won't auto-sync state between queries.
_engine       = create_engine(_DB_URL, pool_pre_ping=True)
_SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


def get_db() -> Generator[Session, None, None]:
    """
    Dependency that provides a database session for the duration of a request.

    WHY A GENERATOR (yield)?
      The code before `yield` runs before the route function.
      The route function runs and gets the `db` session.
      The code after `yield` (the finally block) runs after the route
      finishes — even if it raised an exception.

      This guarantees the session is always closed and returned to the
      connection pool, no matter what happens in the route. Without this,
      a crashed route would leak a database connection.

    USAGE IN A ROUTE:
      def my_route(db: Session = Depends(get_db)):
          results = db.execute(text("SELECT ...")).fetchall()
          return results
    """
    db = _SessionLocal()
    try:
        yield db        # hand the session to the route function
    finally:
        db.close()      # always runs — connection returned to pool
