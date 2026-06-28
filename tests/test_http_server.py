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

    def post(self, payload, token=None):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/mcp",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                body = r.read()
                return r.status, (json.loads(body) if body else None)
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"null")

    def get(self, path):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=5) as r:
            return r.status, json.loads(r.read())

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def server():
    s = Server()
    yield s
    s.close()


def test_initialize_over_http(server):
    code, resp = server.post({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert code == 200
    assert resp["result"]["serverInfo"]["name"] == "codegraph-mcp"


def test_tools_call_over_http_and_audit(server):
    code, resp = server.post({
        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {"name": "search_symbols", "arguments": {"query": "loadUser"}},
    })
    assert code == 200
    payload = json.loads(resp["result"]["content"][0]["text"])
    assert payload["results"][0]["name"] == "loadUser"
    assert any(r.action == "tool_call" for r in server.store.audit.tail(5))


def test_health_endpoint(server):
    code, resp = server.get("/health")
    assert code == 200 and resp["status"] == "ok"


def test_notification_returns_204(server):
    code, resp = server.post({"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert code == 204
    assert resp is None


def test_require_token_rejects_missing_and_invalid():
    s = Server(require_token=True)
    try:
        code, resp = s.post({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        assert code == 401
        code, resp = s.post({"jsonrpc": "2.0", "id": 1, "method": "initialize"}, token="cg_bogus")
        assert code == 401
        # a valid token is accepted
        token, _ = TokenStore(s.store.conn).issue("http-agent", {"read"})
        code, resp = s.post({"jsonrpc": "2.0", "id": 1, "method": "initialize"}, token=token)
        assert code == 200
    finally:
        s.close()
