"""Scenario 13 - a Mermaid blast-radius diagram for a PR description.

Pick the busiest symbol, compute its blast radius, and render it as a Mermaid
diagram you can paste straight into a pull-request description so reviewers see -
at a glance, across languages - everything that depends on the thing you touched.
"""
from _common import fresh_store, rule
from codegraph.viz import mermaid_impact


def main() -> None:
    store = fresh_store()
    rule("IMPACT VISUAL  -  a paste-ready Mermaid blast-radius diagram")

    hot = store.hotspots(1)
    if not hot:
        print("\n(no hotspots in this graph)")
        store.close()
        return
    target = hot[0]
    blast = store.impact(target["id"])
    print(f"\nMost depended-on symbol: '{target['name']}' [{target['lang']}] "
          f"with {target['callers']} direct caller(s).")
    print(f"Blast radius: {blast['impacted_count']} symbol(s) across "
          f"{len({r['lang'] for r in blast['impacted']})} language(s).\n")

    print("```mermaid")
    print(mermaid_impact(store, target["id"]))
    print("```")
    print("\nReviewers see the cross-language fallout before approving.")
    store.close()


if __name__ == "__main__":
    main()
