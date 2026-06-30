"""Scenario 17 - a dead-code report for a cleanup sprint.

Orphans are functions/methods with no callers that aren't HTTP entrypoints -
dead-code candidates. Cross-language edges count as callers, so a handler
reached only from another language is correctly NOT flagged. This produces a
ranked cleanup list with a one-line rationale per finding.
"""
from _common import fresh_store, rule


def main() -> None:
    store = fresh_store()
    rule("DEAD-CODE REPORT  -  safe-to-delete candidates, cross-language aware")

    orphans = store.orphans()
    print(f"\n{len(orphans)} dead-code candidate(s):\n")
    for o in orphans:
        print(f"   {o['lang']:>10}  {o['qualname']:<16} {o['path']}:{o['start_line']}")
        print(f"               -> no callers, not an HTTP route handler")

    # contrast: show a symbol that LOOKS unused locally but is reached cross-language
    handler = next((s for s in store.symbols_by_name("get_user") if s.lang == "python"), None)
    if handler:
        xcallers = [c for c in store.callers_of(handler.id) if c.lang != handler.lang]
        print(f"\nNOT flagged: '{handler.qualname()}' [python] - it has no local caller, "
              f"but {len(xcallers)} cross-language caller(s) reach it over HTTP:")
        for c in xcallers:
            print(f"   <- {c.name} [{c.lang}]")
    print("\nDelete the orphans; keep the handlers that only look unused.")
    store.close()


if __name__ == "__main__":
    main()
