"""Scenario 8 - reviewers diffing a change.

A line diff tells you what text changed. A *graph* diff tells you what changed
in the shape of the code: symbols added/removed, signatures changed, endpoints
moved, and - uniquely - cross-language dependencies added or broken. Here we
break an API contract and watch the graph diff surface the cross-language fallout.
"""
import os
import tempfile

from _common import rule
from codegraph.diff import diff_paths


def write(d, rel, text):
    p = os.path.join(d, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)


def main() -> None:
    rule("GRAPH DIFF  -  what changed in the *shape* of the code")
    a = tempfile.mkdtemp(prefix="cg_diff_a_")
    b = tempfile.mkdtemp(prefix="cg_diff_b_")

    # BEFORE: a TS client and a Python handler agree on /api/users/{id}
    write(a, "web/client.ts",
          "export async function loadUser(id) {\n"
          "  return fetch(`/api/users/${id}`);\n}\n")
    write(a, "api/svc.py",
          "@app.route('/api/users/<id>')\ndef get_user(id):\n    return id\n")

    # AFTER: the backend route is renamed to /api/accounts/{id} -> edge breaks,
    # and get_user gains a parameter.
    write(b, "web/client.ts",
          "export async function loadUser(id) {\n"
          "  return fetch(`/api/users/${id}`);\n}\n")
    write(b, "api/svc.py",
          "@app.route('/api/accounts/<id>')\ndef get_user(id, fields):\n    return id\n")

    d = diff_paths(a, b)
    s = d["summary"]
    print(f"\nsignature changes: {s['signatures_changed']}")
    for c in d["symbols"]["signature_changed"]:
        print(f"   {c['symbol']}: {c['old_signature']}  ->  {c['new_signature']}")
    print(f"\nendpoints removed: {s['endpoints_removed']}, added: {s['endpoints_added']}")
    for e in d["endpoints"]["removed"]:
        print(f"   - {e['method']} {e['route']} ({e['symbol']})")
    for e in d["endpoints"]["added"]:
        print(f"   + {e['method']} {e['route']} ({e['symbol']})")
    print(f"\ncross-language edges removed: {s['cross_language_edges_removed']}")
    for e in d["cross_language_edges"]["removed"]:
        print(f"   BROKEN: {e['from']} -> {e['to']}")
    print("\nThe TS client still calls the old route - the graph diff caught the break a "
          "line diff would never connect.")


if __name__ == "__main__":
    main()
