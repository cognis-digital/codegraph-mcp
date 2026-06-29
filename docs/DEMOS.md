# Demos

Five runnable scenarios in [`../demos/`](../demos/), each targeting a different
audience. Every scenario rebuilds its own throwaway graph from the bundled
polyglot sample repo, so you can run them in any order or on their own.

```bash
python demos/run_all.py          # all five, end to end
python demos/02_cross_language.py  # or just one
```

## 1. AI agent workflow — *look before you leap*
**Audience:** teams building AI coding agents.
Before an agent edits `loadUser`, it asks the graph: what is this symbol, who
calls it, what does it call, and what's the blast radius if I change it? Those
four MCP reads give the agent the contract to preserve and the tests to run —
and each read is authorized and logged.

## 2. Cross-language edges — *the dependency a context window misses*
**Audience:** polyglot teams.
A TypeScript `fetch('/api/users/:id')` is resolved to the Go, Python, Java, C#,
*and* Rust handlers that serve that route. These files share no symbol name, so
only a structural join across the HTTP boundary finds the dependency. Change the
route on either side and the graph shows the break.

## 3. Impact & refactor — *hotspots, dead code, blast radius*
**Audience:** staff engineers planning a refactor.
The three questions every refactor starts with: where does a change ripple
furthest (**hotspots**), what is safe to delete (**orphans**), and what is the
blast radius of touching a core symbol (**impact**, across languages).

## 4. Audit & compliance — *provable reads*
**Audience:** security and compliance.
Issue a scoped read-only agent token, generate audited activity, verify the
hash chain, then tamper with one row directly in the database — and watch
`verify()` catch the edit and report the first broken sequence. "Which agent
read what, and when" becomes a fact you can show a regulator.

## 5. Visualize — *the architecture map*
**Audience:** architects and reviewers.
Render the module-level architecture as Mermaid (drawn inline by GitHub) or
Graphviz DOT, with cross-language HTTP boundaries dashed and highlighted.

---

Each demo prints clear, narrated output and exits 0, so they double as smoke
tests — `tests/` covers the same code paths under `pytest`.
