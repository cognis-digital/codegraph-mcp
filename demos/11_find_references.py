"""Scenario 11 - rename / refactor safety.

Before renaming a symbol, find every place its name is referenced. Unlike a
text grep, these references are attributed to the *enclosing symbol*, so you get
"who uses this, and from inside what function" - the worklist for a safe rename.
"""
from _common import fresh_store, rule


def main() -> None:
    store = fresh_store()
    rule("FIND REFERENCES  -  the worklist for a safe rename")

    for name in ("lookup", "normalize"):
        refs = store.find_references(name)
        print(f"\n'{name}' is referenced {len(refs)} time(s):")
        for r in refs:
            enclosing = store.get_symbol(r["in_symbol"]) if r["in_symbol"] else None
            where = f"inside {enclosing.qualname()}" if enclosing else "(top level)"
            print(f"   {r['path']}:{r['line']:<4} {where}")

    print("\nEach reference is tied to the function that makes it - rename with confidence.")
    store.close()


if __name__ == "__main__":
    main()
