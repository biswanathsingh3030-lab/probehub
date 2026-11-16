import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

BUILD_SCRIPT = Path(__file__).resolve().parent.parent / "build_pyz.py"

pytestmark = pytest.mark.skipif(
    sys.version_info < (3, 11),
    reason="build_pyz.py requires tomllib (Python 3.11+); the shipped probe itself stays 3.10+",
)


def run_build(tmp_path, *extra_args):
    output = tmp_path / "probe.pyz"
    result = subprocess.run(
        [sys.executable, str(BUILD_SCRIPT), "-o", str(output), *extra_args],
        capture_output=True,
        text=True,
    )
    return result, output


def test_build_creates_valid_pyz_with_baked_defaults(tmp_path):
    result, output = run_build(tmp_path, "--hub-url", "http://TEST-PLACEHOLDER:9999")
    assert result.returncode == 0, result.stderr
    assert output.is_file()

    with zipfile.ZipFile(output) as zf:
        names = zf.namelist()
        assert "probe/_defaults.py" in names
        assert "probe/cli.py" in names
        assert "__main__.py" in names
        assert not any("__pycache__" in n or n.endswith(".egg-info") or ".egg-info/" in n for n in names)

        defaults_src = zf.read("probe/_defaults.py").decode("utf-8")

    assert "DEFAULT_HUB_URL = 'http://TEST-PLACEHOLDER:9999'" in defaults_src
    assert "DEFAULT_TOKEN = ''" in defaults_src
    assert "VERSION = " in defaults_src


def test_build_bakes_token_when_given(tmp_path):
    result, output = run_build(
        tmp_path, "--hub-url", "http://TEST-PLACEHOLDER:9999", "--token", "sekrit"
    )
    assert result.returncode == 0, result.stderr

    with zipfile.ZipFile(output) as zf:
        defaults_src = zf.read("probe/_defaults.py").decode("utf-8")

    assert "DEFAULT_TOKEN = 'sekrit'" in defaults_src


def test_build_requires_hub_url(tmp_path):
    result, _ = run_build(tmp_path)
    assert result.returncode != 0
    assert "--hub-url" in result.stderr


def test_built_pyz_runs_and_dry_runs(tmp_path):
    result, output = run_build(tmp_path, "--hub-url", "http://TEST-PLACEHOLDER:9999")
    assert result.returncode == 0, result.stderr

    run_result = subprocess.run(
        [sys.executable, str(output), "--dry-run", "--probe-id", "built-pyz-test"],
        capture_output=True,
        text=True,
    )
    assert run_result.returncode == 0, run_result.stderr
    envelope = json.loads(run_result.stdout)
    assert envelope["probe_id"] == "built-pyz-test"
    assert "hostname" in envelope["data"]
