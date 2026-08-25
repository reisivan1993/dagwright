import json
import threading
from pathlib import Path
from typing import Any, cast
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest
from typer.testing import CliRunner

from dagwright.cli import app
from dagwright.viewer import LOOPBACK_HOST, build_viewer_snapshot, create_viewer_server

ROOT = Path(__file__).parents[1]
CONTRACT = ROOT / "examples/customer-analytics/dataproduct.yaml"


def test_snapshot_is_deterministic_and_contains_review_surfaces() -> None:
    first = build_viewer_snapshot(CONTRACT)
    second = build_viewer_snapshot(CONTRACT)

    assert first.payload == second.payload
    payload = cast(dict[str, Any], json.loads(first.payload))
    assert payload["product"]["name"] == "customer-analytics"
    assert payload["summary"]["nodes"] == 12
    assert payload["summary"]["edges"] == 11
    assert payload["summary"]["generationOnly"] is True
    assert len(payload["plan"]["steps"]) == 12
    paths = {artifact["path"] for artifact in payload["artifacts"]}
    assert "contract.normalized.json" in paths
    assert "pipeline.ir.json" in paths
    assert "dags/dagwright__customer_analytics.py" in paths
    assert "spark/build_customer_engagement.py" in paths
    assert "manifest.json" in paths


def test_snapshot_applies_explicit_overlay() -> None:
    overlay = ROOT / "examples/customer-analytics/development.overlay.yaml"

    payload = json.loads(build_viewer_snapshot(CONTRACT, [overlay]).payload)

    assert payload["contract"]["metadata"]["environment"] == "development"


def test_server_is_loopback_only_and_serves_hardened_read_only_routes() -> None:
    server = create_viewer_server(build_viewer_snapshot(CONTRACT), 0)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    host, port = cast(tuple[str, int], server.server_address)
    try:
        assert host == LOOPBACK_HOST
        with urlopen(f"http://{host}:{port}/", timeout=2) as response:
            assert response.status == 200
            assert b"DAGwright Viewer" in response.read()
            assert response.headers["Cache-Control"] == "no-store"
            assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
        with urlopen(f"http://{host}:{port}/api/snapshot", timeout=2) as response:
            assert json.loads(response.read())["summary"]["nodes"] == 12
        with pytest.raises(HTTPError) as missing:
            urlopen(f"http://{host}:{port}/unknown", timeout=2)
        assert missing.value.code == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_server_rejects_invalid_port() -> None:
    with pytest.raises(ValueError, match="port must be between"):
        create_viewer_server(build_viewer_snapshot(CONTRACT), 65536)


def test_ui_cli_builds_snapshot_and_starts_server(monkeypatch: pytest.MonkeyPatch) -> None:
    observed: dict[str, object] = {}

    def fake_serve(snapshot: object, port: int, *, open_browser: bool) -> None:
        observed.update(snapshot=snapshot, port=port, open_browser=open_browser)

    monkeypatch.setattr("dagwright.cli.serve_viewer", fake_serve)

    result = CliRunner().invoke(app, ["ui", str(CONTRACT), "--port", "9876", "--no-open"])

    assert result.exit_code == 0
    assert observed["port"] == 9876
    assert observed["open_browser"] is False
