"""Render the run-lineage DAG as a mermaid provenance diagram."""
from __future__ import annotations

from research_os.daemon.lineage import build_lineage, lineage_to_mermaid


def test_renders_nodes_and_edge():
    manifests = [
        {"id": "r1", "name": "load", "status": "succeeded",
         "artifacts": [{"path": "a.csv", "sha256": "abc123", "change": "created"}]},
        {"id": "r2", "name": "analyze", "status": "succeeded",
         "provenance": {"inputs": {"a.csv": "abc123"}},
         "artifacts": [{"path": "fig.png", "sha256": "def456", "change": "created"}]},
    ]
    out = lineage_to_mermaid(build_lineage(manifests))
    assert out.startswith("flowchart LR")
    assert "load" in out and "analyze" in out
    assert "n_r1" in out and "n_r2" in out
    assert "-->" in out  # the dependency edge rendered


def test_empty_graph():
    out = lineage_to_mermaid({"nodes": [], "edges": []})
    assert "flowchart LR" in out
    assert "no tracked runs" in out


def test_node_ids_are_mermaid_safe():
    out = lineage_to_mermaid(build_lineage([
        {"id": "run-with.dots", "name": 'has "quotes"', "status": "running"},
    ]))
    # id sanitized, label quote-escaped — no raw double quote breaking the node
    assert "n_run_with_dots" in out


def test_roots_and_leaves_classed():
    manifests = [
        {"id": "src", "name": "s", "status": "succeeded",
         "artifacts": [{"path": "x", "sha256": "h1", "change": "created"}]},
        {"id": "end", "name": "e", "status": "succeeded",
         "provenance": {"inputs": {"x": "h1"}}},
    ]
    out = lineage_to_mermaid(build_lineage(manifests))
    assert "class n_src root" in out
    assert "class n_end leaf" in out
