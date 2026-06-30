"""Scenario 15 - the headline metric, reproducibly.

The "Navigation Paradox": a front-end caller and the back-end handler it depends
on share no symbol name, so a name-grep finds the dependency 0% of the time -
while codegraph's cross-language graph finds it 100%. This runs the bundled
benchmark on a small generated repo and prints the recall comparison.
"""
from _common import rule
from bench.benchmark import run


def main() -> None:
    rule("BENCHMARK RECALL  -  the dependency grep can't find, the graph always can")
    n = 10
    print(f"\nGenerating {n} micro-services ({n * 4} files, 4 languages) and indexing...")
    r = run(n)

    print(f"\nthroughput: {r['files']} files, {r['symbols']} symbols, "
          f"{r['cross_language_edges']} cross-language edges in {r['index_seconds']}s "
          f"({r['files_per_sec']} files/s)")
    print("\ncross-language dependency recall")
    print("  (find the front-end caller that breaks if a back-end handler changes)")
    print(f"   codegraph (graph impact):  {r['recall']['codegraph']}")
    print(f"   grep by symbol name:       {r['recall']['grep_by_name']}")
    print(f"   grep by route substring:   {r['recall']['grep_by_route']}")
    print("\nStructure beats search for the dependency that crosses a language boundary.")


if __name__ == "__main__":
    main()
