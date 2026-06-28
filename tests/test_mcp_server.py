import io
import json
from pathlib import Path

import pytest

from codegraph.graph import Store
from codegraph.indexer import index_path
from codegraph.mcp_server import MCPServer
from codegraph.tokens import TokenStore

SAMPLE = Path(__file__).resolve().parent.parent / "examples" / "sample_repo"


def indexed_store():
    store = Store(":memory:")
    index_path(store, SAMPLE)
    return store


def drive(server, request):
    """Send one request through handle() and return the parsed JSON response."""
    server.outstream = io.StringIO()
    server.handle(request)
    out = server.outstream.getvalue().strip()
    return json.loads(out) if out else None


def test_initialize_and_list():
    server = MCPServer(indexed_store())
    init = drive(server, {"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert init["result"]["serverInfo"]["name"] == "codegraph-mcp"

    listed = drive(server, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    tool_names = {t["name"] for t in listed["result"]["tools"]}
    assert {"search_symbols", "find_callers", "impact_analysis", "cross_language_edges",
            "find_orphans", "find_hotspots"} <= tool_names


def test_tools_call_search_and_audit_logged():
    store = indexed_store()
    server = MCPServer(store)
    resp = drive(server, {
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": "search_symbols", "arguments": {"query": "loadUser"}},
    })
    payload = json.loads(resp["result"]["content"][0]["text"])
    assert payload["results"][0]["name"] == "loadUser"
    # the read was recorded
    actions = [r.action for r in store.audit.tail(5)]
    assert "tool_call" in actions


def test_unknown_tool_errors():
    server = MCPServer(indexed_store())
    resp = drive(server, {
        "jsonrpc": "2.0", "id": 4, "method": "tools/call",
        "params": {"name": "nope", "arguments": {}},
    })
    assert resp["error"]["code"] == -32602


def test_scope_enforced_with_token():
    store = indexed_store()
    ts = TokenStore(store.conn)
    token, _ = ts.issue("audit-only", {"audit"})  # no 'read'
    server = MCPServer(store, token=token)
    resp = drive(server, {
        "jsonrpc": "2.0", "id": 5, "method": "tools/call",
        "params": {"name": "search_symbols", "arguments": {"query": "x"}},
    })
    assert "error" in resp
    assert "scope" in resp["error"]["message"]
    # denial is itself audited
    assert any(r.action == "tool_call_denied" for r in store.audit.tail(5))


def test_invalid_token_rejected():
    store = indexed_store()
    with pytest.raises(PermissionError):
        MCPServer(store, token="cg_bogus")


def test_read_token_allows_call():
    store = indexed_store()
    ts = TokenStore(store.conn)
    token, _ = ts.issue("reader", {"read"})
    server = MCPServer(store, token=token)
    resp = drive(server, {
        "jsonrpc": "2.0", "id": 6, "method": "tools/call",
        "params": {"name": "graph_stats", "arguments": {}},
    })
    assert resp["result"]["isError"] is False
