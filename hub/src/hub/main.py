"""FastAPI application for the hub."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from hub.config import load_settings
from hub.db import PostgresStore
from hub.schemas import IngestResult, ProbeEnvelope


def create_app(store=None) -> FastAPI:
    """Build the app. Pass `store` to inject a storage backend (used by tests)."""

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

    return app


app = create_app()
