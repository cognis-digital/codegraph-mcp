"""Unit tests for the Store layer: writes, reads, and the graph queries that
sit directly on SQLite (search ranking, impact depth, orphans, hotspots,
project graph, stats, meta, reset_file)."""
from pathlib import Path

import pytest

from codegraph.graph import Store, Symbol
from codegraph.indexer import index_path

SAMPLE = Path(__file__).resolve().parent.parent / "examples" / "sample_repo"


def indexed():
    s = Store(":memory:")
    index_path(s, SAMPLE)
    return s


# ---- Symbol dataclass -----------------------------------------------------
def test_symbol_qualname_with_container():
    sym = Symbol(1, "handle", "method", "python", "Service", "def handle()",
                 "a/b.py", 3, 5)
    assert sym.qualname() == "Service.handle"


def test_symbol_qualname_without_container():
    sym = Symbol(1, "helper", "function", "python", None, "def helper()",
                 "a/b.py", 3, 5)
    assert sym.qualname() == "helper"


def test_symbol_as_dict_shape():
    sym = Symbol(7, "f", "function", "go", None, "func f()", "server/x.go", 10, 20)
    d = sym.as_dict()
    assert d["id"] == 7
    assert d["qualname"] == "f"
    assert d["location"] == "server/x.go:10"
    assert d["start_line"] == 10 and d["end_line"] == 20
    assert set(d) >= {"id", "name", "qualname", "kind", "lang", "container",
                      "signature", "location", "path", "start_line", "end_line"}


# ---- meta -----------------------------------------------------------------
def test_meta_set_get_roundtrip():
    s = Store(":memory:")
    assert s.get_meta("missing") is None
    s.set_meta("k", "v")
    assert s.get_meta("k") == "v"


def test_meta_upsert_overwrites():
    s = Store(":memory:")
    s.set_meta("k", "one")
    s.set_meta("k", "two")
    assert s.get_meta("k") == "two"


# ---- file lifecycle -------------------------------------------------------
def test_add_file_and_reset_cascades():
    s = Store(":memory:")
    fid = s.add_file("x.py", "python", "sha", 1.0)
    s.add_symbol(fid, "f", "function", "python", 1, 2)
    s.commit()
    assert s.stats()["symbols"] == 1
    s.reset_file("x.py")
    assert s.stats()["symbols"] == 0
    assert s.stats()["files"] == 0


def test_reset_file_missing_is_noop():
    s = Store(":memory:")
    s.reset_file("does/not/exist.py")  # must not raise
    assert s.stats()["files"] == 0


# ---- search ranking -------------------------------------------------------
def test_search_exact_match_ranks_first():
    s = Store(":memory:")
    fid = s.add_file("x.py", "python", "sha", 1.0)
    s.add_symbol(fid, "loadUserProfile", "function", "python", 1, 2)
    s.add_symbol(fid, "loadUser", "function", "python", 3, 4)
    s.commit()
    hits = s.search_symbols("loadUser")
    assert hits[0].name == "loadUser"  # exact, and shorter


def test_search_kind_filter():
    s = indexed()
    classes = s.search_symbols("User", kind="class")
    assert classes
    assert all(h.kind == "class" for h in classes)


def test_search_limit_caps_results():
    s = Store(":memory:")
    fid = s.add_file("x.py", "python", "sha", 1.0)
    for i in range(10):
        s.add_symbol(fid, f"thing{i}", "function", "python", i, i)
    s.commit()
    assert len(s.search_symbols("thing", limit=3)) == 3


def test_search_no_match_returns_empty():
    assert indexed().search_symbols("zzz_no_such_symbol") == []


def test_get_symbol_missing_returns_none():
    assert indexed().get_symbol(999999) is None


def test_symbols_by_name_multiple_languages():
    s = indexed()
    langs = {sym.lang for sym in s.symbols_by_name("lookup")}
    assert {"python", "go", "rust"} <= langs


# ---- callers / callees ----------------------------------------------------
def test_callers_callees_empty_for_unknown_id():
    s = indexed()
    assert s.callers_of(999999) == []
    assert s.callees_of(999999) == []


def test_callees_match_callers_inverse():
    s = indexed()
    lookup = next(x for x in s.symbols_by_name("lookup") if x.lang == "python")
    for callee in s.callees_of(lookup.id):
        assert lookup.id in {c.id for c in s.callers_of(callee.id)}


# ---- impact ---------------------------------------------------------------
def test_impact_unknown_symbol_is_empty():
    res = indexed().impact(999999)
    assert res["impacted_count"] == 0
    assert res["impacted"] == []
    assert res["root"] == 999999


def test_impact_depth_zero_returns_nothing():
    s = indexed()
    get_user = next(x for x in s.symbols_by_name("get_user") if x.lang == "python")
    assert s.impact(get_user.id, max_depth=0)["impacted_count"] == 0


def test_impact_records_increasing_depth():
    s = indexed()
    lookup = next(x for x in s.symbols_by_name("lookup") if x.lang == "python")
    res = s.impact(lookup.id)
    depths = [r["depth"] for r in res["impacted"]]
    assert depths == sorted(depths)
    assert all(d >= 1 for d in depths)


def test_impact_depth_limit_truncates():
    s = indexed()
    lookup = next(x for x in s.symbols_by_name("lookup") if x.lang == "python")
    shallow = s.impact(lookup.id, max_depth=1)
    deep = s.impact(lookup.id, max_depth=6)
    assert shallow["impacted_count"] <= deep["impacted_count"]
    assert all(r["depth"] == 1 for r in shallow["impacted"])


# ---- endpoints ------------------------------------------------------------
def test_endpoints_role_filter():
    s = indexed()
    servers = s.endpoints(role="server")
    clients = s.endpoints(role="client")
    assert servers and clients
    assert all(e["role"] == "server" for e in servers)
    assert all(e["role"] == "client" for e in clients)
    assert len(s.endpoints()) == len(servers) + len(clients)


def test_endpoints_unknown_role_empty():
    assert indexed().endpoints(role="nope") == []


# ---- orphans / hotspots ---------------------------------------------------
def test_orphans_limit_respected():
    s = indexed()
    assert len(s.orphans(limit=1)) <= 1


def test_hotspots_limit_and_counts_present():
    s = indexed()
    hot = s.hotspots(limit=3)
    assert len(hot) <= 3
    assert all("callers" in h and h["callers"] >= 1 for h in hot)


def test_hotspots_empty_graph():
    assert Store(":memory:").hotspots() == []


def test_orphans_empty_graph():
    assert Store(":memory:").orphans() == []


# ---- project graph & stats ------------------------------------------------
def test_project_graph_empty_store():
    pg = Store(":memory:").project_graph()
    assert pg == {"modules": [], "edges": []}


def test_project_graph_weights_positive():
    s = indexed()
    pg = s.project_graph()
    assert all(e["weight"] >= 1 for e in pg["edges"])
    assert all(set(e) == {"from", "to", "kind", "weight"} for e in pg["edges"])


def test_stats_empty_store():
    st = Store(":memory:").stats()
    assert st["files"] == 0 and st["symbols"] == 0 and st["edges"] == 0
    assert st["languages"] == {}


def test_stats_counts_match_tables():
    s = indexed()
    st = s.stats()
    assert st["files"] == s.conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    assert st["symbols"] == s.conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]
    assert sum(st["languages"].values()) == st["files"]


def test_add_edge_dedup_via_unique():
    s = Store(":memory:")
    fid = s.add_file("x.py", "python", "sha", 1.0)
    a = s.add_symbol(fid, "a", "function", "python", 1, 2)
    b = s.add_symbol(fid, "b", "function", "python", 3, 4)
    s.add_edge(a, b, "calls")
    s.add_edge(a, b, "calls")  # duplicate ignored by UNIQUE(src,dst,kind)
    s.commit()
    assert s.stats()["edges"] == 1


def test_close_is_idempotent_enough():
    s = Store(":memory:")
    s.close()
    # operating on a closed connection raises sqlite ProgrammingError
    with pytest.raises(Exception):
        s.stats()
