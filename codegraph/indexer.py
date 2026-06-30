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


def _ingest_file(store: Store, root: Path, path: Path, stats: IndexStats) -> None:
    """Parse one file and write its symbols, refs, and endpoints (no edges).

    Idempotent: a file whose content SHA is unchanged since last index is
    skipped. Edge resolution is global and happens once, in `rebuild_edges`.
    """
    lang = language_for(path)
    ext = extractor_for(lang) if lang else None
    if not ext:
        stats.skipped += 1
        return
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        stats.skipped += 1
        return

    rel = str(path.relative_to(root)).replace(os.sep, "/")
    sha = _sha(text)
    if store.get_meta(f"file_sha:{rel}") == sha:
        return  # unchanged since last index
    store.reset_file(rel, commit=False)

    result = ext.extract(text)
    file_id = store.add_file(rel, lang, sha, time.time())
    store.set_meta(f"file_sha:{rel}", sha, commit=False)
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

    for ref in result.refs:
        in_sym = local_syms.get(ref.in_symbol) if ref.in_symbol else None
        store.add_ref(file_id, ref.name, ref.line, in_sym)

    for ep in result.endpoints:
        sid = local_syms.get(ep.in_symbol) if ep.in_symbol else None
        if sid is not None:
            store.add_endpoint(sid, ep.role, ep.method, ep.route)
            stats.endpoints += 1


def rebuild_edges(store: Store) -> int:
    """Recompute all edges from the symbols/refs tables. Returns cross-lang count.

    Call edges are derived from references: a reference recorded inside symbol
    S to a name N becomes an edge S -> every symbol named N. Doing this from the
    tables (rather than in-memory during parse) is what lets incremental
    indexing touch only changed files yet keep the global call graph correct.
    """
    store.conn.execute("DELETE FROM edges")

    name_ids: dict[str, list[int]] = {}
    for sid, name in store.conn.execute("SELECT id, name FROM symbols"):
        name_ids.setdefault(name, []).append(sid)

    for src_id, name in store.conn.execute(
        "SELECT in_symbol, name FROM refs WHERE in_symbol IS NOT NULL"
    ):
        for dst_id in name_ids.get(name, []):
            if dst_id != src_id:
                store.add_edge(src_id, dst_id, "calls")
    store.commit()
    return crosslang.resolve(store)


def index_path(store: Store, root: str | Path, actor: str = "indexer") -> IndexStats:
    """Index a directory tree into `store`. Idempotent per file (by content SHA)."""
    root = Path(root).resolve()
    stats = IndexStats()
    if not root.exists():
        raise FileNotFoundError(f"index_path: no such directory: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"index_path: not a directory: {root}")

    for path in iter_source_files(root):
        _ingest_file(store, root, path, stats)
    store.commit()

    stats.cross_edges = rebuild_edges(store)
    store.audit.append(actor=actor, action="index", target=str(root),
                       detail=stats.as_dict())
    return stats


def _run_git(args: list[str], *, what: str) -> str:
    """Run a git command, raising a clear RuntimeError if git fails or is absent."""
    try:
        proc = subprocess.run(args, check=True, capture_output=True, text=True)
    except FileNotFoundError as e:  # git not installed / not on PATH
        raise RuntimeError(f"{what}: git executable not found on PATH") from e
    except subprocess.CalledProcessError as e:
        detail = (e.stderr or e.stdout or "").strip()
        raise RuntimeError(f"{what}: git failed (exit {e.returncode}): {detail}") from e
    return proc.stdout


def changed_files(repo: str | Path, base: str, head: str = "HEAD") -> tuple[list[str], list[str]]:
    """Return (added_or_modified, deleted) paths between two git refs."""
    out = _run_git(
        ["git", "-C", str(repo), "diff", "--name-status", f"{base}..{head}"],
        what="index_incremental",
    )
    am: list[str] = []
    deleted: list[str] = []
    for line in out.splitlines():
        parts = line.split("\t")
        status = parts[0]
        if status.startswith("D"):
            deleted.append(parts[-1])
        elif status.startswith("R"):  # rename: old path gone, new path added
            deleted.append(parts[1])
            am.append(parts[2])
        else:  # A, M, C, T ...
            am.append(parts[-1])
    return am, deleted


def index_incremental(store: Store, root: str | Path, base: str, head: str = "HEAD",
                      actor: str = "indexer") -> IndexStats:
    """Re-index only the files changed between two git refs, then rebuild edges.

    Added/modified files are re-parsed from the working tree; deleted files are
    dropped from the graph. Parsing is skipped for everything unchanged — the
    whole point — while the call/cross-language graph stays correct because
    edges are recomputed globally from the tables afterward.
    """
    root = Path(root).resolve()
    stats = IndexStats()
    am, deleted = changed_files(root, base, head)

    for rel in deleted:
        store.reset_file(rel.replace(os.sep, "/"), commit=False)
        store.conn.execute("DELETE FROM meta WHERE key=?", (f"file_sha:{rel}",))

    for rel in am:
        path = root / rel
        if not path.exists():  # modified-then-deleted in the working tree
            store.reset_file(rel.replace(os.sep, "/"), commit=False)
            continue
        _ingest_file(store, root, path, stats)
    store.commit()

    stats.cross_edges = rebuild_edges(store)
    store.audit.append(actor=actor, action="index_incremental",
                       target=f"{base}..{head}",
                       detail={**stats.as_dict(), "deleted": len(deleted)})
    return stats


def index_git(store: Store, url: str, ref: Optional[str] = None, actor: str = "indexer") -> IndexStats:
    """Shallow-clone a remote read-only and index it. Source is never retained."""
    with tempfile.TemporaryDirectory(prefix="codegraph-clone-") as tmp:
        cmd = ["git", "clone", "--depth", "1"]
        if ref:
            cmd += ["--branch", ref]
        cmd += [url, tmp]
        _run_git(cmd, what=f"index_git({url})")
        store.set_meta("source_url", url)
        return index_path(store, tmp, actor=actor)
