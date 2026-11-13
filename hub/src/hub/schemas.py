"""Request/response models for the hub API."""

from datetime import datetime
from typing import Any

from pydantic import AwareDatetime, BaseModel, Field


# Lowercase slug, e.g. "system", "photo", "app.logs".
CATEGORY_PATTERN = r"^[a-z0-9][a-z0-9_.-]{0,63}$"


class ProbeEnvelope(BaseModel):
    probe_id: str = Field(min_length=1, max_length=128)
    category: str = Field(pattern=CATEGORY_PATTERN)
    collected_at: AwareDatetime
    data: dict[str, Any]


class IngestResult(BaseModel):
    id: int
    received_at: datetime
