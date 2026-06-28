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


def test_rust_extractor_funcs_types_and_routes():
    src = (
        "use axum::routing::get;\n"
        "pub fn router() -> Router {\n"
        "  Router::new().route(\"/api/users/{id}\", get(get_user))\n"
        "}\n"
        "struct User {\n"
        "  id: String,\n"
        "}\n"
        "fn get_user() -> String {\n"
        "  lookup(\"x\")\n"
        "}\n"
        "trait Repo;\n"
    )
    res = extractor_for("rust").extract(src)
    by_name = {s.name: s for s in res.symbols}
    assert "router" in by_name and by_name["router"].kind == "function"
    assert "User" in by_name and by_name["User"].kind == "type"
    assert "get_user" in by_name
    # 'trait Repo;' is a declaration with no body -> still captured, no distant brace grab
    assert "Repo" in by_name and by_name["Repo"].start_line == by_name["Repo"].end_line
    assert "lookup" in by_name["get_user"].calls
    assert any(e.role == "server" and e.route == "/api/users/{id}" for e in res.endpoints)


def test_java_extractor_methods_and_spring_routes():
    src = (
        "@RestController\n"
        "public class UserController {\n"
        "  @GetMapping(\"/api/users/{id}\")\n"
        "  public User getUser(String id) {\n"
        "    return lookup(id);\n"
        "  }\n"
        "  private User lookup(String id) {\n"
        "    return new User(id);\n"
        "  }\n"
        "}\n"
    )
    res = extractor_for("java").extract(src)
    by_name = {s.name: s for s in res.symbols}
    assert "UserController" in by_name and by_name["UserController"].kind == "class"
    assert "getUser" in by_name and by_name["getUser"].kind == "method"
    assert "lookup" in by_name["getUser"].calls
    # the @GetMapping annotation binds to the method that follows it
    server = [e for e in res.endpoints if e.role == "server"]
    assert any(e.route == "/api/users/{id}" and e.in_symbol == "getUser" for e in server)


def test_csharp_extractor_methods_and_aspnet_routes():
    src = (
        "public class UsersController : ControllerBase {\n"
        "  [HttpGet(\"/api/users/{id}\")]\n"
        "  public User GetUser(string id) {\n"
        "    return Lookup(id);\n"
        "  }\n"
        "  private User Lookup(string id) {\n"
        "    return new User(id);\n"
        "  }\n"
        "}\n"
    )
    res = extractor_for("csharp").extract(src)
    by_name = {s.name: s for s in res.symbols}
    assert "UsersController" in by_name
    assert "GetUser" in by_name and "Lookup" in by_name["GetUser"].calls
    assert any(e.role == "server" and e.route == "/api/users/{id}"
               and e.in_symbol == "GetUser" for e in res.endpoints)


def test_csharp_client_route_in_body():
    src = (
        "public class Client {\n"
        "  public async Task Fetch() {\n"
        "    await http.GetAsync(\"/api/users/1\");\n"
        "  }\n"
        "}\n"
    )
    res = extractor_for("csharp").extract(src)
    assert any(e.role == "client" and e.route.startswith("/api/users") for e in res.endpoints)


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
