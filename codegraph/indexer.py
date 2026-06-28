"""Indexer: walk a source tree, extract, and build the resolved graph.

Pipeline per file:
  1. pick an extractor by suffix; skip files we don't understand
  2. record the file (with a content SHA so re-indexing is idempotent)
  3. insert symbols, refs, and endpoints
  4. after all files are in, resolve intra-repo call edges (by name) and
     cross-language HTTP edges

"Overlay, not migration": `index_path` accepts any directory — a working
checkout, an exported tarball, or a freshly cloned remote — and never moves or
mutates the source. `index_git` clones a remote read-only into a temp dir.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Iterable, Optional

from . import crosslang
from .extractors import extractor_for, language_for
from .graph import Store

DEFAULT_IGNORES = {
    ".git", "node_modules", "vendor", "dist", "build", "__pycache__",
    ".venv", "venv", ".mypy_cache", ".pytest_cache", "target",
}


def _sha(text: str) -> str:
    return hashlib.blake2b(text.encode("utf-8", "replace"), digest_size=16).hexdigest()


def iter_source_files(root: Path, ignores: Optional[set[str]] = None) -> Iterable[Path]:
    ignores = ignores or DEFAULT_IGNORES
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in ignores]
        for fn in filenames:
            p = Path(dirpath) / fn
            if language_for(p):
                yield p


class IndexStats:
    def __init__(self) -> None:
        self.files = 0
        self.symbols = 0
        self.endpoints = 0
        self.skipped = 0
        self.cross_edges = 0

    def as_dict(self) -> dict:
        return {
            "files": self.files,
            "symbols": self.symbols,
            "endpoints": self.endpoints,
            "skipped": self.skipped,
            "cross_language_edges": self.cross_edges,
        }


def index_path(store: Store, root: str | Path, actor: str = "indexer") -> IndexStats:
    """Index a directory tree into `store`. Idempotent per file (by content SHA)."""
    root = Path(root).resolve()
    stats = IndexStats()
    if not root.exists():
        raise FileNotFoundError(root)

    # qualname -> symbol_id, populated as we insert, used to resolve edges
    sym_index: dict[str, list[int]] = {}
    pending_calls: list[tuple[int, list[str]]] = []
    pending_endpoints: list[tuple[str, object]] = []  # (qualname, RawEndpoint)

    for path in iter_source_files(root):
        lang = language_for(path)
        ext = extractor_for(lang) if lang else None
        if not ext:
            stats.skipped += 1
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            stats.skipped += 1
            continue

        rel = str(path.relative_to(root)).replace(os.sep, "/")
        sha = _sha(text)
        existing = store.get_meta(f"file_sha:{rel}")
        if existing == sha:
            continue  # unchanged since last index
        store.reset_file(rel)

        result = ext.extract(text)
        file_id = store.add_file(rel, lang, sha, time.time())
        store.set_meta(f"file_sha:{rel}", sha)
        stats.files += 1

        local_syms: dict[str, int] = {}
        for sym in result.symbols:
            sid = store.add_symbol(
                file_id, sym.name, sym.kind, lang, sym.start_line, sym.end_line,
                container=sym.container, signature=sym.signature,
            )
            stats.symbols += 1
            qual = f"{sym.container}.{sym.name}" if sym.container else sym.name
            local_syms[qual] = sid
            local_syms.setdefault(sym.name, sid)
            sym_index.setdefault(qual, []).append(sid)
            sym_index.setdefault(sym.name, []).append(sid)
            if sym.calls:
                pending_calls.append((sid, sym.calls))

        for ref in result.refs:
            in_sym = local_syms.get(ref.in_symbol) if ref.in_symbol else None
            store.add_ref(file_id, ref.name, ref.line, in_sym)

        for ep in result.endpoints:
            pending_endpoints.append((ep.in_symbol, ep))
            sid = local_syms.get(ep.in_symbol) if ep.in_symbol else None
            if sid is not None:
                store.add_endpoint(sid, ep.role, ep.method, ep.route)
                stats.endpoints += 1

    store.commit()

    # resolve intra-repo call edges by name (best-effort; ambiguous names link
    # to all candidates, which is the conservative choice for impact analysis)
    for src_id, calls in pending_calls:
        for name in calls:
            for dst_id in sym_index.get(name, []):
                if dst_id != src_id:
                    store.add_edge(src_id, dst_id, "calls")
    store.commit()

    stats.cross_edges = crosslang.resolve(store)

    store.audit.append(
        actor=actor,
        action="index",
        target=str(root),
        detail=stats.as_dict(),
    )
    return stats


def index_git(store: Store, url: str, ref: Optional[str] = None, actor: str = "indexer") -> IndexStats:
    """Shallow-clone a remote read-only and index it. Source is never retained."""
    with tempfile.TemporaryDirectory(prefix="codegraph-clone-") as tmp:
        cmd = ["git", "clone", "--depth", "1"]
        if ref:
            cmd += ["--branch", ref]
        cmd += [url, tmp]
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        store.set_meta("source_url", url)
        return index_path(store, tmp, actor=actor)
