"""The code knowledge graph, backed by a single SQLite file.

A deliberately small relational schema captures everything the query tools
need:

  files      one row per indexed source file
  symbols    functions / methods / classes / types, with location + signature
  refs       call sites and identifier uses (the raw material for callers)
  edges      resolved relationships between symbols (calls, cross-language)
  endpoints  HTTP routes a symbol either serves or calls (cross-language seed)

SQLite is intentional: the whole graph is one portable file, there is no
server to operate, and a self-hosting team can copy, back up, or air-gap it
trivially.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .audit import AuditLog

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS files (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    path       TEXT NOT NULL UNIQUE,
    lang       TEXT NOT NULL,
    sha        TEXT NOT NULL,
    indexed_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS symbols (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id    INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    name       TEXT NOT NULL,
    kind       TEXT NOT NULL,          -- function | method | class | type
    lang       TEXT NOT NULL,
    container  TEXT,                   -- enclosing class/type, if any
    signature  TEXT,
    start_line INTEGER NOT NULL,
    end_line   INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS refs (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id   INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    name      TEXT NOT NULL,           -- the identifier being referenced
    line      INTEGER NOT NULL,
    in_symbol INTEGER REFERENCES symbols(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS edges (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    src     INTEGER NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,
    dst     INTEGER NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,
    kind    TEXT NOT NULL,             -- calls | cross_lang_http
    detail  TEXT,
    UNIQUE(src, dst, kind)
);

CREATE TABLE IF NOT EXISTS endpoints (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol_id INTEGER NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,
    role      TEXT NOT NULL,           -- server | client
    method    TEXT NOT NULL,           -- GET | POST | ANY ...
    route     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name);
CREATE INDEX IF NOT EXISTS idx_symbols_file ON symbols(file_id);
CREATE INDEX IF NOT EXISTS idx_refs_name ON refs(name);
CREATE INDEX IF NOT EXISTS idx_edges_src ON edges(src);
CREATE INDEX IF NOT EXISTS idx_edges_dst ON edges(dst);
CREATE INDEX IF NOT EXISTS idx_endpoints_route ON endpoints(route);
"""


@dataclass
class Symbol:
    id: int
    name: str
    kind: str
    lang: str
    container: Optional[str]
    signature: Optional[str]
    path: str
    start_line: int
    end_line: int

    def qualname(self) -> str:
        return f"{self.container}.{self.name}" if self.container else self.name

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "qualname": self.qualname(),
            "kind": self.kind,
            "lang": self.lang,
            "container": self.container,
            "signature": self.signature,
            "location": f"{self.path}:{self.start_line}",
            "path": self.path,
            "start_line": self.start_line,
            "end_line": self.end_line,
        }


class Store:
    """Owns the SQLite connection and exposes graph reads and writes."""

    def __init__(self, db_path: str | Path = ":memory:"):
        self.db_path = str(db_path)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)
        self.conn.commit()
        self.audit = AuditLog(self.conn)

    # ---- lifecycle -------------------------------------------------------
    def close(self) -> None:
        self.conn.close()

    def set_meta(self, key: str, value: str, commit: bool = True) -> None:
        self.conn.execute(
            "INSERT INTO meta(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        if commit:
            self.conn.commit()

    def get_meta(self, key: str) -> Optional[str]:
        row = self.conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    def reset_file(self, path: str, commit: bool = True) -> None:
        """Remove a file and everything derived from it (for re-indexing)."""
        row = self.conn.execute("SELECT id FROM files WHERE path=?", (path,)).fetchone()
        if row:
            # ON DELETE CASCADE handles symbols/refs/edges/endpoints.
            self.conn.execute("DELETE FROM files WHERE id=?", (row[0],))
            if commit:
                self.conn.commit()

    # ---- writes ----------------------------------------------------------
    def add_file(self, path: str, lang: str, sha: str, indexed_at: float) -> int:
        cur = self.conn.execute(
            "INSERT INTO files(path, lang, sha, indexed_at) VALUES(?,?,?,?)",
            (path, lang, sha, indexed_at),
        )
        return int(cur.lastrowid)

    def add_symbol(
        self,
        file_id: int,
        name: str,
        kind: str,
        lang: str,
        start_line: int,
        end_line: int,
        container: Optional[str] = None,
        signature: Optional[str] = None,
    ) -> int:
        cur = self.conn.execute(
            "INSERT INTO symbols(file_id, name, kind, lang, container, signature, "
            "start_line, end_line) VALUES(?,?,?,?,?,?,?,?)",
            (file_id, name, kind, lang, container, signature, start_line, end_line),
        )
        return int(cur.lastrowid)

    def add_ref(self, file_id: int, name: str, line: int, in_symbol: Optional[int]) -> None:
        self.conn.execute(
            "INSERT INTO refs(file_id, name, line, in_symbol) VALUES(?,?,?,?)",
            (file_id, name, line, in_symbol),
        )

    def add_edge(self, src: int, dst: int, kind: str, detail: str = "") -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO edges(src, dst, kind, detail) VALUES(?,?,?,?)",
            (src, dst, kind, detail),
        )

    def add_endpoint(self, symbol_id: int, role: str, method: str, route: str) -> None:
        self.conn.execute(
            "INSERT INTO endpoints(symbol_id, role, method, route) VALUES(?,?,?,?)",
            (symbol_id, role, method, route),
        )

    def commit(self) -> None:
        self.conn.commit()

    # ---- reads -----------------------------------------------------------
    def _symbol_from_row(self, r) -> Symbol:
        return Symbol(
            id=r[0], name=r[1], kind=r[2], lang=r[3], container=r[4],
            signature=r[5], path=r[6], start_line=r[7], end_line=r[8],
        )

    _SYMBOL_COLS = (
        "s.id, s.name, s.kind, s.lang, s.container, s.signature, "
        "f.path, s.start_line, s.end_line"
    )

    def search_symbols(self, query: str, kind: Optional[str] = None, limit: int = 50) -> list[Symbol]:
        sql = (
            f"SELECT {self._SYMBOL_COLS} FROM symbols s JOIN files f ON f.id = s.file_id "
            "WHERE s.name LIKE ?"
        )
        params: list = [f"%{query}%"]
        if kind:
            sql += " AND s.kind = ?"
            params.append(kind)
        sql += " ORDER BY (s.name = ?) DESC, length(s.name) ASC LIMIT ?"
        params.extend([query, limit])
        rows = self.conn.execute(sql, params).fetchall()
        return [self._symbol_from_row(r) for r in rows]

    def get_symbol(self, symbol_id: int) -> Optional[Symbol]:
        r = self.conn.execute(
            f"SELECT {self._SYMBOL_COLS} FROM symbols s JOIN files f ON f.id = s.file_id "
            "WHERE s.id = ?",
            (symbol_id,),
        ).fetchone()
        return self._symbol_from_row(r) if r else None

    def symbols_by_name(self, name: str) -> list[Symbol]:
        rows = self.conn.execute(
            f"SELECT {self._SYMBOL_COLS} FROM symbols s JOIN files f ON f.id = s.file_id "
            "WHERE s.name = ?",
            (name,),
        ).fetchall()
        return [self._symbol_from_row(r) for r in rows]

    def callers_of(self, symbol_id: int) -> list[Symbol]:
        """Direct callers: symbols with a `calls`/cross-language edge into this one."""
        rows = self.conn.execute(
            f"SELECT {self._SYMBOL_COLS} FROM edges e "
            "JOIN symbols s ON s.id = e.src JOIN files f ON f.id = s.file_id "
            "WHERE e.dst = ?",
            (symbol_id,),
        ).fetchall()
        return [self._symbol_from_row(r) for r in rows]

    def callees_of(self, symbol_id: int) -> list[Symbol]:
        rows = self.conn.execute(
            f"SELECT {self._SYMBOL_COLS} FROM edges e "
            "JOIN symbols s ON s.id = e.dst JOIN files f ON f.id = s.file_id "
            "WHERE e.src = ?",
            (symbol_id,),
        ).fetchall()
        return [self._symbol_from_row(r) for r in rows]

    def find_references(self, name: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT f.path, r.line, r.in_symbol FROM refs r JOIN files f ON f.id = r.file_id "
            "WHERE r.name = ? ORDER BY f.path, r.line",
            (name,),
        ).fetchall()
        return [{"path": r[0], "line": r[1], "in_symbol": r[2]} for r in rows]

    def impact(self, symbol_id: int, max_depth: int = 6) -> dict:
        """Transitive callers ("blast radius"): who breaks if this symbol changes."""
        seen: dict[int, int] = {}
        frontier = [symbol_id]
        depth = 0
        while frontier and depth < max_depth:
            depth += 1
            nxt: list[int] = []
            for sid in frontier:
                for caller in self.callers_of(sid):
                    if caller.id not in seen:
                        seen[caller.id] = depth
                        nxt.append(caller.id)
            frontier = nxt
        impacted = []
        for sid, d in sorted(seen.items(), key=lambda kv: kv[1]):
            sym = self.get_symbol(sid)
            if sym:
                row = sym.as_dict()
                row["depth"] = d
                impacted.append(row)
        return {"root": symbol_id, "impacted_count": len(impacted), "impacted": impacted}

    def endpoints(self, role: Optional[str] = None) -> list[dict]:
        sql = (
            "SELECT e.id, e.symbol_id, e.role, e.method, e.route, s.name, s.lang, f.path "
            "FROM endpoints e JOIN symbols s ON s.id = e.symbol_id "
            "JOIN files f ON f.id = s.file_id"
        )
        params: list = []
        if role:
            sql += " WHERE e.role = ?"
            params.append(role)
        rows = self.conn.execute(sql, params).fetchall()
        return [
            {
                "id": r[0], "symbol_id": r[1], "role": r[2], "method": r[3],
                "route": r[4], "symbol": r[5], "lang": r[6], "path": r[7],
            }
            for r in rows
        ]

    def cross_language_edges(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT e.src, e.dst, e.detail, "
            "ss.name, ss.lang, sf.path, ds.name, ds.lang, df.path "
            "FROM edges e "
            "JOIN symbols ss ON ss.id = e.src JOIN files sf ON sf.id = ss.file_id "
            "JOIN symbols ds ON ds.id = e.dst JOIN files df ON df.id = ds.file_id "
            "WHERE e.kind = 'cross_lang_http'",
        ).fetchall()
        return [
            {
                "detail": r[2],
                "from": {"symbol": r[3], "lang": r[4], "path": r[5], "id": r[0]},
                "to": {"symbol": r[6], "lang": r[7], "path": r[8], "id": r[1]},
            }
            for r in rows
        ]

    def orphans(self, limit: int = 100) -> list[dict]:
        """Functions/methods with no callers and not HTTP entrypoints.

        These are dead-code candidates: nothing in the graph reaches them and
        they aren't reachable from outside as a route handler. (Cross-language
        edges count as callers, so a handler invoked only from another language
        is correctly *not* flagged.)
        """
        rows = self.conn.execute(
            f"SELECT {self._SYMBOL_COLS} FROM symbols s JOIN files f ON f.id = s.file_id "
            "WHERE s.kind IN ('function', 'method') "
            "AND s.id NOT IN (SELECT dst FROM edges) "
            "AND s.id NOT IN (SELECT symbol_id FROM endpoints WHERE role='server') "
            "ORDER BY f.path, s.start_line LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._symbol_from_row(r).as_dict() for r in rows]

    def hotspots(self, limit: int = 20) -> list[dict]:
        """Most depended-on symbols, ranked by number of incoming edges.

        High in-degree symbols are where a change ripples furthest — the places
        to review hardest and test most.
        """
        rows = self.conn.execute(
            f"SELECT {self._SYMBOL_COLS}, COUNT(e.src) AS callers "
            "FROM symbols s JOIN files f ON f.id = s.file_id "
            "JOIN edges e ON e.dst = s.id "
            "GROUP BY s.id ORDER BY callers DESC, s.name LIMIT ?",
            (limit,),
        ).fetchall()
        out = []
        for r in rows:
            d = self._symbol_from_row(r).as_dict()
            d["callers"] = r[9]
            out.append(d)
        return out

    def stats(self) -> dict:
        def count(table: str) -> int:
            return int(self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])

        langs = self.conn.execute(
            "SELECT lang, COUNT(*) FROM files GROUP BY lang ORDER BY 2 DESC"
        ).fetchall()
        return {
            "files": count("files"),
            "symbols": count("symbols"),
            "refs": count("refs"),
            "edges": count("edges"),
            "endpoints": count("endpoints"),
            "cross_language_edges": len(self.cross_language_edges()),
            "languages": {lang: n for lang, n in langs},
        }
