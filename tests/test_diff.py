from pathlib import Path

from codegraph.diff import diff_paths


def write(d: Path, rel: str, text: str):
    p = d / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_diff_detects_add_remove_change(tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"

    write(a, "svc.py",
          "def kept(x):\n    return x\n"
          "def gone(y):\n    return y\n"
          "def changing(a):\n    return a\n")
    # b: 'gone' removed, 'added' new, 'changing' gains a parameter
    write(b, "svc.py",
          "def kept(x):\n    return x\n"
          "def added(z):\n    return z\n"
          "def changing(a, b):\n    return a + b\n")

    d = diff_paths(a, b)
    names = lambda rows: {r["symbol"] for r in rows}
    assert "added" in names(d["symbols"]["added"])
    assert "gone" in names(d["symbols"]["removed"])
    assert "changing" in names(d["symbols"]["signature_changed"])
    assert "kept" not in names(d["symbols"]["added"]) | names(d["symbols"]["removed"])
    assert d["summary"]["symbols_added"] == 1
    assert d["summary"]["symbols_removed"] == 1
    assert d["summary"]["signatures_changed"] == 1


def test_diff_tracks_cross_language_edge_changes(tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"

    # A: a TS client whose route has no server handler yet
    write(a, "client.ts",
          "export async function load(id) {\n"
          "  return fetch(`/api/items/${id}`);\n"
          "}\n")
    write(a, "noop.py", "def unrelated():\n    return 1\n")

    # B: same client, plus a Python handler for that route -> a new cross-lang edge
    write(b, "client.ts",
          "export async function load(id) {\n"
          "  return fetch(`/api/items/${id}`);\n"
          "}\n")
    write(b, "api.py",
          "@app.route('/api/items/<id>')\n"
          "def get_item(id):\n"
          "    return id\n")

    d = diff_paths(a, b)
    assert d["summary"]["cross_language_edges_added"] >= 1
    assert any("load" in e["from"] and "get_item" in e["to"]
               for e in d["cross_language_edges"]["added"])


def test_diff_identical_is_empty(tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    for d in (a, b):
        write(d, "x.py", "def f():\n    return g()\n\ndef g():\n    return 1\n")
    result = diff_paths(a, b)
    s = result["summary"]
    assert all(v == 0 for v in s.values())
