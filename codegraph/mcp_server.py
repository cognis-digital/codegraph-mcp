"""A minimal Model Context Protocol server over stdio (JSON-RPC 2.0).

This implements just enough of MCP for an agent host to discover and call the
graph tools: `initialize`, `tools/list`, and `tools/call`. We deliberately use
plain JSON-RPC over stdin/stdout with no third-party SDK — the wire format is
public and stable, and a zero-dependency server is far easier to vet and to run
inside an air-gapped or regulated environment.

Two properties matter for the product thesis:
  * every `tools/call` is written to the hash-chained audit log, tagged with
    the calling agent's token label — so "which agent read what, when" is
    provable after the fact;
  * a token's scopes are checked on every call; revocation is immediate.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Callable, Optional, TextIO

from .graph import Store
from .tokens import TokenInfo, TokenStore

PROTOCOL_VERSION = "2025-06-18"
SERVER_NAME = "codegraph-mcp"


def _ok(symbols) -> list[dict]:
    return [s.as_dict() for s in symbols]


class CodeGraphTools:
    """The callable tool surface over a Store. Pure functions of (args)->data."""

    def __init__(self, store: Store):
        self.store = store

    # each tool returns a JSON-serializable object
    def search_symbols(self, query: str, kind: Optional[str] = None, limit: int = 50) -> dict:
        return {"results": _ok(self.store.search_symbols(query, kind, limit))}

    def get_symbol(self, symbol_id: int) -> dict:
        sym = self.store.get_symbol(int(symbol_id))
        return {"symbol": sym.as_dict() if sym else None}

    def find_references(self, name: str) -> dict:
        return {"name": name, "references": self.store.find_references(name)}

    def find_callers(self, symbol_id: int) -> dict:
        return {"callers": _ok(self.store.callers_of(int(symbol_id)))}

    def find_callees(self, symbol_id: int) -> dict:
        return {"callees": _ok(self.store.callees_of(int(symbol_id)))}

    def impact_analysis(self, symbol_id: int, max_depth: int = 6) -> dict:
        return self.store.impact(int(symbol_id), int(max_depth))

    def cross_language_edges(self) -> dict:
        return {"edges": self.store.cross_language_edges()}

    def find_orphans(self, limit: int = 100) -> dict:
        return {"orphans": self.store.orphans(int(limit))}

    def find_hotspots(self, limit: int = 20) -> dict:
        return {"hotspots": self.store.hotspots(int(limit))}

    def project_graph(self) -> dict:
        return self.store.project_graph()

    def graph_stats(self) -> dict:
        return self.store.stats()


# (name, handler-attr, description, input schema properties, required)
TOOL_SPECS = [
    ("search_symbols", "search_symbols",
     "Search indexed symbols (functions, methods, classes, types) by name substring.",
     {"query": {"type": "string"},
      "kind": {"type": "string", "enum": ["function", "method", "class", "type"]},
      "limit": {"type": "integer", "default": 50}},
     ["query"]),
    ("get_symbol", "get_symbol",
     "Fetch one symbol's full record (signature, location, container) by id.",
     {"symbol_id": {"type": "integer"}}, ["symbol_id"]),
    ("find_references", "find_references",
     "List every call site / identifier use of a name across the repo.",
     {"name": {"type": "string"}}, ["name"]),
    ("find_callers", "find_callers",
     "List symbols that directly call the given symbol (includes cross-language).",
     {"symbol_id": {"type": "integer"}}, ["symbol_id"]),
    ("find_callees", "find_callees",
     "List symbols the given symbol directly calls.",
     {"symbol_id": {"type": "integer"}}, ["symbol_id"]),
    ("impact_analysis", "impact_analysis",
     "Transitive callers ('blast radius') of a symbol — what may break if it changes.",
     {"symbol_id": {"type": "integer"}, "max_depth": {"type": "integer", "default": 6}},
     ["symbol_id"]),
    ("cross_language_edges", "cross_language_edges",
     "List resolved cross-language HTTP edges (e.g. a TS fetch -> a Go/Python handler).",
     {}, []),
    ("find_orphans", "find_orphans",
     "Dead-code candidates: functions/methods with no callers and not HTTP entrypoints.",
     {"limit": {"type": "integer", "default": 100}}, []),
    ("find_hotspots", "find_hotspots",
     "Most depended-on symbols (highest caller count) — where changes ripple furthest.",
     {"limit": {"type": "integer", "default": 20}}, []),
    ("project_graph", "project_graph",
     "Module/package-level dependency graph: modules and the (weighted) edges between them.",
     {}, []),
    ("graph_stats", "graph_stats",
     "Summary counts for the indexed graph (files, symbols, edges, languages).",
     {}, []),
]

# scope required to invoke each tool
_TOOL_SCOPE = {name: "read" for name, *_ in TOOL_SPECS}


class MCPServer:
    def __init__(
        self,
        store: Store,
        token: Optional[str] = None,
        instream: TextIO = sys.stdin,
        outstream: TextIO = sys.stdout,
    ):
        self.store = store
        self.tools = CodeGraphTools(store)
        self.tokenstore = TokenStore(store.conn)
        self.instream = instream
        self.outstream = outstream
        self.identity: TokenInfo | None = None
        self.actor = "anonymous"
        if token:
            info = self.tokenstore.authenticate(token)
            if info is None:
                raise PermissionError("invalid or revoked token")
            self.identity = info
            self.actor = f"agent:{info.label}"

    # ---- JSON-RPC plumbing ----------------------------------------------
    def _send(self, obj: dict) -> None:
        self.outstream.write(json.dumps(obj) + "\n")
        self.outstream.flush()

    @staticmethod
    def _ok(req_id, result) -> dict:
        return {"jsonrpc": "2.0", "id": req_id, "result": result}

    @staticmethod
    def _err(req_id, code: int, message: str) -> dict:
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}

    def serve_forever(self) -> None:
        """stdio transport: one JSON-RPC message per line."""
        for line in self.instream:
            line = line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
            except json.JSONDecodeError:
                self._send(self._err(None, -32700, "parse error"))
                continue
            resp = self.dispatch(req)
            if resp is not None:
                self._send(resp)

    # ---- request dispatch -----------------------------------------------
    def handle(self, req: dict) -> None:
        """Dispatch and send (used by the stdio loop and tests)."""
        resp = self.dispatch(req)
        if resp is not None:
            self._send(resp)

    def dispatch(self, req: dict) -> Optional[dict]:
        """Pure request -> response. Returns None for notifications.

        Transport-agnostic: the stdio loop and the HTTP transport both call this.
        """
        method = req.get("method")
        req_id = req.get("id")
        params = req.get("params") or {}

        if method == "initialize":
            return self._ok(req_id, {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": "0.1.0"},
            })
        if method == "notifications/initialized":
            return None  # notification, no response
        if method == "tools/list":
            return self._ok(req_id, {"tools": self._tool_list()})
        if method == "tools/call":
            return self._call_tool(req_id, params)
        if req_id is not None:
            return self._err(req_id, -32601, f"method not found: {method}")
        return None

    def _tool_list(self) -> list[dict]:
        out = []
        for name, _attr, desc, props, required in TOOL_SPECS:
            out.append({
                "name": name,
                "description": desc,
                "inputSchema": {
                    "type": "object",
                    "properties": props,
                    "required": required,
                },
            })
        return out

    def _authorize(self, tool: str) -> Optional[str]:
        """Return an error message if not allowed, else None."""
        needed = _TOOL_SCOPE.get(tool, "read")
        if self.identity is None:
            return None  # open mode (no token configured) — allow reads
        if needed not in self.identity.scopes:
            return f"token '{self.identity.label}' lacks scope '{needed}'"
        return None

    def _call_tool(self, req_id, params: dict) -> dict:
        name = params.get("name")
        args = params.get("arguments") or {}
        handler_attr = dict((n, a) for n, a, *_ in TOOL_SPECS).get(name)
        if not handler_attr:
            return self._err(req_id, -32602, f"unknown tool: {name}")

        denied = self._authorize(name)
        if denied:
            self.store.audit.append(self.actor, "tool_call_denied", name, {"reason": denied})
            return self._err(req_id, -32001, denied)

        handler: Callable[..., Any] = getattr(self.tools, handler_attr)
        try:
            data = handler(**args)
        except TypeError as e:
            return self._err(req_id, -32602, f"bad arguments: {e}")
        except Exception as e:  # noqa: BLE001 - report tool errors to the agent
            return self._err(req_id, -32000, f"tool error: {e}")

        # provable read: log the call (and a compact result fingerprint)
        self.store.audit.append(
            self.actor, "tool_call", name,
            {"arguments": args, "result_keys": sorted(data.keys()) if isinstance(data, dict) else []},
        )
        return self._ok(req_id, {
            "content": [{"type": "text", "text": json.dumps(data, indent=2)}],
            "isError": False,
        })
