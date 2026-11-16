"""Register the probe as a macOS launchd LoginItem/agent (stdlib only).

Installs a LaunchAgent that runs the probe `.pyz` once at login and then on a
fixed interval via launchd's own timer (`StartInterval`), instead of using a
long-lived supervised process. No third-party process manager is involved.
"""

import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

LABEL = "com.probehub.probe"


def canonical_pyz_path() -> Path:
    """Where the probe `.pyz` should live once installed as a service.

    Deliberately OS-agnostic (plain ``~/.probehub/``, not ``~/Library/...``)
    since the same path should still make sense once Linux/Windows support
    is added later (out of scope for now).
    """
    return Path.home() / ".probehub" / "probe.pyz"


# Kept as a module-level name for convenience/back-compat; always resolves
# Path.home() fresh via canonical_pyz_path() rather than freezing it at
# import time.
CANONICAL_PYZ_PATH = canonical_pyz_path()


def plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def log_dir() -> Path:
    return Path.home() / "Library" / "Logs" / "probehub"


class UnsupportedPlatformError(RuntimeError):
    pass


def _require_macos() -> None:
    # Single extension point: add an equivalent branch (e.g. systemd) here
    # when Linux support lands, instead of scattering platform checks.
    if sys.platform != "darwin":
        raise UnsupportedPlatformError(
            f"macos_service only supports macOS (sys.platform={sys.platform!r})"
        )


def build_plist(
    python_exe: str,
    pyz_path,
    probe_id: str,
    category: str,
    token: str,
    interval: int,
) -> dict:
    """Pure function: build the launchd plist dict. No I/O, no subprocess."""
    env_vars = {"PYTHONUNBUFFERED": "1"}
    if token:
        env_vars["PROBEHUB_TOKEN"] = token

    return {
        "Label": LABEL,
        "ProgramArguments": [
            python_exe,
            str(pyz_path),
            "--probe-id",
            probe_id,
            "--category",
            category,
        ],
        "RunAtLoad": True,
        "StartInterval": int(interval),
        "EnvironmentVariables": env_vars,
        "StandardOutPath": str(log_dir() / "probe.out.log"),
        "StandardErrorPath": str(log_dir() / "probe.err.log"),
    }


def install(
    pyz_path=None,
    probe_id: str = "",
    category: str = "system",
    token: str = "",
    interval: int = 300,
) -> None:
    _require_macos()

    if pyz_path is None:
        pyz_path = Path(sys.argv[0]).resolve()

    canonical = canonical_pyz_path()
    if Path(pyz_path).resolve() != canonical:
        canonical.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(pyz_path, canonical)

    plist_path().parent.mkdir(parents=True, exist_ok=True)
    log_dir().mkdir(parents=True, exist_ok=True)

    plist = build_plist(sys.executable, canonical, probe_id, category, token, interval)
    with open(plist_path(), "wb") as fh:
        plistlib.dump(plist, fh)

    uid = os.getuid()
    # Unload any existing registration first; expected to fail (and is
    # ignored) if the job isn't currently loaded.
    subprocess.run(
        ["launchctl", "bootout", f"gui/{uid}/{LABEL}"],
        capture_output=True,
        text=True,
    )

    result = subprocess.run(
        ["launchctl", "bootstrap", f"gui/{uid}", str(plist_path())],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"launchctl bootstrap failed (exit {result.returncode}): {result.stderr}"
        )

    print(f"installed {LABEL}")
    print(f"  pyz:        {canonical}")
    print(f"  stdout log: {log_dir() / 'probe.out.log'}")
    print(f"  stderr log: {log_dir() / 'probe.err.log'}")


def uninstall(purge: bool = False) -> None:
    _require_macos()

    uid = os.getuid()
    subprocess.run(
        ["launchctl", "bootout", f"gui/{uid}/{LABEL}"],
        capture_output=True,
        text=True,
    )

    plist_path().unlink(missing_ok=True)

    if purge:
        canonical = canonical_pyz_path()
        canonical.unlink(missing_ok=True)

    print(f"uninstalled {LABEL}")


def status() -> None:
    _require_macos()

    uid = os.getuid()
    result = subprocess.run(
        ["launchctl", "print", f"gui/{uid}/{LABEL}"],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print(f"{LABEL}: not installed or not loaded")
        return

    pid_line = next(
        (line.strip() for line in result.stdout.splitlines() if line.strip().startswith("pid =")),
        None,
    )
    if pid_line:
        print(f"{LABEL}: installed and loaded ({pid_line})")
    else:
        print(f"{LABEL}: installed and loaded")
