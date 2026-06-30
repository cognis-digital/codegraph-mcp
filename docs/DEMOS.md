# Demos

Twenty runnable scenarios in [`../demos/`](../demos/), each targeting a real
audience and use case. Every scenario rebuilds its own throwaway graph (from the
bundled polyglot sample repo, a generated repo, or an inline fixture), so you can
run them in any order or on their own.

```bash
python demos/run_all.py            # all twenty, end to end
python demos/02_cross_language.py  # or just one
```

> On Windows, prefix with `PYTHONUTF8=1` so the box-drawing output renders.

Each demo prints clear, narrated output and exits 0, so they double as smoke
tests — `tests/` covers the same code paths under `pytest`.

## Core walkthrough (1–5)

### 1. AI agent workflow — *look before you leap*
**Audience:** teams building AI coding agents.
Before an agent edits `loadUser`, it asks the graph: what is this symbol, who
calls it, what does it call, and what's the blast radius if I change it? Those
four MCP reads give the agent the contract to preserve and the tests to run.

### 2. Cross-language edges — *the dependency a context window misses*
**Audience:** polyglot teams.
A TypeScript `fetch('/api/users/:id')` is resolved to the Go, Python, Java, C#,
*and* Rust handlers that serve that route. These files share no symbol name, so
only a structural join across the HTTP boundary finds the dependency.

### 3. Impact & refactor — *hotspots, dead code, blast radius*
**Audience:** staff engineers planning a refactor.
Where does a change ripple furthest (**hotspots**), what is safe to delete
(**orphans**), and what is the blast radius of touching a core symbol
(**impact**, across languages).

### 4. Audit & compliance — *provable reads*
**Audience:** security and compliance.
Issue a scoped read-only token, generate audited activity, verify the hash
chain, then tamper with one row and watch `verify()` catch it and report the
first broken sequence.

### 5. Visualize — *the architecture map*
**Audience:** architects and reviewers.
Render the module-level architecture as Mermaid (drawn inline by GitHub) or
Graphviz DOT, with cross-language HTTP boundaries dashed and highlighted.

## Integration & protocol (6–10)

### 6. MCP protocol — *the bytes on the wire*
**Audience:** MCP integrators.
Speak raw JSON-RPC 2.0 to the server in-process — `initialize`, `tools/list`,
`tools/call` — exactly what a Claude/IDE MCP client exchanges over stdio. No SDK.

### 7. Scoped tokens — *least privilege for agents*
**Audience:** platform security.
The full token lifecycle: a read token works, an audit-only token is denied on a
read tool (and the denial is logged), and revocation takes effect immediately.

### 8. Graph diff — *what changed in the shape of the code*
**Audience:** reviewers.
Break an API contract (rename a route, add a parameter) and watch the graph diff
surface the signature change, the moved endpoint, and the **broken
cross-language edge** a line diff would never connect.

### 9. Incremental index — *re-parse only what a commit touched*
**Audience:** CI / pre-commit integrations.
Build a tiny git repo, commit a change, and re-index only the delta — while the
global call/cross-language graph stays correct via a full edge rebuild.

### 10. HTTP transport — *same tools, over a socket*
**Audience:** hosts that can't spawn a subprocess.
Start the stdlib HTTP server on an ephemeral port, hit `/health`, and call a tool
with a bearer token — identical behaviour and audit log to stdio.

## Day-to-day engineering (11–15)

### 11. Find references — *the worklist for a safe rename*
**Audience:** anyone renaming a symbol.
Every reference to a name, attributed to the enclosing function — "who uses this,
and from inside what" — not just matching lines.

### 12. Audit export — *re-verify the chain offline*
**Audience:** external auditors.
Export the audit log to JSON Lines and re-implement the BLAKE2b chain check from
scratch (a dozen lines) to confirm integrity without trusting our binary.

### 13. Impact visual — *a paste-ready blast-radius diagram*
**Audience:** PR authors.
Render the blast radius of the busiest symbol as a Mermaid diagram to drop into a
pull-request description.

### 14. Endpoint inventory — *the whole API surface*
**Audience:** API gateway / security review.
Every server route grouped with its handlers (across all six languages), plus
client calls flagged as matched or unmatched.

### 15. Benchmark recall — *the headline metric, reproducibly*
**Audience:** skeptics.
Run the bundled benchmark: codegraph finds the cross-language caller 100% of the
time; a name-grep finds it 0%.

## Advanced & forensics (16–20)

### 16. Agent safe edit — *from question to a structured edit plan*
**Audience:** agent builders.
Demo 1 taken all the way to a decision: locate the symbol, read its contract,
enumerate callers/callees and blast radius, and emit a JSON edit plan with the
tests to run.

### 17. Dead-code report — *safe-to-delete, cross-language aware*
**Audience:** cleanup sprints.
Rank dead-code candidates and contrast them with a handler that *looks* unused
locally but is reached over HTTP from another language (correctly not flagged).

### 18. Polyglot symbols — *one query, six languages*
**Audience:** anyone new to the codebase.
Search the same concept across the whole repo and see the unified symbol record
the graph returns regardless of source language.

### 19. Tamper forensics — *verify() localizes the alteration*
**Audience:** incident response.
Simulate edit, delete, and reorder tampering and show `verify()` pointing at the
first broken sequence each time.

### 20. Module architecture — *the dependency map as data*
**Audience:** architects.
The module-level graph as queryable data: files, symbols, languages per module,
and the weighted call/HTTP edges between them.
