"""Collectors, one per data category. Every value they return must be JSON-serialisable.

To add a category (e.g. "photo"), write a function that returns a dict and register it
in COLLECTORS below. Binary data such as images should be base64-encoded strings.
"""

import os
import platform
import shutil
import socket
from pathlib import Path
from typing import Any, Callable


def _meminfo() -> dict[str, int] | None:
    """Memory in bytes from /proc/meminfo (Linux only)."""
    path = Path("/proc/meminfo")
    if not path.exists():
        return None
    values: dict[str, int] = {}
    for line in path.read_text().splitlines():
        key, _, rest = line.partition(":")
        if key in ("MemTotal", "MemAvailable", "SwapTotal", "SwapFree"):
            values[key] = int(rest.split()[0]) * 1024  # kB -> bytes
    return {
        "total": values.get("MemTotal", 0),
        "available": values.get("MemAvailable", 0),
        "swap_total": values.get("SwapTotal", 0),
        "swap_free": values.get("SwapFree", 0),
    }


def _uptime_seconds() -> float | None:
    path = Path("/proc/uptime")
    if not path.exists():
        return None
    return float(path.read_text().split()[0])


def collect_system() -> dict[str, Any]:
    """Basic host metrics."""
    disk = shutil.disk_usage("/")
    data: dict[str, Any] = {
        "hostname": socket.gethostname(),
        "os": platform.system(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu_count": os.cpu_count(),
        "disk_root": {"total": disk.total, "used": disk.used, "free": disk.free},
    }
    if hasattr(os, "getloadavg"):
        data["load_avg"] = list(os.getloadavg())
    mem = _meminfo()
    if mem is not None:
        data["memory"] = mem
    uptime = _uptime_seconds()
    if uptime is not None:
        data["uptime_seconds"] = uptime
    return data


# category name -> collector. Names must match the hub's rule: lowercase [a-z0-9_.-], max 64.
COLLECTORS: dict[str, Callable[[], dict[str, Any]]] = {
    "system": collect_system,
}

DEFAULT_CATEGORY = "system"


def collect(category: str = DEFAULT_CATEGORY) -> dict[str, Any]:
    try:
        collector = COLLECTORS[category]
    except KeyError:
        raise ValueError(f"unknown category {category!r}; known: {sorted(COLLECTORS)}") from None
    return collector()
