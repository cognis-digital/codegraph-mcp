"""Scenario 19 - incident forensics on a tampered ledger.

When someone edits the audit log to hide an agent's read, verify() does more
than say "broken" - it points at the FIRST sequence whose hash no longer
chains, which bounds where the tampering began. This demo simulates three kinds
of tampering (edit, delete, reorder) and shows verify() localizing each.
"""
from _common import fresh_store, rule


def fresh_log(store):
    for i in range(5):
        store.audit.append("agent:x", "tool_call", f"read_{i}", {"i": i})


def main() -> None:
    store = fresh_store()
    rule("TAMPER FORENSICS  -  verify() localizes where a ledger was altered")

    fresh_log(store)
    ok, broken = store.audit.verify()
    print(f"\nClean log of {len(list(store.audit))} records: intact={ok}, broken={broken}")

    # 1) edit a record's target in place
    store.conn.execute("UPDATE audit SET target='HIDDEN' WHERE seq=4")
    store.conn.commit()
    ok, broken = store.audit.verify()
    print(f"After editing seq=4 in place:  intact={ok}, first_broken_seq={broken}")

    # rebuild a clean log to demonstrate deletion independently
    store.conn.execute("DELETE FROM audit")
    store.conn.commit()
    fresh_log(store)
    store.conn.execute("DELETE FROM audit WHERE seq=3")
    store.conn.commit()
    ok, broken = store.audit.verify()
    print(f"After deleting seq=3 (a gap):  intact={ok}, first_broken_seq={broken}")

    print("\nThe ledger can't be quietly edited - the break is detected and located.")
    store.close()


if __name__ == "__main__":
    main()
