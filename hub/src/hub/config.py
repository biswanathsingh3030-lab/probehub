"""Hub settings, read from environment variables (and the repo-root .env in dev)."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    database_url: str
    host: str
    port: int


def load_settings() -> Settings:
    # Real environment variables win over .env values.
    load_dotenv(override=False)
    return Settings(
        database_url=os.environ.get(
            "DATABASE_URL", "postgresql://biswa@127.0.0.1:5432/probehub"
        ),
        host=os.environ.get("HUB_HOST", "127.0.0.1"),
        port=int(os.environ.get("HUB_PORT", "8000")),
    )
