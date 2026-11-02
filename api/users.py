"""Seed analyst and admin from ANALYST_PASSWORD and ADMIN_PASSWORD.

Restarting the API re-hashes those passwords, so changing the env var rotates them.
If either password is unset, seeding is skipped and login will fail until it is set.
"""

import logging
import os

from sqlalchemy import text

from api.dependencies import _SessionLocal, hash_password

logger = logging.getLogger(__name__)

# Keeps an already-created database working. A fresh Compose volume gets this
# table from db/schema.sql before the API starts.
_CREATE_USERS = text("""
    CREATE TABLE IF NOT EXISTS users (
        user_id          UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
        username         VARCHAR(50)  NOT NULL UNIQUE,
        hashed_password  VARCHAR(255) NOT NULL,
        role             VARCHAR(20)  NOT NULL CHECK (role IN ('analyst', 'admin')),
        created_at       TIMESTAMP    NOT NULL DEFAULT NOW()
    )
""")

_UPSERT_USER = text("""
    INSERT INTO users (username, hashed_password, role)
    VALUES (:username, :hashed_password, :role)
    ON CONFLICT (username) DO UPDATE SET
        hashed_password = EXCLUDED.hashed_password,
        role            = EXCLUDED.role
""")


def seed_users() -> None:
    accounts = [
        ("analyst", os.getenv("ANALYST_PASSWORD"), "analyst"),
        ("admin", os.getenv("ADMIN_PASSWORD"), "admin"),
    ]
    missing = [name for name, password, _role in accounts if not password]
    if missing:
        logger.warning("Skipping user seed; set passwords for: %s", ", ".join(missing))
        return

    db = _SessionLocal()
    try:
        db.execute(_CREATE_USERS)
        for username, password, role in accounts:
            db.execute(
                _UPSERT_USER,
                {
                    "username": username,
                    "hashed_password": hash_password(password),
                    "role": role,
                },
            )
        db.commit()
        logger.info("Seeded users: analyst, admin")
    except Exception:
        db.rollback()
        logger.exception("User seed failed")
        raise
    finally:
        db.close()
