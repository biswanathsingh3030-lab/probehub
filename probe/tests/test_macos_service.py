import sys
import types
from pathlib import Path

import pytest

from probe import macos_service


class FakeCompletedProcess:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class RecordingRun:
    """Stand-in for subprocess.run that records every call and never shells out."""

    def __init__(self, returncode=0, stdout="", stderr=""):
        self.calls = []
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr

    def __call__(self, argv, **kwargs):
        self.calls.append(argv)
        return FakeCompletedProcess(self.returncode, self.stdout, self.stderr)


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    return tmp_path


def test_build_plist_fields_without_token(home):
    plist = macos_service.build_plist(
        "/usr/bin/python3", Path("/tmp/probe.pyz"), "p1", "system", "", 300
    )
    assert plist["Label"] == macos_service.LABEL
    assert plist["ProgramArguments"] == [
        "/usr/bin/python3",
        "/tmp/probe.pyz",
        "--probe-id",
        "p1",
        "--category",
        "system",
    ]
    assert plist["RunAtLoad"] is True
    assert plist["StartInterval"] == 300
    assert "KeepAlive" not in plist
    assert plist["EnvironmentVariables"] == {"PYTHONUNBUFFERED": "1"}
    assert "ProcessType" not in plist
    assert plist["StandardOutPath"] == str(home / "Library" / "Logs" / "probehub" / "probe.out.log")
    assert plist["StandardErrorPath"] == str(home / "Library" / "Logs" / "probehub" / "probe.err.log")


def test_build_plist_includes_token_when_set(home):
    plist = macos_service.build_plist(
        "/usr/bin/python3", Path("/tmp/probe.pyz"), "p1", "system", "secret", 60
    )
    assert plist["EnvironmentVariables"] == {
        "PYTHONUNBUFFERED": "1",
        "PROBEHUB_TOKEN": "secret",
    }


def test_install_copies_pyz_writes_plist_and_calls_launchctl(home, monkeypatch):
    fake_pyz = home / "downloads" / "probe.pyz"
    fake_pyz.parent.mkdir(parents=True)
    fake_pyz.write_bytes(b"fake zipapp contents")
    monkeypatch.setattr(sys, "argv", [str(fake_pyz)])

    recorder = RecordingRun(returncode=0)
    monkeypatch.setattr(macos_service.subprocess, "run", recorder)

    macos_service.install(probe_id="p1", category="system", token="", interval=60)

    canonical = macos_service.canonical_pyz_path()
    assert canonical == home / ".probehub" / "probe.pyz"
    assert canonical.read_bytes() == b"fake zipapp contents"

    plist_file = macos_service.plist_path()
    assert plist_file == home / "Library" / "LaunchAgents" / "com.probehub.probe.plist"
    assert plist_file.is_file()

    import plistlib

    with open(plist_file, "rb") as fh:
        written = plistlib.load(fh)
    assert written["ProgramArguments"][1] == str(canonical)
    assert written["StartInterval"] == 60

    assert len(recorder.calls) == 2
    assert recorder.calls[0][:2] == ["launchctl", "bootout"]
    assert recorder.calls[1][:2] == ["launchctl", "bootstrap"]
    assert recorder.calls[1][-1] == str(plist_file)


def test_install_skips_self_copy_when_already_canonical(home, monkeypatch):
    canonical = macos_service.canonical_pyz_path()
    canonical.parent.mkdir(parents=True)
    canonical.write_bytes(b"already here")
    monkeypatch.setattr(sys, "argv", [str(canonical)])

    recorder = RecordingRun(returncode=0)
    monkeypatch.setattr(macos_service.subprocess, "run", recorder)

    macos_service.install(probe_id="p1", category="system", token="", interval=60)

    assert canonical.read_bytes() == b"already here"
    assert len(recorder.calls) == 2


def test_install_raises_on_bootstrap_failure(home, monkeypatch):
    fake_pyz = home / "probe.pyz"
    fake_pyz.write_bytes(b"x")
    monkeypatch.setattr(sys, "argv", [str(fake_pyz)])

    def fake_run(argv, **kwargs):
        if argv[1] == "bootstrap":
            return FakeCompletedProcess(returncode=1, stderr="boom")
        return FakeCompletedProcess(returncode=0)

    monkeypatch.setattr(macos_service.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="boom"):
        macos_service.install(probe_id="p1", category="system", token="", interval=60)


def test_uninstall_removes_plist_and_ignores_missing_job(home, monkeypatch):
    plist_file = macos_service.plist_path()
    plist_file.parent.mkdir(parents=True)
    plist_file.write_bytes(b"placeholder")

    recorder = RecordingRun(returncode=1)  # bootout failing (not loaded) must still be ignored
    monkeypatch.setattr(macos_service.subprocess, "run", recorder)

    macos_service.uninstall()

    assert not plist_file.exists()
    assert recorder.calls[0][:2] == ["launchctl", "bootout"]


def test_uninstall_purge_removes_canonical_pyz(home, monkeypatch):
    canonical = macos_service.canonical_pyz_path()
    canonical.parent.mkdir(parents=True)
    canonical.write_bytes(b"x")
    plist_file = macos_service.plist_path()
    plist_file.parent.mkdir(parents=True)
    plist_file.write_bytes(b"x")

    monkeypatch.setattr(macos_service.subprocess, "run", RecordingRun())

    macos_service.uninstall(purge=True)

    assert not canonical.exists()
    assert not plist_file.exists()


def test_uninstall_idempotent_when_never_installed(home, monkeypatch):
    monkeypatch.setattr(macos_service.subprocess, "run", RecordingRun())
    macos_service.uninstall()  # must not raise


def test_status_reports_loaded(home, monkeypatch, capsys):
    monkeypatch.setattr(
        macos_service.subprocess,
        "run",
        RecordingRun(returncode=0, stdout="    pid = 4242\n    state = running\n"),
    )
    macos_service.status()
    out = capsys.readouterr().out
    assert "installed and loaded" in out
    assert "pid = 4242" in out


def test_status_reports_not_loaded(home, monkeypatch, capsys):
    monkeypatch.setattr(macos_service.subprocess, "run", RecordingRun(returncode=1))
    macos_service.status()
    out = capsys.readouterr().out
    assert "not installed or not loaded" in out


@pytest.mark.parametrize("fn_name,kwargs", [("install", {}), ("uninstall", {}), ("status", {})])
def test_platform_guard_blocks_non_macos(home, monkeypatch, fn_name, kwargs):
    monkeypatch.setattr(sys, "platform", "linux")

    def forbidden_run(*args, **kwargs):
        raise AssertionError("subprocess.run must not be called on an unsupported platform")

    monkeypatch.setattr(macos_service.subprocess, "run", forbidden_run)

    fn = getattr(macos_service, fn_name)
    with pytest.raises(macos_service.UnsupportedPlatformError):
        fn(**kwargs)

    assert list(home.rglob("*")) == []
