"""Run lineage graph — the provenance DAG (Phase 1.13).

DESIGN_V4.md feature #7. Individual runs are recorded (Phase 1.7) and
comparable (1.12), but research is a *chain*: run A produces a cleaned
dataset, run B trains on it, run C plots B's output. When a result is
questioned ("where did fig3 come from?") or an input changes ("I re-ran
the cleaning step — what's now stale?"), you need the graph, not the
list.

The link is **content-addressed and exact**, requiring no manual
declaration: run B depends on run A iff one of B's recorded input hashes
equals one of A's recorded output (artifact) hashes. Because every run
already hashes its inputs (provenance.inputs) and outputs (artifacts),
the DAG falls out of data we're already capturing — no new bookkeeping,
no guessing.

Pure, stdlib-only, fully testable. The daemon method + CLI are thin
wrappers over ``build_lineage``.
"""
from __future__ import annotations

from typing import Any


def _artifact_hashes(manifest: dict) -> dict[str, str]:
    """Map output artifact path -> sha256 for a run manifest.

    Only artifacts that were created/modified carry a meaningful hash;
    deleted artifacts have no content to link on.
    """
    out: dict[str, str] = {}
    for art in manifest.get("artifacts") or []:
        sha = art.get("sha256")
        path = art.get("path")
        if sha and path and art.get("change") != "deleted":
            out[path] = sha
    return out


def _input_hashes(manifest: dict) -> dict[str, str]:
    """Map input path -> sha256 for a run manifest (from provenance)."""
    prov = manifest.get("provenance") or {}
    inputs = prov.get("inputs") or {}
    # inputs is {path: 'sha256:...'} already.
    return {p: h for p, h in inputs.items() if h}


def _run_id(manifest: dict) -> str:
    return manifest.get("id") or manifest.get("run_id") or "?"


def build_lineage(manifests: list[dict]) -> dict[str, Any]:
    """Compute the content-addressed run dependency DAG.

    Args:
        manifests: run manifests (each with ``id``, ``artifacts``,
            ``provenance.inputs``). Order-independent.

    Returns a dict:
        nodes:  [{id, name, status, started, n_inputs, n_outputs}]
        edges:  [{from, to, via}] — ``from`` produced an artifact whose
                hash matches an input of ``to``; ``via`` lists the
                (producer_path, consumer_path, sha) matches.
        roots:  ids with no incoming edge (pure sources).
        leaves: ids with no outgoing edge (terminal results).
        orphans: ids with no edges at all (unlinked runs).
    """
    # Index: sha256 -> [(run_id, output_path)] for every produced artifact.
    producers: dict[str, list[tuple[str, str]]] = {}
    for m in manifests:
        rid = _run_id(m)
        for path, sha in _artifact_hashes(m).items():
            producers.setdefault(sha, []).append((rid, path))

    nodes: list[dict] = []
    for m in manifests:
        rid = _run_id(m)
        spec = m.get("spec") or {}
        nodes.append({
            "id": rid,
            "name": m.get("name") or spec.get("cmd") or rid,
            "status": m.get("status", "?"),
            "started": m.get("started_at") or m.get("created_at"),
            "n_inputs": len(_input_hashes(m)),
            "n_outputs": len(_artifact_hashes(m)),
        })

    # Edges: for each run's inputs, find any producer of that exact hash.
    # Skip self-links (a run consuming its own output).
    edges: list[dict] = []
    edge_index: dict[tuple[str, str], list[dict]] = {}
    for m in manifests:
        consumer = _run_id(m)
        for in_path, in_sha in _input_hashes(m).items():
            for prod_id, prod_path in producers.get(in_sha, []):
                if prod_id == consumer:
                    continue
                key = (prod_id, consumer)
                match = {
                    "producer_path": prod_path,
                    "consumer_path": in_path,
                    "sha256": in_sha,
                }
                edge_index.setdefault(key, []).append(match)

    for (frm, to), matches in edge_index.items():
        edges.append({"from": frm, "to": to, "via": matches})

    all_ids = {_run_id(m) for m in manifests}
    has_incoming = {e["to"] for e in edges}
    has_outgoing = {e["from"] for e in edges}
    linked = has_incoming | has_outgoing

    return {
        "nodes": nodes,
        "edges": edges,
        "roots": sorted(all_ids - has_incoming - (all_ids - linked)),
        "leaves": sorted(all_ids - has_outgoing - (all_ids - linked)),
        "orphans": sorted(all_ids - linked),
        "counts": {
            "runs": len(all_ids),
            "edges": len(edges),
            "linked": len(linked),
        },
    }


def ancestors(lineage: dict, run_id: str) -> list[str]:
    """All runs transitively upstream of ``run_id`` (its provenance chain).

    Answers "where did this result come from?" — every run whose output
    fed, directly or indirectly, into ``run_id``.
    """
    parents: dict[str, set[str]] = {}
    for e in lineage.get("edges", []):
        parents.setdefault(e["to"], set()).add(e["from"])
    seen: set[str] = set()
    stack = list(parents.get(run_id, set()))
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        stack.extend(parents.get(cur, set()))
    return sorted(seen)


def descendants(lineage: dict, run_id: str) -> list[str]:
    """All runs transitively downstream of ``run_id``.

    Answers "if I re-run this, what becomes stale?" — every run that
    consumed, directly or indirectly, an output of ``run_id``.
    """
    children: dict[str, set[str]] = {}
    for e in lineage.get("edges", []):
        children.setdefault(e["from"], set()).add(e["to"])
    seen: set[str] = set()
    stack = list(children.get(run_id, set()))
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        stack.extend(children.get(cur, set()))
    return sorted(seen)


def topo_order(lineage: dict, subset: "set[str] | None" = None) -> list[str]:
    """Topologically sort runs so producers come before consumers.

    Restricted to ``subset`` when given (edges to runs outside the subset
    are ignored for ordering, but still respected as prerequisites already
    satisfied). Within a dependency tier, ids are sorted for determinism.
    A cycle (should never happen — lineage is content-addressed and
    acyclic by construction) degrades gracefully: cyclic remainder is
    appended in sorted order rather than dropped.

    This is the order a selective re-run must follow: rebuild an upstream
    result before the downstream run that consumes it.
    """
    ids = {n["id"] for n in lineage.get("nodes", [])}
    if subset is not None:
        ids = ids & subset

    # parents within the working set
    parents: dict[str, set[str]] = {i: set() for i in ids}
    children: dict[str, set[str]] = {i: set() for i in ids}
    for e in lineage.get("edges", []):
        frm, to = e["from"], e["to"]
        if frm in ids and to in ids:
            parents[to].add(frm)
            children[frm].add(to)

    # Kahn's algorithm, deterministic tie-break.
    ready = sorted(i for i in ids if not parents[i])
    out: list[str] = []
    indeg = {i: len(parents[i]) for i in ids}
    while ready:
        cur = ready.pop(0)
        out.append(cur)
        newly: list[str] = []
        for c in children[cur]:
            indeg[c] -= 1
            if indeg[c] == 0:
                newly.append(c)
        if newly:
            ready = sorted(ready + newly)

    if len(out) < len(ids):  # cycle fallback — never expected
        out.extend(sorted(ids - set(out)))
    return out
