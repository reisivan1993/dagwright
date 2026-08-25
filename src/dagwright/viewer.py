"""Local-only, read-only browser viewer for deterministic compilation output."""

import json
import threading
import webbrowser
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from typing import Any

from dagwright.adapters.airflow import Airflow3Adapter
from dagwright.compiler import compile_contract, load_validated_sql
from dagwright.compiler.planning import build_execution_plan
from dagwright.contracts import parse_contract_file
from dagwright.overlays import apply_overlays, parse_overlay_file
from dagwright.review import build_review_bundle

LOOPBACK_HOST = "127.0.0.1"


@dataclass(frozen=True)
class ViewerSnapshot:
    """Serialized view data created before the HTTP server starts."""

    payload: bytes


def build_viewer_snapshot(
    contract_path: Path, overlay_paths: list[Path] | None = None
) -> ViewerSnapshot:
    """Compile one contract and return its complete read-only viewer payload."""
    contract = parse_contract_file(contract_path)
    overlays = [parse_overlay_file(path) for path in overlay_paths or []]
    contract = apply_overlays(contract, overlays)
    sql = load_validated_sql(contract, contract_path.parent)
    compilation = compile_contract(contract)
    adapter = Airflow3Adapter()
    violations = adapter.validate(compilation.ir)
    if violations:
        from dagwright.adapters.base import UnsupportedSemanticsError

        raise UnsupportedSemanticsError(adapter.capabilities().name, violations)
    bundle = build_review_bundle(
        compilation,
        adapter,
        target="all",
        sql_by_transformation=sql,
    )
    plan = build_execution_plan(compilation.ir)
    artifacts = [
        {
            "path": item.path,
            "role": item.role,
            "mediaType": item.media_type,
            "sha256": item.sha256,
            "size": len(item.content),
            "content": item.content.decode("utf-8"),
        }
        for item in bundle.files
    ]
    artifacts.append(
        {
            "path": "manifest.json",
            "role": "compilation_manifest",
            "mediaType": "application/json",
            "sha256": bundle.manifest_sha256,
            "size": len(bundle.manifest_bytes),
            "content": bundle.manifest_bytes.decode("utf-8"),
        }
    )
    payload: dict[str, Any] = {
        "product": {
            "name": compilation.contract.metadata.name,
            "version": compilation.contract.version,
            "owner": compilation.contract.metadata.owner,
            "description": compilation.contract.metadata.description,
        },
        "summary": {
            "contractDigest": compilation.contract_digest,
            "irDigest": compilation.ir_digest,
            "manifestDigest": bundle.manifest_sha256,
            "nodes": len(compilation.ir.nodes),
            "edges": len(compilation.ir.edges),
            "artifacts": len(artifacts),
            "generationOnly": True,
        },
        "graph": {
            "nodes": [
                {
                    "id": node.stable_id,
                    "kind": node.kind,
                    "name": node.name,
                }
                for node in compilation.ir.nodes
            ],
            "edges": [
                {
                    "id": edge.stable_id,
                    "source": edge.source,
                    "target": edge.target,
                    "kind": edge.kind,
                }
                for edge in compilation.ir.edges
            ],
        },
        "plan": plan.model_dump(mode="json", by_alias=True),
        "contract": json.loads(compilation.contract_bytes),
        "ir": json.loads(compilation.ir_bytes),
        "manifest": bundle.manifest.model_dump(mode="json", by_alias=True),
        "artifacts": artifacts,
    }
    return ViewerSnapshot(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    )


class ViewerServer(ThreadingHTTPServer):
    """HTTP server carrying one immutable viewer snapshot."""

    snapshot: ViewerSnapshot


class ViewerHandler(BaseHTTPRequestHandler):
    """Serve only the packaged viewer and its precomputed snapshot."""

    server: ViewerServer

    def do_GET(self) -> None:
        routes = {
            "/": ("viewer/index.html", "text/html; charset=utf-8"),
            "/app.js": ("viewer/app.js", "text/javascript; charset=utf-8"),
            "/style.css": ("viewer/style.css", "text/css; charset=utf-8"),
        }
        if self.path == "/api/snapshot":
            self._respond(self.server.snapshot.payload, "application/json; charset=utf-8")
            return
        resource = routes.get(self.path)
        if resource is None:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        relative, content_type = resource
        self._respond(files("dagwright").joinpath(relative).read_bytes(), content_type)

    def _respond(self, body: bytes, content_type: str) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'",
        )
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


def create_viewer_server(snapshot: ViewerSnapshot, port: int) -> ViewerServer:
    """Create a loopback-only server; port zero requests an ephemeral test port."""
    if not 0 <= port <= 65535:
        raise ValueError("port must be between 0 and 65535")
    server = ViewerServer((LOOPBACK_HOST, port), ViewerHandler)
    server.snapshot = snapshot
    return server


def serve_viewer(snapshot: ViewerSnapshot, port: int = 8787, *, open_browser: bool = True) -> None:
    """Serve until interrupted, never binding beyond the IPv4 loopback interface."""
    server = create_viewer_server(snapshot, port)
    actual_port = server.server_address[1]
    url = f"http://{LOOPBACK_HOST}:{actual_port}/"
    print(f"DAGwright Viewer: {url}")
    print("Read-only local view; press Ctrl+C to stop.")
    if open_browser:
        threading.Timer(0.1, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
