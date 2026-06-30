"""More diff scenarios: endpoint moves, removed cross-language edges, renames,
multi-file, and error handling."""
from pathlib import Path

import pytest

from codegraph.diff import diff_git, diff_paths, diff_stores
from codegraph.graph import Store
from codegraph.indexer import index_path


def write(d: Path, rel: str, text: str):
    p = d / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def store_of(path):
    s = Store(":memory:")
    index_path(s, path)
    return s


def test_diff_stores_directly(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    write(a, "x.py", "def f():\n    return 1\n")
    write(b, "x.py", "def f():\n    return 1\ndef g():\n    return 2\n")
    old, new = store_of(a), store_of(b)
    d = diff_stores(old, new)
    assert d["summary"]["symbols_added"] == 1
    assert {r["symbol"] for r in d["symbols"]["added"]} == {"g"}


def test_endpoint_added_detected(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    write(a, "s.py", "def f():\n    return 1\n")
    write(b, "s.py", "@app.route('/new')\ndef f():\n    return 1\n")
    d = diff_paths(a, b)
    assert d["summary"]["endpoints_added"] >= 1
    assert any(e["route"] == "/new" for e in d["endpoints"]["added"])


def test_endpoint_removed_detected(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    write(a, "s.py", "@app.route('/gone')\ndef f():\n    return 1\n")
    write(b, "s.py", "def f():\n    return 1\n")
    d = diff_paths(a, b)
    assert any(e["route"] == "/gone" for e in d["endpoints"]["removed"])


def test_cross_language_edge_removed(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    # A has both client and server (edge exists); B drops the server
    write(a, "web/c.ts", "function load() { return fetch('/api/items'); }\n")
    write(a, "api/s.py", "@app.route('/api/items')\ndef get_items():\n    return 1\n")
    write(b, "web/c.ts", "function load() { return fetch('/api/items'); }\n")
    write(b, "api/s.py", "def unrelated():\n    return 1\n")
    d = diff_paths(a, b)
    assert d["summary"]["cross_language_edges_removed"] >= 1


def test_signature_change_records_both_sides(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    write(a, "x.py", "def f(a):\n    return a\n")
    write(b, "x.py", "def f(a, b):\n    return a\n")
    d = diff_paths(a, b)
    chg = d["symbols"]["signature_changed"][0]
    assert "a)" in chg["old_signature"]
    assert "b)" in chg["new_signature"]


def test_diff_added_and_removed_sorted(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    write(a, "x.py", "def keep():\n    return 1\n")
    write(b, "x.py",
          "def keep():\n    return 1\ndef zeta():\n    return 1\ndef alpha():\n    return 1\n")
    d = diff_paths(a, b)
    syms = [r["symbol"] for r in d["symbols"]["added"]]
    assert syms == sorted(syms)


def test_diff_git_requires_both_refs(tmp_path):
    with pytest.raises(ValueError):
        diff_git(tmp_path, "", "HEAD")


def test_diff_git_bad_repo_raises_runtimeerror(tmp_path):
    with pytest.raises(RuntimeError):
        diff_git(tmp_path, "HEAD~1", "HEAD")
