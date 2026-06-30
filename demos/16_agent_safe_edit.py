"""Scenario 16 - an agent's full pre-edit safety check, end to end.

A realistic agent loop before it touches code: locate the symbol, read its
signature (the contract), enumerate direct callers and callees, compute the
blast radius, and emit a structured "edit plan" - the tests to run and the
contracts to preserve. This is demo 1 taken all the way to a decision.
"""
import json

from _common import fresh_store, find_one, rule


def main() -> None:
    store = fresh_store()
    rule("AGENT SAFE EDIT  -  from question to a structured edit plan")

    task = "Add input validation to the Python user handler."
    print(f"\nTask: {task!r}\n")

    sym = next(s for s in store.symbols_by_name("get_user") if s.lang == "python")
    callers = store.callers_of(sym.id)
    callees = store.callees_of(sym.id)
    blast = store.impact(sym.id)

    plan = {
        "target": sym.as_dict()["location"],
        "contract_to_preserve": sym.signature,
        "direct_callers": [f"{c.name} [{c.lang}]" for c in callers],
        "calls_into": [f"{c.name} [{c.lang}]" for c in callees],
        "blast_radius": blast["impacted_count"],
        "cross_language_dependents": sorted(
            {r["lang"] for r in blast["impacted"] if r["lang"] != sym.lang}),
        "recommended_tests": [f"contract test for {c.name}"
                              for c in callers] or ["smoke test the handler"],
    }
    print("Structured edit plan the agent can act on:")
    print(json.dumps(plan, indent=2))
    print("\nThe agent now knows exactly what it must not break.")
    store.close()


if __name__ == "__main__":
    main()
