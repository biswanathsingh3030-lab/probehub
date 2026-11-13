import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from probe import cli
from probe.collector import COLLECTORS, collect
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
    assert "sent system id=7" in capsys.readouterr().out
    assert cli.main(["--hub-url", "http://127.0.0.1:9", "--probe-id", "p1"]) == 1


def test_cli_dry_run_prints_envelope(capsys):
    assert cli.main(["--dry-run", "--probe-id", "p1"]) == 0
    env = json.loads(capsys.readouterr().out)
    assert env["probe_id"] == "p1"
    assert env["category"] == "system"
    assert "hostname" in env["data"]


def test_send_includes_bearer_token(fake_hub):
    url, received = fake_hub
    send(url, build_envelope("p1", "system", {}), token="secret")
    assert received[0][3] == "Bearer secret"


def test_cli_reads_token_from_env(fake_hub, monkeypatch):
    monkeypatch.setenv("PROBEHUB_TOKEN", "from-env")
    assert cli.parse_args(["--probe-id", "p1"]).token == "from-env"
