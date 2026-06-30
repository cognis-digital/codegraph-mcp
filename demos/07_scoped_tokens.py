"""Scenario 7 - platform security.

Agents get scoped, revocable bearer tokens - never ambient access. This plays
out the full lifecycle: issue a read-only token (it works), try an audit-only
token on a read tool (denied, and the denial is itself logged), then revoke and
watch the next call fail immediately.
"""
import io
import json

from _common import fresh_store, rule
from codegraph.mcp_server import MCPServer
from codegraph.tokens import TokenStore


def call(server, name, **args):
    server.outstream = io.StringIO()
    server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                   "params": {"name": name, "arguments": args}})
    return json.loads(server.outstream.getvalue().strip())


def main() -> None:
    store = fresh_store()
    rule("SCOPED TOKENS  -  least privilege for agents, revocable instantly")
    ts = TokenStore(store.conn)

    reader, rinfo = ts.issue("reader-agent", {"read"})
    auditor, ainfo = ts.issue("audit-agent", {"audit"})
    print(f"\nIssued 'reader-agent' (scopes={sorted(rinfo.scopes)}) "
          f"and 'audit-agent' (scopes={sorted(ainfo.scopes)})")

    ok = call(MCPServer(store, token=reader), "graph_stats")
    print(f"\nreader-agent calls graph_stats -> isError={ok['result']['isError']}  (allowed)")

    denied = call(MCPServer(store, token=auditor), "graph_stats")
    print(f"audit-agent calls graph_stats -> {denied['error']['message']}  (denied)")

    ts.revoke(rinfo.id)
    print(f"\nRevoked reader-agent (id={rinfo.id}). Authenticating now:")
    try:
        MCPServer(store, token=reader)
        print("   ...unexpectedly accepted")
    except PermissionError as e:
        print(f"   PermissionError: {e}  (revocation is immediate)")

    print("\nDenials and revocations are themselves audit events - see demo 4.")
    store.close()


if __name__ == "__main__":
    main()
