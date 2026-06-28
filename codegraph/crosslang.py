"""Cross-language edge resolution.

The graph's most useful trick is connecting code that never references the
other side by symbol name — a TypeScript `fetch('/api/users/:id')` and the Go
or Python handler registered for that same route. We do it by matching client
endpoints to server endpoints on the normalized (method, route) pair after both
have been recorded by the extractors.

This is the relationship that long-context retrieval misses: the two files
share no token, so only a structural join surfaces the dependency.
"""

from __future__ import annotations

from .extractors.base import normalize_route
from .graph import Store


def resolve(store: Store) -> int:
    """Create cross_lang_http edges from clients to matching servers.

    Returns the number of edges created. An edge goes from the *client* symbol
    (the caller) to the *server* symbol (the handler), so it shows up correctly
    in callers/impact queries on the handler.
    """
    servers = store.endpoints(role="server")
    clients = store.endpoints(role="client")

    # index servers by normalized route, keeping method for tie-breaking
    by_route: dict[str, list[dict]] = {}
    for s in servers:
        by_route.setdefault(normalize_route(s["route"]), []).append(s)

    created = 0
    for c in clients:
        route = normalize_route(c["route"])
        matches = by_route.get(route)
        if not matches:
            continue
        method = c["method"]
        # Prefer a server whose method matches; otherwise accept ANY/any.
        chosen = [
            s for s in matches
            if method in ("ANY", s["method"]) or s["method"] == "ANY"
        ] or matches
        for s in chosen:
            if s["symbol_id"] == c["symbol_id"]:
                continue
            detail = f"{method} {c['route']} -> {s['method']} {s['route']}"
            before = store.conn.total_changes
            store.add_edge(c["symbol_id"], s["symbol_id"], "cross_lang_http", detail)
            if store.conn.total_changes > before:
                created += 1
    store.commit()
    return created
