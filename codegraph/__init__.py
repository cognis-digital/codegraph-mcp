"""codegraph-mcp — a no-train, on-prem code knowledge graph for AI agents.

codegraph indexes a repository into a queryable graph of symbols, callers,
and cross-language edges, then serves that graph to AI agents over the Model
Context Protocol (MCP). Every agent read is recorded in a hash-chained,
tamper-evident audit log, and access is gated by scoped, revocable tokens.

Design tenets:
  * No training. The graph is built only to answer queries. Your code is never
    used to rank, sell, or train a model, and nothing leaves the machine.
  * Overlay, not migration. Point codegraph at any existing checkout or git
    URL. You keep hosting your code wherever it already lives.
  * Provable reads. Every query an agent makes lands in an append-only,
    hash-chained ledger that can be verified offline.
"""

__version__ = "0.1.0"
__all__ = ["__version__"]
