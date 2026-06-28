#!/usr/bin/env python3
"""End-to-end demo: index the sample repo, run a cross-language query, and
show that every agent read landed in a verifiable audit log.

    python demo.py
"""

from pathlib import Path

from codegraph.graph import Store
from codegraph.indexer import index_path

SAMPLE = Path(__file__).resolve().parent / "examples" / "sample_repo"


def main() -> None:
    store = Store(":memory:")
    stats = index_path(store, SAMPLE)
    print("== indexed sample repo ==")
    print(" ", stats.as_dict())
    print("  languages:", store.stats()["languages"])

    print("\n== cross-language edges (client -> handler) ==")
    for e in store.cross_language_edges():
        f, t = e["from"], e["to"]
        print(f"  {f['symbol']} ({f['lang']})  ->  {t['symbol']} ({t['lang']})   [{e['detail']}]")

    print("\n== blast radius of the Python get_user handler ==")
    (get_user,) = store.symbols_by_name("get_user")
    impact = store.impact(get_user.id)
    for row in impact["impacted"]:
        print(f"  depth {row['depth']}: {row['qualname']} ({row['lang']}) @ {row['location']}")

    print("\n== audit log is intact and tamper-evident ==")
    ok, broken = store.audit.verify()
    print(f"  verify() -> intact={ok} first_broken={broken}")
    print(f"  records: {len(list(store.audit))}")

    store.close()


if __name__ == "__main__":
    main()
