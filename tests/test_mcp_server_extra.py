"""Deeper MCP server tests: every tool, error codes, notifications, scope
matrix, audit fingerprints, and the CodeGraphTools surface directly."""
import io
import json
from pathlib import Path

import pytest

from codegraph.graph import Store
from codegraph.indexer import index_path
from codegraph.mcp_server import TOOL_SPECS, CodeGraphTools, MCPServer
from codegraph.tokens import TokenStore

SAMPLE = Path(__file__).resolve().parent.parent / "examples" / "sample_repo"


def indexed():
    s = Store(":memory:")
    index_path(s, SAMPLE)
    return s


def drive(server, request):
    server.outstream = io.StringIO()
    server.handle(request)
    out = server.outstream.getvalue().strip()
    return json.loads(out) if out else None


def call(server, name, **args):
    return drive(server, {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                          "params": {"name": name, "arguments": args}})


def payload(resp):
    return json.loads(resp["result"]["content"][0]["text"])


# ---- tool surface, directly ----------------------------------------------
def test_tools_object_covers_all_specs():
    tools = CodeGraphTools(indexed())
    for name, attr, *_ in TOOL_SPECS:
        assert hasattr(tools, attr), f"missing handler {attr}"


def test_search_symbols_tool_shape():
    t = CodeGraphTools(indexed())
    out = t.search_symbols("loadUser")
    assert out["results"][0]["name"] == "loadUser"


def test_get_symbol_missing_returns_none_field():
    t = CodeGraphTools(indexed())
    assert t.get_symbol(999999)["symbol"] is None


def test_find_references_tool():
    t = CodeGraphTools(indexed())
    out = t.find_references("lookup")
    assert out["name"] == "lookup"
    assert isinstance(out["references"], list)


def test_find_callees_tool():
    s = indexed()
    t = CodeGraphTools(s)
    get_user = next(x for x in s.symbols_by_name("get_user") if x.lang == "python")
    names = {c["name"] for c in t.find_callees(get_user.id)["callees"]}
    assert "lookup" in names


def test_impact_tool_passes_depth():
    s = indexed()
    t = CodeGraphTools(s)
    lookup = next(x for x in s.symbols_by_name("lookup") if x.lang == "python")
    assert t.impact_analysis(lookup.id, max_depth=1)["impacted"] != []


def test_graph_stats_tool():
    assert CodeGraphTools(indexed()).graph_stats()["files"] >= 6


# ---- JSON-RPC dispatch ----------------------------------------------------
def test_initialize_protocol_version():
    resp = drive(MCPServer(indexed()), {"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert "protocolVersion" in resp["result"]


def test_tools_list_has_schemas():
    resp = drive(MCPServer(indexed()), {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    for tool in resp["result"]["tools"]:
        assert "inputSchema" in tool
        assert tool["inputSchema"]["type"] == "object"


def test_notification_initialized_no_response():
    server = MCPServer(indexed())
    server.outstream = io.StringIO()
    server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert server.outstream.getvalue() == ""


def test_unknown_method_returns_method_not_found():
    resp = drive(MCPServer(indexed()), {"jsonrpc": "2.0", "id": 9, "method": "frobnicate"})
    assert resp["error"]["code"] == -32601


def test_notification_unknown_method_silent():
    server = MCPServer(indexed())
    # no id => notification => no error response even for unknown method
    assert server.dispatch({"jsonrpc": "2.0", "method": "whatever"}) is None


def test_unknown_tool_error_code():
    resp = call(MCPServer(indexed()), "nope")
    assert resp["error"]["code"] == -32602


def test_bad_arguments_error_code():
    # search_symbols requires query; omit it -> TypeError -> -32602
    resp = call(MCPServer(indexed()), "search_symbols")
    assert resp["error"]["code"] == -32602


def test_extra_argument_rejected():
    resp = call(MCPServer(indexed()), "graph_stats", bogus=1)
    assert resp["error"]["code"] == -32602


def test_every_read_tool_succeeds():
    server = MCPServer(indexed())
    for name in ("cross_language_edges", "find_orphans", "find_hotspots",
                 "project_graph", "graph_stats"):
        resp = call(server, name)
        assert resp["result"]["isError"] is False, name


def test_parse_error_on_bad_json():
    server = MCPServer(indexed())
    server.outstream = io.StringIO()
    server.instream = io.StringIO("{not json}\n")
    server.serve_forever()
    resp = json.loads(server.outstream.getvalue().strip())
    assert resp["error"]["code"] == -32700


def test_serve_forever_skips_blank_lines():
    server = MCPServer(indexed())
    server.outstream = io.StringIO()
    server.instream = io.StringIO(
        "\n   \n" + json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}) + "\n")
    server.serve_forever()
    lines = [l for l in server.outstream.getvalue().splitlines() if l.strip()]
    assert len(lines) == 1


# ---- audit fingerprints ---------------------------------------------------
def test_tool_call_logs_argument_and_result_keys():
    store = indexed()
    server = MCPServer(store)
    call(server, "search_symbols", query="loadUser")
    rec = next(r for r in store.audit.tail(5) if r.action == "tool_call")
    assert rec.detail["arguments"] == {"query": "loadUser"}
    assert "results" in rec.detail["result_keys"]


# ---- scope matrix ---------------------------------------------------------
def test_admin_scope_alone_lacks_read():
    store = indexed()
    token, _ = TokenStore(store.conn).issue("admin-only", {"admin"})
    server = MCPServer(store, token=token)
    resp = call(server, "graph_stats")
    assert "scope" in resp["error"]["message"]


def test_read_scope_allows_all_read_tools():
    store = indexed()
    token, _ = TokenStore(store.conn).issue("reader", {"read"})
    server = MCPServer(store, token=token)
    assert call(server, "project_graph")["result"]["isError"] is False


def test_actor_label_recorded_for_token():
    store = indexed()
    token, _ = TokenStore(store.conn).issue("agent-7", {"read"})
    server = MCPServer(store, token=token)
    call(server, "graph_stats")
    rec = next(r for r in store.audit.tail(5) if r.action == "tool_call")
    assert rec.actor == "agent:agent-7"


def test_anonymous_actor_when_no_token():
    store = indexed()
    server = MCPServer(store)
    call(server, "graph_stats")
    rec = next(r for r in store.audit.tail(5) if r.action == "tool_call")
    assert rec.actor == "anonymous"


def test_revoked_token_rejected_at_construction():
    store = indexed()
    ts = TokenStore(store.conn)
    token, info = ts.issue("temp", {"read"})
    ts.revoke(info.id)
    with pytest.raises(PermissionError):
        MCPServer(store, token=token)
