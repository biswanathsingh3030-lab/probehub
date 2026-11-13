"""Send an envelope to the hub over HTTP (urllib, no third-party deps)."""

import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

INGEST_PATH = "/api/v1/data"


class SendError(Exception):
    pass


def build_envelope(probe_id: str, category: str, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "probe_id": probe_id,
        "category": category,
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "data": data,
    }


def send(hub_url: str, envelope: dict[str, Any], timeout: float = 10.0) -> dict[str, Any]:
    url = hub_url.rstrip("/") + INGEST_PATH
    request = urllib.request.Request(
        url,
        data=json.dumps(envelope).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SendError(f"hub returned HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise SendError(f"could not reach hub at {url}: {exc}") from exc
