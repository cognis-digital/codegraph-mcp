"""Scenario 1 - AI agent builders.

Before an AI coding agent edits a function, it should *look before it leaps*:
what is this symbol, who calls it, and what breaks if I change it? codegraph
serves exactly those answers over MCP. This demo plays the agent's side of that
conversation against the live graph.
"""
from _common import fresh_store, rule, find_one


def main() -> None:
    store = fresh_store()
    rule("AI AGENT WORKFLOW  -  look before you leap, over MCP")

    print("\nAgent task: \"Modify loadUser to add caching.\" First, understand it.\n")

    sym = find_one(store, "loadUser")
    print(f"1) search_symbols('loadUser') -> {sym.name}  [{sym.lang}]  {sym.path}:{sym.start_line}")

    callers = store.callers_of(sym.id)
    print(f"\n2) callers_of({sym.id}) -> {len(callers)} caller(s):")
    for c in callers:
        print(f"     - {c.name}  [{c.lang}]  {c.path}")

    callees = store.callees_of(sym.id)
    print(f"\n3) callees_of({sym.id}) -> {len(callees)} callee(s):")
    for c in callees:
        print(f"     - {c.name}  [{c.lang}]  {c.path}")

    blast = store.impact(sym.id)
    print(f"\n4) impact({sym.id}) -> blast radius of {blast['impacted_count']} symbol(s):")
    for row in blast["impacted"][:8]:
        print(f"     depth {row['depth']}: {row['name']}  [{row['lang']}]")

    print("\nThe agent now knows the contract it must preserve and the tests to run.")
    print("Every one of these reads was authorized and logged (see demo 4).")
    store.close()


if __name__ == "__main__":
    main()
