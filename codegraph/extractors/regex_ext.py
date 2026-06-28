"""Regex/brace-scan extractors for JavaScript, TypeScript, and Go.

These languages don't ship a parser in the Python stdlib, so rather than pull
in a heavy native dependency (tree-sitter et al.) for a v0.1, we use targeted
patterns plus a brace scanner to find each symbol's body. That body text is
reused to collect call sites and HTTP routes, which keeps the extractor a
single pass and good enough to demonstrate real cross-language edges. The
extractor interface is identical to the AST-based one, so a stronger backend
can be dropped in later without touching the indexer.
"""

from __future__ import annotations

import re
from typing import List, Tuple

from .base import ExtractResult, Extractor, RawEndpoint, RawRef, RawSymbol

_CALL_RE = re.compile(r"\b([A-Za-z_$][\w$]*)\s*\(")
_CALL_KEYWORDS = {
    "if", "for", "while", "switch", "catch", "return", "function", "await",
    "typeof", "new", "func", "go", "defer", "make", "len", "cap", "append",
    "print", "println", "panic", "recover", "range", "select", "case",
}


def _find_body(text: str, open_idx: int) -> Tuple[int, int]:
    """Given the index of an opening brace, return (close_idx, end_line_offset).

    Counts braces while skipping the contents of string and char literals and
    line/block comments so braces inside them don't unbalance the scan.
    """
    depth = 0
    i = open_idx
    n = len(text)
    newlines = 0
    while i < n:
        c = text[i]
        if c == "\n":
            newlines += 1
            i += 1
            continue
        if c in "\"'`":
            quote = c
            i += 1
            while i < n and text[i] != quote:
                if text[i] == "\\":
                    i += 1
                elif text[i] == "\n":
                    newlines += 1
                i += 1
            i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                if text[i] == "\n":
                    newlines += 1
                i += 1
            i += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i, newlines
        i += 1
    return n - 1, newlines


def _line_of(text: str, idx: int) -> int:
    return text.count("\n", 0, idx) + 1


def _collect_calls(body: str) -> List[str]:
    seen = set()
    out: List[str] = []
    for m in _CALL_RE.finditer(body):
        name = m.group(1)
        if name in _CALL_KEYWORDS or name in seen:
            continue
        seen.add(name)
        out.append(name)
    return out


class _BraceExtractor(Extractor):
    """Shared machinery; subclasses provide the definition patterns + routes."""

    def_patterns: List[Tuple[str, re.Pattern]] = []

    def _routes(self, body: str, qual: str, base_line: int) -> List[RawEndpoint]:
        return []

    def extract(self, text: str) -> ExtractResult:
        result = ExtractResult()
        claimed: List[Tuple[int, int]] = []  # (start_idx, end_idx) of nested bodies

        for kind, pat in self.def_patterns:
            for m in pat.finditer(text):
                name = m.group("name")
                start_line = _line_of(text, m.start())
                brace = text.find("{", m.end() - 1)
                if brace == -1:
                    # e.g. an interface/type alias without a block on this line
                    result.symbols.append(
                        RawSymbol(name=name, kind=kind, start_line=start_line,
                                  end_line=start_line, signature=m.group(0).strip())
                    )
                    continue
                close, nl = _find_body(text, brace)
                end_line = start_line + nl
                body = text[brace + 1:close]
                calls = _collect_calls(body)
                qual = name
                result.symbols.append(
                    RawSymbol(
                        name=name, kind=kind, start_line=start_line, end_line=end_line,
                        signature=m.group(0).strip().rstrip("{").strip(), calls=calls,
                    )
                )
                for c in calls:
                    result.refs.append(RawRef(name=c, line=start_line, in_symbol=qual))
                for ep in self._routes(body, qual, start_line):
                    result.endpoints.append(ep)
        return result


class JsExtractor(_BraceExtractor):
    def __init__(self, lang: str = "javascript"):
        self.lang = lang
        self.def_patterns = [
            ("function", re.compile(r"\bfunction\s+(?P<name>[A-Za-z_$][\w$]*)\s*\(")),
            ("function", re.compile(
                r"\b(?:export\s+)?(?:const|let|var)\s+(?P<name>[A-Za-z_$][\w$]*)\s*=\s*"
                r"(?:async\s*)?\([^)]*\)\s*=>\s*\{")),
            ("class", re.compile(r"\bclass\s+(?P<name>[A-Za-z_$][\w$]*)")),
        ]

    _SERVER_RE = re.compile(
        r"\b(?:app|router|api|server)\.(?P<m>get|post|put|delete|patch|all|use)\s*\(\s*"
        r"[\"'`](?P<route>/[^\"'`]*)[\"'`]")
    _FETCH_RE = re.compile(r"\bfetch\s*\(\s*[\"'`](?P<route>/[^\"'`]*)[\"'`]")
    _AXIOS_RE = re.compile(
        r"\baxios(?:\.(?P<m>get|post|put|delete|patch))?\s*\(\s*"
        r"[\"'`](?P<route>/[^\"'`]*)[\"'`]")

    def _routes(self, body: str, qual: str, base_line: int) -> List[RawEndpoint]:
        eps: List[RawEndpoint] = []
        for m in self._SERVER_RE.finditer(body):
            method = m.group("m").upper()
            method = "ANY" if method in ("ALL", "USE") else method
            eps.append(RawEndpoint("server", method, m.group("route"),
                                   base_line + body.count("\n", 0, m.start()), qual))
        for m in self._FETCH_RE.finditer(body):
            eps.append(RawEndpoint("client", "ANY", m.group("route"),
                                   base_line + body.count("\n", 0, m.start()), qual))
        for m in self._AXIOS_RE.finditer(body):
            method = (m.group("m") or "ANY").upper()
            eps.append(RawEndpoint("client", method, m.group("route"),
                                   base_line + body.count("\n", 0, m.start()), qual))
        return eps


class GoExtractor(_BraceExtractor):
    lang = "go"

    def __init__(self):
        self.def_patterns = [
            ("method", re.compile(
                r"\bfunc\s*\([^)]*\)\s*(?P<name>[A-Za-z_][\w]*)\s*\(")),
            ("function", re.compile(r"\bfunc\s+(?P<name>[A-Za-z_][\w]*)\s*\(")),
            ("type", re.compile(
                r"\btype\s+(?P<name>[A-Za-z_][\w]*)\s+(?:struct|interface)\s*\{")),
        ]

    _SERVER_RE = re.compile(
        r"\b(?:http\.HandleFunc|\w+\.HandleFunc|\w+\.Handle|"
        r"\w+\.(?:GET|POST|PUT|DELETE|PATCH))\s*\(\s*"
        r"[\"`](?P<route>/[^\"`]*)[\"`]")
    _CLIENT_RE = re.compile(
        r"\bhttp\.(?P<m>Get|Post|Put|Delete|Head)\s*\(\s*[\"`](?P<route>/[^\"`]*)[\"`]")

    def _routes(self, body: str, qual: str, base_line: int) -> List[RawEndpoint]:
        eps: List[RawEndpoint] = []
        for m in self._SERVER_RE.finditer(body):
            eps.append(RawEndpoint("server", "ANY", m.group("route"),
                                   base_line + body.count("\n", 0, m.start()), qual))
        for m in self._CLIENT_RE.finditer(body):
            eps.append(RawEndpoint("client", m.group("m").upper(), m.group("route"),
                                   base_line + body.count("\n", 0, m.start()), qual))
        return eps
