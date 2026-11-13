"""Hub settings, read from environment variables (and the repo-root .env in dev)."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    database_url: str
    host: str
    port: int
    api_token: str
    max_body_bytes: int


def load_settings() -> Settings:
    # Real environment variables win over .env values.
    load_dotenv(override=False)
    return Settings(
        database_url=os.environ.get(
            "DATABASE_URL", "postgresql://biswa@127.0.0.1:5432/probehub"
        ),
        host=os.environ.get("HUB_HOST", "127.0.0.1"),
        port=int(os.environ.get("HUB_PORT", "8100")),
        api_token=os.environ.get("HUB_API_TOKEN", ""),
        max_body_bytes=int(os.environ.get("HUB_MAX_BODY_BYTES", str(1024 * 1024))),
    )
