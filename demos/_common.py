"""Shared helpers for the demo scenarios."""
from __future__ import annotations

import os
import sys
import tempfile

# allow `python demos/xx.py` from anywhere
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from codegraph.graph import Store          # noqa: E402
from codegraph.indexer import index_path   # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE = os.path.join(REPO_ROOT, "examples", "sample_repo")


def fresh_store(sample: str = SAMPLE) -> Store:
    """Index the polyglot sample repo into a throwaway db and return the store."""
    db = os.path.join(tempfile.mkdtemp(prefix="codegraph_demo_"), "graph.db")
    store = Store(db)
    index_path(store, sample)
    return store


def rule(title: str) -> None:
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def find_one(store: Store, name: str):
    hits = store.search_symbols(name, None, 1)
    return hits[0] if hits else None
