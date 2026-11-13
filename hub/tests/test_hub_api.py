from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from hub.main import create_app


class FakeStore:
    def __init__(self, healthy: bool = True) -> None:
        self.healthy = healthy
        self.rows: list[tuple] = []

    def ping(self) -> bool:
        return self.healthy

    def insert(self, probe_id, category, collected_at, data):
        self.rows.append((probe_id, category, collected_at, data))
        return len(self.rows), datetime(2026, 11, 11, tzinfo=timezone.utc)


@pytest.fixture
def store():
    return FakeStore()


@pytest.fixture
def client(store):
    with TestClient(create_app(store=store)) as c:
        yield c


VALID = {
    "probe_id": "laptop-01",
    "category": "system",
    "collected_at": "2026-11-11T16:45:00Z",
    "data": {"cpu_count": 8, "nested": {"a": [1, 2]}},
}


def test_ingest_stores_envelope(client, store):
    resp = client.post("/api/v1/data", json=VALID)
    assert resp.status_code == 201
    assert resp.json()["id"] == 1
    probe_id, category, collected_at, data = store.rows[0]
    assert probe_id == "laptop-01"
    assert category == "system"
    assert collected_at.tzinfo is not None
    assert data == VALID["data"]


@pytest.mark.parametrize(
    "patch",
    [
        {"probe_id": ""},
        {"probe_id": "x" * 129},
        {"collected_at": "2026-11-11T16:45:00"},  # no timezone
        {"collected_at": "not-a-date"},
        {"data": [1, 2, 3]},  # must be an object
        {"category": ""},
        {"category": "Photo"},  # lowercase only
        {"category": "has space"},
        {"category": "x" * 65},
    ],
)
def test_ingest_rejects_invalid(client, store, patch):
    resp = client.post("/api/v1/data", json={**VALID, **patch})
    assert resp.status_code == 422
    assert store.rows == []


@pytest.mark.parametrize("field", ["probe_id", "category", "collected_at", "data"])
def test_ingest_rejects_missing_field(client, field):
    body = {k: v for k, v in VALID.items() if k != field}
    assert client.post("/api/v1/data", json=body).status_code == 422


def test_health_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "db": "ok"}


def test_health_db_down():
    with TestClient(create_app(store=FakeStore(healthy=False))) as c:
        assert c.get("/health").status_code == 503
