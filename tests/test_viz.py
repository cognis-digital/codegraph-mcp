"""Tests for the Mermaid / DOT graph visualizers."""
import os

from codegraph.graph import Store
from codegraph.indexer import index_path
from codegraph import viz

SAMPLE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "examples", "sample_repo")


def _store(tmp_path):
    s = Store(str(tmp_path / "g.db"))
    index_path(s, SAMPLE)
    return s


def test_mermaid_project_has_nodes_and_xlang(tmp_path):
    s = _store(tmp_path)
    m = viz.mermaid_project(s)
    assert m.startswith("flowchart")
    assert "m_web" in m and "m_api" in m
    assert "-. " in m              # at least one dashed cross-language edge
    assert "classDef xlang" in m
    s.close()


def test_dot_project_is_digraph(tmp_path):
    s = _store(tmp_path)
    d = viz.dot_project(s)
    assert d.startswith("digraph codegraph")
    assert "->" in d
    assert d.strip().endswith("}")
    s.close()


def test_impact_view_requires_symbol(tmp_path):
    s = _store(tmp_path)
    try:
        viz.render(s, view="impact", fmt="mermaid", symbol_id=None)
        assert False, "should have raised"
    except ValueError:
        pass
    s.close()


def test_impact_mermaid_renders_for_hotspot(tmp_path):
    s = _store(tmp_path)
    hot = s.hotspots(1)
    assert hot, "sample repo should have a hotspot"
    m = viz.mermaid_impact(s, hot[0]["id"])
    assert m.startswith("flowchart")
    assert f's{hot[0]["id"]}' in m
    s.close()
