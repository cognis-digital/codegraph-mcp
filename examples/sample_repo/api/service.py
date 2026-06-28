"""A second back-end, in Python, serving the same /api/users/<id> route.

This makes the demo show a client edge fanning out to handlers in two
different languages (Go and Python) — the kind of blast radius that matters
when you change an API contract.
"""

from flask import Flask

app = Flask(__name__)


@app.route("/api/users/<id>", methods=["GET"])
def get_user(id):
    return lookup(id)


@app.route("/api/health")
def health():
    return "ok"


def lookup(id):
    return {"id": id, "name": normalize(id)}


def normalize(value):
    return str(value).strip()
