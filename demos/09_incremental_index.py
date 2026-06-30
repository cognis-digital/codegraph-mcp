"""Scenario 9 - CI / pre-commit integrations.

On a large repo you don't want to re-parse the world on every commit. codegraph
indexes incrementally: only files changed between two git refs are re-parsed,
yet the global call/cross-language graph stays correct because edges are
recomputed from the tables afterward. This demo builds a tiny git repo, makes a
commit, and re-indexes just the delta.
"""
import os
import subprocess
import tempfile

from _common import rule
from codegraph.graph import Store
from codegraph.indexer import changed_files, index_incremental, index_path


def git(repo, *args):
    subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True, text=True)


def write(repo, rel, text):
    with open(os.path.join(repo, rel), "w", encoding="utf-8") as f:
        f.write(text)


def main() -> None:
    rule("INCREMENTAL INDEX  -  re-parse only what a commit touched")
    repo = tempfile.mkdtemp(prefix="cg_inc_")
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "demo@demo")
    git(repo, "config", "user.name", "demo")
    write(repo, "a.py", "def f():\n    return g()\n\ndef g():\n    return 1\n")
    write(repo, "b.py", "def h():\n    return 2\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "c1")
    base = subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()

    store = Store(":memory:")
    index_path(store, repo)
    print(f"\nFull index: {store.stats()['symbols']} symbols (f, g, h)")

    # commit a change: add new() calling f, delete b.py
    write(repo, "a.py",
          "def f():\n    return g()\n\ndef g():\n    return 1\n\ndef new():\n    return f()\n")
    os.remove(os.path.join(repo, "b.py"))
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "c2")

    am, deleted = changed_files(repo, base, "HEAD")
    print(f"\nchanged since {base[:7]}: modified/added={am}  deleted={deleted}")

    stats = index_incremental(store, repo, base, "HEAD")
    print(f"\nIncremental re-index parsed {stats.files} file(s) (only a.py).")
    print(f"   'h' (from deleted b.py) gone: {store.symbols_by_name('h') == []}")
    new = store.symbols_by_name("new")
    reaches_f = bool(new) and any(c.name == "f" for c in store.callees_of(new[0].id))
    print(f"   new edge new -> f resolved by global rebuild: {reaches_f}")
    print("\nTouch one file, keep a correct whole-repo graph.")
    store.close()


if __name__ == "__main__":
    main()
