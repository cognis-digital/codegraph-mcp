"""Scenario 4 - security & compliance.

"Which agent read what, and when?" must be a fact you can show a regulator, not
a guess. Every read lands in a hash-chained, tamper-evident audit log, and agent
tokens are scoped. This demo issues a scoped token, generates audited activity,
verifies the chain, then tampers with a row and shows the verification fail.
"""
from _common import fresh_store, rule
from codegraph.tokens import TokenStore


def main() -> None:
    store = fresh_store()
    rule("AUDIT & COMPLIANCE  -  provable reads, scoped tokens, tamper-evident")

    ts = TokenStore(store.conn)
    token, info = ts.issue("ci-readonly-agent", {"read"})
    store.audit.append("admin", "token_issue", info.label, {"scopes": sorted(info.scopes)})
    print(f"\nIssued scoped token id={info.id} label='{info.label}' scopes={sorted(info.scopes)}")
    print(f"   (only the hash is stored; the token is shown once: {token[:12]}...)")

    # simulate audited agent reads
    for action, target in [("tool_call", "search_symbols"), ("tool_call", "impact"),
                            ("tool_call", "cross_language_edges")]:
        store.audit.append("ci-readonly-agent", action, target, {"ok": True})

    print("\nRecent audit tail:")
    for r in store.audit.tail(5):
        print(f"   #{r.seq}  {r.actor:<18} {r.action:<12} {r.target:<22} {r.hash[:12]}...")

    ok, broken = store.audit.verify()
    print(f"\nverify() -> intact={ok}  first_broken_seq={broken}")

    # tamper: rewrite a row's detail directly in the DB, bypassing append()
    store.conn.execute("UPDATE audit SET target='search_symbols_HACKED' WHERE seq=("
                       "SELECT MIN(seq) FROM audit WHERE action='tool_call')")
    store.conn.commit()
    ok2, broken2 = store.audit.verify()
    print(f"After tampering one row: intact={ok2}  first_broken_seq={broken2}")
    print("\nThe chain catches the edit - you can prove the log was not altered.")
    store.close()


if __name__ == "__main__":
    main()
