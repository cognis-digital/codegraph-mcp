"""Visualize the code graph as Mermaid or Graphviz DOT.

The graph codegraph already builds is most useful when you can *see* it. This
module renders two views, in formats that need no extra tooling:

  * **Mermaid** — GitHub, GitLab, Obsidian and most Markdown renderers draw it
    inline, so the architecture map lives right in your README or wiki.
  * **Graphviz DOT** — pipe to `dot -Tsvg` for a publication-quality image.

Two views are offered:

  * ``project`` — the module-level architecture map (directories as nodes,
    call/HTTP edges between them). Cross-language HTTP edges are drawn dashed.
  * ``impact`` — the blast radius of a single symbol: everything that
    transitively calls it, the set that breaks if you change it.
"""

from __future__ import annotations

import re
from typing import Optional

from .graph import Store

_LANG_COLOR = {
    "python": "#3572A5", "typescript": "#2b7489", "javascript": "#f1e05a",
    "go": "#00ADD8", "rust": "#dea584", "java": "#b07219", "csharp": "#178600",
}


def _node_id(name: str) -> str:
    """A Mermaid/DOT-safe identifier for an arbitrary module path."""
    nid = re.sub(r"[^0-9A-Za-z]", "_", name)
    return "m_" + (nid or "root")


def mermaid_project(store: Store, direction: str = "LR") -> str:
    g = store.project_graph()
    lines = [f"flowchart {direction}"]
    for m in g["modules"]:
        langs = "/".join(m["languages"])
        label = f'{m["module"]}<br/>{m["files"]}f · {m["symbols"]}s · {langs}'
        lines.append(f'    {_node_id(m["module"])}["{label}"]')
    for e in g["edges"]:
        a, b = _node_id(e["from"]), _node_id(e["to"])
        if e["kind"] == "cross_lang_http":
            lines.append(f'    {a} -. "HTTP ×{e["weight"]}" .-> {b}')
        else:
            lines.append(f'    {a} -- "calls ×{e["weight"]}" --> {b}')
    # color cross-language source/target modules so the boundary pops
    lines.append("    classDef xlang stroke:#f4b400,stroke-width:3px;")
    xmods = {_node_id(e["from"]) for e in g["edges"] if e["kind"] == "cross_lang_http"}
    xmods |= {_node_id(e["to"]) for e in g["edges"] if e["kind"] == "cross_lang_http"}
    if xmods:
        lines.append("    class " + ",".join(sorted(xmods)) + " xlang;")
    return "\n".join(lines)


def mermaid_impact(store: Store, symbol_id: int, max_depth: int = 6) -> str:
    root = store.get_symbol(symbol_id)
    res = store.impact(symbol_id, max_depth)
    lines = ["flowchart TD"]
    rlabel = f'{root.name}<br/>{root.lang}' if root else str(symbol_id)
    lines.append(f'    s{symbol_id}(["{rlabel}"]):::root')
    for row in res["impacted"]:
        lines.append(f'    s{row["id"]}["{row["name"]}<br/>{row["lang"]} · depth {row["depth"]}"]')
    # edges: caller -> (something it reaches toward root); approximate by depth layering
    by_depth: dict[int, list] = {}
    for row in res["impacted"]:
        by_depth.setdefault(row["depth"], []).append(row["id"])
    prev = [symbol_id]
    for d in sorted(by_depth):
        for sid in by_depth[d]:
            for p in prev:
                lines.append(f"    s{sid} --> s{p}")
        prev = by_depth[d]
    lines.append("    classDef root fill:#f4b400,stroke:#333,stroke-width:2px;")
    return "\n".join(lines)


def dot_project(store: Store) -> str:
    g = store.project_graph()
    lines = ["digraph codegraph {", '  rankdir=LR;', '  node [shape=box,style="rounded,filled",fillcolor="#eef"];']
    for m in g["modules"]:
        langs = "/".join(m["languages"])
        color = _LANG_COLOR.get(m["languages"][0], "#eeeeff") if m["languages"] else "#eeeeff"
        lines.append(f'  {_node_id(m["module"])} [label="{m["module"]}\\n{m["files"]}f {m["symbols"]}s {langs}",fillcolor="{color}33"];')
    for e in g["edges"]:
        style = 'style=dashed,color="#f4b400",penwidth=2' if e["kind"] == "cross_lang_http" else "color=gray40"
        lbl = ("HTTP ×" if e["kind"] == "cross_lang_http" else "×") + str(e["weight"])
        lines.append(f'  {_node_id(e["from"])} -> {_node_id(e["to"])} [label="{lbl}",{style}];')
    lines.append("}")
    return "\n".join(lines)


def render(store: Store, view: str = "project", fmt: str = "mermaid",
           symbol_id: Optional[int] = None, max_depth: int = 6) -> str:
    if view == "impact":
        if symbol_id is None:
            raise ValueError("impact view requires --symbol")
        if fmt != "mermaid":
            raise ValueError("impact view is mermaid-only for now")
        return mermaid_impact(store, symbol_id, max_depth)
    if fmt == "dot":
        return dot_project(store)
    return mermaid_project(store)
