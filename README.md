# codegraph-mcp

[![CI](https://github.com/cognis-digital/codegraph-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/cognis-digital/codegraph-mcp/actions/workflows/ci.yml)

**A no-train, on-prem code knowledge graph that you serve to AI agents over MCP — with a hash-chained audit row for every read.**

AI coding agents are only as good as the code understanding you can hand them. The cloud assistants solve this by ingesting your repositories into their own infrastructure — which is a non-starter for any team whose code can't leave the building. `codegraph-mcp` gives those teams the same structural code intelligence **without the trust trade-off**:

- **No training, ever.** The graph exists only to answer queries. Your code is never used to rank, sell, recommend, or train a model, and nothing leaves the machine.
- **Overlay, not migration.** Point it at any checkout or git URL. Keep hosting your code exactly where it already lives — GitHub, GitLab, an internal mirror, an air-gapped drive.
- **Provable reads.** Every query an agent makes is appended to a tamper-evident, hash-chained audit log you can verify offline. "Which agent read what, and when" becomes a fact you can show a regulator, not a guess.
- **Zero heavy dependencies.** Pure Python standard library + SQLite. One file is the whole graph. Trivial to vet, back up, and run in a restricted network.

Architecture comprehension — *how the pieces connect* — is what actually helps an agent, and independent research keeps finding it beats stuffing a giant context window with raw files. `codegraph-mcp` builds that comprehension as a graph and exposes it as MCP tools.

---

## What it does

On every push or re-index, `codegraph-mcp` parses your source and builds a queryable graph of:

- **Symbols** — functions, methods, classes, and types, with signatures and exact locations.
- **Call edges** — who calls whom, within and across files.
- **Cross-language edges** — the edge nobody else resolves: a TypeScript `fetch('/api/users/:id')` linked to the Go *and* Python handlers that serve that route. These files share no symbol name, so only a structural join finds the dependency.
- **References** — every call site / use of a name.

Then it answers the questions an agent (or a human) actually asks: *find this symbol, who calls it, what's the blast radius if I change it, what crosses a language boundary here.*

## Quick start

```bash
git clone https://github.com/cognis-digital/codegraph-mcp
cd codegraph-mcp
pip install -e .          # or just run via `python -m codegraph`

# 1. Index any repo (a local path, or a git URL it clones read-only)
codegraph index ./examples/sample_repo --db graph.db
codegraph index https://github.com/your-org/your-service.git --db graph.db

# 2. Query the graph
codegraph query search loadUser --db graph.db
codegraph query impact 7 --db graph.db          # transitive callers ("blast radius")
codegraph query xlang --db graph.db             # cross-language HTTP edges

# 3. Serve it to an agent over MCP — stdio or HTTP
codegraph token issue ci-agent --scopes read --db graph.db   # prints a bearer token
codegraph serve --db graph.db --token cg_XXXX                 # stdio
codegraph serve --db graph.db --http --port 8765 --require-token   # HTTP (POST /mcp)

# Diff the graph between two git refs — what changed in the *shape* of the code
codegraph diff main feature/x --repo .

# 4. Prove what happened
codegraph audit --db graph.db -n 20
codegraph audit --db graph.db --verify          # replays the hash chain
```

### See it work in 5 seconds

```bash
python demo.py
```

```
== cross-language edges (client -> handler) ==
  loadUser (typescript)  ->  get_user (python)   [ANY /api/users/${userId} -> GET /api/users/<id>]
  loadUser (typescript)  ->  routes (go)         [ANY /api/users/${userId} -> ANY /api/users/{id}]
  checkHealth (typescript) -> health (python)    [ANY /api/health -> ANY /api/health]
  ...
== blast radius of the Python get_user handler ==
  depth 1: loadUser (typescript) @ web/client.ts:10
== audit log is intact and tamper-evident ==
  verify() -> intact=True first_broken=None
```

## MCP tools

When you run `codegraph serve`, the following tools are advertised to the agent host over MCP (`initialize` → `tools/list` → `tools/call`). Every call is scope-checked and audited.

| Tool | Purpose |
|------|---------|
| `search_symbols` | Find symbols by name substring (optionally filter by kind). |
| `get_symbol` | Full record for one symbol id (signature, location, container). |
| `find_references` | Every call site / use of a name. |
| `find_callers` | Direct callers of a symbol — **includes cross-language edges**. |
| `find_callees` | What a symbol calls. |
| `impact_analysis` | Transitive callers — the blast radius of a change. |
| `cross_language_edges` | All resolved cross-language HTTP edges. |
| `find_orphans` | Dead-code candidates: functions/methods with no callers and not HTTP entrypoints. |
| `find_hotspots` | Most depended-on symbols (highest caller count) — where changes ripple furthest. |
| `graph_stats` | File / symbol / edge / language counts. |

The server speaks plain JSON-RPC 2.0 — no proprietary transport, no SDK to audit — over **either stdio or HTTP**. Point a subprocess-style host at `codegraph serve`, or an HTTP host at `codegraph serve --http` (bearer token via `Authorization: Bearer …`, `GET /health` for readiness). Both transports share the exact same dispatch, scope checks, and audit logging.

## Graph diff

`codegraph diff <refA> <refB>` compares the knowledge graph between two git refs and reports what changed in the **shape** of the code — not the text:

```bash
codegraph diff main feature/x --repo .
```

```json
{ "summary": { "symbols_added": 3, "symbols_removed": 1, "signatures_changed": 2,
               "endpoints_added": 1, "cross_language_edges_added": 1, ... },
  "cross_language_edges": { "added": [ { "from": "load (typescript)", "to": "get_item (python)" } ] } }
```

That last line is the one a text diff can never give you: a front-end change and a back-end change in the same PR were **newly wired together across a language boundary**. Reviewers see the contract that just formed.

## Security model

- **Scoped, revocable tokens.** Agents authenticate with a bearer token mapped to scopes (`read`, `audit`, `admin`). Only a salted BLAKE2b hash of each token is stored, so a database leak doesn't leak usable credentials. Revocation is immediate.
- **Tamper-evident audit log.** Each record's hash commits to the previous record's hash (BLAKE2b over a canonical JSON encoding). Altering, inserting, or deleting any historical record breaks the chain, and `audit --verify` reports the first broken sequence number. The scheme is simple enough to re-implement in any language for independent verification.
- **Local by construction.** SQLite file, standard library only, no outbound network calls except an explicit, read-only `git clone` when you index a remote.

## Language support

| Language | Backend | Symbols | Calls | HTTP routes |
|----------|---------|:-------:|:-----:|:-----------:|
| Python | `ast` (exact) | ✓ | ✓ | ✓ (decorators + `requests`/`httpx`) |
| JavaScript / TypeScript | regex + brace scan | ✓ | ✓ | ✓ (`fetch`/`axios` + `app`/`router`) |
| Go | regex + brace scan | ✓ | ✓ | ✓ (`HandleFunc`/gin/echo + `http.Get`) |
| Rust | regex + brace scan | ✓ | ✓ | ✓ (axum `.route` + `reqwest`) |
| Java | regex + brace scan | ✓ | ✓ | ✓ (Spring `@GetMapping` + RestTemplate/WebClient) |
| C# | regex + brace scan | ✓ | ✓ | ✓ (ASP.NET `[HttpGet]`/`[Route]` + HttpClient) |

**Six languages, with cross-language edges resolved between any of them** — a single TypeScript `fetch('/api/users/:id')` resolves to the Python, Go, Rust, Java, *and* C# handlers serving that route. The extractor interface is language-agnostic; adding a language (or swapping in a tree-sitter backend for one) doesn't touch the indexer or the graph.

## Benchmark

The graph earns its keep on the dependency no text search can see: a front-end caller and the back-end handler it depends on share **no symbol name**, only a route. `bench/benchmark.py` generates a multi-language repo and measures how often each strategy finds that cross-language dependency:

```bash
python bench/benchmark.py --services 120
```

```
## cross-language dependency recall
  (find the front-end caller that breaks if a back-end handler changes)
  codegraph (graph impact):   120/120
  grep by symbol name:        0/120
  grep by route substring:    120/120 (files only, not symbols)
```

**100% vs 0%.** A symbol-name search can't cross the language boundary at all; a route-substring search finds *files* but not the symbol-level, transitive impact you actually need. The graph gives you both. (This is the "Navigation Paradox" — independent research finds graph-structured navigation beats retrieval/long-context on exactly these hidden-dependency tasks.)

## How it compares

Cloud code assistants give you great comprehension but require sending your code to their infrastructure, where it may be retained or used to improve a model. Self-hosted forges give you control but make you migrate your hosting to get the indexed graph. `codegraph-mcp` deliberately splits the difference: **the comprehension layer is the product, the graph never trains anything, and it overlays the repos you already have.**

| | Cloud assistant | Self-hosted forge | **codegraph-mcp** |
|---|---|---|---|
| Code leaves your machine | yes | no | **no** |
| Used to train a model | often | sometimes | **never** |
| Requires migrating your hosting | no | **yes** | **no — overlays existing repos** |
| Tamper-evident audit of agent reads | no | roadmap | **shipped** |
| Cross-language dependency graph | partial | Go + TS | **6 langs: Py · JS/TS · Go · Rust · Java · C#** |
| Runs air-gapped | no | heavy (DB + services) | **single file, stdlib + SQLite** |
| Published benchmark | — | none | **yes (reproducible)** |

The overlay model is the wedge: you get the indexed graph and the audit trail **without leaving GitHub/GitLab**, and the audit is tamper-evident *today*, not on a roadmap.

## Testing

```bash
pip install -e ".[dev]"
pytest -q          # 46 tests
```

## License

Apache-2.0. © Cognis Digital.

> Status: v0.1 — runnable and tested. HTTP transport and KG diff are shipped. Roadmap: more languages (Ruby, Kotlin, PHP), incremental per-commit indexing, and a project-graph (module/package) view.
