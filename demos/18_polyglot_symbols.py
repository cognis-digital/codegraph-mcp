"""Scenario 18 - one query, six languages.

codegraph normalizes Python (AST), JS/TS/Go/Rust/Java/C# (brace-scan) into a
single symbol model: name, kind, container, signature, span. This demo searches
the same concept ('User') across the whole polyglot repo and shows the unified
records the graph returns regardless of source language.
"""
from collections import Counter

from _common import fresh_store, rule


def main() -> None:
    store = fresh_store()
    rule("POLYGLOT SYMBOLS  -  one symbol model across six languages")

    stats = store.stats()
    print("\nIndexed languages: " + ", ".join(
        f"{lang}({n})" for lang, n in sorted(stats["languages"].items())))

    print("\nSymbols matching 'User' across the repo:")
    for sym in store.search_symbols("User", limit=20):
        container = f"{sym.container}." if sym.container else ""
        print(f"   {sym.lang:>10}  {sym.kind:<8} {container}{sym.name:<14} "
              f"{sym.path}:{sym.start_line}")

    kinds = Counter(s.kind for s in store.search_symbols("", limit=1000))
    print(f"\nSymbol-kind breakdown (whole repo): "
          + ", ".join(f"{k}={v}" for k, v in sorted(kinds.items())))
    print("Same query, same record shape - the language boundary disappears.")
    store.close()


if __name__ == "__main__":
    main()
