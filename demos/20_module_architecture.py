"""Scenario 20 - the architecture map, as data.

Zoom out from individual symbols to modules (directories): how many files and
symbols each holds, what languages live there, and the weighted call / HTTP
edges between them. This is the dependency map an architect wants first - and
it's plain data you can feed to a dashboard, not just a picture.
"""
from _common import fresh_store, rule


def main() -> None:
    store = fresh_store()
    rule("MODULE ARCHITECTURE  -  the dependency map as queryable data")

    g = store.project_graph()
    print(f"\n{len(g['modules'])} modules:")
    for m in g["modules"]:
        print(f"   {m['module']:<10} {m['files']}f {m['symbols']:>3}s  "
              f"[{'/'.join(m['languages'])}]")

    print(f"\n{len(g['edges'])} inter-module edges (weighted):")
    for e in g["edges"]:
        kind = "HTTP" if e["kind"] == "cross_lang_http" else "calls"
        print(f"   {e['from']:<8} --{kind} x{e['weight']}--> {e['to']}")

    xlang = [e for e in g["edges"] if e["kind"] == "cross_lang_http"]
    fanout = {}
    for e in xlang:
        fanout.setdefault(e["from"], set()).add(e["to"])
    if fanout:
        src = max(fanout, key=lambda k: len(fanout[k]))
        print(f"\nBusiest cross-language source: '{src}' reaches "
              f"{len(fanout[src])} backend module(s): {', '.join(sorted(fanout[src]))}")
    print("\nFeed this to a dashboard, a linter, or a reviewer - it's just data.")
    store.close()


if __name__ == "__main__":
    main()
