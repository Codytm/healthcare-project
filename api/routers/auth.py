"""Exchange a username and password for a JWT that carries sub and role."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.dependencies import create_access_token, get_db, verify_password
from api.models import Token

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/login", response_model=Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    # Unknown username and wrong password share one 401, so callers cannot tell them apart.
    row = db.execute(
        text("""
            SELECT username, hashed_password, role
            FROM users
            WHERE username = :username
        """),
        {"username": form_data.username},
    ).fetchone()

    if row is None or not verify_password(form_data.password, row.hashed_password):
        logger.info("Failed login for username '%s'", form_data.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token({"sub": row.username, "role": row.role})
    logger.info("User '%s' logged in with role '%s'", row.username, row.role)
    return Token(access_token=token)
