"""One live query path. Skips when Postgres has no aggregate rows."""

import os

import pytest


def test_mortality_records_query(client):
    login = client.post(
        "/auth/login",
        data={"username": "analyst", "password": os.environ["ANALYST_PASSWORD"]},
    )
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = client.get("/mortality/records", headers=headers, params={"size": 1})
    assert response.status_code == 200
    body = response.json()
    assert body["page"] == 1
    assert body["size"] == 1
    if body["total"] == 0:
        pytest.skip("demo_aggregates has no rows")

    assert len(body["data"]) == 1
    row = body["data"][0]
    assert row["icd10_code"]
    assert row["year"]

    trends = client.get(
        "/mortality/trends",
        headers=headers,
        params={"icd10_code": row["icd10_code"]},
    )
    assert trends.status_code == 200
    cached = client.get(
        "/mortality/trends",
        headers=headers,
        params={"icd10_code": row["icd10_code"]},
    )
    assert cached.status_code == 200
    assert cached.json() == trends.json()
