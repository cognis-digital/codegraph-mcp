"""More visualizer cases: render() validation, DOT details, empty graphs,
direction, node-id sanitization, impact rendering."""
from pathlib import Path

import pytest

from codegraph import viz
from codegraph.graph import Store
from codegraph.indexer import index_path
from codegraph.viz import _node_id

SAMPLE = Path(__file__).resolve().parent.parent / "examples" / "sample_repo"


def indexed(tmp_path):
    s = Store(str(tmp_path / "g.db"))
    index_path(s, SAMPLE)
    return s


def test_node_id_sanitizes_path():
    assert _node_id("a/b-c.d") == "m_a_b_c_d"
    assert _node_id("") == "m_root"


def test_render_unknown_view_raises(tmp_path):
    s = indexed(tmp_path)
    with pytest.raises(ValueError):
        viz.render(s, view="galaxy")


def test_render_unknown_format_raises(tmp_path):
    s = indexed(tmp_path)
    with pytest.raises(ValueError):
        viz.render(s, fmt="svg")


def test_render_project_mermaid_default(tmp_path):
    out = viz.render(indexed(tmp_path))
    assert out.startswith("flowchart")


def test_render_project_dot(tmp_path):
    out = viz.render(indexed(tmp_path), fmt="dot")
    assert out.startswith("digraph codegraph")


def test_impact_view_dot_not_supported(tmp_path):
    s = indexed(tmp_path)
    hot = s.hotspots(1)[0]
    with pytest.raises(ValueError):
        viz.render(s, view="impact", fmt="dot", symbol_id=hot["id"])


def test_mermaid_direction_honored(tmp_path):
    s = indexed(tmp_path)
    assert viz.mermaid_project(s, direction="TD").startswith("flowchart TD")


def test_mermaid_project_empty_graph():
    out = viz.mermaid_project(Store(":memory:"))
    assert out.strip() == "flowchart LR\n    classDef xlang stroke:#f4b400,stroke-width:3px;".strip() \
        or out.startswith("flowchart")


def test_dot_project_empty_graph():
    out = viz.dot_project(Store(":memory:"))
    assert out.startswith("digraph codegraph") and out.strip().endswith("}")


def test_dot_marks_cross_language_dashed(tmp_path):
    out = viz.dot_project(indexed(tmp_path))
    assert "style=dashed" in out
    assert "HTTP" in out


def test_mermaid_impact_for_unknown_symbol(tmp_path):
    s = indexed(tmp_path)
    # a non-existent id renders the root box but no impacted nodes
    out = viz.mermaid_impact(s, 999999)
    assert out.startswith("flowchart TD")
    assert "s999999" in out


def test_mermaid_impact_contains_root_class(tmp_path):
    s = indexed(tmp_path)
    hot = s.hotspots(1)[0]
    out = viz.mermaid_impact(s, hot["id"])
    assert "classDef root" in out
