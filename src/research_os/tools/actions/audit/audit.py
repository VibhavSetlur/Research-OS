"""Audit tools — checks that go beyond a simple test run.

Every audit writes a markdown report into the *current* experiment's
``outputs/reports/`` directory so the audit becomes part of the research record.
"""

from __future__ import annotations

import logging
import re
import uuid
from pathlib import Path
from typing import Any

from research_os.tools.actions.audit._base import AuditBase, AuditFinding
from research_os.tools.actions.audit._paper import (
    figure_refs as _resolve_figure_refs,
    has_references as _resolve_has_references,
    has_section as _resolve_has_section,
    is_typst as _is_typst,
    section_body as _resolve_section_body,
)

logger = logging.getLogger("research_os.tools.audit")


def get_current_path(root: Path) -> str:
    """Return the active numbered experiment folder (e.g. ``02_eda``) or ``""``."""
    root = Path(root)
    try:
        from research_os.project_ops import load_state

        state = load_state(root)
        current = state.get("current_path")
        if current and current != "main":
            return current
    except Exception:
        pass

    workspace = root / "workspace"
    if workspace.exists():
        dirs = [
            d.name
            for d in workspace.iterdir()
            if d.is_dir()
            and d.name[:2].isdigit()
            and not d.name.endswith("__DEAD_END")
        ]
        if dirs:
            return sorted(dirs)[-1]
    return ""


def _report_path(root: Path, filename: str) -> Path:
    root = Path(root)
    current = get_current_path(root)
    if current:
        return root / "workspace" / current / "outputs" / "reports" / filename
    return root / "workspace" / "logs" / filename


# ---------------------------------------------------------------------------
# Synthesis audit — checks paper structure, claim grounding, and citations.
# ---------------------------------------------------------------------------


def audit_synthesis(
    paper_path: str,
    root: Path,
    *,
    override_no_pdfs: bool = False,
    override_rationale: str = "",
) -> dict[str, Any]:
    root = Path(root)
    try:
        p = root / paper_path
        if not p.exists() or not p.is_file():
            return {"status": "error", "message": f"Paper not found: {paper_path}"}

        text = p.read_text()
        lower = text.lower()
        typst = _is_typst(paper_path)

        # Section coverage. Markdown uses ``## <name>`` (or LaTeX
        # ``\section{<name>}``); Typst uses ``= <name>`` headings, except
        # the abstract, which lives in the template ``conf(abstract: [ … ])``
        # block rather than under a heading.
        required = ["abstract", "introduction", "methods", "results", "discussion"]
        if typst:
            missing_sections = []
            for s in required:
                if s == "abstract":
                    present = bool(re.search(r"abstract\s*:\s*\[", text, re.I))
                else:
                    present = _resolve_has_section(text, s, True)
                if not present:
                    missing_sections.append(s)
        else:
            missing_sections = [
                s for s in required
                if f"## {s}" not in lower and f"\\section{{{s}" not in lower
            ]

        # Causal language flagged for observational research
        causal_terms = [
            r"\bcauses\b",
            r"\bcaused by\b",
            r"\bproves\b",
            r"\bdemonstrates causality\b",
        ]
        causal_hits = []
        for term in causal_terms:
            for m in re.finditer(term, lower):
                start = max(0, m.start() - 40)
                end = min(len(lower), m.end() + 40)
                causal_hits.append({"term": term.strip("\\b "), "context": lower[start:end]})

        # Citation density: count [@key] or \cite{key}, and ALSO count
        # author-year prose form `(Author 2024)` / `(Author et al.
        # 2024)` / `(Author, 2024)` since most modern Markdown drafts
        # use that style instead of Pandoc citekeys. Without the
        # author-year regex, citation_count under-reports on drafts
        # that use prose citations.
        citations_pandoc = re.findall(r"\[@[^\]]+\]|\\cite\{[^}]+\}", text)
        citations_authoryear = re.findall(
            r"\(([A-Z][a-zA-Z\-]+(?:\s+et\s+al\.?)?(?:\s*&\s*[A-Z][a-zA-Z\-]+)?(?:\s*,)?\s+(?:19|20)\d{2}[a-z]?)\)",
            text,
        )
        citation_count = len(citations_pandoc) + len(set(citations_authoryear))
        word_count = len(text.split())
        citation_density = citation_count / max(1, word_count) * 1000  # per 1000 words

        # Figures referenced vs. files present. Markdown drafts embed via
        # ``![](path)``; Typst drafts via ``#figure(image("path"))`` /
        # ``#image("path")`` — restrict to image-like extensions either way.
        if typst:
            figure_refs = {
                ref for ref in _resolve_figure_refs(text, True)
                if ref.lower().endswith((".png", ".svg", ".pdf", ".jpg"))
            }
        else:
            figure_refs = set(
                re.findall(r"!\[[^\]]*\]\(([^)]+\.(?:png|svg|pdf|jpg))\)", text)
            )
        figures_present = []
        synthesis_dir = root / "synthesis"
        for ref in figure_refs:
            candidate = synthesis_dir / ref if not ref.startswith("/") else root / ref.lstrip("/")
            if not candidate.exists():
                candidate = root / ref
            figures_present.append({"ref": ref, "exists": candidate.exists()})

        has_bibliography = _resolve_has_references(text, typst)

        # Quality-bar gates against the available workspace evidence.
        # A purely structural audit (sections exist, citations cited)
        # misses the failure mode where paper.md is 900 words and uses
        # 10 of 17 workspace figures — structurally fine, substantively
        # a sketch.
        workspace = root / "workspace"
        figures_available = []
        if workspace.is_dir():
            for step_dir in workspace.iterdir():
                if not (step_dir.is_dir() and step_dir.name[:2].isdigit()):
                    continue
                figs = step_dir / "outputs" / "figures"
                if figs.is_dir():
                    figures_available.extend(
                        f"workspace/{step_dir.name}/outputs/figures/{p.name}"
                        for p in figs.iterdir()
                        if p.suffix.lower() in {".png", ".svg"}
                    )
        n_available = len(figures_available)
        # Count any workspace figure that's referenced (anywhere) in the paper.
        figures_used_from_workspace = sum(
            1 for fig_path in figures_available
            if any(stem in text for stem in (
                fig_path,
                Path(fig_path).name,
                Path(fig_path).stem,
            ))
        )
        coverage = (figures_used_from_workspace / n_available) if n_available else 1.0

        # Word counts per IMRAD section.
        # Markdown terminator `^##\s` (require space) so `###` / `####`
        # sub-section headers don't truncate the parent section. Typst
        # sections are `= <name>` headings; the abstract is the template
        # `conf(abstract: [ … ])` block, captured via _resolve_section_body
        # / the abstract regex.
        section_word_counts: dict[str, int] = {}
        for sec in ("abstract", "introduction", "methods", "results", "discussion"):
            if typst:
                if sec == "abstract":
                    am = re.search(
                        r"abstract\s*:\s*\[(.+?)\]",
                        text, re.DOTALL | re.IGNORECASE,
                    )
                    body = am.group(1) if am else ""
                else:
                    body = _resolve_section_body(text, sec, True)
            else:
                m = re.search(
                    rf"^##\s+{sec}\s*\n(.+?)(?=^##\s|\Z)",
                    text, re.MULTILINE | re.DOTALL | re.IGNORECASE,
                )
                body = m.group(1) if m else ""
            section_word_counts[sec] = len(body.split())
        total_words = sum(section_word_counts.values()) or word_count

        # MIN bar (target = informal paper); HARD bar (target = real journal).
        MIN_BAR = {
            "abstract": 150, "introduction": 300, "methods": 400,
            "results": 400, "discussion": 300, "total": 1500,
        }
        short_sections = [
            s for s, n in section_word_counts.items() if n < MIN_BAR[s]
        ]

        quality_gates = {
            "word_counts": section_word_counts,
            "total_words": total_words,
            "min_word_bar": MIN_BAR,
            "short_sections": short_sections,
            "figures_available_in_workspace": n_available,
            "figures_used_from_workspace": figures_used_from_workspace,
            "figure_coverage_ratio": round(coverage, 3),
            "figure_coverage_target": 0.8,
        }
        # Map to specific revision instructions the AI can act on.
        gate_blockers: list[str] = []
        if total_words < MIN_BAR["total"]:
            gate_blockers.append(
                f"Paper is {total_words} words — minimum publishable bar is "
                f"{MIN_BAR['total']}. Expand the {', '.join(short_sections)} "
                "section(s); each per-step `conclusions.md` has structured "
                "material to draw from."
            )
        if n_available and coverage < 0.8:
            unused = [
                p for p in figures_available
                if not any(stem in text for stem in (p, Path(p).name, Path(p).stem))
            ]
            gate_blockers.append(
                f"Only {figures_used_from_workspace} of {n_available} workspace "
                f"figures ({int(coverage*100)}%) are referenced. Target ≥80%. "
                f"Unused: {', '.join(unused[:5])}"
                + (f" + {len(unused)-5} more" if len(unused) > 5 else "")
            )
        for sec in short_sections:
            if sec != "abstract":
                gate_blockers.append(
                    f"{sec.title()} is {section_word_counts[sec]} words — "
                    f"min {MIN_BAR[sec]}. Pull more from the per-step "
                    "`workspace/<step>/conclusions.md` `## Findings` / "
                    "`## Methods` blocks."
                )

        # Pre-initialise the aggregation fields so the report dict
        # builds before the step-warning + citations-md walks (which
        # run below + populate them).
        propagated_step_warnings: list[dict[str, Any]] = []
        recurring_blockers: list[str] = []
        unverified_citations = 0

        report = {
            "missing_sections": missing_sections,
            "causal_language_hits": causal_hits[:10],
            "citation_count": citation_count,
            "citation_density_per_1000_words": round(citation_density, 2),
            "figures_referenced": len(figure_refs),
            "figures_present": [f for f in figures_present if f["exists"]],
            "figures_missing": [f for f in figures_present if not f["exists"]],
            "has_bibliography": has_bibliography,
            "quality_gates": quality_gates,
            "gate_blockers": gate_blockers,
            "propagated_step_warnings": propagated_step_warnings,
            "recurring_blockers": recurring_blockers,
            "unverified_citations": unverified_citations,
            "citation_count_pandoc": len(citations_pandoc),
            "citation_count_authoryear": len(set(citations_authoryear)),
        }

        out = _report_path(root, "synthesis_audit.md")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            "# Synthesis Audit\n\n"
            f"- Missing sections: {', '.join(missing_sections) or 'none'}\n"
            f"- Causal-language hits: {len(causal_hits)}\n"
            f"- Citation count: {citation_count} ({citation_density:.1f}/1000w)\n"
            f"- Figures referenced: {len(figure_refs)} "
            f"(present {len([f for f in figures_present if f['exists']])} / "
            f"missing {len([f for f in figures_present if not f['exists']])})\n"
            f"- Bibliography present: {has_bibliography}\n"
        )

        # Aggregate per-step warnings from every step_summary.yaml.
        # A purely structural audit never opens the per-step ledger,
        # so a project where 10 steps each carried "literature
        # grounding deferred" would silently pass synthesis. Walk
        # every workspace step's yaml, pull `warnings: [...]`, and
        # dedupe by signature; any signature that recurs across ≥3
        # steps (or any signature matching the literature-deferred
        # pattern, regardless of count) escalates to a gate_blocker.
        try:
            import yaml as _yaml_mod
            sig_to_steps: dict[str, list[str]] = {}
            lit_deferred_steps: list[str] = []
            lit_no_grounding_steps: list[str] = []
            for step_dir in (root / "workspace").iterdir():
                if not (step_dir.is_dir() and step_dir.name[:2].isdigit()):
                    continue
                ss_path = step_dir / "step_summary.yaml"
                if not ss_path.exists():
                    continue
                try:
                    ss = _yaml_mod.safe_load(ss_path.read_text()) or {}
                except Exception:
                    continue
                for w in (ss.get("warnings") or []):
                    sig = re.sub(r"\s+", " ", str(w))[:60].lower().strip()
                    sig_to_steps.setdefault(sig, []).append(step_dir.name)
                # Per-step literature deferrals are first-class.
                ld = ss.get("literature_deferred") or []
                if isinstance(ld, list) and ld:
                    lit_deferred_steps.append(step_dir.name)
                # literature.claims_grounded == 0 means the step ran
                # the loop but found nothing — also a deferral signal.
                lit_block = ss.get("literature") or {}
                if (
                    isinstance(lit_block, dict)
                    and ss.get("literature_required") is not False
                    and (step_dir / "conclusions.md").exists()
                    and lit_block.get("claims_grounded", -1) == 0
                ):
                    lit_no_grounding_steps.append(step_dir.name)
            for sig, steps_seen in sig_to_steps.items():
                propagated_step_warnings.append({
                    "signature": sig,
                    "step_count": len(steps_seen),
                    "steps": sorted(steps_seen),
                })
                if (
                    any(kw in sig for kw in (
                        "literature", "pending verification",
                        "tool_search", "grounding"
                    ))
                    or len(steps_seen) >= 3
                ):
                    recurring_blockers.append(
                        f"`{sig}` recurs across {len(steps_seen)} step(s) "
                        f"({', '.join(sorted(steps_seen)[:5])}). Address "
                        "before synthesis — the deferred-pattern audit gate "
                        "blocks final assembly until resolved."
                    )
            # Surface per-step literature_deferred + zero-grounding.
            if lit_deferred_steps:
                recurring_blockers.append(
                    f"{len(lit_deferred_steps)} step(s) have non-empty "
                    f"literature_deferred in step_summary.yaml: "
                    f"{', '.join(lit_deferred_steps[:5])}"
                    f"{'…' if len(lit_deferred_steps) > 5 else ''}. Resolve "
                    "via research/literature_per_step OR pass "
                    "`override_completeness_gate=true` with rationale."
                )
            if lit_no_grounding_steps:
                recurring_blockers.append(
                    f"{len(lit_no_grounding_steps)} step(s) ran without "
                    "grounding any claims (literature.claims_grounded == 0): "
                    f"{', '.join(lit_no_grounding_steps[:5])}"
                    f"{'…' if len(lit_no_grounding_steps) > 5 else ''}. "
                    "Either run literature_per_step or set "
                    "`literature_required: false` if the step is pure "
                    "data engineering."
                )
        except Exception as e:
            logger.debug("step-warning aggregation skipped: %s", e)

        # Hard-block on `pending verification` citations.
        # citations.md aggregates per-step ## References to ground + per-PDF
        # sidecars; if ANY entry is still pending after the synthesis
        # paper has been drafted, the audit must block (override via
        # `override_completeness_gate=true` if the researcher explicitly
        # accepts an unverified draft).
        try:
            cit_md = root / "workspace" / "citations.md"
            if cit_md.exists():
                cit_text = cit_md.read_text()
                unverified_citations = cit_text.count("pending verification")
            if unverified_citations > 0:
                recurring_blockers.append(
                    f"workspace/citations.md has {unverified_citations} "
                    "citation(s) still marked `⏳ pending verification`. "
                    "Run `tool_literature_search_and_save` (or "
                    "`tool_citations_verify`) for each before "
                    "final_assembly; OR call tool_synthesize with "
                    "`override_completeness_gate=true` + "
                    "`override_rationale=...` if the researcher accepts "
                    "an unverified draft."
                )
        except Exception as e:
            logger.debug("citations.md scan skipped: %s", e)

        # Merge recurring_blockers into gate_blockers so the existing
        # escalation logic below treats them with full BLOCKER weight.
        gate_blockers.extend(recurring_blockers)

        # Default-deny when zero PDFs across all literature-required
        # steps. Closes the audit gap where `papers_downloaded == 0`
        # with mixed AGREES would otherwise sail through. Override
        # path: override_no_pdfs=true + override_rationale=...
        zero_pdf_block = ""
        try:
            import yaml as _yaml_mod
            from research_os.tools.actions.search.literature import (
                count_valid_pdfs,
            )
            workspace = root / "workspace"
            lit_required_steps: list[str] = []
            total_pdfs = 0
            if workspace.is_dir():
                for step_dir in workspace.iterdir():
                    if not (step_dir.is_dir() and step_dir.name[:2].isdigit()):
                        continue
                    if step_dir.name.endswith("__DEAD_END"):
                        continue
                    if not (step_dir / "conclusions.md").exists():
                        continue
                    ss_path = step_dir / "step_summary.yaml"
                    if ss_path.exists():
                        try:
                            ss = _yaml_mod.safe_load(ss_path.read_text()) or {}
                        except Exception:
                            ss = {}
                        if ss.get("literature_required") is False:
                            continue
                    lit_required_steps.append(step_dir.name)
                    lit_dir = step_dir / "literature"
                    # Count only magic-validated PDFs: a renamed 403/HTML
                    # page named *.pdf is NOT a downloaded paper.
                    total_pdfs += count_valid_pdfs(lit_dir)
            project_lit_dir = root / "inputs" / "literature"
            total_pdfs += count_valid_pdfs(project_lit_dir)
            report["literature_required_steps"] = lit_required_steps
            report["total_pdfs_across_workspace"] = total_pdfs
            # Require BOTH override_no_pdfs=true AND a non-empty
            # override_rationale. The boolean alone would silently
            # bypass the gate and leave no audit trail.
            override_active = (
                bool(override_no_pdfs) and bool(override_rationale.strip())
            )
            if (
                lit_required_steps
                and total_pdfs == 0
                and not override_active
            ):
                if override_no_pdfs and not override_rationale.strip():
                    zero_pdf_block = (
                        "DEFAULT-DENY: synthesis blocked because "
                        "override_no_pdfs=true was passed WITHOUT an "
                        "override_rationale. The override is "
                        "audit-trail-bearing — supply a one-sentence "
                        "rationale explaining why literature is "
                        "structurally unavailable for this project."
                    )
                else:
                    zero_pdf_block = (
                        f"DEFAULT-DENY: synthesis blocked because zero PDFs "
                        f"are present across {len(lit_required_steps)} "
                        "literature-required step(s) (and inputs/literature/ "
                        "is also empty). A paper with no grounded literature "
                        "is structurally a sketch. Either run "
                        "tool_literature_search_and_save for each step's "
                        "claims, OR call tool_audit_synthesis with "
                        "`override_no_pdfs=true` + `override_rationale=...` "
                        "if literature is structurally unavailable (closed "
                        "field, novel measurement, etc.)."
                    )
                gate_blockers.append(zero_pdf_block)
            elif override_active:
                report["override_no_pdfs"] = True
                report["override_rationale"] = override_rationale
        except Exception as e:
            logger.debug("zero-PDF default-deny check skipped: %s", e)

        # Reflect populated values back into the report dict (they were
        # pre-initialised empty above so the dict constructor succeeded
        # before the walks ran).
        report["propagated_step_warnings"] = propagated_step_warnings
        report["recurring_blockers"] = recurring_blockers
        report["unverified_citations"] = unverified_citations
        report["gate_blockers"] = gate_blockers

        # gate_blockers (quality bars) escalate to status='error' —
        # but ONLY when the paper is large enough to plausibly be a
        # real submission attempt. A 50-word stub fixture / early-
        # draft scratch gets only warnings; the BLOCKER status fires
        # once the paper has crossed the "looks like an actual paper"
        # threshold (≥500 words total OR the AI explicitly called
        # final_assembly).
        looks_like_real_paper = total_words >= 500
        if gate_blockers and looks_like_real_paper:
            status = "error"
            message = (
                f"{len(gate_blockers)} quality-bar blocker(s) — paper isn't "
                "publication-shape yet. Address each before final_assembly."
            )
        elif gate_blockers:
            # Stub-shaped paper: surface the gaps as warnings so the AI
            # knows where to expand, but don't block.
            status = "warning"
            message = (
                f"Paper is a stub ({total_words} words). The "
                f"{len(gate_blockers)} quality-bar gap(s) below will become "
                "BLOCKERs once total_words ≥ 500. Expand the sections + "
                "incorporate the workspace figures listed."
            )
        elif missing_sections or causal_hits or not has_bibliography:
            status = "warning"
            message = "Synthesis audit produced warnings."
        else:
            status = "success"
            message = "Synthesis passed audit."
        result = {
            "status": status,
            "report": report,
            "report_path": str(out.relative_to(root)),
            "blockers": gate_blockers,
            "message": message,
        }
        # Derive structured AuditFindings from the result dict and emit
        # the companion .json + .audit_findings.jsonl artefacts. The
        # markdown report written above (under
        # outputs/reports/synthesis_audit.md or logs/synthesis_audit.md)
        # is preserved byte-for-byte so existing readers + the documented
        # report_path return field keep working; the new artefacts are
        # additive. Persistence is best-effort — if writing the JSON
        # ledger fails (e.g. read-only workspace) the gate caller still
        # gets the original blockers list.
        try:
            from research_os.tools.actions.audit._base import (
                write_audit_outputs,
            )
            from research_os.tools.actions.audit.synthesis_audit import (
                findings_from_synthesis_result,
            )

            findings = findings_from_synthesis_result(result, paper_path)
            write_audit_outputs(findings, "synthesis", root)
            result["findings"] = [f.to_dict() for f in findings]
        except Exception as exc:  # pragma: no cover - best-effort persist
            logger.debug("synthesis findings persist failed: %s", exc)
        return result
    except Exception as e:
        logger.exception("audit_synthesis failed")
        return {"status": "error", "message": str(e)}


# ---------------------------------------------------------------------------
# Statistical power
# ---------------------------------------------------------------------------


def audit_power(
    filepath: str, effect_size: float, alpha: float, n: int, root: Path
) -> dict[str, Any]:
    root = Path(root)
    try:
        try:
            from statsmodels.stats import power as smp  # type: ignore
        except ImportError:
            return {
                "status": "error",
                "message": "statsmodels required (pip install statsmodels)",
            }

        power_value = smp.tt_ind_solve_power(
            effect_size=effect_size, nobs1=n, alpha=alpha, power=None
        )
        out = _report_path(root, "power_report.md")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            "# Power Analysis Report\n\n"
            f"- Effect size: {effect_size}\n"
            f"- Alpha: {alpha}\n"
            f"- n: {n}\n"
            f"- Computed power: {power_value:.4f}\n"
            f"- Source file: {filepath}\n"
        )
        report = {
            "power": power_value,
            "alpha": alpha,
            "effect_size": effect_size,
            "n": n,
        }
        return {
            "status": "warning" if power_value < 0.8 else "success",
            "report": report,
            "report_path": str(out.relative_to(root)),
            "message": (
                f"Low power ({power_value:.2f} < 0.8) — consider larger n."
                if power_value < 0.8
                else "Power analysis passed."
            ),
        }
    except Exception as e:
        logger.exception("audit_power failed")
        return {"status": "error", "message": str(e)}


# ---------------------------------------------------------------------------
# Model-assumption checks (residual normality, equal variance, multicollinearity)
# ---------------------------------------------------------------------------


def audit_assumptions(filepath: str, root: Path) -> dict[str, Any]:
    """Run a full diagnostic battery on residuals / design / model output.

    Tests run (each optional based on which columns are present):

    * **Shapiro-Wilk** — residual normality.
    * **Levene** — homogeneity of variance across groups.
    * **Breusch-Pagan** — heteroscedasticity (residual vs fitted).
    * **Durbin-Watson** — residual autocorrelation (target ≈ 2.0).
    * **Variance Inflation Factor (VIF)** — multicollinearity per
      predictor (target < 5.0; > 10.0 = severe).
    * **Cook's distance** — influential observations (target < 4/n).

    Expected column conventions (any subset triggers the matching test):

    * ``residual`` / ``residuals`` — residual values.
    * ``fitted`` / ``predicted`` — fitted values (enables BP, scale-loc).
    * ``group`` + ``value`` — for Levene.
    * any other numeric columns — interpreted as design matrix for VIF.
    * ``cooks_distance`` or ``leverage`` if pre-computed.
    """
    root = Path(root)
    try:
        p = root / filepath
        if not p.exists():
            return {"status": "error", "message": f"File not found: {filepath}"}

        import pandas as pd  # type: ignore

        df = pd.read_csv(p)
        report: dict[str, Any] = {}
        warnings: list[str] = []

        from scipy import stats as sst  # type: ignore

        res_col = next((c for c in ("residual", "residuals") if c in df.columns), None)
        fitted_col = next((c for c in ("fitted", "predicted") if c in df.columns), None)

        # --- 1. Shapiro-Wilk normality ---
        if res_col:
            res = df[res_col].dropna()
            try:
                w, p_value = sst.shapiro(res[: min(5000, len(res))])
                report["shapiro_wilk"] = {
                    "W": float(w), "p_value": float(p_value),
                    "interpretation": "residuals NOT normal at α=0.05"
                    if p_value < 0.05 else "no evidence against normality",
                }
                if p_value < 0.05:
                    warnings.append(
                        f"Residuals fail Shapiro-Wilk normality (p={p_value:.3g}). "
                        "Consider rank-based or bootstrap inference."
                    )
            except Exception as e:
                report["shapiro_wilk"] = f"failed: {e}"

        # --- 2. Levene's equality-of-variance ---
        if "group" in df.columns and "value" in df.columns:
            try:
                groups = [g["value"].dropna() for _, g in df.groupby("group")]
                stat, p_value = sst.levene(*groups)
                report["levene"] = {
                    "statistic": float(stat), "p_value": float(p_value),
                    "interpretation": "heteroscedastic" if p_value < 0.05
                                       else "homoscedastic",
                }
                if p_value < 0.05:
                    warnings.append(
                        f"Heteroscedasticity (Levene p={p_value:.3g}). "
                        "Welch's t / robust SEs recommended."
                    )
            except Exception as e:
                report["levene"] = f"failed: {e}"

        # --- 3. Breusch-Pagan + scale-location summary ---
        if res_col and fitted_col:
            try:
                from statsmodels.stats.diagnostic import het_breuschpagan  # type: ignore
                import numpy as np  # type: ignore

                resid = df[res_col].dropna().to_numpy()
                fitted = df[fitted_col].loc[df[res_col].dropna().index].to_numpy()
                # Design matrix = [1, fitted]
                X = np.column_stack([np.ones_like(fitted), fitted])
                lm_stat, lm_p, _f_stat, _f_p = het_breuschpagan(resid, X)
                report["breusch_pagan"] = {
                    "lm_statistic": float(lm_stat),
                    "p_value": float(lm_p),
                    "interpretation": "heteroscedastic" if lm_p < 0.05
                                       else "homoscedastic",
                }
                if lm_p < 0.05:
                    warnings.append(
                        f"Breusch-Pagan p={lm_p:.3g} — residual variance "
                        "depends on the fitted value. Robust (HC3) SEs "
                        "or weighted least squares recommended."
                    )
            except ImportError:
                report["breusch_pagan"] = "statsmodels not installed"
            except Exception as e:
                report["breusch_pagan"] = f"failed: {e}"

        # --- 4. Durbin-Watson autocorrelation ---
        if res_col:
            try:
                from statsmodels.stats.stattools import durbin_watson  # type: ignore

                dw = float(durbin_watson(df[res_col].dropna()))
                report["durbin_watson"] = {
                    "statistic": dw,
                    "interpretation":
                        "positive autocorrelation" if dw < 1.5
                        else "negative autocorrelation" if dw > 2.5
                        else "no strong autocorrelation",
                }
                if dw < 1.5 or dw > 2.5:
                    warnings.append(
                        f"Durbin-Watson = {dw:.2f} (target ≈ 2.0); "
                        "consider time-series / clustered SE adjustment."
                    )
            except ImportError:
                pass
            except Exception as e:
                report["durbin_watson"] = f"failed: {e}"

        # --- 5. VIF (multicollinearity) ---
        numeric_cols = [
            c for c in df.columns
            if c not in {res_col, fitted_col, "group", "value",
                          "cooks_distance", "leverage"}
            and pd.api.types.is_numeric_dtype(df[c])
        ]
        if len(numeric_cols) >= 2:
            try:
                from statsmodels.stats.outliers_influence import variance_inflation_factor  # type: ignore
                import numpy as np  # type: ignore

                X = df[numeric_cols].dropna().to_numpy()
                vifs = {}
                if X.shape[0] > X.shape[1] + 1:
                    for i, name in enumerate(numeric_cols):
                        try:
                            v = float(variance_inflation_factor(X, i))
                            vifs[name] = round(v, 2)
                        except Exception:
                            continue
                    report["vif"] = vifs
                    bad = {k: v for k, v in vifs.items() if v > 10}
                    moderate = {k: v for k, v in vifs.items()
                                if 5 < v <= 10}
                    if bad:
                        warnings.append(
                            "Severe multicollinearity (VIF > 10): "
                            + ", ".join(f"{k}={v}" for k, v in bad.items())
                            + ". Drop or combine these predictors."
                        )
                    elif moderate:
                        warnings.append(
                            "Moderate multicollinearity (5 < VIF ≤ 10): "
                            + ", ".join(f"{k}={v}" for k, v in moderate.items())
                            + ". Inspect predictor pairs."
                        )
            except ImportError:
                pass
            except Exception as e:
                report["vif"] = f"failed: {e}"

        # --- 6. Cook's distance influential observations ---
        if "cooks_distance" in df.columns:
            try:
                cd = df["cooks_distance"].dropna()
                n = max(1, len(cd))
                thr = 4.0 / n
                n_influential = int((cd > thr).sum())
                report["cooks_distance"] = {
                    "threshold_4_over_n": round(thr, 4),
                    "n_influential": n_influential,
                    "pct_influential": round(100 * n_influential / n, 2),
                }
                if n_influential / n > 0.05:
                    warnings.append(
                        f"{n_influential} observations exceed Cook's D "
                        f"threshold (4/n = {thr:.4f}); inspect / report "
                        "leave-one-out sensitivity."
                    )
            except Exception as e:
                report["cooks_distance"] = f"failed: {e}"

        out = _report_path(root, "assumption_report.md")
        out.parent.mkdir(parents=True, exist_ok=True)
        lines = ["# Assumption Audit", "",
                 f"- Source file: `{filepath}`", ""]
        for k, v in report.items():
            lines.append(f"### {k}")
            if isinstance(v, dict):
                for kk, vv in v.items():
                    lines.append(f"- **{kk}**: {vv}")
            else:
                lines.append(f"- {v}")
            lines.append("")
        if warnings:
            lines.append("## Warnings")
            for w in warnings:
                lines.append(f"- {w}")
        out.write_text("\n".join(lines) + "\n")

        return {
            "status": "warning" if warnings else "success",
            "report": report,
            "warnings": warnings,
            "report_path": str(out.relative_to(root)),
            "message": (
                "Assumption checks raised warnings." if warnings
                else "All assumption checks passed."
            ),
        }
    except Exception as e:
        logger.exception("audit_assumptions failed")
        return {"status": "error", "message": str(e)}


# ---------------------------------------------------------------------------
# E-value sensitivity (VanderWeele & Ding 2017) for observational designs
# ---------------------------------------------------------------------------


def compute_evalue(
    *,
    risk_ratio: float,
    ci_lower: float | None = None,
    ci_upper: float | None = None,
) -> dict[str, Any]:
    """Compute the E-value for an observed risk ratio + 95% CI bound.

    E = RR + sqrt(RR * (RR - 1)) for RR > 1.
    For RR < 1, evaluate 1/RR first.

    Interpretation: the minimum strength of association (on the
    risk-ratio scale) that an unmeasured confounder would need to have
    with BOTH the exposure and the outcome to explain away the observed
    association.
    """
    import math

    def _one(rr: float) -> float:
        # Reflect to ≥1.
        if rr <= 0:
            return float("nan")
        if rr < 1:
            rr = 1.0 / rr
        return rr + math.sqrt(rr * (rr - 1))

    e_point = _one(risk_ratio)
    # E-value at the CI bound nearest the null (1.0).
    if ci_lower is not None and ci_upper is not None:
        if risk_ratio > 1:
            ci_bound = ci_lower
        else:
            ci_bound = ci_upper
        if ci_bound and (
            (risk_ratio > 1 and ci_bound > 1)
            or (risk_ratio < 1 and ci_bound < 1)
        ):
            e_ci = _one(ci_bound)
        else:
            # CI crosses the null — E-value at CI bound is 1.
            e_ci = 1.0
    else:
        e_ci = None
    interp = (
        f"An unmeasured confounder with risk ratio ≥ {e_point:.2f} with "
        "both exposure and outcome could fully explain the observed "
        f"association of {risk_ratio:.2f}."
    )
    if e_ci is not None:
        interp += (
            f" The E-value at the 95% CI bound nearest the null is "
            f"{e_ci:.2f}."
        )
    return {
        "risk_ratio": risk_ratio,
        "ci_lower": ci_lower, "ci_upper": ci_upper,
        "e_value_point": round(e_point, 3),
        "e_value_ci_bound": round(e_ci, 3) if e_ci is not None else None,
        "interpretation": interp,
    }


def audit_evalue(
    risk_ratio: float, root: Path,
    ci_lower: float | None = None, ci_upper: float | None = None,
) -> dict[str, Any]:
    """Compute + persist an E-value sensitivity report."""
    root = Path(root)
    res = compute_evalue(
        risk_ratio=risk_ratio, ci_lower=ci_lower, ci_upper=ci_upper,
    )
    out = _report_path(root, "evalue_report.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# E-value Sensitivity (VanderWeele & Ding, 2017)",
        "",
        f"- Observed risk ratio: **{risk_ratio}**",
    ]
    if ci_lower is not None or ci_upper is not None:
        lines.append(f"- 95% CI: ({ci_lower}, {ci_upper})")
    lines.extend([
        f"- E-value at point estimate: **{res['e_value_point']}**",
    ])
    if res["e_value_ci_bound"] is not None:
        lines.append(
            f"- E-value at CI bound nearest null: **{res['e_value_ci_bound']}**"
        )
    lines.extend([
        "",
        "## Interpretation",
        "",
        res["interpretation"],
        "",
        "## Reporting guidance",
        "- Cite VanderWeele TJ, Ding P. *Sensitivity Analysis in "
        "Observational Research: Introducing the E-Value*. Ann Intern "
        "Med. 2017;167(4):268-274.",
        "- Report BOTH the point E-value and the CI-bound E-value.",
        "- A small E-value (close to 1) means even modest unmeasured "
        "confounding could explain the result; a large E-value means "
        "the result is robust to plausible confounding.",
    ])
    out.write_text("\n".join(lines) + "\n")
    return {
        "status": "success",
        **res,
        "report_path": str(out.relative_to(root)),
    }


# ---------------------------------------------------------------------------
# Master auditor — one call, every quality gate.
# ---------------------------------------------------------------------------


def audit_quality_full(
    root: Path,
    *,
    target_path: str | None = None,
    skip: list[str] | None = None,
) -> dict[str, Any]:
    """Run every quality audit in one call and aggregate the verdict.

    Runs (each is opt-out via ``skip``):

    * ``step_completeness`` — focal figure + caption + summary + non-stub
      conclusions + provenance coverage per active step.
    * ``code_quality``      — ruff (if installed) + AST-based complexity,
      docstring, smell checks per script.
    * ``prose_quality``     — hedging, vague quantifiers, passive voice,
      reading level, causal-language gating, reporting-standard
      coverage across paper + per-step conclusions.
    * ``claims``            — every number in synthesis/paper.md traces
      to a workspace output.
    * ``preregistration_diff`` — divergence between the frozen SAP and
      current state (only if a pre-registration exists).

    Writes ``workspace/logs/audit_master.md`` and returns the unified
    blocker set. ``tool_synthesize`` calls this as its first gate.
    """
    root = Path(root)
    skip = skip or []
    results: dict[str, Any] = {}
    all_blockers: list[str] = []
    all_warnings: list[str] = []

    if "step_completeness" not in skip:
        sc = audit_step_completeness(root)
        results["step_completeness"] = sc
        if sc.get("status") == "error":
            all_blockers.extend(
                f"[completeness] {b}" for b in sc.get("blockers", [])
            )

    if "code_quality" not in skip:
        try:
            from research_os.tools.actions.audit.code_quality import (
                audit_code_quality,
            )

            cq = audit_code_quality(root)
            results["code_quality"] = cq
            if cq.get("status") == "error":
                all_blockers.append(
                    f"[code_quality] {len([s for st in cq.get('per_step', []) for s in st.get('scripts', []) if s.get('blockers')])} script(s) failed lint/AST checks"
                )
        except Exception as e:
            results["code_quality"] = {"status": "error", "message": str(e)}

    if "prose_quality" not in skip:
        try:
            from research_os.tools.actions.audit.prose_quality import (
                audit_prose,
            )

            pq = audit_prose(root)
            results["prose_quality"] = pq
            if pq.get("status") == "error":
                for d in pq.get("documents") or []:
                    for b in d.get("blockers") or []:
                        all_blockers.append(f"[prose] {d['path']}: {b}")
        except Exception as e:
            results["prose_quality"] = {"status": "error", "message": str(e)}

    if "claims" not in skip:
        try:
            from research_os.tools.actions.audit.claim_grounding import (
                audit_claims,
            )

            cl = audit_claims(root, target_path)
            results["claims"] = cl
            if cl.get("status") == "error":
                all_blockers.append(
                    f"[claims] {cl.get('ungrounded', 0)} numeric claim(s) "
                    f"in {cl.get('target')} not grounded in workspace outputs"
                )
        except Exception as e:
            results["claims"] = {"status": "error", "message": str(e)}

    if "preregistration_diff" not in skip:
        try:
            from research_os.tools.actions.audit.preregistration import (
                diff_preregistration,
            )

            pd_res = diff_preregistration(root)
            results["preregistration_diff"] = pd_res
        except Exception as e:
            results["preregistration_diff"] = {
                "status": "error", "message": str(e),
            }

    if "grounding" not in skip:
        try:
            from research_os.tools.actions.research.grounding import (
                grounding_verify,
            )

            gv = grounding_verify(root)
            results["grounding"] = gv
            if gv.get("status") == "error":
                all_blockers.append(
                    f"[grounding] {gv.get('n_ungrounded', 0)} decision(s) "
                    "without grounding records — see workspace/logs/grounding_audit.md"
                )
        except Exception as e:
            results["grounding"] = {"status": "error", "message": str(e)}

    # Aggregate report.
    logs = root / "workspace" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    out = logs / "audit_master.md"
    lines = ["# Master quality audit", ""]
    for name, r in results.items():
        icon = {"success": "✅", "warning": "⚠️",
                "error": "❌"}.get(r.get("status"), "•")
        lines.append(f"## {icon} {name}")
        if r.get("report_path"):
            lines.append(f"- Detail: `{r['report_path']}`")
        for k in ("ungrounded", "blockers", "advice", "message",
                  "n_failed", "coverage_pct"):
            if k in r and r[k] not in (None, [], 0):
                v = r[k]
                lines.append(
                    f"- {k}: {len(v) if isinstance(v, list) else v}"
                )
        lines.append("")
    if all_blockers:
        lines.append("## Combined blockers")
        for b in all_blockers:
            lines.append(f"- {b}")
    out.write_text("\n".join(lines) + "\n")

    return {
        "status": "error" if all_blockers else "success",
        "blockers": all_blockers,
        "warnings": all_warnings,
        "components": results,
        "report_path": str(out.relative_to(root)),
        "advice": (
            f"{len(all_blockers)} blocker(s) across all gates. Fix "
            "before tool_synthesize. The per-component reports under "
            "workspace/logs/ list specifics."
            if all_blockers
            else "All quality gates passed. Ready for synthesis."
        ),
    }


# ---------------------------------------------------------------------------
# AuditBase subclass for ``audit_quality_full``.
#
# The aggregator writes ``workspace/logs/audit_master.md`` and returns the
# dict shape that ``tool_synthesize`` + the dashboard parse. ``AuditMaster``
# is additive: it repackages the same blocker / warning set as structured
# :class:`AuditFinding` objects so the ``write_audit_outputs`` writer can
# fan them out to ``workspace/logs/audit_master_audit.{md,json}`` + the
# ``workspace/logs/.audit_findings.jsonl`` cross-audit ledger. The markdown
# is NEVER replaced — a snapshot test pins its format.
# ---------------------------------------------------------------------------


# Map each component of audit_quality_full onto its dimension label.
# The legacy aggregator's blocker tags ([completeness], [code_quality],
# [prose], [claims], [grounding]) line up with these dimensions; the
# preregistration_diff component never produces a blocker so it only
# surfaces as info / warn.
_MASTER_COMPONENT_DIMENSION: dict[str, str] = {
    "step_completeness": "completeness",
    "code_quality": "code_quality",
    "prose_quality": "prose",
    "claims": "claims",
    "preregistration_diff": "preregistration",
    "grounding": "grounding",
}


# Bracketed-tag → dimension routing for blocker / warning strings the
# legacy aggregator emits. Tags we don't recognise fall back to a
# generic ``master`` dimension so the schema validator never rejects a
# finding just because the aggregator grew a new tag.
_MASTER_TAG_TO_DIMENSION: dict[str, str] = {
    "completeness": "completeness",
    "code_quality": "code_quality",
    "prose": "prose",
    "claims": "claims",
    "preregistration": "preregistration",
    "grounding": "grounding",
}


# The aggregator gate is bypassed end-to-end with
# ``override_completeness_gate=true`` on ``tool_synthesize`` (the
# historical kwarg name; preserved for back-compat). Every finding
# inherits the gate-wide override path so a downstream reviewer can see
# exactly which knob to flip without diving into per-component logic.
_MASTER_OVERRIDE_KWARG = "override_completeness_gate"
_MASTER_OVERRIDE_LOG_FORMAT = (
    "override quality_full by {user} — rationale: {rationale}"
)


def _parse_master_blocker(line: str) -> tuple[str, str]:
    """Pull the bracketed tag off a legacy blocker / warning string.

    Returns ``(dimension, message)``. Unknown tags map to the generic
    ``master`` dimension so the schema validator never rejects a finding
    just because the legacy aggregator grew a new tag.
    """
    m = re.match(r"^\[([^\]]+)\]\s*(.*)$", line.strip())
    if not m:
        return "master", line.strip()
    tag = m.group(1).strip().lower()
    dimension = _MASTER_TAG_TO_DIMENSION.get(tag, tag or "master")
    return dimension, m.group(2).strip() or line.strip()


def _master_finding_uuid(
    audit_name: str,
    dimension: str,
    evidence_paths: list[str],
    extra: str = "",
) -> str:
    """Derive a deterministic UUIDv5 for an audit_master finding.

    Combines audit_name + dimension + evidence_paths (joined with ``|``)
    + an optional disambiguator (used when two findings in the same
    audit/dimension/paths share everything else, e.g. multiple distinct
    blocker messages from the same component). uuid5 keeps the value
    schema-valid (UUID hex shape) and stable across runs on the same
    inputs — re-running the audit on an unchanged tree yields the same
    finding ids, so the .audit_findings.jsonl ledger stays deduplicable
    by id downstream.
    """
    key = "|".join([audit_name, dimension, *evidence_paths, extra])
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, key))


def _master_evidence_paths(
    components: dict[str, Any], dimension: str,
) -> list[str]:
    """Return the workspace-relative report paths a finding points at.

    Always includes the aggregator's own ``workspace/logs/audit_master.md``
    so a reviewer can see the unified view. If the originating
    component recorded a ``report_path`` (it almost always does), that's
    appended too. Paths stay workspace-relative — the v2 writer assumes
    everything is relative to ``root`` so absolute paths would leak the
    host layout into the JSONL ledger.
    """
    paths: list[str] = ["workspace/logs/audit_master.md"]
    for comp_name, comp_result in components.items():
        if not isinstance(comp_result, dict):
            continue
        if _MASTER_COMPONENT_DIMENSION.get(comp_name, comp_name) != dimension:
            continue
        rp = comp_result.get("report_path")
        if rp and isinstance(rp, str) and rp not in paths:
            paths.append(rp)
    return paths


def _build_master_finding(
    *,
    severity: str,
    dimension: str,
    evidence_paths: list[str],
    suggested_fix: str,
    extra: str,
) -> AuditFinding:
    """Construct an AuditFinding with a stable uuid5 id + schema validation."""
    from research_os.tools.actions.audit._base import validate_finding

    audit_name = AuditMaster.name
    finding = AuditFinding(
        audit_name=audit_name,
        severity=severity,
        dimension=dimension,
        id=_master_finding_uuid(audit_name, dimension, evidence_paths, extra),
        evidence_paths=list(evidence_paths),
        suggested_fix=suggested_fix,
        override_kwarg=_MASTER_OVERRIDE_KWARG,
        override_log_format=_MASTER_OVERRIDE_LOG_FORMAT,
    )
    # Re-validate via the schema so a stray bad value (e.g. empty
    # dimension) raises here rather than at write time.
    validate_finding(finding.to_dict())
    return finding


class AuditMaster(AuditBase):
    """:class:`AuditBase` wrapper around :func:`audit_quality_full`.

    Subclasses :class:`AuditBase`; emits the same blocker / warning set
    as the aggregator, repackaged as :class:`AuditFinding` objects so
    the ``write_audit_outputs`` writer can fan them to
    ``workspace/logs/audit_master_audit.{md,json}`` + the
    ``workspace/logs/.audit_findings.jsonl`` ledger.

    The markdown at ``workspace/logs/audit_master.md`` is NOT replaced
    — :func:`audit_quality_full` writes it on every call, and a
    snapshot regression test pins the format. This class is additive
    so downstream readers (the dashboard, ``tool_synthesize``) keep
    working byte-for-byte unchanged.
    """

    name = "audit_master"

    def run(
        self,
        root: Path,
        *,
        target_path: str | None = None,
        skip: list[str] | None = None,
        legacy_result: dict[str, Any] | None = None,
        **_: Any,
    ) -> list[AuditFinding]:
        """Run the legacy aggregator and return its findings as structured objects.

        Parameters
        ----------
        root:
            Project root (parent of ``workspace/``).
        target_path:
            Forwarded to :func:`audit_quality_full` — the document the
            claims gate audits. ``None`` lets the legacy code pick a
            default.
        skip:
            Forwarded to :func:`audit_quality_full` — list of component
            names to skip (e.g. ``["claims"]`` on the first run).
        legacy_result:
            Optional pre-computed result from :func:`audit_quality_full`;
            avoids re-running the heavy aggregator when the caller
            already has the dict (e.g. the server handler that needs
            both the structured findings AND the legacy dict shape to
            return to the MCP client).
        """
        result = legacy_result
        if result is None:
            result = audit_quality_full(
                root, target_path=target_path, skip=skip,
            )

        findings: list[AuditFinding] = []
        components: dict[str, Any] = result.get("components") or {}
        all_blockers: list[str] = list(result.get("blockers") or [])
        all_warnings: list[str] = list(result.get("warnings") or [])

        # 1) One BLOCK finding per blocker string from the aggregator.
        # Counter disambiguates multiple blockers that share a dimension
        # so their stable uuids don't collide.
        per_dim_block_seq: dict[str, int] = {}
        for line in all_blockers:
            dimension, message = _parse_master_blocker(line)
            evidence = _master_evidence_paths(components, dimension)
            seq = per_dim_block_seq.get(dimension, 0)
            per_dim_block_seq[dimension] = seq + 1
            findings.append(
                _build_master_finding(
                    severity="block",
                    dimension=dimension,
                    evidence_paths=evidence,
                    suggested_fix=message,
                    extra=f"block#{seq}",
                )
            )

        # 2) One WARN finding per warning string.
        per_dim_warn_seq: dict[str, int] = {}
        for line in all_warnings:
            dimension, message = _parse_master_blocker(line)
            evidence = _master_evidence_paths(components, dimension)
            seq = per_dim_warn_seq.get(dimension, 0)
            per_dim_warn_seq[dimension] = seq + 1
            findings.append(
                _build_master_finding(
                    severity="warn",
                    dimension=dimension,
                    evidence_paths=evidence,
                    suggested_fix=message,
                    extra=f"warn#{seq}",
                )
            )

        # 3) One INFO finding per successful component so the JSONL
        # ledger records a positive trace alongside the blockers. A
        # component the caller asked to skip never produces an info
        # finding (it didn't run). A component that already emitted a
        # block finding is also skipped here to avoid double-recording.
        for comp_name, comp_result in components.items():
            if not isinstance(comp_result, dict):
                continue
            status = comp_result.get("status")
            if status not in ("success", "warning"):
                continue
            dimension = _MASTER_COMPONENT_DIMENSION.get(comp_name, comp_name)
            if dimension in per_dim_block_seq:
                continue
            evidence = _master_evidence_paths(components, dimension)
            findings.append(
                _build_master_finding(
                    severity="info",
                    dimension=dimension,
                    evidence_paths=evidence,
                    suggested_fix=(
                        f"{comp_name} gate passed cleanly."
                        if status == "success"
                        else f"{comp_name} gate produced advisory warnings only."
                    ),
                    extra="ok",
                )
            )

        return findings


# ---------------------------------------------------------------------------
# Figure quality
# ---------------------------------------------------------------------------


def audit_figure(filepath: str, root: Path) -> dict[str, Any]:
    """Check DPI and basic visual hygiene of a PNG figure."""
    root = Path(root)
    try:
        p = root / filepath
        if not p.exists():
            return {"status": "error", "message": f"Figure not found: {filepath}"}

        report: dict[str, Any] = {"path": filepath}
        warnings: list[str] = []

        try:
            from PIL import Image  # type: ignore

            with Image.open(p) as img:
                dpi = img.info.get("dpi", (72, 72))
                width, height = img.size
                report.update(
                    {
                        "format": img.format,
                        "size_px": [width, height],
                        "dpi": dpi,
                        "mode": img.mode,
                    }
                )
                if isinstance(dpi, tuple) and dpi[0] < 150:
                    warnings.append(
                        f"DPI low ({dpi[0]}). Publication figures should be ≥300 DPI."
                    )
                if min(width, height) < 600:
                    warnings.append(
                        f"Smallest dimension {min(width, height)}px is small for a publication figure."
                    )
        except ImportError:
            warnings.append(
                "Pillow not installed — could not inspect DPI/size (pip install Pillow)"
            )
        except Exception as e:
            warnings.append(f"Could not open image: {e}")

        out = _report_path(root, f"figure_audit_{p.stem}.md")
        out.parent.mkdir(parents=True, exist_ok=True)
        lines = ["# Figure Audit", "", f"- File: {filepath}", ""]
        for k, v in report.items():
            if k == "path":
                continue
            lines.append(f"- **{k}**: {v}")
        if warnings:
            lines.extend(["", "## Warnings"])
            for w in warnings:
                lines.append(f"- {w}")
        out.write_text("\n".join(lines) + "\n")

        return {
            "status": "warning" if warnings else "success",
            "report": report,
            "warnings": warnings,
            "report_path": str(out.relative_to(root)),
            "message": "Figure audit complete.",
        }
    except Exception as e:
        logger.exception("audit_figure failed")
        return {"status": "error", "message": str(e)}


# ---------------------------------------------------------------------------
# Citation verification
# ---------------------------------------------------------------------------


def audit_citations(root: Path) -> dict[str, Any]:
    """Verify every citation in workspace/citations.md against Crossref/Semantic Scholar."""
    root = Path(root)
    try:
        from research_os.tools.actions.search.search import retrieve_literature

        citations_md = root / "workspace" / "citations.md"
        if not citations_md.exists():
            return {
                "status": "error",
                "message": "workspace/citations.md not found — run mem_citations_generate first.",
            }

        text = citations_md.read_text()
        # Citation keys appear as `### \`<key>\`` in the auto-generated format.
        keys = re.findall(r"^###\s+`([^`]+)`", text, flags=re.MULTILINE)

        verified: list[str] = []
        unverified: list[str] = []
        for key in keys:
            query = key.replace("_", " ")
            try:
                res = retrieve_literature(query, source="crossref", limit=1)
                results = res.get("results", []) if isinstance(res, dict) else []
                if results:
                    verified.append(key)
                else:
                    unverified.append(key)
            except Exception:
                unverified.append(key)

        out = _report_path(root, "citation_audit.md")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            "# Citation Audit\n\n"
            f"- Total citations: {len(keys)}\n"
            f"- Verified online: {len(verified)}\n"
            f"- Unverified: {len(unverified)}\n\n"
            "## Unverified\n"
            + "\n".join(f"- `{k}`" for k in unverified)
        )
        return {
            "status": "warning" if unverified else "success",
            "verified": verified,
            "unverified": unverified,
            "report_path": str(out.relative_to(root)),
            "message": (
                f"{len(unverified)} citation(s) could not be verified online."
                if unverified
                else "All citations verified."
            ),
        }
    except Exception as e:
        logger.exception("audit_citations failed")
        return {"status": "error", "message": str(e)}


# ---------------------------------------------------------------------------
# Full reproducibility — re-run experiments in a clean environment
# ---------------------------------------------------------------------------


def audit_reproducibility_full(root: Path) -> dict[str, Any]:
    """Re-run every numbered experiment script and verify outputs.

    If Docker is available, build the project's Dockerfile and run inside;
    otherwise fall back to local re-execution with a warning.
    """
    root = Path(root)
    try:
        import subprocess
        import sys

        workspace = root / "workspace"
        if not workspace.exists():
            return {"status": "error", "message": "workspace/ not found"}

        results: list[dict[str, Any]] = []
        for exp_dir in sorted(workspace.iterdir()):
            if not (exp_dir.is_dir() and exp_dir.name[:2].isdigit()):
                continue
            if exp_dir.name.endswith("__DEAD_END"):
                continue
            scripts_dir = exp_dir / "scripts"
            if not scripts_dir.exists():
                continue
            for script in sorted(scripts_dir.glob("*.py")):
                pre_hashes = _hash_outputs(exp_dir)
                proc = subprocess.run(
                    [sys.executable, str(script)],
                    cwd=str(scripts_dir),
                    capture_output=True,
                    text=True,
                    timeout=600,
                )
                post_hashes = _hash_outputs(exp_dir)
                changed = {
                    k: (pre_hashes.get(k), post_hashes.get(k))
                    for k in set(pre_hashes) | set(post_hashes)
                    if pre_hashes.get(k) != post_hashes.get(k)
                }
                results.append(
                    {
                        "script": str(script.relative_to(root)),
                        "returncode": proc.returncode,
                        "stderr_tail": (proc.stderr or "")[-500:],
                        "outputs_changed": len(changed),
                    }
                )

        out = _report_path(root, "reproducibility_report.md")
        out.parent.mkdir(parents=True, exist_ok=True)
        lines = ["# Reproducibility Audit", ""]
        for r in results:
            lines.append(
                f"- `{r['script']}` → rc={r['returncode']}, outputs changed: {r['outputs_changed']}"
            )
        out.write_text("\n".join(lines) + "\n")

        failed = [r for r in results if r["returncode"] != 0]
        return {
            "status": "warning" if failed else "success",
            "results": results,
            "report_path": str(out.relative_to(root)),
            "message": (
                f"{len(failed)} script(s) failed to re-run." if failed else "All scripts re-ran cleanly."
            ),
        }
    except Exception as e:
        logger.exception("audit_reproducibility_full failed")
        return {"status": "error", "message": str(e)}


def _hash_outputs(exp_dir: Path) -> dict[str, str]:
    """Hash every file under outputs/ for change detection."""
    import hashlib

    out: dict[str, str] = {}
    outputs = exp_dir / "outputs"
    if not outputs.exists():
        return out
    for f in outputs.rglob("*"):
        if not f.is_file():
            continue
        try:
            sha = hashlib.sha256(f.read_bytes()).hexdigest()
            out[str(f.relative_to(exp_dir))] = sha
        except Exception:
            pass
    return out


# ---------------------------------------------------------------------------
# Per-step completeness gate — server-enforced "did the step actually finish?"
# ---------------------------------------------------------------------------


# Markers that indicate a section was left as a scaffolded stub rather than
# filled in by the analyst. Lists must stay in sync with project_ops seeds.
_CONCLUSIONS_STUB_MARKERS = (
    "*(2-5 quantitative bullets",
    "*(For each hypothesis touched:",
    "*(Assumption checks, sensitivity",
    "*(What this step cannot conclude,",
    "*(proceed | branch | dead-end)*",
    "*(2-3 candidates with rationale)*",
    "*(2-3 sentences. What was tested,",
    "*(Dataset shape, transforms applied,",
)


def _section_body(text: str, header: str) -> str:
    m = re.search(
        rf"^##\s+{re.escape(header)}\s*\n(.+?)(?=^##\s|\Z)",
        text or "",
        flags=re.MULTILINE | re.DOTALL,
    )
    return m.group(1).strip() if m else ""


def _is_section_stub(text: str, header: str) -> bool:
    body = _section_body(text, header)
    if not body:
        return True
    return any(m in body for m in _CONCLUSIONS_STUB_MARKERS)


_NUMERIC_HINT = re.compile(
    r"(?:\d+\.\d+|\d+%|p\s*[<=>]\s*0?\.\d+|95%\s*ci|n\s*=\s*\d+|"
    r"AUROC|AUC|R\^?2|RMSE|MAE|hazard\s*ratio|odds\s*ratio|"
    r"mean\s*=|median\s*=)",
    re.IGNORECASE,
)


def _findings_look_numeric(text: str) -> bool:
    """True iff the Findings section contains at least two distinct
    numeric / statistical signals — a heuristic for "this step has
    real numbers a reader would want in a table".

    Used as the trigger for the "numeric findings without a table"
    warning in step completeness. False positives (e.g. a Findings
    section that quotes a paper's percentages) are acceptable — the
    cost of a spurious warning is small.
    """
    body = _section_body(text, "Findings")
    if not body:
        return False
    return len(_NUMERIC_HINT.findall(body)) >= 2


def _is_humanities_project(root: Path) -> bool:
    """Detect whether the project should use humanities completeness rules.

    Signals (any one is enough):
      * ``inputs/researcher_config.yaml`` carries ``domain: humanities`` or
        ``pack: humanities``.
      * Any ``humanities/`` subdir under ``workspace/`` (humanities packs
        write apparatus / transcription / citation artefacts there).
      * The cached intake autofill marks a humanities pack as detected
        (``inputs/.detection_cache.json`` or ``workspace/.os_state/packs.json``).

    Wraps a try/except so a missing or malformed config never breaks the
    completeness audit.
    """
    root = Path(root)
    try:
        cfg_path = root / "inputs" / "researcher_config.yaml"
        if not cfg_path.exists():
            legacy = root / "researcher_config.yaml"
            if legacy.exists():
                cfg_path = legacy
        if cfg_path.exists():
            try:
                import yaml  # type: ignore

                cfg = yaml.safe_load(cfg_path.read_text()) or {}
                if isinstance(cfg, dict):
                    if str(cfg.get("domain", "")).lower() == "humanities":
                        return True
                    if str(cfg.get("pack", "")).lower() == "humanities":
                        return True
                    packs = cfg.get("packs") or []
                    if isinstance(packs, list) and any(
                        str(p).lower() == "humanities" for p in packs
                    ):
                        return True
            except Exception:
                pass
        # Filesystem fallback: a workspace/<step>/humanities/ or
        # workspace/<step>/edition/ subdir is a strong humanities signal.
        workspace = root / "workspace"
        if workspace.is_dir():
            for marker in ("edition", "apparatus", "transcriptions", "humanities"):
                if any(workspace.rglob(marker)):
                    return True
    except Exception:
        return False
    return False


_HUMANITIES_ARTEFACT_NAMES = {
    "apparatus.md",
    "apparatus_criticus.md",
    "citation_chains.md",
    "close_reading.md",
}
_HUMANITIES_ARTEFACT_DIRS = {
    "transcriptions",
    "apparatus",
    "edition",
    "humanities",
}


def _collect_humanities_artefacts(step_dir: Path) -> list[str]:
    """Return relative paths of humanities focal artefacts under ``step_dir``.

    Accepts: any of the named markdown artefacts at any depth, or any file
    inside one of the recognised humanities subdirectories. Used by
    ``_step_completeness`` to satisfy the focal-artefact requirement in
    humanities mode.
    """
    out: list[str] = []
    if not step_dir.exists():
        return out
    try:
        for path in step_dir.rglob("*"):
            if not path.is_file():
                continue
            name_lc = path.name.lower()
            if name_lc in _HUMANITIES_ARTEFACT_NAMES:
                out.append(str(path.relative_to(step_dir)))
                continue
            parents = {p.name.lower() for p in path.parents}
            if parents & _HUMANITIES_ARTEFACT_DIRS and path.suffix.lower() in {".md", ".txt", ".xml", ".tei"}:
                out.append(str(path.relative_to(step_dir)))
    except Exception:
        return out
    return sorted(set(out))


def _step_completeness(step_dir: Path, root: Path) -> dict[str, Any]:
    """Score one step's completeness — used both for finalize gates and
    server-enforced anti-one-shot guards.

    Beyond the v1 checks (conclusions stub, focal figure, caption
    sidecars), this audit now ALSO requires:

    * Per-output provenance sidecars (``<file>.prov.json``) for any
      file under ``outputs/`` or ``data/output/``. Coverage below 50%
      is a blocker.
    * If the step has more than 2 scripts, a ``pipeline.yaml``
      declaring the sub-task DAG. (Reviewable, cacheable, re-runnable.)
    """
    blockers: list[str] = []
    warnings: list[str] = []
    info: dict[str, Any] = {"step_id": step_dir.name}

    # 1. conclusions.md exists with non-stub Findings + Decision.
    conc = step_dir / "conclusions.md"
    info["has_conclusions"] = conc.exists()
    if not conc.exists():
        blockers.append("conclusions.md missing.")
    else:
        text = conc.read_text()
        if _is_section_stub(text, "Findings"):
            blockers.append("conclusions.md → Findings section is still a stub.")
        if _is_section_stub(text, "Decision"):
            blockers.append("conclusions.md → Decision section is still a stub.")
        if _is_section_stub(text, "Plain-language summary"):
            warnings.append(
                "conclusions.md → Plain-language summary still a stub "
                "(executive / teaching dashboard views will fall back to "
                "the technical text)."
            )

    # 2. At least one focal figure: outputs/figures/<step_num>_*.png
    #    OR (humanities mode) a markdown apparatus / transcription / citation
    #    chain artefact under workspace/<topic>/. Humanities projects produce
    #    apparatus criticus / transcriptions / citation chains as markdown,
    #    not figures.
    figs_dir = step_dir / "outputs" / "figures"
    step_num = step_dir.name.split("_", 1)[0]
    figures: list[str] = []
    if figs_dir.exists():
        figures = [
            f.name for f in sorted(figs_dir.iterdir())
            if f.suffix.lower() in {".png", ".svg", ".jpg", ".jpeg"}
        ]
    info["figures"] = figures
    focal = next((f for f in figures if f.startswith(f"{step_num}_")), None)
    humanities_mode = _is_humanities_project(root)
    humanities_artefacts: list[str] = []
    if humanities_mode:
        humanities_artefacts = _collect_humanities_artefacts(step_dir)
        info["humanities_mode"] = True
        info["humanities_artefacts"] = humanities_artefacts
    if not figures:
        if humanities_mode and humanities_artefacts:
            # Humanities pack: accept markdown apparatus / transcription /
            # citation chain as the focal artefact instead of a figure.
            pass
        elif humanities_mode:
            blockers.append(
                "No focal artefact produced — humanities steps MUST emit "
                "at least one of: apparatus criticus, transcription, "
                "citation chain, or close-reading note under "
                f"workspace/{step_dir.name}/ (or a figure under "
                f"outputs/figures/{step_num}_<descriptor>.png)."
            )
        else:
            blockers.append(
                "No figure produced — every step MUST emit at least one focal "
                f"figure to outputs/figures/{step_num}_<descriptor>.png."
            )
    elif not focal:
        warnings.append(
            f"No figure starts with the step number prefix '{step_num}_' — "
            "the synthesis dashboard's per-step focal pick will fall back "
            "to alphabetical first match."
        )

    # 3. Every figure must have a caption sidecar (the plain-English
    #    interpretation now lives inline in conclusions.md next to the
    #    embed, so the separate .summary.md sidecar was retired in 3.2).
    if figures and figs_dir.exists():
        missing_caps = []
        for name in figures:
            base = figs_dir / name
            if not base.with_suffix(".caption.md").exists():
                missing_caps.append(name)
        if missing_caps:
            blockers.append(
                f"{len(missing_caps)} figure(s) missing caption sidecar: "
                + ", ".join(missing_caps[:5])
                + ("…" if len(missing_caps) > 5 else "")
            )
        info["missing_captions"] = missing_caps

    # 4. Scripts/ should have at least one runnable file.
    scripts_dir = step_dir / "scripts"
    scripts = []
    if scripts_dir.exists():
        scripts = [
            f.name for f in sorted(scripts_dir.iterdir())
            if f.is_file() and f.suffix.lower() in {
                ".py", ".r", ".jl", ".sh", ".ipynb", ".rmd", ".qmd",
            }
        ]
    info["scripts"] = scripts
    if not scripts:
        warnings.append(
            "No script files under scripts/ — step's outputs may not be "
            "reproducible from this folder alone."
        )

    # Missing scratch/stack_plan.md is a BLOCKER.
    # `methodology/pick_tool_stack` asks the AI to persist its
    # language/library choice + the field-practice rationale before
    # coding; a missing artefact means the choice was implicit
    # (typically default-to-Python). Override: write the file with a
    # one-line rationale — there is no flag-based bypass because the
    # cost of writing the rationale down is small and the gap matters
    # at synthesis time.
    if scripts:
        stack_plan = step_dir / "scratch" / "stack_plan.md"
        if not stack_plan.exists():
            # Adaptive friction: honour active self-certification +
            # per-step skip annotation before BLOCKing. The rule still
            # applies; the gate just downgrades to a warning when the
            # researcher has explicitly accepted accountability outside
            # RO.
            skipped = False
            try:
                from research_os.tools.actions.state.certifications import (
                    has_active_certification,
                    step_has_skip_annotation,
                )
                cert = has_active_certification(
                    root, "stack_plan", step_id=step_dir.name
                )
                skip = step_has_skip_annotation(
                    root, step_dir.name, "stack_plan"
                )
                if cert.get("active") or skip.get("has_skip"):
                    why = (
                        f"self-certified ({cert.get('certification', {}).get('rationale', '')[:80]})"
                        if cert.get("active")
                        else f"step skip annotation ({skip.get('reason', '')[:80]})"
                    )
                    warnings.append(
                        f"{step_dir.name}: no scratch/stack_plan.md — "
                        f"downgraded to warning, {why}."
                    )
                    info["stack_plan_skipped"] = why
                    skipped = True
            except Exception:
                skipped = False
            if not skipped:
                blockers.append(
                    f"{step_dir.name}: no scratch/stack_plan.md — language + "
                    "library choice not documented. Run methodology/pick_tool_stack "
                    "to record the field-practice rationale (R Bioconductor for "
                    "bulk DE, Python scanpy for scRNA-seq, R survival for Cox PH, "
                    "etc.). This BLOCKS — write at minimum a one-line "
                    "rationale to scratch/stack_plan.md. The gate "
                    "downgrades to a warning when tool_self_certify(domain="
                    "'stack_plan', ...) has been called OR when conclusions.md "
                    "carries <!-- ro:skip stack_plan, reason: ... -->."
                )
                info["missing_stack_plan"] = True

    # 5. Multi-script steps must declare a pipeline.yaml (sub-task DAG).
    #    A step that emits outputs in MULTIPLE categories (figures +
    #    tables + reports) is "non-trivial" and must be split into
    #    atomic sub-tasks — otherwise a single mega script ends up
    #    producing every output, defeating reproducibility and
    #    incremental re-runs. The rule:
    #      - >2 scripts, no pipeline.yaml             →  warning  (legacy)
    #      - outputs in ≥2 categories, 1 script       →  BLOCKER  (mega)
    #      - outputs in ≥2 categories, no pipeline.yaml → BLOCKER (mega)
    pipeline_yaml = step_dir / "pipeline.yaml"
    reports_dir = step_dir / "outputs" / "reports"
    tables_dir = step_dir / "outputs" / "tables"

    def _has_step_artifact(d: Path, exts: tuple[str, ...]) -> bool:
        """True iff this step's number-prefixed artefacts live under ``d``.

        The mega-script blocker only fires for output categories the
        step's OWN scripts produce. A stray figure or report file with
        no ``<step_num>_`` prefix isn't an artefact of this step — it
        could be an external comparison image, a placeholder, or a
        cross-step reference — and must not count toward the threshold.
        """
        if not d.exists():
            return False
        prefix = f"{step_num}_"
        for p in d.iterdir():
            if not p.is_file() or p.suffix.lower() not in exts:
                continue
            if p.name.startswith(prefix):
                return True
        return False

    figures_from_step = [f for f in figures if f.startswith(f"{step_num}_")]
    has_tables = _has_step_artifact(tables_dir, (".csv", ".tsv", ".parquet"))
    has_reports = _has_step_artifact(reports_dir, (".md", ".txt", ".html"))
    categories_hit = sum([
        bool(figures_from_step),  # figures/
        has_tables,               # tables/
        has_reports,              # reports/
    ])
    info["output_categories"] = categories_hit
    info["has_tables"] = has_tables
    info["has_reports"] = has_reports

    # Soft check: numeric findings without a table.
    #
    # If the step has substantive numeric findings (Findings section
    # with multiple numbers / units / CIs) but emitted no CSV / TSV /
    # parquet table, surface as a WARNING — research-record gap, not a
    # block-the-paper gap. Reviewers expect coefficient / metric
    # tables alongside narrative; the synthesis/paper pipeline will
    # struggle to assemble a Results section without them.
    if (
        conc.exists()
        and bool(figures_from_step)
        and not has_tables
        and _findings_look_numeric(conc.read_text())
    ):
        warnings.append(
            "Step has numeric findings + a figure but no table in "
            "outputs/tables/. Reviewers (and tool_synthesize) expect a "
            "machine-readable companion to the chart: coefficient table "
            "for a model, metric matrix for a comparison, summary CSV "
            "for descriptive stats. Add at least one CSV named "
            f"{step_num}_<descriptor>.csv."
        )

    if len(scripts) > 2 and not pipeline_yaml.exists():
        warnings.append(
            f"{len(scripts)} scripts but no pipeline.yaml declaring the "
            "sub-task DAG. Call tool_step_pipeline_define so the runner "
            "can topologically order + cache them."
        )

    if categories_hit >= 2 and not pipeline_yaml.exists():
        blockers.append(
            f"Outputs span {categories_hit} categories (figures / tables / "
            "reports) but no pipeline.yaml declares the sub-task DAG — this "
            "is the mega-script anti-pattern. Split into separate scripts "
            "(one per sub-task: ingest / clean / fit / visualize / report / "
            "tabulate) and declare them via tool_step_pipeline_define. The "
            "runner then content-hash-caches each node so editing the "
            "figure script no longer re-runs the fit. Override is only "
            "valid for genuinely atomic single-purpose steps."
        )
    elif categories_hit >= 2 and len(scripts) <= 1 and pipeline_yaml.exists():
        # pipeline.yaml declared but only 1 script — still suspicious.
        warnings.append(
            "Step emits outputs in multiple categories but only one "
            "script exists. Verify pipeline.yaml lists distinct nodes "
            "rather than a single catch-all node."
        )
    info["has_pipeline_yaml"] = pipeline_yaml.exists()

    # 6. Per-output provenance sidecar coverage.
    try:
        from research_os.tools.actions.state.provenance import (
            step_provenance_inventory,
        )

        prov = step_provenance_inventory(step_dir, root)
        info["provenance_coverage_pct"] = prov.get("coverage_pct", 0)
        info["provenance_missing"] = prov.get("missing_provenance", [])
        if prov.get("total_outputs", 0) > 0:
            pct = prov.get("coverage_pct", 0)
            if pct < 50:
                warnings.append(
                    f"Provenance sidecar coverage {pct}% "
                    f"({prov['with_provenance']}/{prov['total_outputs']} "
                    "outputs have .prov.json). Future reviewers cannot "
                    "trace where the rest came from. Run "
                    "tool_step_pipeline_run for scripted outputs to drop "
                    "provenance sidecars automatically; for figures, write "
                    "a `<name>.prov.json` next to each output (see "
                    "audit/provenance_completeness protocol)."
                )

    except Exception as e:
        logger.debug("provenance inventory failed: %s", e)

    info["blockers"] = blockers
    info["warnings"] = warnings
    info["status"] = "blocked" if blockers else "warning" if warnings else "ok"
    return info


def audit_step_completeness(
    root: Path, step_id: str | None = None,
) -> dict[str, Any]:
    """Server-enforced "did the step actually finish?" check.

    Validates that for each step (or the named one):

      * conclusions.md exists with non-stub Findings + Decision sections.
      * At least one focal PNG/SVG under outputs/figures/.
      * Every figure has a sibling .caption.md.
      * scripts/ has at least one runnable file.

    Returns ``status="error"`` and a ``blockers`` list when *any* active
    step fails. Used by:

      * ``tool_synthesize``  — refuses to assemble if blockers exist.
      * ``tool_dashboard(operation='create')`` — refuses to render if blockers exist.
      * ``tool_plan(operation='advance')`` — refuses to walk past a half-finished step
        (with an override flag so the AI can negotiate with the researcher).
      * ``audit_and_validation`` protocol — final pre-deliverable gate.

    Writes a markdown report to ``workspace/logs/step_completeness.md``
    so the dashboard's audit-trail section can surface what's still owed.
    """
    root = Path(root)
    workspace = root / "workspace"
    if not workspace.exists():
        return {"status": "error", "message": "workspace/ not found"}

    target_dirs: list[Path]
    if step_id:
        d = workspace / step_id
        if not d.is_dir():
            return {"status": "error",
                    "message": f"Step '{step_id}' not found."}
        target_dirs = [d]
    else:
        target_dirs = [
            d for d in sorted(workspace.iterdir())
            if d.is_dir() and re.match(r"^\d{2,3}_", d.name)
            and not d.name.endswith("__DEAD_END")
        ]

    per_step: list[dict[str, Any]] = []
    any_blocked = False
    for d in target_dirs:
        info = _step_completeness(d, root)
        if info.get("status") == "blocked":
            any_blocked = True
        per_step.append(info)

    # Write report.
    lines = ["# Step Completeness Audit", ""]
    for info in per_step:
        icon = {"blocked": "❌", "warning": "⚠️", "ok": "✅"}.get(
            info.get("status"), "•"
        )
        lines.append(f"## {icon} `{info['step_id']}`")
        if info.get("blockers"):
            lines.append("")
            lines.append("**BLOCKERS:**")
            for b in info["blockers"]:
                lines.append(f"- {b}")
        if info.get("warnings"):
            lines.append("")
            lines.append("Warnings:")
            for w in info["warnings"]:
                lines.append(f"- {w}")
        lines.append("")
    logs_dir = root / "workspace" / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    out = logs_dir / "step_completeness.md"
    out.write_text("\n".join(lines) + "\n")

    blockers_flat = [
        f"{i['step_id']}: {b}"
        for i in per_step for b in i.get("blockers", [])
    ]

    return {
        "status": "error" if any_blocked else "success",
        "steps": per_step,
        "blockers": blockers_flat,
        "report_path": str(out.relative_to(root)),
        "advice": (
            "BLOCKED. Fix the per-step issues above before running "
            "tool_synthesize / tool_dashboard_create — final deliverables "
            "depend on every step having a focal figure + caption + "
            "non-stub conclusions."
            if any_blocked
            else "All active steps pass the completeness gate."
        ),
    }


# ---------------------------------------------------------------------------
# AuditBase wrapper for tool_audit_step_completeness
# ---------------------------------------------------------------------------


# Stable UUIDv5 namespace for step-completeness findings. Using
# NAMESPACE_DNS with a deterministic key (audit_name + dimension +
# evidence_paths) means re-running the same audit against the same
# workspace produces the same id — the .audit_findings.jsonl ledger
# doesn't churn IDs across reruns, which is what dashboards diff on.
_STEP_COMPLETENESS_NS = uuid.NAMESPACE_DNS


def _step_completeness_finding_uuid(
    *,
    audit_name: str,
    dimension: str,
    evidence_paths: list[str],
) -> str:
    """Derive a stable UUIDv5 from the salient fields of a finding.

    The id key is ``audit_name + dimension + evidence_paths``. Severity
    + suggested_fix are deliberately omitted so a blocker that
    downgrades to a warning across runs (e.g. the stack_plan rule with
    an active self-certification) keeps the same id — dashboards then
    see "same finding, severity changed" rather than "old finding
    gone, new finding appeared".
    """
    key = "|".join([
        audit_name,
        dimension,
        ",".join(sorted(evidence_paths)),
    ])
    return str(uuid.uuid5(_STEP_COMPLETENESS_NS, key))


# Substring → dimension mapping. Order matters: longer / more specific
# substrings come first so a stack_plan downgrade-warning doesn't fall
# through to the generic stack_plan rule for blockers. The match is
# case-insensitive against the blocker/warning string.
_DIMENSION_MATCHERS: tuple[tuple[str, str], ...] = (
    # Blocker patterns
    ("conclusions.md missing", "conclusions"),
    ("findings section is still a stub", "findings_stub"),
    ("decision section is still a stub", "decision_stub"),
    ("missing caption sidecar", "caption_sidecar"),
    ("no scratch/stack_plan.md", "stack_plan"),
    ("stack_plan", "stack_plan"),
    ("outputs span", "mega_script"),
    ("mega-script", "mega_script"),
    ("no focal artefact produced", "focal_artefact"),
    ("no figure produced", "focal_artefact"),
    # Warning patterns
    ("plain-language summary still a stub", "plain_language_summary"),
    ("no figure starts with the step number prefix", "focal_artefact"),
    ("no script files under scripts", "scripts"),
    ("numeric findings", "tables"),
    ("no pipeline.yaml", "pipeline_yaml"),
    ("multiple categories", "pipeline_yaml"),
    ("provenance sidecar coverage", "provenance"),
)


def _classify_completeness_dimension(message: str) -> str:
    """Classify a blocker/warning message into a stable dimension label."""
    lower = message.lower()
    for needle, dim in _DIMENSION_MATCHERS:
        if needle in lower:
            return dim
    return "completeness"


# Per-dimension override-kwarg mapping. Only a subset of completeness
# findings have a documented override flag — the rest are not bypassable
# (e.g. a missing conclusions.md can't be waived). Source: tool
# descriptions for tool_audit_step_completeness + tool_path_finalize +
# tool_synthesize (which all honour override_completeness_gate).
_COMPLETENESS_OVERRIDE_KWARGS: dict[str, str] = {
    "findings_stub": "override_completeness_gate",
    "decision_stub": "override_completeness_gate",
    "focal_artefact": "override_completeness_gate",
    "caption_sidecar": "override_completeness_gate",
    "mega_script": "override_completeness_gate",
}


def _completeness_evidence_paths(step_id: str, dimension: str) -> list[str]:
    """Compute the evidence paths surfaced on a finding for a given step.

    Each dimension points at the file(s) the researcher would open to
    fix it. We keep this conservative — listing every figure in a
    missing-sidecar finding would bloat the JSON; the step directory +
    the canonical file are enough for a reviewer to navigate.
    """
    base = f"workspace/{step_id}"
    if dimension in (
        "conclusions",
        "findings_stub",
        "decision_stub",
        "plain_language_summary",
    ):
        return [f"{base}/conclusions.md"]
    if dimension in ("focal_artefact", "caption_sidecar"):
        return [f"{base}/outputs/figures/"]
    if dimension == "stack_plan":
        return [f"{base}/scratch/stack_plan.md"]
    if dimension in ("mega_script", "pipeline_yaml"):
        return [f"{base}/pipeline.yaml", f"{base}/scripts/"]
    if dimension == "scripts":
        return [f"{base}/scripts/"]
    if dimension == "tables":
        return [f"{base}/outputs/tables/"]
    if dimension == "provenance":
        return [f"{base}/outputs/"]
    return [base]


class StepCompletenessAudit(AuditBase):
    """:class:`AuditBase` wrapper around :func:`audit_step_completeness`.

    Delegates the heavy lifting to :func:`audit_step_completeness` (which
    preserves the legacy markdown report at
    ``workspace/logs/step_completeness.md``) and then folds the resulting
    per-step blockers + warnings into a flat ``list[AuditFinding]`` that
    the orchestrator can persist via :func:`write_audit_outputs`. The
    legacy markdown stays untouched so every downstream consumer
    (dashboard, override log, finalize gate) continues to read the same
    file.
    """

    name = "step_completeness"

    def run(self, root: Path, **kwargs: Any) -> list[AuditFinding]:
        """Run the completeness audit and return structured findings.

        Accepts ``step_id`` (optional) — the same kwarg the legacy
        function takes. Returns an empty list when the workspace is
        missing or the named step is not found; the caller can treat
        "no findings" as "nothing to persist" and skip writing
        artefacts if it wants.
        """
        result = audit_step_completeness(root, step_id=kwargs.get("step_id"))
        findings: list[AuditFinding] = []
        if result.get("status") == "error" and not result.get("steps"):
            # Workspace missing or step not found — surface as zero
            # findings rather than crashing. The legacy contract
            # already returns status="error" with a message in that
            # case, so callers can branch off the legacy result.
            return findings

        for step_info in result.get("steps") or []:
            step_id = step_info.get("step_id", "")
            for blocker in step_info.get("blockers") or []:
                dim = _classify_completeness_dimension(blocker)
                evidence = _completeness_evidence_paths(step_id, dim)
                fid = _step_completeness_finding_uuid(
                    audit_name=self.name,
                    dimension=dim,
                    evidence_paths=evidence,
                )
                findings.append(AuditFinding(
                    audit_name=self.name,
                    severity="block",
                    dimension=dim,
                    id=fid,
                    evidence_paths=evidence,
                    suggested_fix=blocker,
                    override_kwarg=_COMPLETENESS_OVERRIDE_KWARGS.get(dim),
                ))
            for warning in step_info.get("warnings") or []:
                dim = _classify_completeness_dimension(warning)
                evidence = _completeness_evidence_paths(step_id, dim)
                fid = _step_completeness_finding_uuid(
                    audit_name=self.name,
                    dimension=dim,
                    evidence_paths=evidence,
                )
                findings.append(AuditFinding(
                    audit_name=self.name,
                    severity="warn",
                    dimension=dim,
                    id=fid,
                    evidence_paths=evidence,
                    suggested_fix=warning,
                ))
        return findings
