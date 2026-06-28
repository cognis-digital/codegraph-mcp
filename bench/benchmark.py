#!/usr/bin/env python3
"""Reproducible benchmark for codegraph-mcp.

Two things are measured, both on a generated multi-language repository:

  1. Index throughput — files/sec and symbols/sec.
  2. Cross-language dependency recall — the metric that matters. For each
     back-end handler we ask "what breaks if I change this?" and check whether
     the front-end caller (in another language, sharing no symbol name) is
     found. We compare three strategies:

       * codegraph  — graph impact() over normalized-route cross-language edges
       * grep:name  — search the repo for the handler's symbol name
       * grep:route — search the repo for the route substring

The point the benchmark makes is the "Navigation Paradox": the front-end caller
and the back-end handler share no token, so a name search finds nothing and even
a route search returns files, not the symbol-level, transitive impact a graph
gives you. Run it yourself:

    python bench/benchmark.py --services 80
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from codegraph.graph import Store          # noqa: E402
from codegraph.indexer import index_path   # noqa: E402


def generate_repo(root: Path, n: int) -> None:
    """Create n micro-services, each a TS client + Go/Python/Rust handlers that
    serve the same route under different param syntaxes and symbol names."""
    for i in range(n):
        (root / "web").mkdir(parents=True, exist_ok=True)
        (root / "server").mkdir(parents=True, exist_ok=True)
        (root / "api").mkdir(parents=True, exist_ok=True)
        (root / "svc").mkdir(parents=True, exist_ok=True)

        (root / "web" / f"client{i}.ts").write_text(
            f"export async function loadThing{i}(id: string) {{\n"
            f"  const r = await fetch(`/api/thing{i}/${{id}}`);\n"
            f"  return r.json();\n"
            f"}}\n", encoding="utf-8")
        (root / "server" / f"handler{i}.go").write_text(
            f"package main\n"
            f"func routes{i}(mux *http.ServeMux) {{\n"
            f'  mux.HandleFunc("/api/thing{i}/{{id}}", getThing{i})\n'
            f"}}\n"
            f"func getThing{i}(w http.ResponseWriter, r *http.Request) {{\n"
            f"  store{i}(r.PathValue(\"id\"))\n"
            f"}}\n"
            f"func store{i}(id string) {{}}\n", encoding="utf-8")
        (root / "api" / f"svc{i}.py").write_text(
            f"@app.route('/api/thing{i}/<id>', methods=['GET'])\n"
            f"def fetch_thing{i}(id):\n"
            f"    return persist{i}(id)\n"
            f"def persist{i}(id):\n"
            f"    return id\n", encoding="utf-8")
        (root / "svc" / f"svc{i}.rs").write_text(
            f"pub fn router{i}() -> Router {{\n"
            f'  Router::new().route("/api/thing{i}/{{id}}", get(handle{i}))\n'
            f"}}\n"
            f"fn handle{i}() -> String {{ keep{i}() }}\n"
            f"fn keep{i}() -> String {{ String::new() }}\n", encoding="utf-8")


def grep_finds_ts_caller(root: Path, name: str) -> bool:
    """Does a name search land in any TypeScript file? (the cross-lang caller)"""
    pat = re.compile(r"\b" + re.escape(name) + r"\b")
    for dp, _dn, fns in os.walk(root):
        for fn in fns:
            if fn.endswith(".ts"):
                if pat.search((Path(dp) / fn).read_text(encoding="utf-8", errors="replace")):
                    return True
    return False


def run(n: int) -> dict:
    with tempfile.TemporaryDirectory(prefix="codegraph-bench-") as tmp:
        root = Path(tmp)
        generate_repo(root, n)

        store = Store(":memory:")
        t0 = time.perf_counter()
        stats = index_path(store, root)
        elapsed = time.perf_counter() - t0

        # cross-language dependency recall on the Python route handlers
        # (the @app.route handler is the symbol the endpoint binds to)
        graph_hits = grep_name_hits = route_hits = 0
        for i in range(n):
            handler = f"fetch_thing{i}"
            # codegraph: does impact() reach the TS client in another language?
            syms = [s for s in store.symbols_by_name(handler) if s.lang == "python"]
            if syms:
                impacted = store.impact(syms[0].id)["impacted"]
                if any(r["lang"] == "typescript" and r["name"] == f"loadThing{i}"
                       for r in impacted):
                    graph_hits += 1
            # grep by symbol name: can it find the TS caller?
            if grep_finds_ts_caller(root, handler):
                grep_name_hits += 1
        # grep by route substring: a manual workaround that finds files, not symbols
        route_hits = _route_recall(root, n)

        return {
            "services": n,
            "files": stats.files,
            "symbols": stats.symbols,
            "cross_language_edges": stats.cross_edges,
            "index_seconds": round(elapsed, 3),
            "files_per_sec": round(stats.files / elapsed) if elapsed else 0,
            "symbols_per_sec": round(stats.symbols / elapsed) if elapsed else 0,
            "recall": {
                "codegraph": f"{graph_hits}/{n}",
                "grep_by_name": f"{grep_name_hits}/{n}",
                "grep_by_route": f"{route_hits}/{n} (files only, not symbols)",
            },
        }


def _route_recall(root: Path, n: int) -> int:
    hits = 0
    for i in range(n):
        # the route substring DOES appear across languages (param syntax aside),
        # so a manual route-grep finds files — but not symbol-level impact.
        pat = re.compile(re.escape(f"/api/thing{i}/"))
        for dp, _dn, fns in os.walk(root):
            found = False
            for fn in fns:
                if fn.endswith(".ts") and pat.search(
                        (Path(dp) / fn).read_text(encoding="utf-8", errors="replace")):
                    found = True
            if found:
                hits += 1
                break
    return hits


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="codegraph-mcp benchmark")
    ap.add_argument("--services", type=int, default=80,
                    help="number of micro-services to generate (4 files each)")
    args = ap.parse_args(argv)

    print(f"generating {args.services} services ({args.services * 4} files, "
          f"4 languages) and indexing...\n")
    r = run(args.services)

    print("## throughput")
    print(f"  files:                 {r['files']}")
    print(f"  symbols:               {r['symbols']}")
    print(f"  cross-language edges:  {r['cross_language_edges']}")
    print(f"  index time:            {r['index_seconds']}s")
    print(f"  files/sec:             {r['files_per_sec']}")
    print(f"  symbols/sec:           {r['symbols_per_sec']}")
    print("\n## cross-language dependency recall")
    print("  (find the front-end caller that breaks if a back-end handler changes)")
    print(f"  codegraph (graph impact):   {r['recall']['codegraph']}")
    print(f"  grep by symbol name:        {r['recall']['grep_by_name']}")
    print(f"  grep by route substring:    {r['recall']['grep_by_route']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
