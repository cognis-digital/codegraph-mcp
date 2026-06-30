"""More HTTP transport tests: routing, methods, parse errors, scope over HTTP,
notifications, and the root path alias."""
import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from codegraph.graph import Store
from codegraph.http_server import serve_http
from codegraph.indexer import index_path
from codegraph.tokens import TokenStore

SAMPLE = Path(__file__).resolve().parent.parent / "examples" / "sample_repo"


class Server:
    def __init__(self, require_token=False):
        self.store = Store(":memory:", check_same_thread=False)
        index_path(self.store, SAMPLE)
        self.httpd = serve_http(self.store, "127.0.0.1", 0, require_token)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def request(self, method, path, payload=None, token=None, raw=None):
        data = raw if raw is not None else (
            json.dumps(payload).encode() if payload is not None else None)
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}", data=data, method=method,
            headers={"Content-Type": "application/json"})
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                body = r.read()
                return r.status, (json.loads(body) if body else None)
        except urllib.error.HTTPError as e:
            body = e.read()
            return e.code, (json.loads(body) if body else None)

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def server():
    s = Server()
    yield s
    s.close()


def test_root_path_alias_accepts_post(server):
    code, resp = server.request("POST", "/", {"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert code == 200 and resp["result"]["serverInfo"]["name"] == "codegraph-mcp"


def test_unknown_post_path_404(server):
    code, resp = server.request("POST", "/nope", {"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert code == 404


def test_unknown_get_path_404(server):
    code, resp = server.request("GET", "/random")
    assert code == 404


def test_health_payload(server):
    code, resp = server.request("GET", "/health")
    assert code == 200 and resp == {"status": "ok", "server": "codegraph-mcp"}


def test_malformed_json_400(server):
    code, resp = server.request("POST", "/mcp", raw=b"{ not json")
    assert code == 400
    assert resp["error"]["code"] == -32700


def test_empty_body_400(server):
    code, resp = server.request("POST", "/mcp", raw=b"")
    assert code == 400


def test_tool_call_over_http(server):
    code, resp = server.request("POST", "/mcp", {
        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {"name": "graph_stats", "arguments": {}}})
    assert code == 200
    body = json.loads(resp["result"]["content"][0]["text"])
    assert body["files"] >= 6


def test_notification_204_over_http(server):
    code, resp = server.request("POST", "/mcp", {
        "jsonrpc": "2.0", "method": "notifications/initialized"})
    assert code == 204 and resp is None


def test_scope_denied_over_http(server):
    token, _ = TokenStore(server.store.conn).issue("audit-only", {"audit"})
    code, resp = server.request("POST", "/mcp", {
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": "graph_stats", "arguments": {}}}, token=token)
    assert "scope" in resp["error"]["message"]


def test_require_token_missing_is_401():
    s = Server(require_token=True)
    try:
        code, _ = s.request("POST", "/mcp", {"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        assert code == 401
    finally:
        s.close()


def test_require_token_invalid_is_401():
    s = Server(require_token=True)
    try:
        code, _ = s.request("POST", "/mcp",
                            {"jsonrpc": "2.0", "id": 1, "method": "initialize"},
                            token="cg_bogus")
        assert code == 401
    finally:
        s.close()
