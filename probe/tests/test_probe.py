import base64
import json
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest import mock

import pytest

from probe import cli
from probe.collector import COLLECTORS, collect, collect_all, collect_screenshot
from probe.sender import SendError, build_envelope, send


def test_collect_is_json_serialisable():
    data = collect()
    assert data["hostname"]
    assert isinstance(data["cpu_count"], int)
    json.dumps(data)  # must not raise


def test_every_collector_is_json_serialisable_and_named_validly():
    import re

    for name in COLLECTORS:
        assert re.fullmatch(r"[a-z0-9][a-z0-9_.-]{0,63}", name)
        json.dumps(collect(name))


def test_collect_unknown_category_raises():
    with pytest.raises(ValueError):
        collect("nope")


def test_build_envelope_has_aware_timestamp():
    env = build_envelope("p1", "system", {"k": 1})
    assert env["probe_id"] == "p1"
    assert env["category"] == "system"
    assert env["data"] == {"k": 1}
    assert env["collected_at"].endswith("+00:00")


@pytest.fixture
def fake_hub():
    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            received.append(
                (self.path, self.headers["Content-Type"], json.loads(body), self.headers.get("Authorization"))
            )
            status = 201 if self.path == "/api/v1/data" else 404
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"id": 7, "received_at": "2026-11-11T00:00:00Z"}')

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}", received
    server.shutdown()


def test_send_posts_json(fake_hub):
    url, received = fake_hub
    result = send(url + "/", build_envelope("p1", "system", {"k": 1}))
    assert result["id"] == 7
    path, content_type, body, auth = received[0]
    assert path == "/api/v1/data"
    assert content_type == "application/json"
    assert body["probe_id"] == "p1"
    assert body["category"] == "system"
    assert auth is None  # no token configured -> no header


def test_send_unreachable_raises():
    with pytest.raises(SendError):
        send("http://127.0.0.1:9", build_envelope("p1", "system", {}), timeout=2)


def test_cli_once_success_and_failure(fake_hub, capsys):
    url, _ = fake_hub
    assert cli.main(["--hub-url", url, "--probe-id", "p1"]) == 0
    assert "sent all id=7" in capsys.readouterr().out
    assert cli.main(["--hub-url", "http://127.0.0.1:9", "--probe-id", "p1"]) == 1


def test_cli_dry_run_prints_envelope(capsys):
    assert cli.main(["--dry-run", "--probe-id", "p1"]) == 0
    env = json.loads(capsys.readouterr().out)
    assert env["probe_id"] == "p1"
    assert env["category"] == "all"
    assert "hostname" in env["data"]
    assert "screenshot" in env["data"]


def test_send_includes_bearer_token(fake_hub):
    url, received = fake_hub
    send(url, build_envelope("p1", "system", {}), token="secret")
    assert received[0][3] == "Bearer secret"


def test_cli_reads_token_from_env(fake_hub, monkeypatch):
    monkeypatch.setenv("PROBEHUB_TOKEN", "from-env")
    assert cli.parse_args(["--probe-id", "p1"]).token == "from-env"


# Screenshot collector tests
def test_collect_screenshot_returns_dict():
    """Verify that collect_screenshot() returns a dict."""
    result = collect_screenshot()
    assert isinstance(result, dict), f"Expected dict, got {type(result)}"


def test_screenshot_is_json_serializable():
    """Verify that the screenshot result can be JSON-encoded without errors."""
    result = collect_screenshot()
    # Should not raise an exception
    json.dumps(result)


def test_screenshot_has_required_keys():
    """Verify that the dict has either 'images' (on success) or 'error' (on failure)."""
    result = collect_screenshot()
    has_images = "images" in result
    has_error = "error" in result
    assert has_images or has_error, f"Result must have 'images' or 'error' key: {result}"

    if has_images:
        assert isinstance(result["images"], list) and result["images"], "images should be a non-empty list"
        assert result["count"] == len(result["images"])
        for image in result["images"]:
            assert isinstance(image, str), "each image should be a string"
            assert len(image) > 100, "base64 image should be substantial (> 100 chars)"
            base64.b64decode(image, validate=True)  # must be valid base64


def test_screenshot_format_and_timestamp_on_success():
    """If result has 'images', verify 'format' and 'timestamp' are present and valid."""
    result = collect_screenshot()

    if "images" in result:
        assert "format" in result, "image result must have 'format' key"
        assert "timestamp" in result, "image result must have 'timestamp' key"
        assert result["format"] == "png", "format should be 'png'"

        # Verify timestamp is ISO-8601 with timezone info
        timestamp = result["timestamp"]
        assert isinstance(timestamp, str), "timestamp should be a string"
        # ISO-8601 with timezone should have + or - followed by HH:MM
        assert "+" in timestamp or timestamp.endswith("Z"), f"timestamp missing timezone: {timestamp}"


def _fake_capture(png_bytes: bytes, path_argv_index: int = -1):
    """A subprocess.run stand-in that behaves like a real capture tool: it writes
    the image to the file path it was handed, rather than to stdout."""

    def fake_run(argv, **kwargs):
        Path(argv[path_argv_index]).write_bytes(png_bytes)
        return mock.Mock(returncode=0)

    return fake_run


def _fake_displays(*pngs: bytes):
    """screencapture stand-in for N connected displays: given several filenames it
    writes one image per display, main first, and leaves the extra names unused."""

    def fake_run(argv, **kwargs):
        for path, png in zip(argv[2:], pngs):
            Path(path).write_bytes(png)
        return mock.Mock(returncode=0)

    return fake_run


PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200
PNG2 = b"\x89PNG\r\n\x1a\n" + b"\x01" * 300


def test_screenshot_mocked_macos_success():
    with mock.patch("probe.collector.platform.system", return_value="Darwin"):
        with mock.patch("probe.collector.subprocess.run", side_effect=_fake_capture(PNG)) as run:
            result = collect_screenshot()

    assert result["images"] == [base64.b64encode(PNG).decode("utf-8")]
    assert result["count"] == 1
    assert result["format"] == "png"
    assert "timestamp" in result
    argv = run.call_args[0][0]
    assert argv[:2] == ["screencapture", "-x"]
    assert argv[2].endswith(".png")


def test_screenshot_macos_never_passes_dash_as_file():
    """Regression: screencapture(1) takes a file argument and has no stdout mode.
    `screencapture -x -` silently writes a file literally named "-" in the CWD and
    leaves stdout empty, so the collector always returned an error on macOS."""
    with mock.patch("probe.collector.platform.system", return_value="Darwin"):
        with mock.patch("probe.collector.subprocess.run", side_effect=_fake_capture(PNG)) as run:
            collect_screenshot()

    assert "-" not in run.call_args[0][0][1:], "must not hand screencapture a bare '-'"


def test_screenshot_macos_two_displays_gives_two_images_in_order():
    with mock.patch("probe.collector.platform.system", return_value="Darwin"):
        with mock.patch("probe.collector.subprocess.run", side_effect=_fake_displays(PNG, PNG2)):
            result = collect_screenshot()

    assert result["images"] == [
        base64.b64encode(PNG).decode("utf-8"),   # main display first
        base64.b64encode(PNG2).decode("utf-8"),
    ]
    assert result["count"] == 2
    json.dumps(result)


def test_screenshot_macos_unplugging_a_monitor_drops_back_to_one_image():
    with mock.patch("probe.collector.platform.system", return_value="Darwin"):
        with mock.patch("probe.collector.subprocess.run", side_effect=_fake_displays(PNG)):
            result = collect_screenshot()
    assert result["count"] == 1 and len(result["images"]) == 1


def test_screenshot_macos_asks_for_one_file_per_possible_display():
    from probe.collector import MAX_DISPLAYS

    with mock.patch("probe.collector.platform.system", return_value="Darwin"):
        with mock.patch("probe.collector.subprocess.run", side_effect=_fake_displays(PNG)) as run:
            collect_screenshot()
    files = run.call_args[0][0][2:]
    assert len(files) == MAX_DISPLAYS and len(set(files)) == MAX_DISPLAYS


def test_screenshot_macos_cleans_up_temp_file():
    before = set(Path(tempfile.gettempdir()).glob("probe-screenshot-*"))
    with mock.patch("probe.collector.platform.system", return_value="Darwin"):
        with mock.patch("probe.collector.subprocess.run", side_effect=_fake_capture(PNG)):
            collect_screenshot()
    assert set(Path(tempfile.gettempdir()).glob("probe-screenshot-*")) == before


def test_screenshot_mocked_macos_command_not_found():
    with mock.patch("probe.collector.platform.system", return_value="Darwin"):
        with mock.patch("probe.collector.subprocess.run", side_effect=FileNotFoundError()):
            result = collect_screenshot()

    assert "screencapture command not found" in result["error"]
    assert result["platform"] == "Darwin"


def test_screenshot_mocked_macos_timeout():
    with mock.patch("probe.collector.platform.system", return_value="Darwin"):
        with mock.patch(
            "probe.collector.subprocess.run",
            side_effect=subprocess.TimeoutExpired("screencapture", 10),
        ):
            result = collect_screenshot()

    assert "screencapture failed" in result["error"]
    assert "TimeoutExpired" in result["error"]
    assert result["platform"] == "Darwin"


def test_screenshot_mocked_macos_returncode_nonzero():
    with mock.patch("probe.collector.platform.system", return_value="Darwin"):
        with mock.patch("probe.collector.subprocess.run", return_value=mock.Mock(returncode=1)):
            result = collect_screenshot()

    assert "screencapture command failed" in result["error"]
    assert result["platform"] == "Darwin"


def test_screenshot_macos_empty_file_is_an_error():
    """Denied screen-recording permission exits 0 but leaves an empty file."""
    with mock.patch("probe.collector.platform.system", return_value="Darwin"):
        with mock.patch("probe.collector.subprocess.run", side_effect=_fake_capture(b"")):
            result = collect_screenshot()

    assert "Screenshot file is empty" in result["error"]
    assert result["platform"] == "Darwin"


def test_screenshot_mocked_unsupported_platform():
    with mock.patch("probe.collector.platform.system", return_value="Windows"):
        result = collect_screenshot()

    assert "Screenshot not supported on this platform" in result["error"]
    assert result["platform"] == "Windows"


def test_screenshot_mocked_linux_gnome_success():
    with mock.patch("probe.collector.platform.system", return_value="Linux"):
        with mock.patch("probe.collector.subprocess.run", side_effect=_fake_capture(PNG)) as run:
            result = collect_screenshot()

    assert result["images"] == [base64.b64encode(PNG).decode("utf-8")]
    assert result["format"] == "png"
    assert run.call_args[0][0][0] == "gnome-screenshot"


def test_screenshot_mocked_linux_falls_back_to_imagemagick():
    calls = []

    def fake_run(argv, **kwargs):
        calls.append(argv[0])
        if argv[0] == "gnome-screenshot":
            raise FileNotFoundError()
        Path(argv[-1]).write_bytes(PNG)
        return mock.Mock(returncode=0)

    with mock.patch("probe.collector.platform.system", return_value="Linux"):
        with mock.patch("probe.collector.subprocess.run", side_effect=fake_run):
            result = collect_screenshot()

    assert calls == ["gnome-screenshot", "import"]
    assert result["images"] == [base64.b64encode(PNG).decode("utf-8")]


def test_screenshot_mocked_linux_no_tools():
    with mock.patch("probe.collector.platform.system", return_value="Linux"):
        with mock.patch("probe.collector.subprocess.run", side_effect=FileNotFoundError()):
            result = collect_screenshot()

    assert "No screenshot tool found" in result["error"]
    assert result["platform"] == "Linux"


def test_screenshot_has_platform_key_on_error():
    """Verify that error results always have a 'platform' key."""
    # This test assumes the platform the test runs on has screenshot support,
    # or will trigger an error that includes 'platform'.
    # We'll use a mock to force an error.
    with mock.patch("probe.collector.platform.system", return_value="Darwin"):
        with mock.patch("probe.collector.subprocess.run", side_effect=OSError("mock error")):
            result = collect_screenshot()

    assert "error" in result
    assert "platform" in result
    assert result["platform"] == "Darwin"


def test_collect_all_has_system_and_screenshot_in_one_payload():
    with mock.patch("probe.collector.collect_screenshot", return_value={"images": ["AAAA", "BBBB"], "count": 2, "format": "png"}):
        data = collect_all()
    assert data["hostname"]                      # system metrics at the top level
    assert data["screenshot"]["images"] == ["AAAA", "BBBB"]  # all displays, same payload
    json.dumps(data)


def test_collect_all_still_sends_system_data_when_screenshot_fails():
    with mock.patch("probe.collector.collect_screenshot", return_value={"error": "denied", "platform": "Darwin"}):
        data = collect_all()
    assert data["hostname"]
    assert data["screenshot"]["error"] == "denied"


def test_default_category_is_all():
    from probe.collector import DEFAULT_CATEGORY
    assert DEFAULT_CATEGORY == "all" and "all" in COLLECTORS
