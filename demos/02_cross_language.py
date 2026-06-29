"""Scenario 2 - polyglot teams.

The edge nobody else resolves: a TypeScript client calls `fetch('/api/users/:id')`
and a Go (or Python, Java, C#, Rust) handler serves that route. They share no
symbol name, so only a *structural* join across the HTTP boundary finds the
dependency. This is what a single-file context window can never see.
"""
from _common import fresh_store, rule


def main() -> None:
    store = fresh_store()
    rule("CROSS-LANGUAGE EDGES  -  the dependency a context window misses")

    edges = store.cross_language_edges()
    print(f"\nResolved {len(edges)} cross-language HTTP edge(s):\n")
    for e in edges:
        frm, to = e["from"], e["to"]
        print(f"  {frm['lang']:>10} {frm['symbol']:<16} --HTTP {e['detail']:<22}-> "
              f"{to['lang']:<6} {to['symbol']} ({to['path']})")

    langs = sorted({e["from"]["lang"] for e in edges} | {e["to"]["lang"] for e in edges})
    print(f"\nLanguages joined by these edges: {', '.join(langs)}")
    print("Change the route on either side and the graph shows the break - across the language boundary.")
    store.close()


if __name__ == "__main__":
    main()
