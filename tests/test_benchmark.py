from bench.benchmark import run


def test_benchmark_recall_small():
    r = run(6)
    assert r["files"] == 24                       # 6 services x 4 languages
    assert r["symbols"] > 0
    assert r["cross_language_edges"] > 0
    # the headline: graph finds every cross-language dependency, name-grep none
    assert r["recall"]["codegraph"] == "6/6"
    assert r["recall"]["grep_by_name"] == "0/6"
