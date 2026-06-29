"""Run every demo scenario end to end.

    python demos/run_all.py

Each scenario is independent and rebuilds its own throwaway graph from the
polyglot sample repo, so they can be run in any order or on their own.
"""
import importlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SCENARIOS = [
    "01_ai_agent_workflow",
    "02_cross_language",
    "03_impact_and_refactor",
    "04_audit_and_compliance",
    "05_visualize_graph",
]


def main() -> None:
    for name in SCENARIOS:
        mod = importlib.import_module(name)
        mod.main()
    print("\n" + "=" * 70)
    print("  All demo scenarios completed.")
    print("=" * 70)


if __name__ == "__main__":
    main()
