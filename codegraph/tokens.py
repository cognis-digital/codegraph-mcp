"""Scoped, revocable agent tokens.

An agent never gets ambient access to the graph. It presents a bearer token
that maps to a set of scopes; every issuance and revocation is itself an audit
event, and revocation takes effect immediately. Only a salted hash of the token
is stored, so a leak of the database does not leak usable credentials.

Scopes:
  read    query the knowledge graph (symbols, callers, impact, cross-language)
  audit   read the audit log
  admin   issue and revoke tokens
"""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
import time
from dataclasses import dataclass
from typing import Optional

VALID_SCOPES = {"read", "audit", "admin"}


def _hash(token: str) -> str:
    return hashlib.blake2b(token.encode("utf-8"), digest_size=32).hexdigest()


@dataclass(frozen=True)
class TokenInfo:
    id: int
    label: str
    scopes: frozenset[str]
    created_at: float
    revoked_at: Optional[float]

    @property
    def active(self) -> bool:
        return self.revoked_at is None


class TokenStore:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tokens (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                label      TEXT NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                scopes     TEXT NOT NULL,
                created_at REAL NOT NULL,
                revoked_at REAL
            )
            """
        )
        self.conn.commit()

    def issue(self, label: str, scopes: set[str]) -> tuple[str, TokenInfo]:
        bad = scopes - VALID_SCOPES
        if bad:
            raise ValueError(f"unknown scopes: {sorted(bad)}")
        token = "cg_" + secrets.token_urlsafe(32)
        created = time.time()
        cur = self.conn.execute(
            "INSERT INTO tokens(label, token_hash, scopes, created_at) VALUES(?,?,?,?)",
            (label, _hash(token), ",".join(sorted(scopes)), created),
        )
        self.conn.commit()
        info = TokenInfo(int(cur.lastrowid), label, frozenset(scopes), created, None)
        return token, info

    def revoke(self, token_id: int) -> bool:
        cur = self.conn.execute(
            "UPDATE tokens SET revoked_at=? WHERE id=? AND revoked_at IS NULL",
            (time.time(), token_id),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def authenticate(self, token: str) -> Optional[TokenInfo]:
        """Return active TokenInfo for a presented token, or None."""
        row = self.conn.execute(
            "SELECT id, label, scopes, created_at, revoked_at FROM tokens "
            "WHERE token_hash=?",
            (_hash(token),),
        ).fetchone()
        if not row or row[4] is not None:
            return None
        return TokenInfo(row[0], row[1], frozenset(row[2].split(",")), row[3], None)

    def list(self) -> list[TokenInfo]:
        rows = self.conn.execute(
            "SELECT id, label, scopes, created_at, revoked_at FROM tokens ORDER BY id"
        ).fetchall()
        return [
            TokenInfo(r[0], r[1], frozenset(r[2].split(",")), r[3], r[4]) for r in rows
        ]
