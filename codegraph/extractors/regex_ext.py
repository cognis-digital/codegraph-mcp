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
    # rust
    "fn", "impl", "match", "let", "mut", "pub", "unsafe", "move", "dyn",
    "as", "where", "loop", "use", "mod", "ref",
    # java / c#
    "throw", "throws", "using", "lock", "foreach", "instanceof",
    "synchronized", "this", "super", "base", "sizeof", "nameof",
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
        """Routes found *inside* a symbol body (client calls, axum builders)."""
        return []

    def _annotation_routes(self, text: str) -> List[Tuple[int, str, str]]:
        """Routes declared as an annotation/attribute *before* a method.

        Returns (char_position, http_method, route); the engine attaches each to
        the next method symbol after that position (Spring `@GetMapping`,
        ASP.NET `[HttpGet]`, etc.).
        """
        return []

    def extract(self, text: str) -> ExtractResult:
        result = ExtractResult()
        sym_positions: List[Tuple[int, str]] = []  # (start_char, qualname)

        for kind, pat in self.def_patterns:
            for m in pat.finditer(text):
                name = m.group("name")
                start_line = _line_of(text, m.start())
                brace = text.find("{", m.end() - 1)
                semi = text.find(";", m.end() - 1)
                if brace == -1 or (semi != -1 and semi < brace):
                    # a declaration with no block body on this line: a trait/
                    # interface method signature, a unit/tuple struct, a type
                    # alias. Record the symbol but don't scan a (distant) brace.
                    result.symbols.append(
                        RawSymbol(name=name, kind=kind, start_line=start_line,
                                  end_line=start_line, signature=m.group(0).strip())
                    )
                    sym_positions.append((m.start(), name))
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
                sym_positions.append((m.start(), name))
                for c in calls:
                    result.refs.append(RawRef(name=c, line=start_line, in_symbol=qual))
                for ep in self._routes(body, qual, start_line):
                    result.endpoints.append(ep)

        # attach annotation/attribute routes to the method that follows them
        sym_positions.sort()
        for pos, method, route in self._annotation_routes(text):
            qual = self._symbol_after(sym_positions, pos)
            if qual:
                result.endpoints.append(
                    RawEndpoint("server", method, route, _line_of(text, pos), qual))
        return result

    @staticmethod
    def _symbol_after(sym_positions: List[Tuple[int, str]], pos: int) -> str | None:
        for start, name in sym_positions:
            if start >= pos:
                return name
        return None


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


class JavaExtractor(_BraceExtractor):
    """Java: classes/interfaces/enums, methods, calls, and Spring MVC routes.

    Server routes come from `@GetMapping("/x")` / `@RequestMapping(...)`
    annotations (attached to the method that follows), and client routes from
    RestTemplate/WebClient calls inside method bodies.
    """

    lang = "java"

    def __init__(self):
        self.def_patterns = [
            ("class", re.compile(r"\b(?:class|interface|enum)\s+(?P<name>[A-Za-z_]\w*)")),
            ("method", re.compile(
                r"\b(?:public|private|protected)\s+"
                r"(?:static\s+|final\s+|abstract\s+|synchronized\s+|native\s+|default\s+)*"
                r"[\w<>\[\].,?\s]+?\s+(?P<name>[A-Za-z_]\w*)\s*\([^;{]*\)")),
        ]

    _MAPPING = re.compile(
        r"@(?P<kind>Get|Post|Put|Delete|Patch|Request)Mapping\s*\(\s*"
        r"(?:value\s*=\s*|path\s*=\s*)?\"(?P<route>/[^\"]*)\"")
    _CLIENT = re.compile(
        r"\.(?:getForObject|getForEntity|postForObject|postForEntity|exchange|uri)"
        r"\s*\(\s*\"(?P<route>/[^\"]*)\"")

    def _annotation_routes(self, text: str) -> List[Tuple[int, str, str]]:
        out = []
        for m in self._MAPPING.finditer(text):
            kind = m.group("kind")
            out.append((m.start(), "ANY" if kind == "Request" else kind.upper(),
                        m.group("route")))
        return out

    def _routes(self, body: str, qual: str, base_line: int) -> List[RawEndpoint]:
        return [RawEndpoint("client", "ANY", m.group("route"),
                            base_line + body.count("\n", 0, m.start()), qual)
                for m in self._CLIENT.finditer(body)]


class CSharpExtractor(_BraceExtractor):
    """C#: classes/structs/records, methods, calls, and ASP.NET routes.

    Server routes come from `[HttpGet("/x")]` / `[Route("/x")]` attributes, and
    client routes from HttpClient calls inside method bodies.
    """

    lang = "csharp"

    def __init__(self):
        self.def_patterns = [
            ("class", re.compile(
                r"\b(?:class|interface|struct|enum|record)\s+(?P<name>[A-Za-z_]\w*)")),
            ("method", re.compile(
                r"\b(?:public|private|protected|internal)\s+"
                r"(?:static\s+|async\s+|virtual\s+|override\s+|sealed\s+|abstract\s+)*"
                r"[\w<>\[\].,?\s]+?\s+(?P<name>[A-Za-z_]\w*)\s*\([^;{]*\)")),
        ]

    _ATTR = re.compile(
        r"\[Http(?P<kind>Get|Post|Put|Delete|Patch)\s*\(\s*\"(?P<route>/[^\"]*)\"\s*\)\]"
        r"|\[Route\s*\(\s*\"(?P<route2>/[^\"]*)\"\s*\)\]")
    _CLIENT = re.compile(
        r"\.(?:GetAsync|GetStringAsync|GetFromJsonAsync|PostAsync|PostAsJsonAsync|"
        r"PutAsync|DeleteAsync)\s*\(\s*\"(?P<route>/[^\"]*)\"")

    def _annotation_routes(self, text: str) -> List[Tuple[int, str, str]]:
        out = []
        for m in self._ATTR.finditer(text):
            if m.group("route"):
                out.append((m.start(), m.group("kind").upper(), m.group("route")))
            elif m.group("route2"):
                out.append((m.start(), "ANY", m.group("route2")))
        return out

    def _routes(self, body: str, qual: str, base_line: int) -> List[RawEndpoint]:
        return [RawEndpoint("client", "ANY", m.group("route"),
                            base_line + body.count("\n", 0, m.start()), qual)
                for m in self._CLIENT.finditer(body)]


class RustExtractor(_BraceExtractor):
    """Rust: functions/methods, struct/enum/trait types, calls, and axum routes.

    Web routes are recognized from the axum builder pattern
    `.route("/path", get(handler))` (server) and `reqwest`-style client calls,
    so Rust participates in cross-language edges alongside Go/TS/Python.
    """

    lang = "rust"

    def __init__(self):
        self.def_patterns = [
            ("function", re.compile(r"\bfn\s+(?P<name>[A-Za-z_][\w]*)")),
            ("type", re.compile(r"\bstruct\s+(?P<name>[A-Za-z_][\w]*)")),
            ("type", re.compile(r"\benum\s+(?P<name>[A-Za-z_][\w]*)")),
            ("type", re.compile(r"\btrait\s+(?P<name>[A-Za-z_][\w]*)")),
        ]

    _SERVER_RE = re.compile(r"\.route\s*\(\s*\"(?P<route>/[^\"]*)\"")
    _CLIENT_RE = re.compile(
        r"\b(?:reqwest::|\w+\.)(?P<m>get|post|put|delete|patch)\s*\(\s*\"(?P<route>/[^\"]*)\"")

    def _routes(self, body: str, qual: str, base_line: int) -> List[RawEndpoint]:
        eps: List[RawEndpoint] = []
        for m in self._SERVER_RE.finditer(body):
            eps.append(RawEndpoint("server", "ANY", m.group("route"),
                                   base_line + body.count("\n", 0, m.start()), qual))
        for m in self._CLIENT_RE.finditer(body):
            eps.append(RawEndpoint("client", m.group("m").upper(), m.group("route"),
                                   base_line + body.count("\n", 0, m.start()), qual))
        return eps
