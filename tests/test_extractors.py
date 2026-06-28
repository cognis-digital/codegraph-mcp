from codegraph.extractors import extractor_for, language_for
from codegraph.extractors.base import normalize_route


def test_language_detection():
    assert language_for("a.py") == "python"
    assert language_for("a.ts") == "typescript"
    assert language_for("a.tsx") == "typescript"
    assert language_for("a.go") == "go"
    assert language_for("a.rb") is None


def test_normalize_route_variants():
    assert normalize_route("/api/users/:id") == "/api/users/{}"
    assert normalize_route("/api/users/{id}") == "/api/users/{}"
    assert normalize_route("/api/users/<int:id>") == "/api/users/{}"
    assert normalize_route("/api/users/${userId}") == "/api/users/{}"
    assert normalize_route("/api/health/") == "/api/health"
    assert normalize_route("/api/users/:id?x=1") == "/api/users/{}"


def test_python_extractor_symbols_and_calls():
    src = (
        "class Service:\n"
        "    def handle(self, x):\n"
        "        return self.process(x)\n"
        "    def process(self, x):\n"
        "        return helper(x)\n"
        "\n"
        "def helper(x):\n"
        "    return x\n"
    )
    res = extractor_for("python").extract(src)
    names = {s.name: s for s in res.symbols}
    assert names["Service"].kind == "class"
    assert names["handle"].kind == "method"
    assert names["handle"].container == "Service"
    assert names["helper"].kind == "function"
    assert "process" in names["handle"].calls
    assert "helper" in names["process"].calls


def test_python_extractor_routes():
    src = (
        "@app.route('/api/health')\n"
        "def health():\n"
        "    return 'ok'\n"
        "\n"
        "@app.route('/api/users/<id>', methods=['GET'])\n"
        "def get_user(id):\n"
        "    return id\n"
    )
    res = extractor_for("python").extract(src)
    routes = {(e.route, e.role) for e in res.endpoints}
    assert ("/api/health", "server") in routes
    assert ("/api/users/<id>", "server") in routes


def test_python_client_endpoint():
    src = (
        "import requests\n"
        "def fetch_user(i):\n"
        "    return requests.get('/api/users/' + i)\n"
    )
    res = extractor_for("python").extract(src)
    assert any(e.role == "client" and e.route.startswith("/api/users") for e in res.endpoints)


def test_js_extractor_functions_and_fetch():
    src = (
        "export async function loadUser(id) {\n"
        "  const r = await fetch(`/api/users/${id}`);\n"
        "  return parse(r);\n"
        "}\n"
        "const helper = (x) => {\n"
        "  return x;\n"
        "}\n"
    )
    res = extractor_for("typescript").extract(src)
    names = {s.name for s in res.symbols}
    assert "loadUser" in names
    assert "helper" in names
    assert any(e.role == "client" and "/api/users" in e.route for e in res.endpoints)


def test_go_extractor_funcs_and_routes():
    src = (
        "package main\n"
        "func routes(mux *http.ServeMux) {\n"
        "  mux.HandleFunc(\"/api/health\", health)\n"
        "}\n"
        "func health(w http.ResponseWriter, r *http.Request) {\n"
        "  w.Write([]byte(\"ok\"))\n"
        "}\n"
    )
    res = extractor_for("go").extract(src)
    names = {s.name for s in res.symbols}
    assert "routes" in names
    assert "health" in names
    assert any(e.role == "server" and e.route == "/api/health" for e in res.endpoints)


def test_brace_scan_ignores_braces_in_strings():
    src = (
        "function f() {\n"
        "  const s = \"} not a close {\";\n"
        "  inner();\n"
        "}\n"
        "function g() { return 1; }\n"
    )
    res = extractor_for("javascript").extract(src)
    names = {s.name for s in res.symbols}
    assert names == {"f", "g"}
    f = next(s for s in res.symbols if s.name == "f")
    assert "inner" in f.calls
