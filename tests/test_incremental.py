import subprocess

import pytest

from codegraph.graph import Store
from codegraph.indexer import changed_files, index_incremental, index_path


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   capture_output=True, text=True)


def head(repo):
    return subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "r"
    r.mkdir()
    git(r, "init", "-q")
    git(r, "config", "user.email", "t@t")
    git(r, "config", "user.name", "t")
    (r / "a.py").write_text("def f():\n    return g()\n\ndef g():\n    return 1\n")
    (r / "b.py").write_text("def h():\n    return 2\n")
    git(r, "add", "-A")
    git(r, "commit", "-q", "-m", "c1")
    return r


def test_changed_files_classifies(repo):
    base = head(repo)
    (repo / "a.py").write_text("def f():\n    return 99\n")   # modified
    (repo / "b.py").unlink()                                   # deleted
    (repo / "c.py").write_text("def k():\n    return 3\n")     # added
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "c2")
    am, deleted = changed_files(repo, base, "HEAD")
    assert set(am) == {"a.py", "c.py"}
    assert deleted == ["b.py"]


def test_incremental_reparses_only_changed_and_keeps_graph_correct(repo):
    base = head(repo)
    store = Store(":memory:")
    index_path(store, repo)
    assert store.stats()["symbols"] == 3   # f, g, h

    # add a function that calls f; delete b.py
    (repo / "a.py").write_text(
        "def f():\n    return g()\n\ndef g():\n    return 1\n\ndef new():\n    return f()\n")
    (repo / "b.py").unlink()
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "c2")

    stats = index_incremental(store, repo, base, "HEAD")
    assert stats.files == 1                # only a.py was re-parsed

    assert store.symbols_by_name("h") == []          # deleted file's symbol gone
    new = store.symbols_by_name("new")
    assert new                                        # added symbol present
    # the call edge new -> f was resolved by the global edge rebuild
    assert any(c.name == "f" for c in store.callees_of(new[0].id))


def test_incremental_matches_full_reindex(repo):
    base = head(repo)
    store = Store(":memory:")
    index_path(store, repo)

    (repo / "a.py").write_text("def f():\n    return 1\n")   # g removed, f changed
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "c2")
    index_incremental(store, repo, base, "HEAD")

    # a fresh full index of the same tree should agree
    fresh = Store(":memory:")
    index_path(fresh, repo)
    assert store.stats()["symbols"] == fresh.stats()["symbols"]
    assert store.stats()["edges"] == fresh.stats()["edges"]
