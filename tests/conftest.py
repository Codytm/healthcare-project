import os

import pytest
from sqlalchemy.exc import OperationalError


@pytest.fixture(scope="session")
def client():
    if not os.getenv("ANALYST_PASSWORD"):
        pytest.skip("ANALYST_PASSWORD is not set")

    from fastapi.testclient import TestClient
    from api.main import app

    try:
        with TestClient(app) as test_client:
            health = test_client.get("/health")
            if health.json().get("database") != "ok":
                pytest.skip("database unavailable")
            yield test_client
    except OperationalError as exc:
        pytest.skip(f"database unavailable: {exc}")
