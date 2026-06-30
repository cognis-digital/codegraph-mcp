"""Scenario 12 - exporting the audit trail for an external auditor.

The audit chain is just rows: (seq, ts, actor, action, target, detail,
prev_hash, hash). This demo exports the full log to JSON Lines and shows that an
auditor can re-verify the BLAKE2b chain offline with a few lines of code - no
codegraph install, no trust in our binary.
"""
import hashlib
import json

from _common import fresh_store, rule
from codegraph.mcp_server import MCPServer


def independent_verify(records) -> bool:
    """Re-implement the chain check from scratch, as an auditor would."""
    prev = "0" * 64
    for rec in records:
        payload = {k: rec[k] for k in
                   ("seq", "ts", "actor", "action", "target", "detail", "prev_hash")}
        pre = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        h = hashlib.blake2b(digest_size=32)
        h.update(prev.encode("ascii"))
        h.update(b"\x00")
        h.update(pre)
        if h.hexdigest() != rec["hash"] or rec["prev_hash"] != prev:
            return False
        prev = rec["hash"]
    return True


def main() -> None:
    store = fresh_store()
    rule("AUDIT EXPORT  -  re-verify the chain offline, no codegraph needed")

    # generate some audited reads
    import io
    server = MCPServer(store)
    for name in ("graph_stats", "find_hotspots", "cross_language_edges"):
        server.outstream = io.StringIO()
        server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                       "params": {"name": name, "arguments": {}}})

    records = [
        {"seq": r.seq, "ts": r.ts, "actor": r.actor, "action": r.action,
         "target": r.target, "detail": r.detail, "prev_hash": r.prev_hash, "hash": r.hash}
        for r in store.audit
    ]
    print(f"\nExported {len(records)} audit records as JSON Lines (first 2 shown):")
    for rec in records[:2]:
        print("   " + json.dumps({**rec, "hash": rec["hash"][:16] + "..."}))

    print(f"\nIndependent re-verification (re-implemented hash chain): "
          f"{independent_verify(records)}")
    print("The auditor trusts the math, not our code.")
    store.close()


if __name__ == "__main__":
    main()
