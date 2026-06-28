"""Hash-chained, tamper-evident audit log.

Every meaningful action — indexing a repo, an agent query, a token being
issued or revoked — is appended as a record whose hash commits to the hash of
the record before it. Altering or deleting any historical record breaks the
chain from that point forward, which `verify()` detects without needing any
external service.

The chain is deliberately simple (BLAKE2b over a canonical JSON encoding) so
that an auditor can reproduce it from the raw rows with a few lines of code in
any language.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from dataclasses import dataclass
from typing import Iterator, Optional

GENESIS = "0" * 64


def _canonical(payload: dict) -> bytes:
    """Deterministic JSON encoding used as the hash pre-image."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def chain_hash(prev_hash: str, payload: dict) -> str:
    """Compute the hash of a record given the previous record's hash.

    The previous hash is folded in so the result commits to the entire history,
    not just this record's contents.
    """
    h = hashlib.blake2b(digest_size=32)
    h.update(prev_hash.encode("ascii"))
    h.update(b"\x00")
    h.update(_canonical(payload))
    return h.hexdigest()


@dataclass(frozen=True)
class AuditRecord:
    seq: int
    ts: float
    actor: str
    action: str
    target: str
    detail: dict
    prev_hash: str
    hash: str

    def payload(self) -> dict:
        """The fields that are committed to by `hash` (everything but hash)."""
        return {
            "seq": self.seq,
            "ts": self.ts,
            "actor": self.actor,
            "action": self.action,
            "target": self.target,
            "detail": self.detail,
            "prev_hash": self.prev_hash,
        }


class AuditLog:
    """Append-only audit log backed by a SQLite table."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit (
                seq       INTEGER PRIMARY KEY AUTOINCREMENT,
                ts        REAL    NOT NULL,
                actor     TEXT    NOT NULL,
                action    TEXT    NOT NULL,
                target    TEXT    NOT NULL,
                detail    TEXT    NOT NULL,
                prev_hash TEXT    NOT NULL,
                hash      TEXT    NOT NULL
            )
            """
        )
        self._conn.commit()

    def _last_hash(self) -> str:
        row = self._conn.execute(
            "SELECT hash FROM audit ORDER BY seq DESC LIMIT 1"
        ).fetchone()
        return row[0] if row else GENESIS

    def append(
        self,
        actor: str,
        action: str,
        target: str = "",
        detail: Optional[dict] = None,
        *,
        ts: Optional[float] = None,
    ) -> AuditRecord:
        """Append a record and return it. The hash chains onto the prior tail."""
        detail = detail or {}
        ts = time.time() if ts is None else ts
        prev_hash = self._last_hash()

        # seq is assigned by AUTOINCREMENT; mirror SQLite's choice so the hash
        # pre-image matches what verify() recomputes from the stored row.
        row = self._conn.execute("SELECT COALESCE(MAX(seq), 0) FROM audit").fetchone()
        seq = int(row[0]) + 1

        payload = {
            "seq": seq,
            "ts": ts,
            "actor": actor,
            "action": action,
            "target": target,
            "detail": detail,
            "prev_hash": prev_hash,
        }
        digest = chain_hash(prev_hash, payload)
        self._conn.execute(
            "INSERT INTO audit (seq, ts, actor, action, target, detail, prev_hash, hash) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (seq, ts, actor, action, target, json.dumps(detail), prev_hash, digest),
        )
        self._conn.commit()
        return AuditRecord(seq, ts, actor, action, target, detail, prev_hash, digest)

    def tail(self, limit: int = 50) -> list[AuditRecord]:
        rows = self._conn.execute(
            "SELECT seq, ts, actor, action, target, detail, prev_hash, hash "
            "FROM audit ORDER BY seq DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._row(r) for r in rows]

    def __iter__(self) -> Iterator[AuditRecord]:
        rows = self._conn.execute(
            "SELECT seq, ts, actor, action, target, detail, prev_hash, hash "
            "FROM audit ORDER BY seq ASC"
        ).fetchall()
        for r in rows:
            yield self._row(r)

    @staticmethod
    def _row(r) -> AuditRecord:
        return AuditRecord(
            seq=r[0],
            ts=r[1],
            actor=r[2],
            action=r[3],
            target=r[4],
            detail=json.loads(r[5]),
            prev_hash=r[6],
            hash=r[7],
        )

    def verify(self) -> tuple[bool, Optional[int]]:
        """Replay the chain. Returns (ok, first_broken_seq).

        If the log is intact, returns (True, None). If a record has been
        altered, inserted, or removed, returns (False, seq) pointing at the
        first record whose stored hash disagrees with the recomputed chain.
        """
        prev = GENESIS
        for rec in self:
            if rec.prev_hash != prev:
                return False, rec.seq
            expected = chain_hash(rec.prev_hash, rec.payload())
            if expected != rec.hash:
                return False, rec.seq
            prev = rec.hash
        return True, None
