"""More benchmark coverage: scaling, route recall, and the grep baseline."""
from pathlib import Path

from bench.benchmark import generate_repo, grep_finds_ts_caller, run


def test_run_scales_files_with_services():
    r = run(3)
    assert r["files"] == 12          # 3 services x 4 languages
    assert r["recall"]["codegraph"] == "3/3"


def test_grep_by_name_finds_nothing():
    r = run(5)
    assert r["recall"]["grep_by_name"] == "0/5"


def test_throughput_fields_present():
    r = run(2)
    for k in ("index_seconds", "files_per_sec", "symbols_per_sec",
              "cross_language_edges"):
        assert k in r
    assert r["cross_language_edges"] >= 2


def test_generate_repo_creates_four_languages(tmp_path):
    generate_repo(tmp_path, 1)
    suffixes = {p.suffix for p in tmp_path.rglob("*") if p.is_file()}
    assert {".ts", ".go", ".py", ".rs"} <= suffixes


def test_grep_finds_ts_caller_true_for_real_name(tmp_path):
    generate_repo(tmp_path, 1)
    # the TS client function name does appear in a .ts file
    assert grep_finds_ts_caller(tmp_path, "loadThing0") is True
    assert grep_finds_ts_caller(tmp_path, "no_such_symbol") is False


def test_route_recall_finds_files():
    r = run(2)
    assert "files only" in r["recall"]["grep_by_route"]
