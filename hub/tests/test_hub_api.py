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


TOKEN = "test-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def client(store):
    with TestClient(create_app(store=store, token=TOKEN, max_body_bytes=2048), headers=AUTH) as c:
        yield c


@pytest.fixture
def anon(store):
    """Client that sends no credentials."""
    with TestClient(create_app(store=store, token=TOKEN, max_body_bytes=2048)) as c:
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
    with TestClient(create_app(store=FakeStore(healthy=False), token=TOKEN)) as c:
        assert c.get("/health").status_code == 503


@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "Bearer wrong"}, {"Authorization": TOKEN}, {"Authorization": "Basic abc"}],
)
def test_ingest_requires_valid_token(anon, store, headers):
    resp = anon.post("/api/v1/data", json=VALID, headers=headers)
    assert resp.status_code == 401
    assert store.rows == []


def test_health_is_open_without_token(anon):
    assert anon.get("/health").status_code == 200


def test_oversized_body_rejected_by_content_length(client, store):
    big = {**VALID, "data": {"blob": "x" * 5000}}
    assert client.post("/api/v1/data", json=big).status_code == 413
    assert store.rows == []


def test_oversized_chunked_body_rejected(client, store):
    def chunks():
        yield b'{"probe_id": "p", "category": "system", "collected_at": "2026-11-11T16:45:00Z", "data": {"b": "'
        yield b"x" * 5000
        yield b'"}}'

    resp = client.post("/api/v1/data", content=chunks(), headers={"Content-Type": "application/json"})
    assert resp.status_code == 413
    assert store.rows == []


def test_body_under_limit_accepted(client):
    assert client.post("/api/v1/data", json=VALID).status_code == 201


def test_open_when_no_token_configured(store):
    with TestClient(create_app(store=store, token="", max_body_bytes=2048)) as c:
        assert c.post("/api/v1/data", json=VALID).status_code == 201
        big = {**VALID, "data": {"blob": "x" * 5000}}
        assert c.post("/api/v1/data", json=big).status_code == 413  # size limit still applies
