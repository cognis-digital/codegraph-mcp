import sqlite3

import pytest

from codegraph.tokens import TokenStore


def fresh():
    return TokenStore(sqlite3.connect(":memory:"))


def test_issue_and_authenticate():
    ts = fresh()
    token, info = ts.issue("ci-agent", {"read"})
    assert token.startswith("cg_")
    auth = ts.authenticate(token)
    assert auth is not None
    assert auth.scopes == frozenset({"read"})


def test_revoke_blocks_authentication():
    ts = fresh()
    token, info = ts.issue("temp", {"read", "audit"})
    assert ts.authenticate(token) is not None
    assert ts.revoke(info.id) is True
    assert ts.authenticate(token) is None
    # second revoke is a no-op
    assert ts.revoke(info.id) is False


def test_unknown_scope_rejected():
    ts = fresh()
    with pytest.raises(ValueError):
        ts.issue("bad", {"superuser"})


def test_only_hash_stored():
    conn = sqlite3.connect(":memory:")
    ts = TokenStore(conn)
    token, _ = ts.issue("x", {"read"})
    row = conn.execute("SELECT token_hash FROM tokens").fetchone()
    assert token not in row[0]
    assert len(row[0]) == 64  # blake2b-256 hex


def test_bad_token_returns_none():
    ts = fresh()
    assert ts.authenticate("cg_not_a_real_token") is None
