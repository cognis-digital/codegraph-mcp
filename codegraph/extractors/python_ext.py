"""Python extractor built on the standard-library `ast` module.

Because we parse a real AST (not regexes), Python symbol and call extraction is
exact: we know each function/class span, its enclosing container, and every
call made inside its body. We also recognize common web-framework route
decorators and `requests`-style client calls so Python participates in
cross-language edges.
"""

from __future__ import annotations

import ast
from typing import List, Optional

from .base import ExtractResult, Extractor, RawEndpoint, RawRef, RawSymbol

# Decorators like @app.route("/x"), @router.get("/x"), @bp.post("/x")
_ROUTE_DECORATORS = {"route", "get", "post", "put", "delete", "patch"}
# Client calls like requests.get(...), httpx.post(...), session.get(...)
_CLIENT_OBJECTS = {"requests", "httpx", "session", "client", "aiohttp"}
_HTTP_METHODS = {"get", "post", "put", "delete", "patch", "head", "options"}


class PythonExtractor(Extractor):
    lang = "python"

    def extract(self, text: str) -> ExtractResult:
        result = ExtractResult()
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return result
        visitor = _Visitor(result)
        visitor.visit(tree)
        return result


def _end_line(node: ast.AST, default: int) -> int:
    return int(getattr(node, "end_lineno", None) or getattr(node, "lineno", default))


def _signature(node) -> str:
    args = [a.arg for a in node.args.args]
    if node.args.vararg:
        args.append("*" + node.args.vararg.arg)
    if node.args.kwarg:
        args.append("**" + node.args.kwarg.arg)
    prefix = "async def " if isinstance(node, ast.AsyncFunctionDef) else "def "
    return f"{prefix}{node.name}({', '.join(args)})"


class _Visitor(ast.NodeVisitor):
    def __init__(self, result: ExtractResult):
        self.result = result
        self.container_stack: List[str] = []

    @property
    def container(self) -> Optional[str]:
        return self.container_stack[-1] if self.container_stack else None

    # ---- definitions -----------------------------------------------------
    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.result.symbols.append(
            RawSymbol(
                name=node.name,
                kind="class",
                start_line=node.lineno,
                end_line=_end_line(node, node.lineno),
                container=self.container,
                signature=f"class {node.name}",
            )
        )
        self.container_stack.append(node.name)
        self.generic_visit(node)
        self.container_stack.pop()

    def _visit_func(self, node) -> None:
        kind = "method" if self.container else "function"
        qual = f"{self.container}.{node.name}" if self.container else node.name
        calls = _collect_calls(node)
        self.result.symbols.append(
            RawSymbol(
                name=node.name,
                kind=kind,
                start_line=node.lineno,
                end_line=_end_line(node, node.lineno),
                container=self.container,
                signature=_signature(node),
                calls=calls,
            )
        )
        # route decorators -> server endpoint
        for dec in node.decorator_list:
            ep = _route_from_decorator(dec, qual, node.lineno)
            if ep:
                self.result.endpoints.append(ep)
        # client http calls inside the body -> client endpoint
        for ep in _client_endpoints(node, qual):
            self.result.endpoints.append(ep)
        # references for callers()
        for name in calls:
            self.result.refs.append(RawRef(name=name, line=node.lineno, in_symbol=qual))

        self.container_stack.append(node.name)
        self.generic_visit(node)
        self.container_stack.pop()

    visit_FunctionDef = _visit_func
    visit_AsyncFunctionDef = _visit_func


def _call_name(call: ast.Call) -> Optional[str]:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _collect_calls(node) -> List[str]:
    names: List[str] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            name = _call_name(child)
            if name:
                names.append(name)
    # de-dup but preserve order
    seen = set()
    out = []
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def _str_const(node: ast.AST) -> Optional[str]:
    """A string literal, or the literal prefix of a `"/path/" + var` expression."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _str_const(node.left)
        if left is not None:
            return left
    if isinstance(node, ast.JoinedStr):  # f-string: take the leading literal
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                return value.value
    return None


def _str_arg(call: ast.Call) -> Optional[str]:
    for arg in call.args:
        s = _str_const(arg)
        if s is not None:
            return s
    return None


def _route_from_decorator(dec: ast.AST, qual: str, line: int) -> Optional[RawEndpoint]:
    if not isinstance(dec, ast.Call) or not isinstance(dec.func, ast.Attribute):
        return None
    attr = dec.func.attr
    if attr not in _ROUTE_DECORATORS:
        return None
    route = _str_arg(dec)
    if not route:
        return None
    method = "ANY" if attr == "route" else attr.upper()
    # @app.route("/x", methods=["POST"])
    for kw in dec.keywords:
        if kw.arg == "methods" and isinstance(kw.value, (ast.List, ast.Tuple)):
            vals = [e.value for e in kw.value.elts if isinstance(e, ast.Constant)]
            if vals:
                method = str(vals[0]).upper()
    return RawEndpoint(role="server", method=method, route=route, line=line, in_symbol=qual)


def _client_endpoints(node, qual: str) -> List[RawEndpoint]:
    out: List[RawEndpoint] = []
    for child in ast.walk(node):
        if not isinstance(child, ast.Call) or not isinstance(child.func, ast.Attribute):
            continue
        attr = child.func.attr
        obj = child.func.value
        obj_name = obj.id if isinstance(obj, ast.Name) else getattr(obj, "attr", "")
        if attr in _HTTP_METHODS and obj_name in _CLIENT_OBJECTS:
            route = _str_arg(child)
            if route and route.startswith("/"):
                out.append(
                    RawEndpoint(
                        role="client",
                        method=attr.upper(),
                        route=route,
                        line=getattr(child, "lineno", node.lineno),
                        in_symbol=qual,
                    )
                )
    return out
