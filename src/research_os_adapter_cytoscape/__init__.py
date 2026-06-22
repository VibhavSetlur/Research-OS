"""Cytoscape session (.cys) adapter.

Detects:
    * `.cys` files (Cytoscape session archives) anywhere under
      `workspace/` or `scratch/` in the project root.

A `.cys` file is a zip archive containing:
    * one or more `.xgmml` network files (XML graph markup)
    * `.cytable` tabular attribute files
    * `properties` text files describing visual styles + layout

This adapter parses `.cys` archives with the stdlib `zipfile` +
`xml.etree.ElementTree` modules only — no Cytoscape installation,
no Java runtime, and no `py4cytoscape` are required at detect()
or extract() time.

Per network extracted:
    * name
    * node count
    * edge count
    * node attribute schema (list of {name, type})
    * edge attribute schema (list of {name, type})
    * layout algorithm (best-effort, parsed from session properties)

Limitations (documented in the returned `_notes` field):
    * Cytoscape's `.cys` format is not formally specified outside of
      the Cytoscape source — the embedded XGMML + cytable layout has
      shifted between Cytoscape 2.x, 3.x, and 3.10+. The parser is
      tolerant of missing files but may miss session-wide settings
      that live under bespoke binary blobs (e.g. compiled VizMap
      style serialisations).
    * Visual styles are surfaced only by their declared `name`
      attribute; per-visual-property bindings (mapper functions) are
      NOT decoded.
    * Layout coordinates inside the XGMML are preserved by the
      static-export tool but not promoted to the extract() payload.

Optional tools:
    * tool_cytoscape_export_static(cys_file, output_path?, network?)
      — extracts the embedded XGMML, builds a `networkx` graph, and
      renders a static PNG/SVG with matplotlib. Degrades gracefully
      (writes a placeholder `.md` note) when matplotlib or networkx
      are unavailable.
"""
from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any

from research_os.adapters import (
    AdapterRegistration,
    AdapterTool,
    err_envelope as _err,
    ok_envelope as _ok,
    register_adapter,
)


__version__ = "1.8.0"

log = logging.getLogger(__name__)


# A .cys is an untrusted zip a researcher may have downloaded or received
# from a collaborator. Cap the decompressed size of any single member so a
# small archive whose member inflates to many GB (zip-bomb / zip-
# amplification) cannot exhaust memory before parsing. Mirrors the sibling
# adapters' size-cap pattern.
_MAX_MEMBER_BYTES = 100 * 1024 * 1024  # 100 MiB


def _safe_zip_read(zf: zipfile.ZipFile, name: str) -> bytes | None:
    """Read a zip member with a hard decompressed-size cap.

    Returns ``None`` (and logs) when the member's declared size exceeds the
    cap, or when the actual decompressed stream runs past the cap (defends
    against a spoofed ``ZipInfo.file_size``). Never reads an unbounded
    amount into memory.
    """
    try:
        info = zf.getinfo(name)
    except (KeyError, zipfile.BadZipFile):
        return None
    if info.file_size > _MAX_MEMBER_BYTES:
        log.debug(
            "skipping oversized member %s (%d bytes > cap %d)",
            name, info.file_size, _MAX_MEMBER_BYTES,
        )
        return None
    try:
        with zf.open(name) as fh:
            data = fh.read(_MAX_MEMBER_BYTES + 1)
    except (KeyError, zipfile.BadZipFile, OSError) as exc:
        log.debug("could not read %s: %s", name, exc)
        return None
    if len(data) > _MAX_MEMBER_BYTES:
        log.debug("member %s exceeded cap during read; dropping", name)
        return None
    return data


def _resolve_inside_root(root: Path, candidate: str) -> Path | None:
    """Resolve ``candidate`` and require it to stay inside ``root``.

    Rejects absolute paths and ``..`` traversal that escape the project
    root (zip-slip / arbitrary-write), mirroring the central
    ``server.handlers.meta_workspace._resolve_inside_root`` guard. Returns
    ``None`` on escape; a resolved absolute Path otherwise.
    """
    root_r = root.resolve()
    p = Path(candidate)
    resolved = p.resolve() if p.is_absolute() else (root_r / p).resolve()
    try:
        resolved.relative_to(root_r)
    except ValueError:
        return None
    return resolved


# ── detection ─────────────────────────────────────────────────────────


def _candidate_cys(root: Path) -> list[Path]:
    """Return all `.cys` files under workspace/ + scratch/ + project root."""
    found: list[Path] = []
    search_dirs = [root / "workspace", root / "scratch", root]
    seen: set[Path] = set()
    for d in search_dirs:
        if not d.exists():
            continue
        try:
            for p in d.rglob("*.cys"):
                if not p.is_file():
                    continue
                rp = p.resolve()
                if rp in seen:
                    continue
                seen.add(rp)
                found.append(p)
        except Exception:
            continue
    return found


def detect(root: Path) -> bool:
    return bool(_candidate_cys(root))


# ── extraction ────────────────────────────────────────────────────────


# Strip XML namespace from a tag — XGMML uses
# `http://www.cs.rpi.edu/XGMML` plus an arbitrary number of style /
# graphics sub-namespaces that vary by Cytoscape version.
_NS_RE = re.compile(r"^\{[^}]+\}")


def _localname(tag: str) -> str:
    return _NS_RE.sub("", tag or "")


def _xgmml_attr_type(att_elem: ET.Element) -> str:
    """Return the declared type of an XGMML <att> element."""
    return (att_elem.get("type") or att_elem.get("cy:type") or "string").lower()


def _parse_xgmml(data: bytes) -> dict[str, Any] | None:
    """Parse a single XGMML payload into our network summary dict."""
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        log.debug("xgmml parse failed: %s", exc)
        return None

    if _localname(root.tag) != "graph":
        # Some Cytoscape exports wrap the graph one level down.
        graph = None
        for child in root.iter():
            if _localname(child.tag) == "graph":
                graph = child
                break
        if graph is None:
            return None
        root = graph

    name = (
        root.get("label")
        or root.get("name")
        or root.get("id")
        or "unnamed"
    )

    node_attrs: dict[str, str] = {}
    edge_attrs: dict[str, str] = {}
    nodes = 0
    edges = 0
    for child in root:
        local = _localname(child.tag)
        if local == "node":
            nodes += 1
            for att in child:
                if _localname(att.tag) != "att":
                    continue
                key = att.get("name")
                if not key:
                    continue
                node_attrs.setdefault(key, _xgmml_attr_type(att))
        elif local == "edge":
            edges += 1
            for att in child:
                if _localname(att.tag) != "att":
                    continue
                key = att.get("name")
                if not key:
                    continue
                edge_attrs.setdefault(key, _xgmml_attr_type(att))

    return {
        "name": name,
        "nodes": nodes,
        "edges": edges,
        "node_attributes": [{"name": k, "type": v} for k, v in node_attrs.items()],
        "edge_attributes": [{"name": k, "type": v} for k, v in edge_attrs.items()],
    }


_LAYOUT_PROP_RE = re.compile(
    r"(?:layout(?:Algorithm)?|preferredLayoutAlgorithm)\s*=\s*(\S+)",
    re.IGNORECASE,
)


def _scan_layout(text: str) -> str | None:
    m = _LAYOUT_PROP_RE.search(text)
    if m:
        return m.group(1).strip()
    return None


_STYLE_NAME_RE = re.compile(r'visualStyle\s+name\s*=\s*"([^"]+)"', re.IGNORECASE)


def _scan_visual_style_names(text: str) -> list[str]:
    return _STYLE_NAME_RE.findall(text)


def _parse_cys(path: Path) -> dict[str, Any]:
    """Parse a single .cys archive into the per-file summary."""
    summary: dict[str, Any] = {
        "path": str(path),
        "networks": [],
        "visual_styles": [],
        "layout": None,
        "error": None,
    }
    try:
        zf = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as exc:
        summary["error"] = f"not a valid zip: {exc}"
        return summary
    try:
        with zf:
            names = zf.namelist()
            xgmml_names = [n for n in names if n.lower().endswith(".xgmml")]
            for n in xgmml_names:
                data = _safe_zip_read(zf, n)
                if data is None:
                    log.debug("skipping unreadable/oversized %s in %s", n, path)
                    continue
                parsed = _parse_xgmml(data)
                if parsed is None:
                    continue
                # Per-network layout often lives next to the XGMML as a
                # sibling properties file under the same network folder.
                net_dir = n.rsplit("/", 1)[0] if "/" in n else ""
                layout = None
                if net_dir:
                    for sibling in names:
                        if not sibling.startswith(net_dir + "/"):
                            continue
                        if sibling.lower().endswith(("properties", ".props", ".txt")):
                            sib_data = _safe_zip_read(zf, sibling)
                            if sib_data is None:
                                continue
                            txt = sib_data.decode("utf-8", errors="ignore")
                            layout = _scan_layout(txt)
                            if layout:
                                break
                parsed["layout"] = layout
                summary["networks"].append(parsed)

            for n in names:
                low = n.lower()
                if low.endswith("vizmap.props") or low.endswith("session_vizmap.xml"):
                    vm_data = _safe_zip_read(zf, n)
                    if vm_data is None:
                        continue
                    txt = vm_data.decode("utf-8", errors="ignore")
                    summary["visual_styles"].extend(_scan_visual_style_names(txt))
                if summary["layout"] is None and low.endswith(("properties", ".props")):
                    pr_data = _safe_zip_read(zf, n)
                    if pr_data is None:
                        continue
                    txt = pr_data.decode("utf-8", errors="ignore")
                    summary["layout"] = _scan_layout(txt)

            # de-dup visual styles while preserving order
            seen: set[str] = set()
            uniq: list[str] = []
            for v in summary["visual_styles"]:
                if v not in seen:
                    seen.add(v)
                    uniq.append(v)
            summary["visual_styles"] = uniq
    except Exception as exc:  # pragma: no cover — defensive
        summary["error"] = f"read failed: {exc}"
    return summary


_EXTRACT_NOTES = (
    "Cytoscape .cys is a zip archive of XGMML + cytable + properties; "
    "Cytoscape does not publish a formal schema, so the parser is "
    "tolerant: missing files are skipped rather than fatal. Visual "
    "styles are surfaced by name only — per-property mapper functions "
    "are not decoded. Per-network layout is parsed best-effort from "
    "sibling .properties files inside the archive."
)


def extract(root: Path, step_id: str | None = None) -> dict:
    cys_files = _candidate_cys(root)
    if step_id:
        step_prefix = (root / "workspace" / step_id).resolve()
        cys_files = [
            p for p in cys_files
            if str(p.resolve()).startswith(str(step_prefix))
        ]
    networks: list[dict] = []
    visual_styles: list[str] = []
    file_summaries: list[dict] = []
    for path in cys_files:
        summary = _parse_cys(path)
        rel = str(path.relative_to(root)) if path.is_relative_to(root) else str(path)
        file_summaries.append({
            "path": rel,
            "network_count": len(summary["networks"]),
            "visual_style_count": len(summary["visual_styles"]),
            "error": summary["error"],
        })
        for net in summary["networks"]:
            net_out = dict(net)
            net_out["source_cys"] = rel
            if net_out.get("layout") is None and summary.get("layout"):
                net_out["layout"] = summary["layout"]
            networks.append(net_out)
        for v in summary["visual_styles"]:
            if v not in visual_styles:
                visual_styles.append(v)
    return {
        "cys_files": file_summaries,
        "networks": networks,
        "visual_styles": visual_styles,
        "_notes": _EXTRACT_NOTES,
    }


def describe() -> dict:
    return {
        "name": "cytoscape",
        "version": __version__,
        "formats_supported": ["cys"],
    }


# ── optional tools ────────────────────────────────────────────────────


# Envelope helpers (_ok / _err) are imported from research_os.adapters.


def _xgmml_to_edge_list(data: bytes) -> tuple[list[str], list[tuple[str, str]], dict[str, tuple[float, float]]] | None:
    """Return (nodes, edges, positions) from an XGMML payload."""
    try:
        graph = ET.fromstring(data)
    except ET.ParseError:
        return None
    if _localname(graph.tag) != "graph":
        for child in graph.iter():
            if _localname(child.tag) == "graph":
                graph = child
                break
        else:
            return None
    nodes: list[str] = []
    positions: dict[str, tuple[float, float]] = {}
    edges: list[tuple[str, str]] = []
    for child in graph:
        local = _localname(child.tag)
        if local == "node":
            nid = child.get("id") or child.get("label")
            if not nid:
                continue
            nodes.append(nid)
            for gfx in child:
                if _localname(gfx.tag) == "graphics":
                    try:
                        x = float(gfx.get("x"))
                        y = float(gfx.get("y"))
                        positions[nid] = (x, y)
                    except (TypeError, ValueError):
                        # Missing or non-numeric coord — skip this node's
                        # position; layout will fall back to spring layout.
                        continue
        elif local == "edge":
            src = child.get("source")
            tgt = child.get("target")
            if src and tgt:
                edges.append((src, tgt))
    return nodes, edges, positions


def _handle_export_static(name: str, arguments: dict, root: Path) -> Any:
    cys_file = (arguments.get("cys_file") or "").strip()
    if not cys_file:
        return _err("cys_file is required")
    # Containment: reject absolute paths or ../ traversal that escape the
    # project root (a .cys is untrusted; the output must not be writable
    # anywhere on disk).
    cys_path = _resolve_inside_root(root, cys_file)
    if cys_path is None:
        return _err(f"cys_file escapes project root: {cys_file}")
    if not cys_path.exists():
        return _err(f"cys file not found: {cys_path}")

    output_path = arguments.get("output_path")
    network_filter = arguments.get("network")

    if output_path:
        out_path = _resolve_inside_root(root, output_path)
        if out_path is None:
            return _err(f"output_path escapes project root: {output_path}")
    else:
        out_path = cys_path.with_suffix(".png")

    # Try-import heavy deps; degrade gracefully.
    try:
        import matplotlib  # noqa: F401
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        placeholder = out_path.with_suffix(".md")
        try:
            placeholder.write_text(
                f"# Cytoscape static export placeholder\n\n"
                f"Source: `{cys_path}`\n\n"
                f"matplotlib is not installed in this environment, so the "
                f"static PNG/SVG could not be rendered. Install matplotlib "
                f"(and optionally networkx) to enable this tool, or open "
                f"the `.cys` file in Cytoscape directly.\n"
            )
        except OSError as exc:
            return _err(f"could not write placeholder: {exc}")
        return _ok({
            "status": "warning",
            "message": "matplotlib not installed; wrote placeholder note instead.",
            "placeholder": str(placeholder),
        })

    try:
        import networkx as nx
        have_nx = True
    except ImportError:
        have_nx = False

    try:
        zf = zipfile.ZipFile(cys_path)
    except (zipfile.BadZipFile, OSError) as exc:
        return _err(f"cannot open .cys archive: {exc}")

    rendered: list[dict] = []
    with zf:
        xgmml_names = [n for n in zf.namelist() if n.lower().endswith(".xgmml")]
        if not xgmml_names:
            return _err("no XGMML payloads found inside .cys archive")
        for n in xgmml_names:
            data = _safe_zip_read(zf, n)
            if data is None:
                log.debug("skip unreadable/oversized %s", n)
                continue
            parsed = _xgmml_to_edge_list(data)
            if parsed is None:
                continue
            nodes, edges, positions = parsed
            net_name = n.rsplit("/", 1)[-1].rsplit(".", 1)[0]
            if network_filter and network_filter not in net_name:
                continue
            target = out_path if len(xgmml_names) == 1 else (
                out_path.with_name(f"{out_path.stem}__{net_name}{out_path.suffix}")
            )
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                return _err(f"cannot create output dir: {exc}")

            fig, ax = plt.subplots(figsize=(8, 8))
            if have_nx:
                g = nx.DiGraph()
                g.add_nodes_from(nodes)
                g.add_edges_from(edges)
                pos = positions if positions else nx.spring_layout(g, seed=42)
                nx.draw_networkx_nodes(g, pos, ax=ax, node_size=40)
                nx.draw_networkx_edges(g, pos, ax=ax, alpha=0.4, arrowsize=6)
            else:
                # Hand-rolled minimal renderer when networkx is missing.
                pos = positions if positions else {
                    nid: (i % 20, i // 20) for i, nid in enumerate(nodes)
                }
                xs = [pos[n][0] for n in nodes if n in pos]
                ys = [pos[n][1] for n in nodes if n in pos]
                ax.scatter(xs, ys, s=20)
                for src, tgt in edges:
                    if src in pos and tgt in pos:
                        ax.plot(
                            [pos[src][0], pos[tgt][0]],
                            [pos[src][1], pos[tgt][1]],
                            color="gray", linewidth=0.4, alpha=0.4,
                        )
            ax.set_axis_off()
            ax.set_title(net_name)
            try:
                fig.savefig(target, dpi=150, bbox_inches="tight")
            except (OSError, ValueError) as exc:
                plt.close(fig)
                return _err(f"savefig failed: {exc}")
            plt.close(fig)
            rendered.append({
                "network": net_name,
                "output": str(target),
                "nodes": len(nodes),
                "edges": len(edges),
                "used_embedded_layout": bool(positions),
            })

    if not rendered:
        return _ok({
            "status": "warning",
            "message": (
                "No networks were rendered. Check the `network` filter or "
                "confirm the .cys contains XGMML payloads."
            ),
        })
    return _ok({
        "cys_file": str(cys_path),
        "rendered": rendered,
        "networkx_available": have_nx,
    })


# ── adapter registration ──────────────────────────────────────────────


_TOOLS_MD_PATTERNS = (
    (r"cy3sbml|cytoscape", "Cytoscape session present"),
)


def register() -> AdapterRegistration:
    return register_adapter(
        name="cytoscape",
        version=__version__,
        description="Cytoscape .cys session archive provenance extractor (zipfile + XGMML, no Cytoscape install required).",
        detect=detect,
        extract=extract,
        describe=describe,
        tools_md_patterns=_TOOLS_MD_PATTERNS,
        tools=(
            AdapterTool(
                name="tool_cytoscape_export_static",
                handler=_handle_export_static,
                schema={
                    "type": "object",
                    "properties": {
                        "cys_file": {"type": "string"},
                        "output_path": {"type": "string"},
                        "network": {"type": "string"},
                    },
                    "required": ["cys_file"],
                    "description": "Render a static PNG/SVG snapshot of one (or every) network embedded in a .cys archive. Parses the bundled XGMML, optionally uses networkx for layout, and renders with matplotlib. Degrades to a placeholder Markdown note when matplotlib is unavailable; uses an embedded XGMML layout when present, otherwise a spring layout. No Cytoscape install required.",
                },
            ),
        ),
    )
