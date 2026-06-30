"""Knowledge-graph diff between two snapshots of a codebase.

Comparing two graphs answers a question a line diff can't: not "what text
changed" but "what changed in the *shape* of the code" — which symbols appeared
or vanished, whose signature changed, which HTTP endpoints moved, and — the part
no one else does — which **cross-language** dependencies were added or broken.

The core (`diff_stores`) works on two already-indexed graphs, so it is trivial
to unit-test. `diff_paths` indexes two directories; `diff_git` materializes two
git refs into throwaway worktrees and diffs them.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from .graph import Store
from .indexer import index_path


def _snapshot(store: Store):
    symbols: dict[tuple, dict] = {}
    for path, name, container, sig, kind, lang in store.conn.execute(
        "SELECT f.path, s.name, s.container, s.signature, s.kind, s.lang "
        "FROM symbols s JOIN files f ON f.id = s.file_id"
    ):
        qual = f"{container}.{name}" if container else name
        symbols[(path, qual)] = {"signature": sig, "kind": kind, "lang": lang}

    endpoints = {
        (e["role"], e["method"], e["route"], e["symbol"], e["lang"])
        for e in store.endpoints()
    }
    xlang = {
        (e["from"]["symbol"], e["from"]["lang"], e["to"]["symbol"], e["to"]["lang"])
        for e in store.cross_language_edges()
    }
    return symbols, endpoints, xlang


def _sym_entry(key: tuple, meta: dict) -> dict:
    path, qual = key
    return {"path": path, "symbol": qual, "kind": meta["kind"], "lang": meta["lang"]}


def diff_stores(old: Store, new: Store) -> dict:
    """Diff two indexed graphs. Returns added/removed/changed symbols, endpoint
    changes, and cross-language edge changes, plus a summary."""
    so, eo, xo = _snapshot(old)
    sn, en, xn = _snapshot(new)

    added = [_sym_entry(k, sn[k]) for k in sn.keys() - so.keys()]
    removed = [_sym_entry(k, so[k]) for k in so.keys() - sn.keys()]
    changed = [
        {**_sym_entry(k, sn[k]), "old_signature": so[k]["signature"],
         "new_signature": sn[k]["signature"]}
        for k in so.keys() & sn.keys()
        if so[k]["signature"] != sn[k]["signature"]
    ]

    def _ep(t):
        return {"role": t[0], "method": t[1], "route": t[2], "symbol": t[3], "lang": t[4]}

    def _xl(t):
        return {"from": f"{t[0]} ({t[1]})", "to": f"{t[2]} ({t[3]})"}

    sort = lambda rows, *keys: sorted(rows, key=lambda r: tuple(r[k] for k in keys))

    return {
        "symbols": {
            "added": sort(added, "path", "symbol"),
            "removed": sort(removed, "path", "symbol"),
            "signature_changed": sort(changed, "path", "symbol"),
        },
        "endpoints": {
            "added": [_ep(t) for t in sorted(en - eo)],
            "removed": [_ep(t) for t in sorted(eo - en)],
        },
        "cross_language_edges": {
            "added": [_xl(t) for t in sorted(xn - xo)],
            "removed": [_xl(t) for t in sorted(xo - xn)],
        },
        "summary": {
            "symbols_added": len(added),
            "symbols_removed": len(removed),
            "signatures_changed": len(changed),
            "endpoints_added": len(en - eo),
            "endpoints_removed": len(eo - en),
            "cross_language_edges_added": len(xn - xo),
            "cross_language_edges_removed": len(xo - xn),
        },
    }


def diff_paths(path_a: str | Path, path_b: str | Path) -> dict:
    old = Store(":memory:")
    index_path(old, path_a)
    new = Store(":memory:")
    index_path(new, path_b)
    try:
        return diff_stores(old, new)
    finally:
        old.close()
        new.close()


def diff_git(repo: str | Path, ref_a: str, ref_b: str) -> dict:
    """Diff two git refs by materializing each into a throwaway worktree."""
    repo = str(repo)
    if not ref_a or not ref_b:
        raise ValueError("diff_git: both ref_a and ref_b are required")
    with tempfile.TemporaryDirectory(prefix="cg-a-") as ta, \
            tempfile.TemporaryDirectory(prefix="cg-b-") as tb:
        worktrees = [(ref_a, ta), (ref_b, tb)]
        try:
            for ref, tmp in worktrees:
                try:
                    subprocess.run(["git", "-C", repo, "worktree", "add", "--detach", tmp, ref],
                                   check=True, capture_output=True, text=True)
                except FileNotFoundError as e:
                    raise RuntimeError("diff_git: git executable not found on PATH") from e
                except subprocess.CalledProcessError as e:
                    detail = (e.stderr or e.stdout or "").strip()
                    raise RuntimeError(
                        f"diff_git: could not check out ref {ref!r}: {detail}") from e
            return diff_paths(ta, tb)
        finally:
            for _ref, tmp in worktrees:
                subprocess.run(["git", "-C", repo, "worktree", "remove", "--force", tmp],
                               capture_output=True, text=True)
