from pathlib import Path

from codegraph.graph import Store
from codegraph.indexer import index_path

SAMPLE = Path(__file__).resolve().parent.parent / "examples" / "sample_repo"


def build():
    store = Store(":memory:")
    stats = index_path(store, SAMPLE)
    return store, stats


def test_indexes_three_languages():
    store, stats = build()
    s = store.stats()
    assert s["languages"].get("python", 0) >= 1
    assert s["languages"].get("typescript", 0) >= 1
    assert s["languages"].get("go", 0) >= 1
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
    [get_user] = [s for s in store.symbols_by_name("get_user")]
    callees = {c.name for c in store.callees_of(get_user.id)}
    assert "lookup" in callees


def test_cross_language_edges_present():
    store, _ = build()
    edges = store.cross_language_edges()
    # the TS client calling /api/users/${id} should link to a non-TS handler
    langs_reached = {e["to"]["lang"] for e in edges if e["from"]["lang"] == "typescript"}
    assert "python" in langs_reached or "go" in langs_reached
    assert any(e["from"]["symbol"] == "loadUser" for e in edges)


def test_impact_includes_cross_language_caller():
    store, _ = build()
    # changing the python get_user handler should implicate the TS client
    [get_user] = [s for s in store.symbols_by_name("get_user")]
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
