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
    "06_mcp_protocol",
    "07_scoped_tokens",
    "08_graph_diff",
    "09_incremental_index",
    "10_http_transport",
    "11_find_references",
    "12_audit_export",
    "13_impact_visual",
    "14_endpoint_inventory",
    "15_benchmark_recall",
    "16_agent_safe_edit",
    "17_dead_code_report",
    "18_polyglot_symbols",
    "19_tamper_forensics",
    "20_module_architecture",
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
