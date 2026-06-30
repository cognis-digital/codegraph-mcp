"""Scenario 6 - MCP integrators.

What an agent host actually sees on the wire. We speak raw JSON-RPC 2.0 to the
server in-process: initialize, list tools, then call one - exactly the bytes a
Claude/IDE MCP client exchanges over stdio. No SDK, no network.
"""
import io
import json

from _common import fresh_store, rule
from codegraph.mcp_server import MCPServer


def request(server, payload):
    server.outstream = io.StringIO()
    server.handle(payload)
    out = server.outstream.getvalue().strip()
    return json.loads(out) if out else None


def main() -> None:
    store = fresh_store()
    rule("MCP PROTOCOL  -  raw JSON-RPC an agent host exchanges over stdio")
    server = MCPServer(store)

    init = request(server, {"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    info = init["result"]["serverInfo"]
    print(f"\ninitialize -> {info['name']} v{info['version']} "
          f"(protocol {init['result']['protocolVersion']})")

    listed = request(server, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    tools = listed["result"]["tools"]
    print(f"\ntools/list -> {len(tools)} tools the agent can call:")
    for t in tools:
        req = ",".join(t["inputSchema"]["required"]) or "-"
        print(f"   - {t['name']:<22} required: {req}")

    resp = request(server, {
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": "search_symbols", "arguments": {"query": "loadUser"}}})
    payload = json.loads(resp["result"]["content"][0]["text"])
    print(f"\ntools/call search_symbols('loadUser') -> "
          f"{payload['results'][0]['name']} [{payload['results'][0]['lang']}]")
    print("\nEvery line above is real JSON-RPC; nothing left the machine.")
    store.close()


if __name__ == "__main__":
    main()
