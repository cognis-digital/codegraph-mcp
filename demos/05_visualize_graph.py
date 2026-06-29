"""Scenario 5 - architects & reviewers.

A graph is most useful when you can see it. codegraph renders the module-level
architecture as Mermaid (drawn inline by GitHub/GitLab/Obsidian) or Graphviz
DOT. Cross-language HTTP edges are dashed and highlighted so the polyglot
boundaries jump out.
"""
from _common import fresh_store, rule
from codegraph.viz import mermaid_project, dot_project


def main() -> None:
    store = fresh_store()
    rule("VISUALIZE  -  the architecture map, as Mermaid and DOT")

    print("\nMermaid (paste into any Markdown file - it renders inline):\n")
    print("```mermaid")
    print(mermaid_project(store))
    print("```")

    print("\nGraphviz DOT (pipe to `dot -Tsvg` for a poster-quality image):\n")
    print(dot_project(store)[:600] + "\n   ...")
    store.close()


if __name__ == "__main__":
    main()
