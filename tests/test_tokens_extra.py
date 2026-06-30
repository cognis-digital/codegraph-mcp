"""Edge cases and error paths for scoped agent tokens."""
import sqlite3

import pytest

from codegraph.tokens import VALID_SCOPES, TokenStore, _hash


def fresh():
    return TokenStore(sqlite3.connect(":memory:"))


def test_empty_scope_set_rejected():
    with pytest.raises(ValueError) as e:
        fresh().issue("x", set())
    assert "scope" in str(e.value)


def test_blank_label_rejected():
    with pytest.raises(ValueError):
        fresh().issue("   ", {"read"})


def test_multi_scope_issue_and_auth():
    ts = fresh()
    token, info = ts.issue("multi", {"read", "audit", "admin"})
    assert info.scopes == frozenset(VALID_SCOPES)
    assert ts.authenticate(token).scopes == frozenset(VALID_SCOPES)


def test_unknown_scope_lists_offenders():
    ts = fresh()
    with pytest.raises(ValueError) as e:
        ts.issue("x", {"read", "superuser", "root"})
    msg = str(e.value)
    assert "root" in msg and "superuser" in msg


def test_tokens_are_unique_per_issue():
    ts = fresh()
    t1, _ = ts.issue("a", {"read"})
    t2, _ = ts.issue("b", {"read"})
    assert t1 != t2
    assert ts.authenticate(t1).label == "a"
    assert ts.authenticate(t2).label == "b"


def test_revoke_unknown_id_false():
    assert fresh().revoke(999) is False


def test_list_reflects_active_state():
    ts = fresh()
    _, a = ts.issue("keep", {"read"})
    _, b = ts.issue("drop", {"read"})
    ts.revoke(b.id)
    by_id = {t.id: t for t in ts.list()}
    assert by_id[a.id].active is True
    assert by_id[b.id].active is False
    assert by_id[b.id].revoked_at is not None


def test_list_is_ordered_by_id():
    ts = fresh()
    for lbl in ("a", "b", "c"):
        ts.issue(lbl, {"read"})
    ids = [t.id for t in ts.list()]
    assert ids == sorted(ids)


def test_tokeninfo_active_property():
    ts = fresh()
    _, info = ts.issue("x", {"read"})
    auth = ts.authenticate("cg_" + "0" * 10)
    assert auth is None
    assert info.active is True


def test_hash_is_deterministic_and_hex():
    h = _hash("cg_sample")
    assert h == _hash("cg_sample")
    assert len(h) == 64
    int(h, 16)  # valid hex


def test_authenticate_empty_string_none():
    assert fresh().authenticate("") is None
