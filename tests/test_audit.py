import sqlite3

from codegraph.audit import AuditLog, chain_hash


def fresh():
    return AuditLog(sqlite3.connect(":memory:"))


def test_append_and_tail():
    log = fresh()
    log.append("admin", "a", "t1")
    log.append("agent:x", "b", "t2", {"k": 1})
    tail = log.tail(10)
    assert [r.action for r in tail] == ["b", "a"]  # newest first
    assert tail[0].detail == {"k": 1}


def test_chain_links_records():
    log = fresh()
    r1 = log.append("admin", "a")
    r2 = log.append("admin", "b")
    assert r2.prev_hash == r1.hash
    ok, broken = log.verify()
    assert ok and broken is None


def test_verify_detects_tampering():
    conn = sqlite3.connect(":memory:")
    log = AuditLog(conn)
    log.append("admin", "a", "t")
    log.append("admin", "b", "t")
    log.append("admin", "c", "t")
    # tamper with the middle record's target
    conn.execute("UPDATE audit SET target='HACKED' WHERE seq=2")
    conn.commit()
    ok, broken = log.verify()
    assert not ok
    assert broken == 2


def test_verify_detects_deletion():
    conn = sqlite3.connect(":memory:")
    log = AuditLog(conn)
    log.append("admin", "a")
    log.append("admin", "b")
    log.append("admin", "c")
    conn.execute("DELETE FROM audit WHERE seq=2")
    conn.commit()
    ok, broken = log.verify()
    assert not ok
    assert broken == 3  # the record after the gap no longer chains


def test_chain_hash_is_order_sensitive():
    p = {"seq": 1, "ts": 0.0, "actor": "a", "action": "x", "target": "", "detail": {}, "prev_hash": "0" * 64}
    h1 = chain_hash("0" * 64, p)
    h2 = chain_hash("1" * 64, p)
    assert h1 != h2
