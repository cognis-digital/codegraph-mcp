"""HTTP transport for the MCP server.

Some agent hosts can't spawn a stdio subprocess — they expect to POST JSON-RPC
over HTTP. This serves the exact same tool surface and `dispatch()` logic as the
stdio server, so behaviour (and the audit log, and scope checks) are identical;
only the wire transport differs.

  POST /mcp        a JSON-RPC request -> a JSON-RPC response (204 for notifications)
  GET  /health     a readiness probe

The bearer token is read from the `Authorization: Bearer <token>` header per
request, so one endpoint can serve many differently-scoped agents. Standard
library only (`http.server`); single-threaded, which keeps the shared SQLite
connection safe and is plenty for an on-prem/agent endpoint.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional

from .graph import Store
from .mcp_server import MCPServer


def make_handler(store: Store, require_token: bool = False):
    class Handler(BaseHTTPRequestHandler):
        server_version = "codegraph-mcp/0.1"

        def _json(self, code: int, obj: dict) -> None:
            body = json.dumps(obj).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _token(self) -> Optional[str]:
            auth = self.headers.get("Authorization", "")
            if auth.lower().startswith("bearer "):
                return auth[7:].strip()
            return None

        def do_GET(self) -> None:
            if self.path == "/health":
                self._json(200, {"status": "ok", "server": "codegraph-mcp"})
            else:
                self._json(404, {"error": "not found"})

        def do_POST(self) -> None:
            if self.path not in ("/", "/mcp"):
                self._json(404, {"error": "not found"})
                return
            length = int(self.headers.get("Content-Length", 0) or 0)
            raw = self.rfile.read(length) if length else b""
            try:
                req = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                self._json(400, MCPServer._err(None, -32700, "parse error"))
                return

            token = self._token()
            if require_token and not token:
                self._json(401, MCPServer._err(req.get("id"), -32001, "bearer token required"))
                return
            try:
                server = MCPServer(store, token=token)
            except PermissionError as e:
                self._json(401, MCPServer._err(req.get("id"), -32001, str(e)))
                return

            resp = server.dispatch(req)
            if resp is None:
                self.send_response(204)
                self.end_headers()
                return
            self._json(200, resp)

        def log_message(self, *args) -> None:  # silence default stderr logging
            pass

    return Handler


def serve_http(store: Store, host: str = "127.0.0.1", port: int = 8765,
               require_token: bool = False) -> HTTPServer:
    """Build (but don't start) an HTTPServer. Call `.serve_forever()` to run."""
    return HTTPServer((host, port), make_handler(store, require_token))
