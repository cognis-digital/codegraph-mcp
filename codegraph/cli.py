"""codegraph command-line interface.

    codegraph index <path|git-url> [--db FILE] [--ref BRANCH]
    codegraph query <subcommand> ...        # search / callers / impact / xlang / refs
    codegraph stats [--db FILE]
    codegraph serve [--db FILE] [--token TOKEN]   # MCP server over stdio
    codegraph token <issue|revoke|list> ...
    codegraph audit [--db FILE] [--verify] [-n N]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .diff import diff_git, diff_paths
from .graph import Store
from .indexer import index_git, index_path
from .mcp_server import MCPServer
from .tokens import TokenStore

DEFAULT_DB = "codegraph.db"


def _store(args) -> Store:
    return Store(getattr(args, "db", DEFAULT_DB))


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, default=str))


def cmd_index(args) -> int:
    store = _store(args)
    try:
        target = args.target
        if target.startswith(("http://", "https://", "git@")) or target.endswith(".git"):
            stats = index_git(store, target, ref=args.ref)
        else:
            stats = index_path(store, target)
        _print({"indexed": target, "stats": stats.as_dict()})
        return 0
    finally:
        store.close()


def cmd_stats(args) -> int:
    store = _store(args)
    try:
        _print(store.stats())
        return 0
    finally:
        store.close()


def cmd_diff(args) -> int:
    if args.paths:
        _print(diff_paths(args.a, args.b))
    else:
        _print(diff_git(args.repo, args.a, args.b))
    return 0


def cmd_query(args) -> int:
    store = _store(args)
    try:
        sub = args.qsub
        if sub == "search":
            _print({"results": [s.as_dict() for s in store.search_symbols(args.name, args.kind, args.limit)]})
        elif sub == "refs":
            _print({"name": args.name, "references": store.find_references(args.name)})
        elif sub == "callers":
            _print({"callers": [s.as_dict() for s in store.callers_of(args.symbol_id)]})
        elif sub == "callees":
            _print({"callees": [s.as_dict() for s in store.callees_of(args.symbol_id)]})
        elif sub == "impact":
            _print(store.impact(args.symbol_id, args.max_depth))
        elif sub == "xlang":
            _print({"edges": store.cross_language_edges()})
        elif sub == "orphans":
            _print({"orphans": store.orphans(args.limit)})
        elif sub == "hotspots":
            _print({"hotspots": store.hotspots(args.limit)})
        elif sub == "project-graph":
            _print(store.project_graph())
        else:  # pragma: no cover
            print(f"unknown query: {sub}", file=sys.stderr)
            return 2
        return 0
    finally:
        store.close()


def cmd_serve(args) -> int:
    # HTTP mode serves from a worker thread, so the connection must be usable
    # across threads (requests are still handled one at a time).
    store = Store(getattr(args, "db", DEFAULT_DB), check_same_thread=not args.http)
    try:
        if args.http:
            from .http_server import serve_http
            httpd = serve_http(store, args.host, args.port, args.require_token)
            print(f"codegraph-mcp serving over HTTP at http://{args.host}:{args.port}/mcp "
                  f"(db={args.db}, require_token={args.require_token})", file=sys.stderr)
            try:
                httpd.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                httpd.server_close()
            return 0
        server = MCPServer(store, token=args.token)
        print(f"codegraph-mcp serving over stdio (db={args.db})", file=sys.stderr)
        server.serve_forever()
        return 0
    except PermissionError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    finally:
        store.close()


def cmd_token(args) -> int:
    store = _store(args)
    try:
        ts = TokenStore(store.conn)
        if args.tsub == "issue":
            scopes = set(args.scopes.split(",")) if args.scopes else {"read"}
            token, info = ts.issue(args.label, scopes)
            store.audit.append("admin", "token_issue", args.label, {"scopes": sorted(scopes)})
            _print({"token": token, "id": info.id, "label": info.label, "scopes": sorted(info.scopes),
                    "note": "store this token now; only its hash is kept"})
        elif args.tsub == "revoke":
            ok = ts.revoke(args.id)
            store.audit.append("admin", "token_revoke", str(args.id), {"ok": ok})
            _print({"revoked": ok, "id": args.id})
        elif args.tsub == "list":
            _print({"tokens": [
                {"id": t.id, "label": t.label, "scopes": sorted(t.scopes), "active": t.active}
                for t in ts.list()
            ]})
        return 0
    finally:
        store.close()


def cmd_audit(args) -> int:
    store = _store(args)
    try:
        if args.verify:
            ok, broken = store.audit.verify()
            _print({"intact": ok, "first_broken_seq": broken})
            return 0 if ok else 1
        recs = store.audit.tail(args.n)
        _print({"audit": [
            {"seq": r.seq, "ts": r.ts, "actor": r.actor, "action": r.action,
             "target": r.target, "detail": r.detail, "hash": r.hash[:16] + "…"}
            for r in recs
        ]})
        return 0
    finally:
        store.close()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="codegraph", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version", version=f"codegraph {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    # --db is shared by every leaf command via this parent parser, so it can be
    # passed in any position (e.g. `query search loadUser --db g.db`).
    db_parent = argparse.ArgumentParser(add_help=False)
    db_parent.add_argument("--db", default=DEFAULT_DB, help="graph database file")

    pi = sub.add_parser("index", parents=[db_parent], help="index a path or git URL")
    pi.add_argument("target")
    pi.add_argument("--ref", default=None, help="branch/tag when indexing a git URL")
    pi.set_defaults(func=cmd_index)

    ps = sub.add_parser("stats", parents=[db_parent], help="show graph statistics")
    ps.set_defaults(func=cmd_stats)

    pdf = sub.add_parser("diff", help="diff the knowledge graph between two git refs (or two paths)")
    pdf.add_argument("a", help="ref A (or path A with --paths)")
    pdf.add_argument("b", help="ref B (or path B with --paths)")
    pdf.add_argument("--repo", default=".", help="git repo to diff refs in (default: .)")
    pdf.add_argument("--paths", action="store_true", help="treat A and B as directories, not git refs")
    pdf.set_defaults(func=cmd_diff)

    pq = sub.add_parser("query", help="query the graph")
    qsub = pq.add_subparsers(dest="qsub", required=True)
    q1 = qsub.add_parser("search", parents=[db_parent]); q1.add_argument("name"); q1.add_argument("--kind"); q1.add_argument("--limit", type=int, default=50)
    q2 = qsub.add_parser("refs", parents=[db_parent]); q2.add_argument("name")
    q3 = qsub.add_parser("callers", parents=[db_parent]); q3.add_argument("symbol_id", type=int)
    q4 = qsub.add_parser("callees", parents=[db_parent]); q4.add_argument("symbol_id", type=int)
    q5 = qsub.add_parser("impact", parents=[db_parent]); q5.add_argument("symbol_id", type=int); q5.add_argument("--max-depth", dest="max_depth", type=int, default=6)
    qsub.add_parser("xlang", parents=[db_parent])
    q6 = qsub.add_parser("orphans", parents=[db_parent]); q6.add_argument("--limit", type=int, default=100)
    q7 = qsub.add_parser("hotspots", parents=[db_parent]); q7.add_argument("--limit", type=int, default=20)
    qsub.add_parser("project-graph", parents=[db_parent])
    pq.set_defaults(func=cmd_query)

    pv = sub.add_parser("serve", parents=[db_parent], help="serve the graph to agents over MCP (stdio or HTTP)")
    pv.add_argument("--token", default=None, help="require this agent token (stdio mode)")
    pv.add_argument("--http", action="store_true", help="serve over HTTP instead of stdio")
    pv.add_argument("--host", default="127.0.0.1", help="HTTP bind host")
    pv.add_argument("--port", type=int, default=8765, help="HTTP bind port")
    pv.add_argument("--require-token", dest="require_token", action="store_true",
                    help="reject HTTP requests without a bearer token")
    pv.set_defaults(func=cmd_serve)

    pt = sub.add_parser("token", help="manage scoped agent tokens")
    tsub = pt.add_subparsers(dest="tsub", required=True)
    t1 = tsub.add_parser("issue", parents=[db_parent]); t1.add_argument("label"); t1.add_argument("--scopes", default="read")
    t2 = tsub.add_parser("revoke", parents=[db_parent]); t2.add_argument("id", type=int)
    tsub.add_parser("list", parents=[db_parent])
    pt.set_defaults(func=cmd_token)

    pa = sub.add_parser("audit", parents=[db_parent], help="inspect or verify the audit log")
    pa.add_argument("--verify", action="store_true", help="replay and verify the hash chain")
    pa.add_argument("-n", type=int, default=20)
    pa.set_defaults(func=cmd_audit)

    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
