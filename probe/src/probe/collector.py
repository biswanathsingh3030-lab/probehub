"""Collectors, one per data category. Every value they return must be JSON-serialisable.

To add a category (e.g. "photo"), write a function that returns a dict and register it
in COLLECTORS below. Binary data such as images should be base64-encoded strings.
"""

import base64
import os
import platform
import shutil
import socket
import subprocess
import tempfile
from datetime import datetime, timezone
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


def collect_screenshot() -> dict[str, Any]:
    """Capture every connected display as base64 PNGs. Supports macOS and Linux.

    Success: {"images": [<b64>, ...], "count": N, "format": "png", "timestamp": ...}.
    `images` has one entry per display (main display first), so a laptop with an
    external monitor yields two. Failure: {"error": ..., "platform": ...}.
    """
    system = platform.system()

    try:
        if system == "Darwin":  # macOS
            return _screenshot_macos()
        elif system == "Linux":
            return _screenshot_linux()
        else:
            return {
                "error": "Screenshot not supported on this platform",
                "platform": system,
            }
    except Exception as e:
        return {
            "error": f"Screenshot capture failed: {type(e).__name__}",
            "platform": system,
        }


# Upper bound on displays captured per send; screencapture ignores extra filenames.
MAX_DISPLAYS = 8


def _temp_png() -> Path:
    """A fresh private path to capture into.

    Not a fixed name like /tmp/screenshot.png: that is world-writable and
    predictable, so another user could pre-create or symlink it.
    """
    fd, name = tempfile.mkstemp(prefix="probe-screenshot-", suffix=".png")
    os.close(fd)
    return Path(name)


def _screenshot_macos() -> dict[str, Any]:
    """Capture every display on macOS.

    screencapture(1) is `screencapture [-flags] file [file ...]` -- it has no
    stdout mode (passing "-" writes a file literally named "-"). Given several
    filenames it writes one image per display, main display first, and ignores
    the names left over. So hand it MAX_DISPLAYS names in a private temp dir and
    keep whichever files appear.
    """
    workdir = Path(tempfile.mkdtemp(prefix="probe-screenshot-"))
    targets = [workdir / f"display-{n}.png" for n in range(1, MAX_DISPLAYS + 1)]
    try:
        try:
            result = subprocess.run(
                ["screencapture", "-x", *map(str, targets)],
                capture_output=True,
                timeout=15,
            )
        except FileNotFoundError:
            return {
                "error": "screencapture command not found",
                "platform": "Darwin",
            }
        except (subprocess.TimeoutExpired, OSError) as e:
            return {
                "error": f"screencapture failed: {type(e).__name__}",
                "platform": "Darwin",
            }

        if result.returncode != 0:
            return {
                "error": "screencapture command failed",
                "platform": "Darwin",
            }
        # Screen-recording permission denied leaves empty files; _encode_screenshots
        # turns "nothing but empty files" into an error dict.
        return _encode_screenshots([t for t in targets if t.exists()], "Darwin")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _screenshot_linux() -> dict[str, Any]:
    """Capture the screen on Linux using gnome-screenshot or ImageMagick.

    Both tools capture the whole desktop as ONE image (all monitors stitched
    side by side), so `images` has a single entry here.
    """
    temp_file = _temp_png()
    attempts = (
        (["gnome-screenshot", "-f", str(temp_file)], "Linux (GNOME)"),
        (["import", "-window", "root", str(temp_file)], "Linux (ImageMagick)"),
    )
    try:
        for argv, label in attempts:
            try:
                result = subprocess.run(argv, capture_output=True, timeout=10)
            except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
                continue  # tool missing or failed, try the next one
            if result.returncode == 0 and temp_file.exists():
                return _encode_screenshots([temp_file], label)
        return {
            "error": "No screenshot tool found (try gnome-screenshot or ImageMagick)",
            "platform": "Linux",
        }
    finally:
        temp_file.unlink(missing_ok=True)


def _encode_screenshots(file_paths: list[Path], platform_name: str) -> dict[str, Any]:
    """Read PNG files and return them base64-encoded as an array. Caller deletes the files."""
    images: list[str] = []
    try:
        for path in file_paths:
            png_bytes = path.read_bytes()
            if png_bytes:  # empty = permission denied for that capture
                images.append(base64.b64encode(png_bytes).decode("utf-8"))
    except OSError as e:
        return {
            "error": f"Failed to read screenshot: {type(e).__name__}",
            "platform": platform_name,
        }
    if not images:
        return {
            "error": "Screenshot file is empty",
            "platform": platform_name,
        }
    return {
        "images": images,
        "count": len(images),
        "format": "png",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def collect_all() -> dict[str, Any]:
    """Everything in one payload: host metrics at the top level, plus a `screenshot` key.

    The screenshot collector never raises (it returns {"error", "platform"} on
    failure), so a denied permission or missing tool still sends the system data.
    """
    data = collect_system()
    data["screenshot"] = collect_screenshot()
    return data


# category name -> collector. Names must match the hub's rule: lowercase [a-z0-9_.-], max 64.
# "all" is what the probe sends by default; the single-purpose ones stay for debugging.
COLLECTORS: dict[str, Callable[[], dict[str, Any]]] = {
    "all": collect_all,
    "system": collect_system,
    "screenshot": collect_screenshot,
}

DEFAULT_CATEGORY = "all"


def collect(category: str = DEFAULT_CATEGORY) -> dict[str, Any]:
    try:
        collector = COLLECTORS[category]
    except KeyError:
        raise ValueError(f"unknown category {category!r}; known: {sorted(COLLECTORS)}") from None
    return collector()
