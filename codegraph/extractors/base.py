"""Extractor interface and the plain-data records extractors emit.

An extractor is given the text of one file and returns three flat lists:
symbols defined in the file, references (call sites / identifier uses), and
HTTP endpoints the file either serves or calls. The indexer is responsible for
turning that flat output into graph rows and resolving edges across files.

Keeping extractors free of any database knowledge makes them trivial to test
and to add languages to.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class RawSymbol:
    name: str
    kind: str  # function | method | class | type
    start_line: int
    end_line: int
    container: str | None = None
    signature: str | None = None
    # Names referenced *inside* this symbol's body. Used to build call edges
    # without a second pass over the file.
    calls: List[str] = field(default_factory=list)


@dataclass
class RawRef:
    name: str
    line: int
    in_symbol: str | None = None  # qualname of the enclosing symbol, if any


@dataclass
class RawEndpoint:
    role: str  # server | client
    method: str  # GET | POST | ANY ...
    route: str
    line: int
    # qualname of the symbol this endpoint belongs to; the indexer maps it to id
    in_symbol: str | None = None


@dataclass
class ExtractResult:
    symbols: List[RawSymbol] = field(default_factory=list)
    refs: List[RawRef] = field(default_factory=list)
    endpoints: List[RawEndpoint] = field(default_factory=list)


class Extractor:
    """Base class. Subclasses implement `extract`."""

    lang = "unknown"

    def extract(self, text: str) -> ExtractResult:  # pragma: no cover - interface
        raise NotImplementedError


def normalize_route(route: str) -> str:
    """Canonicalize a route so a client call and a server handler can match.

    Path parameters in different syntaxes collapse to a single placeholder:
        /users/:id        -> /users/{}
        /users/{id}       -> /users/{}
        /users/<int:id>   -> /users/{}
        /users/${userId}  -> /users/{}
    A trailing slash is dropped (except for the root path).
    """
    import re

    r = route.strip()
    # strip query string / fragments
    r = r.split("?", 1)[0].split("#", 1)[0]
    # template literal interpolation: ${...}
    r = re.sub(r"\$\{[^}]*\}", "{}", r)
    # express/koa style :param  and  flask/go style {param} / <conv:param>
    r = re.sub(r":[A-Za-z_][A-Za-z0-9_]*", "{}", r)
    r = re.sub(r"<[^>]+>", "{}", r)
    r = re.sub(r"\{[^}]*\}", "{}", r)
    if len(r) > 1:
        r = r.rstrip("/")
    if not r.startswith("/"):
        r = "/" + r
    return r
