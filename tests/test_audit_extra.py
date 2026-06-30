"""Deeper tests for the hash-chained audit log."""
import sqlite3

from codegraph.audit import GENESIS, AuditLog, AuditRecord, chain_hash


def fresh():
    return AuditLog(sqlite3.connect(":memory:"))


def test_empty_log_verifies():
    ok, broken = fresh().verify()
    assert ok and broken is None


def test_first_record_chains_onto_genesis():
    log = fresh()
    r = log.append("admin", "init")
    assert r.prev_hash == GENESIS
    assert r.seq == 1


def test_seq_is_monotonic():
    log = fresh()
    seqs = [log.append("a", "x").seq for _ in range(5)]
    assert seqs == [1, 2, 3, 4, 5]


def test_tail_limit_and_order():
    log = fresh()
    for i in range(5):
        log.append("a", f"act{i}")
    tail = log.tail(2)
    assert [r.action for r in tail] == ["act4", "act3"]  # newest first


def test_iter_is_ascending():
    log = fresh()
    for i in range(3):
        log.append("a", f"act{i}")
    assert [r.action for r in log] == ["act0", "act1", "act2"]


def test_detail_roundtrips_nested():
    log = fresh()
    detail = {"arguments": {"query": "x", "limit": 5}, "nested": {"a": [1, 2, 3]}}
    log.append("agent", "tool_call", "search", detail)
    assert log.tail(1)[0].detail == detail


def test_explicit_timestamp_used():
    log = fresh()
    r = log.append("a", "x", ts=123.5)
    assert r.ts == 123.5


def test_record_payload_excludes_hash():
    rec = AuditRecord(1, 0.0, "a", "x", "t", {}, GENESIS, "deadbeef")
    assert "hash" not in rec.payload()
    assert rec.payload()["prev_hash"] == GENESIS


def test_chain_hash_changes_with_payload():
    base = {"seq": 1, "ts": 0.0, "actor": "a", "action": "x", "target": "",
            "detail": {}, "prev_hash": GENESIS}
    h1 = chain_hash(GENESIS, base)
    h2 = chain_hash(GENESIS, {**base, "action": "y"})
    assert h1 != h2


def test_tamper_first_record_detected():
    conn = sqlite3.connect(":memory:")
    log = AuditLog(conn)
    log.append("a", "first")
    log.append("a", "second")
    conn.execute("UPDATE audit SET actor='evil' WHERE seq=1")
    conn.commit()
    ok, broken = log.verify()
    assert not ok and broken == 1


def test_tamper_detail_detected():
    conn = sqlite3.connect(":memory:")
    log = AuditLog(conn)
    log.append("a", "x", detail={"ok": True})
    log.append("a", "y")
    conn.execute("UPDATE audit SET detail='{\"ok\": false}' WHERE seq=1")
    conn.commit()
    ok, broken = log.verify()
    assert not ok and broken == 1


def test_reordering_breaks_chain():
    conn = sqlite3.connect(":memory:")
    log = AuditLog(conn)
    log.append("a", "x")
    log.append("a", "y")
    # swap the two hashes -> prev_hash linkage breaks
    conn.execute("UPDATE audit SET hash='" + "f" * 64 + "' WHERE seq=1")
    conn.commit()
    ok, broken = log.verify()
    assert not ok
