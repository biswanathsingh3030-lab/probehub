"""FastAPI application for the hub."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from hub.config import load_settings
from hub.db import PostgresStore
from hub.guard import Guard
from hub.schemas import IngestResult, ProbeEnvelope


def create_app(store=None, token: str | None = None, max_body_bytes: int | None = None) -> FastAPI:
    """Build the app. `store`, `token` and `max_body_bytes` can be injected (used by tests);
    otherwise they come from settings. An empty token means the API is open (no auth)."""
    if token is None or max_body_bytes is None:
        settings = load_settings()
        token = settings.api_token if token is None else token
        max_body_bytes = settings.max_body_bytes if max_body_bytes is None else max_body_bytes

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        own_store = store is None
        app.state.store = store or PostgresStore(load_settings().database_url)
        if own_store:
            app.state.store.open()
        yield
        if own_store:
            app.state.store.close()

    app = FastAPI(title="ProbeHub", version="0.1.0", lifespan=lifespan)

    @app.get("/health")
    def health(request: Request):
        if request.app.state.store.ping():
            return {"status": "ok", "db": "ok"}
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "degraded", "db": "unreachable"},
        )

    @app.post(
        "/api/v1/data",
        response_model=IngestResult,
        status_code=status.HTTP_201_CREATED,
    )
    def ingest(envelope: ProbeEnvelope, request: Request) -> IngestResult:
        row_id, received_at = request.app.state.store.insert(
            envelope.probe_id, envelope.category, envelope.collected_at, envelope.data
        )
        return IngestResult(id=row_id, received_at=received_at)

    app.add_middleware(Guard, token=token, max_body_bytes=max_body_bytes)
    return app

