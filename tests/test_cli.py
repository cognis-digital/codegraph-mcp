"""End-to-end CLI tests driving codegraph.cli.main() with argv lists and
capturing JSON stdout. Covers index/stats/query/diff/viz/token/audit."""
import json
from pathlib import Path

import pytest

from codegraph import cli

SAMPLE = Path(__file__).resolve().parent.parent / "examples" / "sample_repo"


def run(capsys, *argv):
    rc = cli.main(list(argv))
    out = capsys.readouterr().out
    return rc, out


def run_json(capsys, *argv):
    rc, out = run(capsys, *argv)
    return rc, json.loads(out)


@pytest.fixture
def db(tmp_path, capsys):
    path = str(tmp_path / "g.db")
    rc, data = run_json(capsys, "index", str(SAMPLE), "--db", path)
    assert rc == 0
    return path


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as e:
        cli.main(["--version"])
    assert e.value.code == 0


def test_index_reports_stats(db, capsys, tmp_path):
    rc, data = run_json(capsys, "stats", "--db", db)
    assert rc == 0
    assert data["files"] >= 6
    for lang in ("python", "go", "rust", "java", "csharp", "typescript"):
        assert lang in data["languages"]


def test_index_missing_path_errors(tmp_path):
    with pytest.raises(FileNotFoundError):
        cli.main(["index", str(tmp_path / "nope"), "--db", str(tmp_path / "g.db")])


def test_query_search(db, capsys):
    rc, data = run_json(capsys, "query", "search", "loadUser", "--db", db)
    assert rc == 0
    assert data["results"][0]["name"] == "loadUser"


def test_query_search_kind_filter(db, capsys):
    rc, data = run_json(capsys, "query", "search", "User", "--kind", "class", "--db", db)
    assert all(r["kind"] == "class" for r in data["results"])


def test_query_refs(db, capsys):
    rc, data = run_json(capsys, "query", "refs", "lookup", "--db", db)
    assert rc == 0 and data["name"] == "lookup"


def test_query_callers_and_callees(db, capsys):
    rc, search = run_json(capsys, "query", "search", "get_user", "--db", db)
    sid = next(r["id"] for r in search["results"] if r["lang"] == "python")
    rc, callees = run_json(capsys, "query", "callees", str(sid), "--db", db)
    assert any(c["name"] == "lookup" for c in callees["callees"])
    rc, callers = run_json(capsys, "query", "callers", str(sid), "--db", db)
    assert any(c["name"] == "loadUser" for c in callers["callers"])


def test_query_impact(db, capsys):
    rc, search = run_json(capsys, "query", "search", "lookup", "--kind", "function", "--db", db)
    sid = next(r["id"] for r in search["results"] if r["lang"] == "python")
    rc, impact = run_json(capsys, "query", "impact", str(sid), "--db", db)
    assert impact["impacted_count"] >= 1


def test_query_xlang(db, capsys):
    rc, data = run_json(capsys, "query", "xlang", "--db", db)
    assert rc == 0 and len(data["edges"]) >= 1


def test_query_orphans(db, capsys):
    rc, data = run_json(capsys, "query", "orphans", "--db", db)
    assert rc == 0 and isinstance(data["orphans"], list)


def test_query_hotspots(db, capsys):
    rc, data = run_json(capsys, "query", "hotspots", "--limit", "3", "--db", db)
    assert rc == 0 and len(data["hotspots"]) <= 3


def test_query_project_graph(db, capsys):
    rc, data = run_json(capsys, "query", "project-graph", "--db", db)
    assert "modules" in data and "edges" in data


def test_diff_paths(capsys, tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    for d, body in ((a, "def f():\n    return 1\n"),
                    (b, "def f():\n    return 1\ndef g():\n    return 2\n")):
        d.mkdir()
        (d / "x.py").write_text(body, encoding="utf-8")
    rc, data = run_json(capsys, "diff", str(a), str(b), "--paths")
    assert rc == 0 and data["summary"]["symbols_added"] == 1


def test_viz_mermaid_stdout(db, capsys):
    rc, out = run(capsys, "viz", "--db", db, "--format", "mermaid")
    assert rc == 0 and out.startswith("flowchart")


def test_viz_dot_to_file(db, capsys, tmp_path):
    out_file = tmp_path / "graph.dot"
    rc, _ = run(capsys, "viz", "--db", db, "--format", "dot", "--out", str(out_file))
    assert rc == 0
    assert out_file.read_text(encoding="utf-8").startswith("digraph codegraph")


def test_token_issue_list_revoke(db, capsys):
    rc, issued = run_json(capsys, "token", "issue", "agent-x", "--scopes", "read,audit", "--db", db)
    assert issued["token"].startswith("cg_")
    tid = issued["id"]
    rc, listed = run_json(capsys, "token", "list", "--db", db)
    assert any(t["id"] == tid and t["active"] for t in listed["tokens"])
    rc, revoked = run_json(capsys, "token", "revoke", str(tid), "--db", db)
    assert revoked["revoked"] is True
    rc, listed2 = run_json(capsys, "token", "list", "--db", db)
    assert any(t["id"] == tid and not t["active"] for t in listed2["tokens"])


def test_audit_tail_and_verify(db, capsys):
    rc, data = run_json(capsys, "audit", "--db", db, "-n", "5")
    assert rc == 0 and isinstance(data["audit"], list)
    assert any(r["action"] == "index" for r in data["audit"])
    rc, verify = run_json(capsys, "audit", "--db", db, "--verify")
    assert rc == 0 and verify["intact"] is True


def test_audit_verify_detects_tamper(db, capsys):
    from codegraph.graph import Store
    s = Store(db)
    s.conn.execute("UPDATE audit SET actor='evil' WHERE seq=1")
    s.conn.commit()
    s.close()
    rc, verify = run_json(capsys, "audit", "--db", db, "--verify")
    assert rc == 1 and verify["intact"] is False


def test_no_subcommand_errors():
    with pytest.raises(SystemExit):
        cli.main([])
