"""Publication-quality synthesis — IMRAD paper with real figures, tables, citations.

Produces:
* ``synthesis/paper.md``     — IMRAD markdown with numbered figures, tables,
                               cross-references, and a verified bibliography.
* ``synthesis/paper.tex``    — LaTeX (when ``output_format`` in {latex, both}).
* ``synthesis/references.bib`` — BibTeX of every verified citation actually used.
* ``synthesis/figures/``     — copied images so the markdown is self-contained.
* ``synthesis/tables/``      — copied tabular outputs.

Citation policy
---------------
Every reference in the bibliography MUST be verified (have a DOI or URL +
title + at least one author). Sources:
1. workspace/citations.md keys (verified online via Crossref/S2).
2. Per-step ``workspace/<step>/literature/literature_index.yaml`` sidecars.
3. Top-K live retrieval per section via citations.collect_for_section.

Unverified entries are silently dropped and reported in the response so the
AI can surface them.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("research_os.tools.synthesis.synthesize")


SECTION_BUILDERS_KEYS = (
    "abstract", "introduction", "methods", "results", "discussion",
    "conclusion", "references",
)


# Default IMRAD section order — used when the active pack does not
# declare a `paper_sections` schema.
_DEFAULT_PAPER_SECTIONS = (
    "abstract", "introduction", "methods", "results", "discussion",
    "references",
)


# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------


def synthesize_plan(root: Path) -> dict[str, Any]:
    """Inspect available sources and recommend ordering."""
    methods_path = root / "workspace" / "methods.md"
    citations_path = root / "workspace" / "citations.md"
    analysis_path = root / "workspace" / "analysis.md"

    conclusions: list[str] = []
    workspace_dir = root / "workspace"
    if workspace_dir.exists():
        for exp_dir in sorted(workspace_dir.iterdir()):
            if (
                exp_dir.is_dir()
                and exp_dir.name[:2].isdigit()
                and not exp_dir.name.endswith("__DEAD_END")
            ):
                conc = exp_dir / "conclusions.md"
                if conc.exists() and len(conc.read_text()) > 100:
                    conclusions.append(exp_dir.name)

    citations_present = (
        citations_path.exists() and citations_path.stat().st_size > 100
    )

    sections = [
        {"id": "methods", "source": "workspace/methods.md",
         "status": "ready" if methods_path.exists() and methods_path.stat().st_size > 100 else "missing"},
        {"id": "results", "source": "workspace/*/conclusions.md + outputs/reports/",
         "status": "ready" if conclusions else "missing",
         "experiments": conclusions},
        {"id": "discussion", "source": "workspace/analysis.md + citations.md",
         "status": "ready" if analysis_path.exists() and citations_present else "partial"},
        {"id": "introduction", "source": "citations.md + research_overview.md",
         "status": "ready" if citations_present else "missing (run literature_search first)"},
        {"id": "abstract", "source": "synthesis of all sections (run AFTER methods/results/discussion)",
         "status": "pending"},
    ]
    return {
        "sections": sections,
        "recommended_order": ["methods", "results", "discussion", "introduction", "abstract"],
        "note": (
            "Call tool_synthesize with section=<id> for each. Citations are "
            "auto-verified online; unverified entries are dropped."
        ),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read(p: Path) -> str:
    return p.read_text() if p.exists() else ""


def _research_question(root: Path) -> str:
    rq = root / "docs" / "research_overview.md"
    if not rq.exists():
        return "Project research question"
    for line in rq.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("*"):
            continue
        return line
    return "Project research question"


def _project_title(root: Path) -> str:
    try:
        from research_os.project_ops import load_state

        s = load_state(root)
        return s.get("project_name") or s.get("project") or "Research Output"
    except Exception:
        return "Research Output"


def _gather_experiment_outputs(root: Path) -> list[dict[str, Any]]:
    """Per-experiment metadata: conclusions, reports, figures, tables, literature."""
    out: list[dict[str, Any]] = []
    workspace = root / "workspace"
    if not workspace.exists():
        return out
    for exp_dir in sorted(workspace.iterdir()):
        if not (exp_dir.is_dir() and exp_dir.name[:2].isdigit()):
            continue
        if exp_dir.name.endswith("__DEAD_END"):
            continue
        entry: dict[str, Any] = {
            "path": exp_dir.name,
            "dir": exp_dir,
            "conclusions": "",
            "reports": [],
            "figures": [],
            "tables": [],
            "literature": [],
        }
        conc = exp_dir / "conclusions.md"
        if conc.exists():
            entry["conclusions"] = conc.read_text()
        reports_dir = exp_dir / "outputs" / "reports"
        if reports_dir.exists():
            for f in sorted(reports_dir.rglob("*.md")):
                entry["reports"].append({"name": f.name, "text": f.read_text()})
        figures_dir = exp_dir / "outputs" / "figures"
        if figures_dir.exists():
            for f in sorted(figures_dir.rglob("*")):
                if f.is_file() and f.suffix.lower() in {".png", ".pdf", ".svg", ".jpg", ".jpeg"}:
                    caption = _read_caption_sidecar(f)
                    entry["figures"].append(
                        {"path": f.relative_to(root).as_posix(),
                         "name": f.name,
                         "caption": caption}
                    )
        tables_dir = exp_dir / "outputs" / "tables"
        if tables_dir.exists():
            for f in sorted(tables_dir.rglob("*")):
                if f.is_file() and f.suffix.lower() in {".csv", ".tsv", ".md"}:
                    caption = _read_caption_sidecar(f)
                    entry["tables"].append(
                        {"path": f.relative_to(root).as_posix(),
                         "name": f.name,
                         "caption": caption,
                         "ext": f.suffix.lower()}
                    )
        # Step-level literature (PDFs + sidecars).
        lit_dir = exp_dir / "literature"
        if lit_dir.exists():
            for f in sorted(lit_dir.iterdir()):
                if not f.is_file():
                    continue
                if f.suffix.lower() not in {".pdf", ".epub"}:
                    continue
                meta = _read_lit_sidecar(f)
                if meta:
                    entry["literature"].append(meta)
        out.append(entry)
    return out


def _read_caption_sidecar(media: Path) -> str:
    """A figure or table's caption can live in a sibling .caption.md file."""
    caption = media.parent / (media.stem + ".caption.md")
    if caption.exists():
        return caption.read_text().strip()
    # Fallback: derive from filename
    return media.stem.replace("_", " ").capitalize()


def _read_lit_sidecar(pdf: Path) -> dict[str, Any] | None:
    """Read .meta.yaml or .meta.json alongside a literature PDF."""
    for ext in (".meta.yaml", ".meta.json"):
        side = pdf.with_suffix(pdf.suffix + ext)
        if side.exists():
            try:
                if ext == ".meta.yaml":
                    import yaml  # type: ignore

                    data = yaml.safe_load(side.read_text()) or {}
                else:
                    data = json.loads(side.read_text())
                if not isinstance(data, dict):
                    return None
                data.setdefault("scope", "workspace_step_literature")
                return data
            except Exception:
                return None
    return None


# ---------------------------------------------------------------------------
# Citation collection (project + step + live)
# ---------------------------------------------------------------------------


def _make_key(entry: dict[str, Any]) -> str:
    from research_os.tools.actions.synthesis.citations import _make_key as _mk

    return _mk(entry)


def _collect_all_verified_citations(
    root: Path, *, output_type: str, query: str,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Gather verified citations from every source.

    Returns ``(pool, failures)``::

        pool     = {citation_key: entry}
        failures = {
            "total": int,                        # all citation-related failures
            "by_provider": {prov: int, ...},     # live retrieval providers
            "samples": [...],                    # at most 3, for the API surface
            "live_retrieval_attempted": bool,
        }

    Sources:
      1. inputs/literature_index.yaml (project-level PDFs).
      2. workspace/<step>/literature/literature_index.yaml (per-step PDFs).
      3. Live retrieval via collect_for_section (provides DOI / URL).

    Failure semantics: a previously silent ``list index out of range``
    inside live retrieval used to make tool_synthesize return
    ``citations_used: 0`` with no signal that the network path even
    ran. Live retrieval now uses the with-failures variant; the failure
    metadata flows out to the caller so the AI can see *why* citations
    are missing.
    """
    from research_os.tools.actions.synthesis.citations import (
        cap_for,
        collect_for_section_with_failures,
    )

    pool: dict[str, dict[str, Any]] = {}
    failures: dict[str, Any] = {
        "total": 0,
        "by_provider": {},
        "samples": [],
        "live_retrieval_attempted": False,
    }

    # 1. Project-level literature index.
    proj_index = root / "inputs" / "literature_index.yaml"
    if proj_index.exists():
        try:
            import yaml  # type: ignore

            data = yaml.safe_load(proj_index.read_text()) or {}
            for filename, meta in (data.get("entries") or {}).items():
                key = meta.get("citation_key") or _make_key(meta)
                meta.setdefault("citation_key", key)
                meta.setdefault("scope", "project_literature")
                meta.setdefault("filename", filename)
                if meta.get("doi") or meta.get("url"):
                    pool[key] = meta
        except Exception as e:
            logger.warning(f"project literature index unreadable: {e}")

    # 2. Step-level literature.
    for exp in _gather_experiment_outputs(root):
        for meta in exp.get("literature", []):
            key = meta.get("citation_key") or _make_key(meta)
            meta.setdefault("citation_key", key)
            if meta.get("doi") or meta.get("url"):
                pool[key] = meta

    # 3. Live retrieval per section query.
    failures["live_retrieval_attempted"] = True
    try:
        live, live_failures = collect_for_section_with_failures(
            query, k=cap_for(output_type), root=root,
        )
        for entry in live:
            key = entry.get("citation_key") or _make_key(entry)
            entry.setdefault("citation_key", key)
            if entry.get("doi") or entry.get("url"):
                pool.setdefault(key, entry)
        failures["total"] += int(live_failures.get("total") or 0)
        for prov, cnt in (live_failures.get("by_provider") or {}).items():
            failures["by_provider"][prov] = (
                failures["by_provider"].get(prov, 0) + cnt
            )
        for s in (live_failures.get("samples") or []):
            if len(failures["samples"]) < 3:
                failures["samples"].append(s)
    except Exception as e:
        # Even the wrapper itself can fail (e.g. import error). Treat the
        # whole live path as one failure rather than crashing synthesis.
        from research_os.tools.actions.synthesis.citations import (
            _log_citation_failure,
        )

        logger.warning(f"live citation retrieval failed: {e}")
        _log_citation_failure(
            provider="live_retrieval",
            query=query,
            exc=e,
            root=root,
        )
        failures["total"] += 1
        failures["by_provider"]["live_retrieval"] = (
            failures["by_provider"].get("live_retrieval", 0) + 1
        )
        if len(failures["samples"]) < 3:
            failures["samples"].append(
                {
                    "provider": "live_retrieval",
                    "exception_type": type(e).__name__,
                    "message": str(e)[:240],
                }
            )

    return pool, failures


def _bound_to_cap(
    pool: dict[str, dict[str, Any]], output_type: str
) -> list[dict[str, Any]]:
    from research_os.tools.actions.synthesis.citations import cap_for

    cap = cap_for(output_type)
    return list(pool.values())[:cap]


def _number_citations(
    refs: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Assign numeric ref ids; return ordered list + key→number map."""
    numbered: list[dict[str, Any]] = []
    key_to_num: dict[str, int] = {}
    for i, entry in enumerate(refs, start=1):
        entry = dict(entry)
        entry["ref_num"] = i
        key = entry.get("citation_key") or _make_key(entry)
        entry["citation_key"] = key
        key_to_num[key] = i
        numbered.append(entry)
    return numbered, key_to_num


# ---------------------------------------------------------------------------
# Figure + table copying / numbering
# ---------------------------------------------------------------------------


def _copy_figures(root: Path, experiments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Copy every per-experiment figure to synthesis/figures/ with figure numbers."""
    figures_dir = root / "synthesis" / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    out: list[dict[str, Any]] = []
    n = 0
    for exp in experiments:
        for fig in exp.get("figures", []):
            n += 1
            src = root / fig["path"]
            dest_name = f"fig{n:02d}_{src.name}"
            dest = figures_dir / dest_name
            try:
                if not dest.exists():
                    shutil.copy2(src, dest)
            except Exception as e:
                logger.warning(f"copy figure failed {src}: {e}")
                continue
            out.append(
                {
                    "number": n,
                    "label": f"fig{n}",
                    "filename": dest_name,
                    "relative_path": f"figures/{dest_name}",
                    "caption": fig.get("caption") or "",
                    "step": exp["path"],
                }
            )
    return out


def _copy_tables(root: Path, experiments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Copy tables and number them. CSV/TSV stays as-is; .md inlines."""
    tables_dir = root / "synthesis" / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    out: list[dict[str, Any]] = []
    n = 0
    for exp in experiments:
        for tab in exp.get("tables", []):
            n += 1
            src = root / tab["path"]
            dest_name = f"tab{n:02d}_{src.name}"
            dest = tables_dir / dest_name
            try:
                if not dest.exists():
                    shutil.copy2(src, dest)
            except Exception as e:
                logger.warning(f"copy table failed {src}: {e}")
                continue
            inline_md = ""
            if tab.get("ext") == ".md":
                try:
                    inline_md = dest.read_text()
                except Exception:
                    pass
            elif tab.get("ext") in {".csv", ".tsv"}:
                inline_md = _csv_to_markdown(dest, sep="," if tab["ext"] == ".csv" else "\t")
            out.append(
                {
                    "number": n,
                    "label": f"tab{n}",
                    "filename": dest_name,
                    "relative_path": f"tables/{dest_name}",
                    "caption": tab.get("caption") or "",
                    "inline_md": inline_md,
                    "step": exp["path"],
                }
            )
    return out


def _csv_to_markdown(path: Path, sep: str = ",", max_rows: int = 30) -> str:
    """Render a CSV/TSV as a small markdown table."""
    try:
        lines = [ln for ln in path.read_text().splitlines() if ln.strip()][: max_rows + 1]
        if not lines:
            return ""
        rows = [[c.strip() for c in ln.split(sep)] for ln in lines]
        header, body = rows[0], rows[1:]
        md = ["| " + " | ".join(header) + " |",
              "|" + "|".join("---" for _ in header) + "|"]
        for r in body:
            md.append("| " + " | ".join(r) + " |")
        if len(lines) > max_rows + 1:
            md.append(f"*(truncated to {max_rows} rows)*")
        return "\n".join(md)
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------


def _build_methods(
    root: Path, key_to_num: dict[str, int], experiments: list[dict[str, Any]]
) -> str:
    body = _read(root / "workspace" / "methods.md")
    if not body.strip():
        return "## Methods\n\n*No methods recorded — run `mem_log(kind='methods', ...)` first.*\n"
    body = _replace_citation_keys(body, key_to_num)
    return "## Methods\n\n" + body + "\n"


def _build_results(
    root: Path,
    key_to_num: dict[str, int],
    experiments: list[dict[str, Any]],
    figures: list[dict[str, Any]],
    tables: list[dict[str, Any]],
) -> str:
    chunks: list[str] = ["## Results\n"]
    for exp in experiments:
        if exp.get("conclusions"):
            chunks.append(f"### {exp['path']}\n")
            chunks.append(_replace_citation_keys(exp["conclusions"], key_to_num))
        for rep in exp.get("reports", []):
            chunks.append(f"#### {rep['name']}\n")
            chunks.append(_replace_citation_keys(rep["text"], key_to_num))
    # Figures section.
    if figures:
        chunks.append("\n### Figures\n")
        for fig in figures:
            chunks.append(
                f"![Figure {fig['number']}: {fig['caption']}]({fig['relative_path']})\n\n"
                f"**Figure {fig['number']}.** {fig['caption']} *(from {fig['step']})*\n"
            )
    if tables:
        chunks.append("\n### Tables\n")
        for tab in tables:
            chunks.append(f"**Table {tab['number']}.** {tab['caption']} *(from {tab['step']})*\n")
            if tab.get("inline_md"):
                chunks.append(tab["inline_md"])
            else:
                chunks.append(f"*See `synthesis/{tab['relative_path']}`.*")
            chunks.append("")
    return "\n".join(chunks)


def _build_discussion(
    root: Path, key_to_num: dict[str, int], experiments: list[dict[str, Any]]
) -> str:
    chunks: list[str] = ["## Discussion\n"]
    analysis = _read(root / "workspace" / "analysis.md")
    if analysis.strip():
        analysis = re.sub(r"```mermaid.*?```", "", analysis, flags=re.DOTALL)
        chunks.append(_replace_citation_keys(analysis, key_to_num))
    evid = _read(root / "synthesis" / "evidence_table.md")
    if evid.strip():
        chunks.append("\n### Evidence table\n")
        chunks.append(evid)
    # Hypothesis status block.
    try:
        from research_os.project_ops import load_state

        hypotheses = load_state(root).get("active_hypotheses", []) or []
        if hypotheses:
            chunks.append("\n### Hypothesis status\n")
            chunks.append("| ID | Status | Statement |")
            chunks.append("|---|---|---|")
            for h in hypotheses:
                chunks.append(
                    f"| {h.get('id', '?')} | {h.get('status', '?')} | "
                    f"{(h.get('statement') or '')[:120]} |"
                )
    except Exception:
        pass
    return "\n".join(chunks) + "\n"


def _build_introduction(root: Path, key_to_num: dict[str, int]) -> str:
    rq = _research_question(root)
    body = (
        "## Introduction\n\n"
        f"This study investigates: **{rq}**\n\n"
        "Prior work informing this question is summarised below, cited inline by "
        "reference number (see the References section).\n"
    )
    return _replace_citation_keys(body, key_to_num)


def _build_abstract(root: Path, experiments: list[dict[str, Any]], output_type: str) -> str:
    """Construct a real IMRAD-style abstract from what the workspace records.

    Hierarchy:
      1. ``synthesis/synthesis_spec.yaml`` ``abstract`` field — author's voice.
      2. The synthesis step's ``Plain-language summary`` (most readable).
      3. Top findings + last step's limitations + first step's methods.
      4. Fallback stub clearly marked as needing author input.
    """
    # 1. Spec override.
    try:
        from research_os.tools.actions.synthesis.dashboard import _load_spec

        spec = _load_spec(root)
        if spec.get("abstract"):
            return "## Abstract\n\n" + str(spec["abstract"]).strip() + "\n"
    except Exception:
        spec = {}

    # 2. Plain-language summary from a synthesis / audit / final step.
    finalist_text = ""
    for exp in reversed(experiments):
        conc = exp.get("conclusions", "")
        m = re.search(
            r"##\s*Plain-language summary\s*\n(.+?)(?=^##|\Z)",
            conc, flags=re.MULTILINE | re.DOTALL | re.IGNORECASE,
        )
        if m:
            body = m.group(1).strip()
            if body and not body.startswith("*("):
                finalist_text = body
                break
    if finalist_text:
        # Already plain-language — package as a single paragraph.
        return "## Abstract\n\n" + finalist_text + "\n"

    # 3. Build a real Background/Methods/Results/Conclusion abstract.
    findings: list[str] = []
    for exp in experiments:
        m = re.search(
            r"##\s*Findings\s*\n(.+?)(?:\n##|\Z)",
            exp.get("conclusions", ""), flags=re.DOTALL,
        )
        if m:
            for line in m.group(1).splitlines():
                line = line.strip()
                if line.startswith(("-", "*")):
                    findings.append(line.lstrip("-* ").strip())
                if len(findings) >= 4:
                    break
        if len(findings) >= 4:
            break

    methods_summary = ""
    for exp in experiments[:3]:
        m = re.search(
            r"##\s*Methods\s*(?:\(full detail\))?\s*\n(.+?)(?:\n##|\Z)",
            exp.get("conclusions", ""), flags=re.DOTALL | re.IGNORECASE,
        )
        if m:
            body = m.group(1).strip()
            if body and not body.startswith("*("):
                first_para = body.split("\n\n")[0].strip()
                methods_summary = first_para[:280] + (
                    "…" if len(first_para) > 280 else ""
                )
                break

    limitation_summary = ""
    for exp in reversed(experiments):
        m = re.search(
            r"##\s*Limitations\s*\n(.+?)(?:\n##|\Z)",
            exp.get("conclusions", ""), flags=re.DOTALL | re.IGNORECASE,
        )
        if m:
            body = m.group(1).strip()
            for line in body.splitlines():
                line = line.strip().lstrip("-* ").strip()
                if line and not line.startswith("*("):
                    limitation_summary = line[:200]
                    break
            if limitation_summary:
                break

    rq = _research_question(root)
    background = (
        f"This study investigates: {rq}"
        if rq and "(blank" not in rq.lower()
        else "*(Populate the research question via the intake or the spec's "
        "`overview.background` field.)*"
    )
    methods_line = (
        methods_summary
        if methods_summary
        else "*(No methods recorded yet — add via `mem_log(kind='methods', ...)` "
        "or set `synthesis_spec.yaml > methods_summary`.)*"
    )
    results_line = (
        " ".join(f.rstrip(".") + "." for f in findings[:3])
        if findings
        else "*(Add ≥1 numbered analysis step with Findings before building the paper.)*"
    )
    conclusion_line = (
        f"Implications follow directly from the findings above; the main "
        f"limitation is that {limitation_summary.rstrip('.').lower()}."
        if limitation_summary
        else "*(Add `## Limitations` to the final step's conclusions.md so "
        "the abstract can close honestly.)*"
    )

    return (
        "## Abstract\n\n"
        f"**Background.** {background}\n\n"
        f"**Methods.** {methods_line}\n\n"
        f"**Results.** {results_line}\n\n"
        f"**Conclusion.** {conclusion_line}\n"
    )


def _build_references_section(
    references: list[dict[str, Any]], style: str = "vancouver"
) -> str:
    if not references:
        return "## References\n\n*(no verified citations available)*\n"
    from research_os.tools.actions.synthesis.citations import (
        format_apa,
        format_vancouver,
    )

    fmt = {"apa": format_apa, "vancouver": format_vancouver}.get(
        style.lower(), format_vancouver
    )
    lines = ["## References", ""]
    for ref in references:
        lines.append(f"{ref['ref_num']}. {fmt(ref)}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Citation-key → numbered reference rewriting
# ---------------------------------------------------------------------------


_CITE_PATTERNS = [
    # Pandoc-style: [@key], [@key; @key2]
    re.compile(r"\[@([a-zA-Z0-9_]+)(?:[;,]\s*@[a-zA-Z0-9_]+)*\]"),
    # \cite{key} or \cite{key1,key2}
    re.compile(r"\\cite\{([a-zA-Z0-9_,]+)\}"),
]


def _replace_citation_keys(text: str, key_to_num: dict[str, int]) -> str:
    """Convert any in-text citation references to numbered [N] form."""
    if not text or not key_to_num:
        return text

    def _convert(match: re.Match) -> str:
        raw = match.group(0)
        # Pull every key inside the match.
        keys = re.findall(r"[a-zA-Z0-9_]+", raw.replace("@", " ").replace("cite", " "))
        nums = [str(key_to_num[k]) for k in keys if k in key_to_num]
        if not nums:
            return raw
        return "[" + ",".join(nums) + "]"

    out = text
    for pat in _CITE_PATTERNS:
        out = pat.sub(_convert, out)
    return out


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def _autonomy_level(root: Path) -> str:
    """Read ``interaction.autonomy_level`` from ``researcher_config.yaml``.

    Falls back to ``"supervised"`` when the file or block is absent. Uses
    ``normalize_autonomy_level`` so ``coaching`` aliases to ``supervised``
    and unknown values default safely.
    """
    try:
        from research_os.tools.actions.state.config import (
            _config_path,
            normalize_autonomy_level,
        )
        import yaml as _yaml

        cfg_path = _config_path(Path(root))
        if not cfg_path.exists():
            return "supervised"
        cfg = _yaml.safe_load(cfg_path.read_text()) or {}
        raw = (cfg.get("interaction") or {}).get("autonomy_level")
        return normalize_autonomy_level(raw)
    except Exception:
        return "supervised"


# Canonical per-section ordering used by the autopilot short-circuit. The
# order mirrors the synthesis_paper.yaml turn sequence (methods → results →
# discussion → introduction → abstract) so a manual multi-turn invocation
# and a single autopilot call produce identical artefacts.
_AUTO_PROCEED_SECTION_ORDER = (
    "methods", "results", "discussion", "introduction", "abstract",
)


# ---------------------------------------------------------------------------
# Pack-aware section schema (theory_math is not IMRAD)
# ---------------------------------------------------------------------------


def _active_pack_name(root: Path) -> str | None:
    """Resolve the active pack for a project.

    Reads ``inputs/researcher_config.yaml`` (or top-level
    ``researcher_config.yaml``) looking for ``pack:`` / ``domain:`` /
    ``packs: [...]`` — same resolution rules as the dashboard's
    detector. Returns the lowercased pack name or ``None``.
    """
    for rel in ("inputs/researcher_config.yaml", "researcher_config.yaml"):
        cfg_path = root / rel
        if not cfg_path.exists():
            continue
        try:
            import yaml  # type: ignore
            cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8",
                                                    errors="ignore")) or {}
        except Exception:
            continue
        if not isinstance(cfg, dict):
            continue
        for key in ("pack", "domain"):
            val = cfg.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip().lower()
        packs = cfg.get("packs")
        if isinstance(packs, list) and packs:
            for entry in packs:
                if isinstance(entry, str) and entry.strip():
                    return entry.strip().lower()
    return None


def _resolve_paper_sections(root: Path) -> tuple[tuple[str, ...], str | None]:
    """Return ``(sections, source_pack)`` for the paper-section schema.

    ``source_pack`` is the pack name when the schema came from a pack
    declaration, ``None`` when we fell back to the IMRAD default. Used
    for diagnostics in the response payload and by tests asserting that
    a non-IMRAD pack drove the ordering.
    """
    pack = _active_pack_name(root)
    if pack:
        try:
            from research_os.plugins import pack_paper_sections

            declared = pack_paper_sections(pack)
            if declared:
                return tuple(declared), pack
        except Exception:
            logger.warning(
                "pack_paper_sections lookup failed for '%s'; "
                "falling back to IMRAD.", pack, exc_info=True,
            )
    return _DEFAULT_PAPER_SECTIONS, None


def _build_generic_section(root: Path, section_id: str,
                           key_to_num: dict[str, int]) -> str:
    """Build a pack-declared section that has no hardcoded builder.

    Pulls ``workspace/<section_id>.md`` when present (mirroring the way
    ``_build_methods`` pulls ``workspace/methods.md``). Heading text is
    a humanised version of the section id (``main_theorems`` → "Main
    Theorems"). Missing file → an explicit *No <section> recorded* stub
    so the absence is visible in the paper, not silent.
    """
    heading = section_id.replace("_", " ").title()
    body = _read(root / "workspace" / f"{section_id}.md")
    if not body.strip():
        return (
            f"## {heading}\n\n*No {heading.lower()} recorded — "
            f"write `workspace/{section_id}.md` to populate this section.*\n"
        )
    return f"## {heading}\n\n" + _replace_citation_keys(body, key_to_num) + "\n"


def synthesize_workspace(
    root: Path,
    *,
    output_format: str = "markdown",
    section: str | None = None,
    output_type: str = "paper",
    citation_style: str = "vancouver",
    auto_proceed: bool = False,
) -> dict[str, Any]:
    """Build a section, OR — when section is None — assemble the full output.

    ``auto_proceed`` (autopilot short-circuit, AUDIT-063)
    ----------------------------------------------------
    When ``True`` AND ``interaction.autonomy_level == "autopilot"``,
    iterate every section in ``_AUTO_PROCEED_SECTION_ORDER`` (writing each
    ``synthesis/<section>.md`` exactly as a per-section call would) and
    THEN run the full assembly that stitches ``synthesis/paper.md`` plus
    the bibliography. The result is the all-sections-in-one-call shortcut
    that the protocol documents for autopilot mode.

    When ``True`` but the autonomy level is anything other than
    ``"autopilot"`` (``manual``, ``supervised``, ``coaching``), the call
    returns an error — the multi-turn enforcement is the whole point of
    the non-autopilot modes and the short-circuit must not bypass it.

    When ``False`` (the default), behaviour is unchanged: pass ``section``
    for a per-section build or omit it for a single-shot full assembly.
    Backwards-compatible with every existing caller.
    """
    try:
        from research_os.project_ops import ensure_lazy_dir

        # ── auto_proceed short-circuit (AUDIT-063) ────────────────────
        if auto_proceed:
            level = _autonomy_level(root)
            if level != "autopilot":
                return {
                    "status": "error",
                    "error": (
                        "auto_proceed=true requires interaction.autonomy_level "
                        f"== 'autopilot' (current: '{level}'). The multi-turn "
                        "section-per-call cadence is enforced in manual / "
                        "supervised / coaching modes to preserve the "
                        "deliberative pace a real paper deserves. To use the "
                        "short-circuit, set interaction.autonomy_level: "
                        "autopilot in inputs/researcher_config.yaml."
                    ),
                }
            # Run every section in canonical order, then final assembly.
            # Each per-section call writes its own synthesis/<id>.md just
            # as a manual multi-turn invocation would.
            sections_written: list[dict[str, Any]] = []
            for sec in _AUTO_PROCEED_SECTION_ORDER:
                sec_res = synthesize_workspace(
                    root,
                    output_format=output_format,
                    section=sec,
                    output_type=output_type,
                    citation_style=citation_style,
                    auto_proceed=False,
                )
                if sec_res.get("status") == "error" or "error" in sec_res:
                    return {
                        "status": "error",
                        "error": (
                            f"auto_proceed: section '{sec}' failed — "
                            f"{sec_res.get('error') or sec_res.get('message')}"
                        ),
                        "sections_completed": [s["section"] for s in sections_written],
                    }
                sections_written.append(sec_res)

            # Final assembly stitches paper.md from the already-written
            # per-section files plus the bibliography.
            full = synthesize_workspace(
                root,
                output_format=output_format,
                section=None,
                output_type=output_type,
                citation_style=citation_style,
                auto_proceed=False,
            )
            if "error" in full:
                return full
            full["auto_proceed"] = True
            full["autonomy_level"] = "autopilot"
            full["sections_processed"] = list(_AUTO_PROCEED_SECTION_ORDER)
            full["per_section_paths"] = [s.get("path") for s in sections_written]
            full["message"] = (
                "auto_proceed: wrote "
                f"{len(sections_written)} sections + full assembly "
                "in one call (autopilot short-circuit)."
            )
            return full

        synthesis_dir = ensure_lazy_dir(root, "synthesis")

        experiments = _gather_experiment_outputs(root)
        figures = _copy_figures(root, experiments)
        tables = _copy_tables(root, experiments)

        question = _research_question(root)
        pool, citation_failures = _collect_all_verified_citations(
            root, output_type=output_type, query=question
        )
        capped = _bound_to_cap(pool, output_type)
        references, key_to_num = _number_citations(capped)

        # Resolve the paper-section schema. Packs may declare a custom
        # ordering (e.g. theory_math wants intro → preliminaries →
        # theorems → proofs → discussion, NOT IMRAD). Fallback is the
        # canonical IMRAD order.
        section_schema, pack_source = _resolve_paper_sections(root)

        # Map of hardcoded section builders. Anything the pack declares
        # that ISN'T in this map gets routed through _build_generic_section
        # which reads workspace/<section_id>.md.
        hardcoded_builders = {
            "methods": lambda: _build_methods(root, key_to_num, experiments),
            "results": lambda: _build_results(
                root, key_to_num, experiments, figures, tables
            ),
            "discussion": lambda: _build_discussion(root, key_to_num, experiments),
            "introduction": lambda: _build_introduction(root, key_to_num),
            "abstract": lambda: _build_abstract(root, experiments, output_type),
            "references": lambda: _build_references_section(references, citation_style),
        }

        def _build_one(sec_id: str) -> str:
            builder = hardcoded_builders.get(sec_id)
            if builder is not None:
                return builder()
            return _build_generic_section(root, sec_id, key_to_num)

        # ── Single-section mode ────────────────────────────────────────
        if section:
            section = section.lower()
            # Allowed = hardcoded builders ∪ anything the pack declares.
            allowed = set(hardcoded_builders) | set(section_schema)
            if section not in allowed:
                return {
                    "status": "error",
                    "error": (
                        f"Unknown section '{section}'. Allowed: "
                        f"{sorted(allowed)}"
                    ),
                }
            body = _build_one(section)
            dest = synthesis_dir / f"{section}.md"
            dest.write_text(body)
            return {
                "status": "success",
                "section": section,
                "path": str(dest.relative_to(root)),
                "citations_used": len(references),
                "citation_retrieval_failures": int(
                    citation_failures.get("total") or 0
                ),
                "citation_failure_detail": {
                    "by_provider": citation_failures.get("by_provider") or {},
                    "samples": citation_failures.get("samples") or [],
                    "live_retrieval_attempted": bool(
                        citation_failures.get("live_retrieval_attempted")
                    ),
                    "log_path": (
                        "workspace/logs/citation_failures.jsonl"
                        if citation_failures.get("total")
                        else None
                    ),
                },
                "figures_numbered": len(figures),
                "tables_numbered": len(tables),
                "message": f"Wrote synthesis/{section}.md.",
                "pack_section_schema_source": pack_source,
            }

        # ── Full assembly ──────────────────────────────────────────────
        title = _project_title(root)
        chunks: list[str] = [
            f"# {title}\n",
            f"*Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}*\n",
        ]
        # Iterate the resolved schema (pack-declared OR IMRAD default).
        # We always append a references section at the end if it isn't
        # already part of the schema so the bibliography is never lost.
        seen_refs = False
        for sec_id in section_schema:
            chunks.append(_build_one(sec_id))
            if sec_id == "references":
                seen_refs = True
        if not seen_refs:
            chunks.append(_build_references_section(references, citation_style))

        paper_md = synthesis_dir / "paper.md"
        paper_md.write_text("\n".join(chunks))

        # references.bib
        from research_os.tools.actions.synthesis.citations import write_references_bib

        bib_path = synthesis_dir / "references.bib"
        write_references_bib(references, bib_path)

        # Track which keys WEREN'T usable for transparency.
        unverified = sorted(set(pool.keys()) - {r["citation_key"] for r in references})

        # Report the sections we actually emitted (schema + auto-appended
        # references if it wasn't declared).
        emitted_sections = list(section_schema) + (
            [] if seen_refs else ["references"]
        )

        result: dict[str, Any] = {
            "status": "success",
            "output_type": output_type,
            "paper_path": str(paper_md.relative_to(root)),
            "bib_path": str(bib_path.relative_to(root)),
            "sections": emitted_sections,
            "pack_section_schema_source": pack_source,
            "citations_used": len(references),
            "citation_retrieval_failures": int(
                citation_failures.get("total") or 0
            ),
            "citation_failure_detail": {
                "by_provider": citation_failures.get("by_provider") or {},
                "samples": citation_failures.get("samples") or [],
                "live_retrieval_attempted": bool(
                    citation_failures.get("live_retrieval_attempted")
                ),
                "log_path": (
                    "workspace/logs/citation_failures.jsonl"
                    if citation_failures.get("total")
                    else None
                ),
            },
            "citation_keys": [r["citation_key"] for r in references],
            "figures_numbered": len(figures),
            "tables_numbered": len(tables),
            "word_count": sum(len(c.split()) for c in chunks),
            "candidates_unused_due_to_cap": unverified,
        }

        if output_format in ("latex", "both"):
            tex_path = synthesis_dir / "paper.tex"
            tex_path.write_text(
                _markdown_to_latex(
                    title=title,
                    chunks=chunks,
                    figures=figures,
                    references=references,
                )
            )
            try:
                from research_os.tools.actions.synthesis.latex import latex_compile

                result["latex_compile"] = latex_compile(root)
            except Exception as e:
                result["latex_compile"] = {"status": "error", "message": str(e)}
            if output_format == "latex":
                result["paper_path"] = str(tex_path.relative_to(root))
        return result

    except Exception as e:
        logger.exception("Synthesis failed")
        return {"error": f"Synthesis failed: {e}"}


# ---------------------------------------------------------------------------
# LaTeX renderer (proper natbib + figures + bibtex)
# ---------------------------------------------------------------------------


def _escape_latex(s: str) -> str:
    if not s:
        return ""
    return (
        s.replace("\\", r"\textbackslash{}")
        .replace("&", r"\&")
        .replace("%", r"\%")
        .replace("$", r"\$")
        .replace("#", r"\#")
        .replace("_", r"\_")
        .replace("{", r"\{")
        .replace("}", r"\}")
    )


def _inline_md_to_latex(text: str) -> str:
    """Render inline markdown to LaTeX with **bold**, *italic*, `code`,
    [text](url), and bracketed [N] citation references preserved."""
    if not text:
        return ""
    out = text
    # Pull out code spans first so we don't escape inside them.
    code_spans: list[str] = []

    def _stash_code(m):
        code_spans.append(m.group(1))
        return f"\x00CODE{len(code_spans) - 1}\x00"

    out = re.sub(r"`([^`]+)`", _stash_code, out)

    # Bold + italic markers before LaTeX-escape.
    bold_spans: list[str] = []

    def _stash_bold(m):
        bold_spans.append(m.group(1))
        return f"\x00BOLD{len(bold_spans) - 1}\x00"

    out = re.sub(r"\*\*([^*]+)\*\*", _stash_bold, out)

    italic_spans: list[str] = []

    def _stash_italic(m):
        italic_spans.append(m.group(1))
        return f"\x00ITA{len(italic_spans) - 1}\x00"

    out = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", _stash_italic, out)

    # Link spans.
    link_spans: list[tuple[str, str]] = []

    def _stash_link(m):
        link_spans.append((m.group(1), m.group(2)))
        return f"\x00LINK{len(link_spans) - 1}\x00"

    out = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", _stash_link, out)

    # Now escape the remaining text.
    out = _escape_latex(out)

    # Restore stashed elements.
    for i, span in enumerate(code_spans):
        out = out.replace(f"\x00CODE{i}\x00",
                          "\\texttt{" + _escape_latex(span) + "}")
    for i, span in enumerate(bold_spans):
        out = out.replace(f"\x00BOLD{i}\x00",
                          "\\textbf{" + _inline_md_to_latex(span) + "}")
    for i, span in enumerate(italic_spans):
        out = out.replace(f"\x00ITA{i}\x00",
                          "\\textit{" + _inline_md_to_latex(span) + "}")
    for i, (label, url) in enumerate(link_spans):
        out = out.replace(
            f"\x00LINK{i}\x00",
            "\\href{" + url.replace("%", r"\%").replace("#", r"\#")
            + "}{" + _inline_md_to_latex(label) + "}",
        )

    # Numeric citations [N] / [N,M] stay as-is (LaTeX accepts them inside text).
    return out


def _try_pandoc(markdown: str, tmp_dir: Path) -> str | None:
    """If pandoc is on PATH, use it to produce a polished LaTeX fragment."""
    import shutil as _shutil
    import subprocess as _sp

    pandoc = _shutil.which("pandoc")
    if not pandoc:
        return None
    src = tmp_dir / "paper.md"
    src.write_text(markdown)
    dest = tmp_dir / "paper.body.tex"
    try:
        res = _sp.run(
            [pandoc, "-f", "markdown", "-t", "latex",
             "--wrap=preserve", str(src), "-o", str(dest)],
            capture_output=True, text=True, timeout=60,
        )
        if res.returncode == 0 and dest.exists():
            return dest.read_text()
    except Exception as e:
        logger.debug("pandoc fallback skipped: %s", e)
    return None


def _markdown_to_latex(
    *,
    title: str,
    chunks: list[str],
    figures: list[dict[str, Any]],
    references: list[dict[str, Any]],
    tmp_dir: Path | None = None,
) -> str:
    """Render the IMRAD markdown into a citation-aware LaTeX document.

    Uses pandoc when available (best fidelity). Otherwise emits a real
    LaTeX body honouring headers, lists, tables, inline formatting,
    figures, and ``[N]`` citation references — no more raw escaped text.
    """
    head = [
        r"\documentclass[11pt]{article}",
        r"\usepackage[utf8]{inputenc}",
        r"\usepackage[T1]{fontenc}",
        r"\usepackage{lmodern}",
        r"\usepackage{graphicx}",
        r"\usepackage[numbers,sort&compress]{natbib}",
        r"\usepackage{hyperref}",
        r"\usepackage{geometry}",
        r"\geometry{margin=1in}",
        r"\usepackage{booktabs}",
        r"\usepackage{microtype}",
        r"\usepackage{parskip}",
        r"\hypersetup{colorlinks=true,linkcolor=blue,citecolor=blue,urlcolor=blue}",
        r"\title{" + _escape_latex(title) + "}",
        r"\date{\today}",
        r"\begin{document}",
        r"\maketitle",
    ]

    markdown_body = "\n\n".join(chunks)

    # Try pandoc — gives the best typesetting.
    if tmp_dir is None:
        import tempfile as _tf
        tmp_dir = Path(_tf.mkdtemp(prefix="research_os_synth_"))
    pandoc_body = _try_pandoc(markdown_body, tmp_dir)
    if pandoc_body:
        return "\n".join(head + [pandoc_body, r"\bibliographystyle{unsrtnat}",
                                 r"\bibliography{references}",
                                 r"\end{document}"])

    # Fallback: our own block renderer.
    body: list[str] = []
    in_list = False
    in_table = False
    table_buf: list[list[str]] = []

    def _flush_list():
        nonlocal in_list
        if in_list:
            body.append(r"\end{itemize}")
            in_list = False

    def _flush_table():
        nonlocal in_table
        if in_table and table_buf:
            cols = len(table_buf[0])
            body.append("\\begin{table}[h!]\n\\centering")
            body.append("\\begin{tabular}{" + "l" * cols + "}")
            body.append("\\toprule")
            for i, row in enumerate(table_buf):
                cells = [_inline_md_to_latex(c) for c in row]
                body.append(" & ".join(cells) + " \\\\")
                if i == 0:
                    body.append("\\midrule")
            body.append("\\bottomrule")
            body.append("\\end{tabular}\n\\end{table}")
            table_buf.clear()
            in_table = False

    for line in markdown_body.splitlines():
        stripped = line.strip()

        # Markdown table row?
        if "|" in stripped and stripped.startswith("|") and stripped.endswith("|"):
            # Separator row (|---|---|): skip; the table builder uses
            # row[0] as the header.
            if re.fullmatch(r"\|[\s\-\|:]+\|", stripped):
                continue
            _flush_list()
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            table_buf.append(cells)
            in_table = True
            continue
        else:
            if in_table:
                _flush_table()

        if line.startswith("# "):
            _flush_list()
            continue  # title already in \maketitle
        if line.startswith("## "):
            _flush_list()
            body.append(r"\section*{" + _inline_md_to_latex(line[3:].strip()) + "}")
            continue
        if line.startswith("### "):
            _flush_list()
            body.append(r"\subsection*{" + _inline_md_to_latex(line[4:].strip()) + "}")
            continue
        if line.startswith("#### "):
            _flush_list()
            body.append(r"\subsubsection*{" + _inline_md_to_latex(line[5:].strip()) + "}")
            continue
        if line.startswith("!["):
            _flush_list()
            m = re.match(r"!\[(.*?)\]\((.+?)\)", line)
            if m:
                caption, path = m.group(1), m.group(2)
                body.append(r"\begin{figure}[h!]")
                body.append(r"  \centering")
                body.append(
                    r"  \includegraphics[width=0.85\linewidth]{" + path + "}"
                )
                body.append(
                    r"  \caption{" + _inline_md_to_latex(caption) + "}"
                )
                body.append(r"\end{figure}")
            continue
        if stripped.startswith(("- ", "* ")):
            if not in_list:
                body.append(r"\begin{itemize}")
                in_list = True
            body.append("  \\item " + _inline_md_to_latex(stripped[2:]))
            continue
        if stripped.startswith("> "):
            _flush_list()
            body.append(r"\begin{quote}")
            body.append(_inline_md_to_latex(stripped[2:]))
            body.append(r"\end{quote}")
            continue
        if stripped:
            _flush_list()
            body.append(_inline_md_to_latex(line))
        else:
            _flush_list()
            body.append("")

    _flush_list()
    _flush_table()

    body.append(r"\bibliographystyle{unsrtnat}")
    body.append(r"\bibliography{references}")
    body.append(r"\end{document}")
    return "\n".join(head + body)
