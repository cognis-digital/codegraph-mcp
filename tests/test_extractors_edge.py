"""Deeper extractor edge cases across all six languages and the shared
brace-scanner / route-normalizer."""
import pytest

from codegraph.extractors import extractor_for, language_for
from codegraph.extractors.base import Extractor, normalize_route


def ex(lang, src):
    return extractor_for(lang).extract(src)


# ---- language detection ---------------------------------------------------
@pytest.mark.parametrize("name,lang", [
    ("a.py", "python"), ("a.PY", "python"),
    ("a.js", "javascript"), ("a.jsx", "javascript"), ("a.mjs", "javascript"),
    ("a.ts", "typescript"), ("a.tsx", "typescript"),
    ("a.go", "go"), ("a.rs", "rust"), ("a.java", "java"), ("a.cs", "csharp"),
])
def test_language_for_known(name, lang):
    assert language_for(name) == lang


@pytest.mark.parametrize("name", ["a.rb", "a.txt", "a", "a.c", "Makefile", "a.kt"])
def test_language_for_unknown(name):
    assert language_for(name) is None


def test_extractor_for_unknown_lang_is_none():
    assert extractor_for("cobol") is None


def test_base_extractor_not_implemented():
    with pytest.raises(NotImplementedError):
        Extractor().extract("x")


# ---- normalize_route ------------------------------------------------------
@pytest.mark.parametrize("raw,norm", [
    ("/users/:id", "/users/{}"),
    ("/users/{id}", "/users/{}"),
    ("/users/<int:id>", "/users/{}"),
    ("/users/${userId}", "/users/{}"),
    ("/a/:x/b/:y", "/a/{}/b/{}"),
    ("/health/", "/health"),
    ("/", "/"),
    ("/x?q=1#frag", "/x"),
    ("users", "/users"),                 # leading slash added
    ("  /trim/  ", "/trim"),             # whitespace stripped
])
def test_normalize_route_cases(raw, norm):
    assert normalize_route(raw) == norm


def test_normalize_route_idempotent():
    once = normalize_route("/users/:id/posts/{pid}")
    assert normalize_route(once) == once


# ---- python ---------------------------------------------------------------
def test_python_async_function_signature():
    res = ex("python", "async def fetch(a, b):\n    return a\n")
    sym = res.symbols[0]
    assert sym.signature.startswith("async def fetch(")
    assert sym.kind == "function"


def test_python_varargs_in_signature():
    res = ex("python", "def f(a, *args, **kwargs):\n    return a\n")
    sig = res.symbols[0].signature
    assert "*args" in sig and "**kwargs" in sig


def test_python_nested_class_container():
    src = "class Outer:\n    class Inner:\n        def m(self):\n            return 1\n"
    res = ex("python", src)
    m = next(s for s in res.symbols if s.name == "m")
    assert m.container == "Inner" and m.kind == "method"


def test_python_decorator_without_route_makes_no_endpoint():
    src = "@staticmethod\ndef f():\n    return 1\n"
    res = ex("python", src)
    assert res.endpoints == []


def test_python_route_methods_kwarg_overrides():
    src = "@app.route('/x', methods=['POST'])\ndef f():\n    return 1\n"
    res = ex("python", src)
    ep = next(e for e in res.endpoints if e.role == "server")
    assert ep.method == "POST"


def test_python_router_get_decorator():
    src = "@router.get('/items/{id}')\ndef item(id):\n    return id\n"
    res = ex("python", src)
    assert any(e.method == "GET" and e.route == "/items/{id}" for e in res.endpoints)


def test_python_client_relative_route_only():
    # absolute URLs (not starting with /) are not treated as routes
    src = ("import requests\n"
           "def f():\n"
           "    requests.get('http://example.com/x')\n"
           "    requests.get('/api/y')\n")
    res = ex("python", src)
    routes = {e.route for e in res.endpoints if e.role == "client"}
    assert "/api/y" in routes
    assert "http://example.com/x" not in routes


def test_python_calls_deduped_preserving_order():
    src = "def f():\n    a()\n    b()\n    a()\n"
    res = ex("python", src)
    f = next(s for s in res.symbols if s.name == "f")
    assert f.calls == ["a", "b"]


def test_python_empty_source():
    res = ex("python", "")
    assert res.symbols == [] and res.refs == [] and res.endpoints == []


# ---- javascript / typescript ----------------------------------------------
def test_js_arrow_function_detected():
    res = ex("javascript", "const add = (a, b) => {\n  return a + b;\n}\n")
    assert any(s.name == "add" for s in res.symbols)


def test_js_axios_method_route():
    src = ("function load() {\n"
           "  axios.post('/api/save', data);\n"
           "}\n")
    res = ex("javascript", src)
    ep = next(e for e in res.endpoints if e.role == "client")
    assert ep.method == "POST" and ep.route == "/api/save"


def test_js_router_use_is_any():
    src = "function setup() {\n  router.use('/mw', fn);\n}\n"
    res = ex("javascript", src)
    assert any(e.role == "server" and e.method == "ANY" for e in res.endpoints)


def test_js_brace_in_template_literal_ignored():
    src = ('function f() {\n'
           '  const x = `a ${"{"} b`;\n'
           '  inner();\n'
           '}\n'
           'function g() { return 1; }\n')
    res = ex("javascript", src)
    assert {s.name for s in res.symbols} == {"f", "g"}


def test_js_line_comment_brace_ignored():
    src = ("function f() {\n"
           "  // closing } in a comment\n"
           "  work();\n"
           "}\n")
    res = ex("javascript", src)
    f = next(s for s in res.symbols if s.name == "f")
    assert "work" in f.calls


def test_js_block_comment_brace_ignored():
    src = ("function f() {\n"
           "  /* } still inside { */\n"
           "  work();\n"
           "}\n")
    res = ex("javascript", src)
    assert any(s.name == "f" for s in res.symbols)


def test_js_keywords_not_counted_as_calls():
    src = ("function f() {\n"
           "  if (x) { for (;;) { while (y) {} } }\n"
           "  real();\n"
           "}\n")
    res = ex("javascript", src)
    f = next(s for s in res.symbols if s.name == "f")
    assert "if" not in f.calls and "for" not in f.calls and "while" not in f.calls
    assert "real" in f.calls


# ---- go -------------------------------------------------------------------
def test_go_method_vs_function_kind():
    src = ("func (s *Server) Handle() {}\n"
           "func Plain() {}\n")
    res = ex("go", src)
    by = {s.name: s for s in res.symbols}
    assert by["Handle"].kind == "method"
    assert by["Plain"].kind == "function"


def test_go_struct_and_interface_types():
    src = "type User struct {\n  ID string\n}\ntype Repo interface {\n  Get()\n}\n"
    res = ex("go", src)
    types = {s.name for s in res.symbols if s.kind == "type"}
    assert {"User", "Repo"} <= types


def test_go_client_get_route():
    src = 'func f() {\n  http.Get("/api/ping")\n}\n'
    res = ex("go", src)
    assert any(e.role == "client" and e.method == "GET" and e.route == "/api/ping"
               for e in res.endpoints)


# ---- rust -----------------------------------------------------------------
def test_rust_trait_declaration_no_body():
    res = ex("rust", "trait Repo;\n")
    repo = next(s for s in res.symbols if s.name == "Repo")
    assert repo.kind == "type"
    assert repo.start_line == repo.end_line  # no distant brace grabbed


def test_rust_enum_and_struct_types():
    res = ex("rust", "struct A { x: i32 }\nenum B { X, Y }\n")
    kinds = {s.name: s.kind for s in res.symbols}
    assert kinds["A"] == "type" and kinds["B"] == "type"


def test_rust_axum_route_server():
    src = 'fn r() -> Router {\n  Router::new().route("/api/x/{id}", get(h))\n}\n'
    res = ex("rust", src)
    assert any(e.role == "server" and e.route == "/api/x/{id}" for e in res.endpoints)


# ---- java -----------------------------------------------------------------
def test_java_request_mapping_is_any():
    src = ("public class C {\n"
           "  @RequestMapping(\"/api/all\")\n"
           "  public String all() { return \"\"; }\n"
           "}\n")
    res = ex("java", src)
    assert any(e.role == "server" and e.method == "ANY" and e.route == "/api/all"
               for e in res.endpoints)


def test_java_mapping_value_kwarg():
    src = ("public class C {\n"
           "  @PostMapping(value = \"/api/post\")\n"
           "  public void p() {}\n"
           "}\n")
    res = ex("java", src)
    assert any(e.method == "POST" and e.route == "/api/post" for e in res.endpoints)


def test_java_client_resttemplate_route():
    src = ("public class C {\n"
           "  public void f() {\n"
           "    rest.getForObject(\"/api/remote\", String.class);\n"
           "  }\n"
           "}\n")
    res = ex("java", src)
    assert any(e.role == "client" and e.route == "/api/remote" for e in res.endpoints)


# ---- c# -------------------------------------------------------------------
def test_csharp_route_attribute_is_any():
    src = ("public class C {\n"
           "  [Route(\"/api/r\")]\n"
           "  public string R() { return \"\"; }\n"
           "}\n")
    res = ex("csharp", src)
    assert any(e.role == "server" and e.method == "ANY" and e.route == "/api/r"
               for e in res.endpoints)


def test_csharp_record_and_struct_types():
    src = "public record Dto(string Id);\npublic struct Point { public int X; }\n"
    res = ex("csharp", src)
    names = {s.name for s in res.symbols if s.kind == "class"}
    assert {"Dto", "Point"} <= names


def test_csharp_async_method_detected():
    src = ("public class C {\n"
           "  public async Task<int> GetAsync() {\n"
           "    return await Fetch();\n"
           "  }\n"
           "}\n")
    res = ex("csharp", src)
    m = next(s for s in res.symbols if s.name == "GetAsync")
    assert "Fetch" in m.calls
