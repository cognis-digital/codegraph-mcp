"""Scenario 3 - staff engineers planning a refactor.

Where does a change ripple furthest, what is safe to delete, and what is the
blast radius of touching a core symbol? Hotspots, orphans and impact answer the
three questions every refactor starts with.
"""
from _common import fresh_store, rule


def main() -> None:
    store = fresh_store()
    rule("IMPACT & REFACTOR  -  hotspots, dead code, and blast radius")

    print("\nHOTSPOTS (most depended-on - review hardest, test most):")
    for h in store.hotspots(8):
        print(f"   {h['callers']:>2} callers  {h['name']:<18} [{h['lang']}]  {h['path']}")

    print("\nORPHANS (no callers, not a route handler - dead-code candidates):")
    orphans = store.orphans(8)
    if orphans:
        for o in orphans:
            print(f"   {o['name']:<18} [{o['lang']}]  {o['path']}:{o['start_line']}")
    else:
        print("   (none - every function is reachable)")

    top = store.hotspots(1)
    if top:
        sid = top[0]["id"]
        blast = store.impact(sid)
        print(f"\nBLAST RADIUS of the #1 hotspot '{top[0]['name']}': "
              f"{blast['impacted_count']} symbol(s) across "
              f"{len({r['lang'] for r in blast['impacted']})} language(s).")
    store.close()


if __name__ == "__main__":
    main()
