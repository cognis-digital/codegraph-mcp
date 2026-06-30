"""Error paths and edge cases for the indexer: missing/invalid roots, unknown
file types, unreadable files, ignore rules, idempotency, and git-failure
messages."""
from pathlib import Path

import pytest

from codegraph.graph import Store
from codegraph.indexer import (
    DEFAULT_IGNORES,
    changed_files,
    index_git,
    index_path,
    iter_source_files,
)


def write(d: Path, rel: str, text: str):
    p = d / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def test_index_missing_path_raises_filenotfound(tmp_path):
    with pytest.raises(FileNotFoundError) as e:
        index_path(Store(":memory:"), tmp_path / "nope")
    assert "no such directory" in str(e.value)


def test_index_a_file_not_dir_raises(tmp_path):
    f = write(tmp_path, "x.py", "def f():\n    return 1\n")
    with pytest.raises(NotADirectoryError):
        index_path(Store(":memory:"), f)


def test_unknown_extensions_skipped(tmp_path):
    write(tmp_path, "readme.md", "# hi")
    write(tmp_path, "data.json", "{}")
    write(tmp_path, "real.py", "def f():\n    return 1\n")
    s = Store(":memory:")
    stats = index_path(s, tmp_path)
    assert stats.files == 1            # only the .py was understood
    assert stats.skipped == 0          # non-source files aren't even iterated


def test_empty_dir_indexes_to_empty_graph(tmp_path):
    s = Store(":memory:")
    stats = index_path(s, tmp_path)
    assert stats.files == 0 and stats.symbols == 0
    assert s.stats()["edges"] == 0


def test_ignored_directories_pruned(tmp_path):
    write(tmp_path, "node_modules/dep.js", "function leak() {}\n")
    write(tmp_path, ".git/hook.py", "def secret():\n    return 1\n")
    write(tmp_path, "src/app.py", "def app():\n    return 1\n")
    files = [str(p) for p in iter_source_files(tmp_path)]
    assert any("app.py" in f for f in files)
    assert not any("node_modules" in f for f in files)
    assert not any(".git" in f for f in files)


def test_custom_ignores_override(tmp_path):
    write(tmp_path, "keep/keep.py", "def k():\n    return 1\n")
    write(tmp_path, "skip/skip.py", "def s():\n    return 1\n")
    files = [str(p) for p in iter_source_files(tmp_path, ignores={"skip"})]
    assert any("keep.py" in f for f in files)
    assert not any("skip.py" in f for f in files)


def test_default_ignores_membership():
    assert {"node_modules", ".git", "__pycache__", "target", "dist"} <= DEFAULT_IGNORES


def test_syntactically_broken_python_is_recorded_but_empty(tmp_path):
    # the Python extractor returns no symbols on a SyntaxError, but the file is
    # still recorded as indexed (so it isn't reprocessed every run)
    write(tmp_path, "broken.py", "def f(:\n  pass\n")
    s = Store(":memory:")
    stats = index_path(s, tmp_path)
    assert stats.files == 1
    assert s.symbols_by_name("f") == []


def test_reindex_after_edit_reparses_one_file(tmp_path):
    write(tmp_path, "a.py", "def f():\n    return 1\n")
    s = Store(":memory:")
    first = index_path(s, tmp_path)
    assert first.files == 1
    # unchanged -> skipped on second pass
    assert index_path(s, tmp_path).files == 0
    # edit the file -> reparsed
    write(tmp_path, "a.py", "def f():\n    return 2\n\ndef g():\n    return 3\n")
    third = index_path(s, tmp_path)
    assert third.files == 1
    assert {x.name for x in s.symbols_by_name("g")}  # new symbol present


def test_nested_directories_indexed(tmp_path):
    write(tmp_path, "a/b/c/deep.py", "def deep():\n    return 1\n")
    s = Store(":memory:")
    index_path(s, tmp_path)
    syms = s.symbols_by_name("deep")
    assert syms and syms[0].path == "a/b/c/deep.py"


def test_actor_recorded_in_audit(tmp_path):
    write(tmp_path, "a.py", "def f():\n    return 1\n")
    s = Store(":memory:")
    index_path(s, tmp_path, actor="ci-bot")
    rec = s.audit.tail(1)[0]
    assert rec.actor == "ci-bot" and rec.action == "index"


def test_changed_files_on_non_git_dir_raises_runtimeerror(tmp_path):
    # a directory that is not a git repo -> our wrapper surfaces a clear message
    with pytest.raises(RuntimeError) as e:
        changed_files(tmp_path, "HEAD~1", "HEAD")
    assert "git failed" in str(e.value) or "not found" in str(e.value)


def test_index_git_bad_url_raises_runtimeerror(tmp_path):
    bad = str(tmp_path / "definitely-not-a-repo")
    with pytest.raises(RuntimeError):
        index_git(Store(":memory:"), bad)
