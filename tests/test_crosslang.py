"""Cross-language HTTP edge resolution in isolation."""
from pathlib import Path

from codegraph.crosslang import resolve
from codegraph.graph import Store
from codegraph.indexer import index_path

SAMPLE = Path(__file__).resolve().parent.parent / "examples" / "sample_repo"


def write(d: Path, rel: str, text: str):
    p = d / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def build(tmp_path):
    s = Store(":memory:")
    index_path(s, tmp_path)
    return s


def test_no_servers_no_edges(tmp_path):
    write(tmp_path, "client.ts",
          "export async function f() { return fetch('/api/x'); }\n")
    s = build(tmp_path)
    assert s.cross_language_edges() == []


def test_param_syntaxes_match_across_languages(tmp_path):
    # TS :id  vs  Python <id>  vs  Go {id}  -> all normalize equal
    write(tmp_path, "web/c.ts",
          "export async function load(id) { return fetch(`/api/u/${id}`); }\n")
    write(tmp_path, "api/s.py",
          "@app.route('/api/u/<id>')\ndef handler(id):\n    return id\n")
    write(tmp_path, "srv/m.go",
          'package main\nfunc reg(m *http.ServeMux) {\n'
          '  m.HandleFunc("/api/u/{id}", h)\n}\n'
          'func h(w http.ResponseWriter, r *http.Request) {}\n')
    s = build(tmp_path)
    reached = {e["to"]["lang"] for e in s.cross_language_edges()
               if e["from"]["symbol"] == "load"}
    assert {"python", "go"} <= reached


def test_method_specific_client_prefers_matching_server(tmp_path):
    write(tmp_path, "web/c.ts",
          "function save() { axios.post('/api/save', d); }\n")
    write(tmp_path, "api/s.py",
          "@app.route('/api/save', methods=['POST'])\n"
          "def do_save():\n    return 1\n")
    s = build(tmp_path)
    edges = s.cross_language_edges()
    assert any(e["from"]["symbol"] == "save" and e["to"]["symbol"] == "do_save"
               for e in edges)


def test_unmatched_route_creates_no_edge(tmp_path):
    write(tmp_path, "web/c.ts",
          "function f() { return fetch('/api/orphan-route'); }\n")
    write(tmp_path, "api/s.py",
          "@app.route('/api/different')\ndef other():\n    return 1\n")
    s = build(tmp_path)
    assert s.cross_language_edges() == []


def test_resolve_is_idempotent(tmp_path):
    s = build(SAMPLE)  # noqa: arg, just need a populated store
    s = Store(":memory:")
    index_path(s, SAMPLE)
    before = len(s.cross_language_edges())
    # rebuild_edges already ran during index; calling resolve again adds nothing
    again = resolve(s)
    assert again == 0
    assert len(s.cross_language_edges()) == before


def test_sample_repo_loaduser_fans_to_five_backends():
    s = Store(":memory:")
    index_path(s, SAMPLE)
    reached = {e["to"]["lang"] for e in s.cross_language_edges()
               if e["from"]["symbol"] == "loadUser"}
    assert {"python", "go", "rust", "java", "csharp"} <= reached


def test_edge_detail_describes_route_mapping(tmp_path):
    write(tmp_path, "web/c.ts",
          "function f() { return fetch('/api/z'); }\n")
    write(tmp_path, "api/s.py",
          "@app.route('/api/z')\ndef z():\n    return 1\n")
    s = build(tmp_path)
    edge = s.cross_language_edges()[0]
    assert "/api/z" in edge["detail"]
