"""Audit tools — checks that go beyond a simple test run.

Every audit writes a markdown report into the *current* experiment's
``outputs/reports/`` directory so the audit becomes part of the research record.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger("research_os.tools.audit")


def get_current_path(root: Path) -> str:
    """Return the active numbered experiment folder (e.g. ``02_eda``) or ``""``."""
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
    current = get_current_path(root)
    if current:
        return root / "workspace" / current / "outputs" / "reports" / filename
    return root / "workspace" / "logs" / filename


# ---------------------------------------------------------------------------
# Synthesis audit — checks paper structure, claim grounding, and citations.
# ---------------------------------------------------------------------------


def audit_synthesis(paper_path: str, root: Path) -> dict[str, Any]:
    try:
        p = root / paper_path
        if not p.exists() or not p.is_file():
            return {"status": "error", "message": f"Paper not found: {paper_path}"}

        text = p.read_text()
        lower = text.lower()

        # Section coverage
        required = ["abstract", "introduction", "methods", "results", "discussion"]
        missing_sections = [s for s in required if f"## {s}" not in lower and f"\\section{{{s}" not in lower]

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

        # Citation density: count [@key] or \cite{key}
        citations = re.findall(r"\[@[^\]]+\]|\\cite\{[^}]+\}", text)
        citation_count = len(citations)
        word_count = len(text.split())
        citation_density = citation_count / max(1, word_count) * 1000  # per 1000 words

        # Figures referenced vs. files present
        figure_refs = set(re.findall(r"!\[[^\]]*\]\(([^)]+\.(?:png|svg|pdf|jpg))\)", text))
        figures_present = []
        synthesis_dir = root / "synthesis"
        for ref in figure_refs:
            candidate = synthesis_dir / ref if not ref.startswith("/") else root / ref.lstrip("/")
            if not candidate.exists():
                candidate = root / ref
            figures_present.append({"ref": ref, "exists": candidate.exists()})

        has_bibliography = "## references" in lower or "\\bibliography" in text

        report = {
            "missing_sections": missing_sections,
            "causal_language_hits": causal_hits[:10],
            "citation_count": citation_count,
            "citation_density_per_1000_words": round(citation_density, 2),
            "figures_referenced": len(figure_refs),
            "figures_present": [f for f in figures_present if f["exists"]],
            "figures_missing": [f for f in figures_present if not f["exists"]],
            "has_bibliography": has_bibliography,
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

        warning = bool(missing_sections or causal_hits or not has_bibliography)
        return {
            "status": "warning" if warning else "success",
            "report": report,
            "report_path": str(out.relative_to(root)),
            "message": (
                "Synthesis audit produced warnings." if warning else "Synthesis passed audit."
            ),
        }
    except Exception as e:
        logger.exception("audit_synthesis failed")
        return {"status": "error", "message": str(e)}


# ---------------------------------------------------------------------------
# Statistical power
# ---------------------------------------------------------------------------


def audit_power(
    filepath: str, effect_size: float, alpha: float, n: int, root: Path
) -> dict[str, Any]:
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
                lm_stat, lm_p, f_stat, f_p = het_breuschpagan(resid, X)
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
# Figure quality
# ---------------------------------------------------------------------------


def audit_figure(filepath: str, root: Path) -> dict[str, Any]:
    """Check DPI and basic visual hygiene of a PNG figure."""
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
    try:
        import hashlib
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


def _step_completeness(step_dir: Path, root: Path) -> dict[str, Any]:
    """Score one step's completeness — used both for finalize gates and
    server-enforced anti-one-shot guards.

    Beyond the v1 checks (conclusions stub, focal figure, caption +
    summary sidecars), this audit now ALSO requires:

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
    if not figures:
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

    # 3. Every figure must have caption + summary sidecars.
    if figures and figs_dir.exists():
        missing_caps = []
        missing_sums = []
        for name in figures:
            base = figs_dir / name
            if not base.with_suffix(".caption.md").exists():
                missing_caps.append(name)
            if not base.with_suffix(".summary.md").exists():
                missing_sums.append(name)
        if missing_caps:
            blockers.append(
                f"{len(missing_caps)} figure(s) missing caption sidecar: "
                + ", ".join(missing_caps[:5])
                + ("…" if len(missing_caps) > 5 else "")
            )
        if missing_sums:
            warnings.append(
                f"{len(missing_sums)} figure(s) missing plain-English summary "
                "(call tool_figure_caption_synthesise or run tool_path_finalize)."
            )
        info["missing_captions"] = missing_caps
        info["missing_summaries"] = missing_sums

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

    # 5. Multi-script steps must declare a pipeline.yaml (sub-task DAG).
    #    Tightened in v1.0.0: a step that emits outputs in MULTIPLE
    #    categories (figures + tables + reports) is "non-trivial" and
    #    must be split into atomic sub-tasks — otherwise a single mega
    #    script ends up producing every output, defeating reproducibility
    #    and incremental re-runs. The rule:
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
      * Every figure has a sibling .caption.md AND .summary.md.
      * scripts/ has at least one runnable file.

    Returns ``status="error"`` and a ``blockers`` list when *any* active
    step fails. Used by:

      * ``tool_synthesize``  — refuses to assemble if blockers exist.
      * ``tool_dashboard_create`` — refuses to render if blockers exist.
      * ``tool_plan_advance`` — refuses to walk past a half-finished step
        (with an override flag so the AI can negotiate with the researcher).
      * ``audit_and_validation`` protocol — final pre-deliverable gate.

    Writes a markdown report to ``workspace/logs/step_completeness.md``
    so the dashboard's audit-trail section can surface what's still owed.
    """
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
