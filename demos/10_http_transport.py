"""Scenario 10 - hosts that can't spawn a subprocess.

Some agent platforms POST JSON-RPC over HTTP instead of stdio. codegraph serves
the identical tool surface, dispatch logic, scope checks, and audit log over a
tiny stdlib HTTP server. This demo starts one on an ephemeral port, hits
/health, and calls a tool with a bearer token - all over the loopback socket.
"""
import json
import threading
import urllib.request

from _common import SAMPLE, rule
from codegraph.graph import Store
from codegraph.http_server import serve_http
from codegraph.indexer import index_path
from codegraph.tokens import TokenStore


def post(port, payload, token=None):
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/mcp", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read())


def main() -> None:
    rule("HTTP TRANSPORT  -  same MCP tools, over a loopback socket")
    # HTTP serves from a worker thread -> the connection must allow cross-thread use
    store = Store(":memory:", check_same_thread=False)
    index_path(store, SAMPLE)

    token, _ = TokenStore(store.conn).issue("http-agent", {"read"})
    httpd = serve_http(store, "127.0.0.1", 0)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        health = urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=5)
        print(f"\nGET /health -> {json.loads(health.read())}")

        resp = post(port, {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                           "params": {"name": "graph_stats", "arguments": {}}}, token=token)
        stats = json.loads(resp["result"]["content"][0]["text"])
        print(f"\nPOST /mcp graph_stats (Bearer http-agent) -> "
              f"{stats['files']} files, {stats['symbols']} symbols, "
              f"{stats['cross_language_edges']} cross-language edges")
        print("\nIdentical behaviour to stdio - only the transport differs.")
    finally:
        httpd.shutdown()
        httpd.server_close()
        store.close()


if __name__ == "__main__":
    main()
