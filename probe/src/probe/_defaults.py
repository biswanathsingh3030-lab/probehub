"""Shared default constants for the probe CLI.

Kept in their own module so other parts of the probe package (and tests) can
import them without pulling in argparse / cli wiring.
"""

import re
from importlib import metadata
from pathlib import Path

DEFAULT_HUB_URL = "http://127.0.0.1:8100"
DEFAULT_TOKEN = ""


def _version_from_pyproject() -> str:
    """Fallback for running from source (unpacked checkout, zipapp, etc.)."""
    pyproject_path = Path(__file__).resolve().parent.parent.parent / "pyproject.toml"
    try:
        text = pyproject_path.read_text(encoding="utf-8")
    except OSError:
        return "0.0.0"

    try:
        import tomllib  # stdlib, Python 3.11+
    except ImportError:
        tomllib = None

    if tomllib is not None:
        try:
            data = tomllib.loads(text)
            version = data.get("project", {}).get("version")
            if version:
                return str(version)
        except Exception:
            pass

    # Minimal line-scan fallback for Python 3.10, where tomllib doesn't exist.
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if match:
        return match.group(1)
    return "0.0.0"


try:
    VERSION = metadata.version("probehub-probe")
except metadata.PackageNotFoundError:
    VERSION = _version_from_pyproject()
