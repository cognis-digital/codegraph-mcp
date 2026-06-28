from pathlib import Path

from codegraph.graph import Store
from codegraph.indexer import index_path

SAMPLE = Path(__file__).resolve().parent.parent / "examples" / "sample_repo"


def build():
    store = Store(":memory:")
    stats = index_path(store, SAMPLE)
    return store, stats


def test_indexes_four_languages():
    store, stats = build()
    s = store.stats()
    assert s["languages"].get("python", 0) >= 1
    assert s["languages"].get("typescript", 0) >= 1
    assert s["languages"].get("go", 0) >= 1
    assert s["languages"].get("rust", 0) >= 1
    assert stats.symbols > 0


def test_symbol_search_and_get():
    store, _ = build()
    hits = store.search_symbols("loadUser")
    assert hits and hits[0].name == "loadUser"
    sym = store.get_symbol(hits[0].id)
    assert sym is not None and sym.lang == "typescript"


def test_call_edges_resolved():
    store, _ = build()
    # get_user (python) calls lookup
    get_user = next(s for s in store.symbols_by_name("get_user") if s.lang == "python")
    callees = {c.name for c in store.callees_of(get_user.id)}
    assert "lookup" in callees


def test_cross_language_edges_present():
    store, _ = build()
    edges = store.cross_language_edges()
    # the TS client calling /api/users/${id} should fan out to non-TS handlers
    langs_reached = {e["to"]["lang"] for e in edges if e["from"]["lang"] == "typescript"}
    assert {"python", "go", "rust"} & langs_reached
    assert any(e["from"]["symbol"] == "loadUser" for e in edges)


def test_cross_language_reaches_all_backends():
    store, _ = build()
    edges = store.cross_language_edges()
    reached = {e["to"]["lang"] for e in edges if e["from"]["symbol"] == "loadUser"}
    # loadUser hits the same route served in Go, Python, and Rust
    assert {"python", "go", "rust"} <= reached


def test_impact_includes_cross_language_caller():
    store, _ = build()
    # changing the python get_user handler should implicate the TS client
    get_user = next(s for s in store.symbols_by_name("get_user") if s.lang == "python")
    impact = store.impact(get_user.id)
    impacted_names = {row["name"] for row in impact["impacted"]}
    assert "loadUser" in impacted_names


def test_reindex_is_idempotent():
    store = Store(":memory:")
    a = index_path(store, SAMPLE)
    b = index_path(store, SAMPLE)
    # second pass sees no changed files
    assert b.files == 0
    assert store.stats()["symbols"] == a.symbols
