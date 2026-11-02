"""Auth tests that do not need Postgres, plus login against a live database."""

import os
from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException
from jose import jwt

from api.dependencies import (
    ALGORITHM,
    SECRET_KEY,
    create_access_token,
    get_current_user,
    require_role,
)
from api.models import TokenData


def test_garbage_token_is_rejected():
    with pytest.raises(HTTPException) as exc:
        get_current_user(token="not-a-token")
    assert exc.value.status_code == 401


def test_expired_token_is_rejected():
    token = jwt.encode(
        {
            "sub": "analyst",
            "role": "analyst",
            "exp": datetime.utcnow() - timedelta(minutes=5),
        },
        SECRET_KEY,
        algorithm=ALGORITHM,
    )
    with pytest.raises(HTTPException) as exc:
        get_current_user(token=token)
    assert exc.value.status_code == 401


def test_access_token_carries_role():
    token = create_access_token({"sub": "analyst", "role": "analyst"})
    user = get_current_user(token=token)
    assert user.username == "analyst"
    assert user.role == "analyst"


def test_analyst_cannot_call_admin_dependency():
    checker = require_role("admin")
    with pytest.raises(HTTPException) as exc:
        checker(current_user=TokenData(username="analyst", role="analyst"))
    assert exc.value.status_code == 403


def test_login_success(client):
    response = client.post(
        "/auth/login",
        data={"username": "analyst", "password": os.environ["ANALYST_PASSWORD"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


def test_login_bad_password(client):
    response = client.post(
        "/auth/login",
        data={"username": "analyst", "password": "wrong-password"},
    )
    assert response.status_code == 401


def test_analyst_cannot_clear_cache(client):
    login = client.post(
        "/auth/login",
        data={"username": "analyst", "password": os.environ["ANALYST_PASSWORD"]},
    )
    assert login.status_code == 200
    response = client.post(
        "/admin/cache/clear",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )
    assert response.status_code == 403
