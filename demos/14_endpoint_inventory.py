"""Scenario 14 - API surface inventory.

Every HTTP route the repo serves or calls, in one place, across all six
languages - the kind of inventory you want for an API gateway config, a security
review, or onboarding. Server routes are grouped with the (possibly multiple)
handlers that serve them, and unmatched client calls are flagged.
"""
from collections import defaultdict

from _common import fresh_store, rule
from codegraph.extractors.base import normalize_route


def main() -> None:
    store = fresh_store()
    rule("ENDPOINT INVENTORY  -  the whole API surface, every language")

    servers = store.endpoints(role="server")
    clients = store.endpoints(role="client")

    by_route = defaultdict(list)
    for s in servers:
        by_route[normalize_route(s["route"])].append(s)

    print(f"\nServer routes ({len(servers)} handlers across "
          f"{len(by_route)} normalized routes):")
    for route in sorted(by_route):
        handlers = by_route[route]
        langs = sorted({h["lang"] for h in handlers})
        print(f"   {route:<22} served by {len(handlers)} handler(s) "
              f"in {', '.join(langs)}")

    print(f"\nClient calls ({len(clients)}):")
    for c in sorted(clients, key=lambda x: (x["lang"], x["route"])):
        matched = normalize_route(c["route"]) in by_route
        flag = "->matched" if matched else "->NO HANDLER (external or dead route)"
        print(f"   {c['lang']:>10} {c['symbol']:<14} {c['method']:<5} {c['route']:<20} {flag}")

    store.close()


if __name__ == "__main__":
    main()
