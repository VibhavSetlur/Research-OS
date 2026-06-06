"""Phase-5 review-rewrite loop for synthesis drafters.

The CRAFT-inspired pattern: a drafter (paper compiler, slide builder,
poster builder) writes an initial output; a reviewer (a set of audit
functions / persona-driven critics) emits structured ``AuditFinding``
records; if any are ``severity="block"`` OR quality improvement is
material, the drafter rewrites with the findings in hand. Converges
either because no blockers remain AND quality plateaued, or because
``max_iter`` is reached.

The loop is a pure orchestrator — it does NOT call an LLM. The
drafter_fn / reviewer_fn it composes ARE the moving parts; this
module just runs the closed loop and persists the trail.

Public surface:

    draft_with_review_rewrite(
        drafter_fn,       # (prior_output, findings, root) -> dict
        reviewer_fn,      # (output, root) -> list[AuditFinding]
        *,
        drafter_name: str,
        root: Path,
        max_iter: int = 3,
        improvement_threshold: float = 0.10,
    ) -> dict

Returns a structured envelope describing every iteration: the drafter's
output dict, the reviewer's findings, the quality metrics, and the
quality delta vs the prior iteration. Each iteration is also persisted
to ``workspace/logs/drafter_loops/<drafter>_iter_<N>.md`` (the rendered
output preview) + ``.json`` (the findings + metrics). A cumulative
``workspace/logs/drafter_loops/quality_progression.md`` table is
rewritten on every call so the researcher can scan the history in one
place.

Quality metrics (deterministic, no LLM required):

* ``citation_count`` — Pandoc ``[@key]`` cites + Typst ``#cite(<key>)``.
* ``numeric_claim_count`` — regex hits for percentages, decimals,
  p-values, sample-size phrases (``n = 42``).
* ``section_coverage`` — fraction of expected ``##`` headings with
  ≥ 1 non-blank body line.
* ``avg_sentence_length`` — proxy for prose fluency (lower ≈ better
  up to a floor, above ~35 = run-on).
* ``type_token_ratio`` — distinct words / total words (proxy for
  lexical variety; higher = better).

The composite ``quality_score`` is a weighted sum of the four (see
``_compute_quality_score``); the threshold compares the delta in this
composite between consecutive iterations.

Reviewer-persona adapter
------------------------

``persona_reviewer(persona_ids)`` returns a reviewer_fn that loads the
named YAML personas under ``assets/reviewer_personas/`` and walks the
drafter's output, emitting one ``AuditFinding`` per ``red_flag`` hit
(severity = ``warn``) plus block-severity findings for hard quality
failures (no citations in a paper, zero sections covered, etc.). The
adapter is deterministic — no LLM — so the loop is testable end-to-end.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from research_os.tools.actions.audit._base import (
    AuditFinding,
    validate_finding,
)

logger = logging.getLogger("research_os.synthesis.drafter_loop")


# ---------------------------------------------------------------------------
# Quality metrics
# ---------------------------------------------------------------------------


_CITE_PATTERNS = (
    re.compile(r"\[@[^\]]+\]"),
    re.compile(r"#cite\(<[^>]+>\)"),
)

_NUMERIC_CLAIM_PATTERNS = (
    re.compile(r"\b\d+(?:\.\d+)?\s*%"),
    re.compile(r"\bp\s*[=<>]\s*0?\.\d+", re.IGNORECASE),
    re.compile(r"\bn\s*=\s*\d+", re.IGNORECASE),
    re.compile(r"\b\d+\.\d+\b"),
)

_SECTION_HEADING_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")
_WORD_RE = re.compile(r"[A-Za-z]+")


def _strip_text(payload: Any) -> str:
    """Coerce a drafter output (dict | path | str) into the underlying text.

    Drafters return rich envelopes (``{"status": "success", "pdf_path":
    "...", "typst_path": "..."}``). The metric routines need the
    SOURCE text — paper.md or slides.typ — so we hunt down a useful
    path-like field, then fall back to the dict's stringified form.
    """
    if isinstance(payload, str):
        # Treat as a path only when it looks like one (no newlines + short
        # enough to survive os.stat). Otherwise it's already the source
        # text — long markdown paragraphs frequently get passed in raw.
        if (
            payload
            and "\n" not in payload
            and len(payload) < 4096
        ):
            try:
                path = Path(payload)
                if path.exists() and path.is_file():
                    return path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                pass
        return payload
    if not isinstance(payload, dict):
        return str(payload or "")

    # Inline-text fields: take as-is, no path resolution.
    for key in ("source_text", "markdown", "md", "preview", "body", "text"):
        v = payload.get(key)
        if isinstance(v, str) and v:
            return v

    # Path-like fields: resolve to text when readable.
    for key in (
        "paper_md_path",
        "paper_path",
        "typst_path",
        "typ_path",
        "html_path",
        "pdf_path",
    ):
        v = payload.get(key)
        if not isinstance(v, str) or not v:
            continue
        # Reject obvious non-paths (multiline strings) before stat() — long
        # filenames raise OSError(ENAMETOOLONG) on most filesystems.
        if "\n" in v or len(v) > 4096:
            continue
        try:
            p = Path(v)
            if p.exists() and p.is_file() and p.suffix.lower() in {
                ".md", ".typ", ".html", ".txt",
            }:
                return p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

    # Files listed under ``files`` (slides emits this).
    for v in payload.get("files") or []:
        if not isinstance(v, str) or "\n" in v or len(v) > 4096:
            continue
        try:
            p = Path(v)
            if p.exists() and p.suffix.lower() in {".md", ".typ", ".html", ".txt"}:
                return p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

    return ""


def _count_citations(text: str) -> int:
    """Pandoc ``[@key]`` + Typst ``#cite(<key>)`` occurrences."""
    n = 0
    for pat in _CITE_PATTERNS:
        n += len(pat.findall(text))
    return n


def _count_numeric_claims(text: str) -> int:
    """Distinct numeric-claim hits across all configured patterns."""
    n = 0
    for pat in _NUMERIC_CLAIM_PATTERNS:
        n += len(pat.findall(text))
    return n


def _section_coverage(text: str, expected_sections: list[str] | None = None) -> float:
    """Fraction of ``##`` sections that carry ≥ 1 non-blank body line.

    When ``expected_sections`` is provided, the denominator is fixed at
    ``len(expected_sections)`` and the numerator counts how many of
    those expected section names appear and are non-empty (case-
    insensitive substring match against the headings present).
    """
    headings = [m.group(1).strip() for m in _SECTION_HEADING_RE.finditer(text)]
    if not headings:
        return 0.0

    # Build a {heading_text: body} map by walking the text and stopping
    # at the next ## boundary.
    spans: dict[str, str] = {}
    matches = list(_SECTION_HEADING_RE.finditer(text))
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        spans[m.group(1).strip().lower()] = body

    if expected_sections:
        hits = 0
        for s in expected_sections:
            key = s.strip().lower()
            for hk, body in spans.items():
                if key in hk and body:
                    hits += 1
                    break
        return hits / max(1, len(expected_sections))

    non_empty = sum(1 for body in spans.values() if body)
    return non_empty / max(1, len(spans))


def _avg_sentence_length(text: str) -> float:
    """Average words per sentence. Returns 0.0 on empty / single-token text."""
    sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]
    if not sentences:
        return 0.0
    total_words = 0
    for s in sentences:
        total_words += len(_WORD_RE.findall(s))
    return total_words / len(sentences)


def _type_token_ratio(text: str) -> float:
    """Distinct words / total words. 0.0 on empty input."""
    tokens = [w.lower() for w in _WORD_RE.findall(text)]
    if not tokens:
        return 0.0
    return len(set(tokens)) / len(tokens)


def compute_metrics(
    output: Any,
    *,
    expected_sections: list[str] | None = None,
) -> dict[str, float]:
    """Run every quality metric over a drafter output.

    Returns a dict with all four metrics plus the composite quality
    score. Callers diff this dict between iterations to decide whether
    the loop has plateaued.
    """
    text = _strip_text(output)
    metrics = {
        "citation_count": float(_count_citations(text)),
        "numeric_claim_count": float(_count_numeric_claims(text)),
        "section_coverage": _section_coverage(text, expected_sections),
        "avg_sentence_length": _avg_sentence_length(text),
        "type_token_ratio": _type_token_ratio(text),
        "text_length_chars": float(len(text)),
    }
    metrics["quality_score"] = _compute_quality_score(metrics)
    return metrics


def _compute_quality_score(metrics: dict[str, float]) -> float:
    """Weighted composite score normalised roughly to ``[0, 1]``.

    Weights are conservative + transparent — the goal is "is iteration
    N+1 materially better than iteration N", not absolute calibration.
    """
    # Citations: 0..10 citations linearly map to 0..1, capped.
    cite = min(1.0, metrics.get("citation_count", 0.0) / 10.0)
    # Numeric claims: 0..15 → 0..1.
    num = min(1.0, metrics.get("numeric_claim_count", 0.0) / 15.0)
    # Section coverage is already 0..1.
    sec = max(0.0, min(1.0, metrics.get("section_coverage", 0.0)))
    # Sentence-length sweet spot is around 18 words. Penalise both
    # very short (< 8) and run-on (> 35). Map distance to a 0..1 score
    # via a triangle peaking at 18.
    sl = metrics.get("avg_sentence_length", 0.0)
    if sl <= 0:
        sl_score = 0.0
    elif sl < 8:
        sl_score = max(0.0, sl / 8.0)
    elif sl <= 18:
        sl_score = 1.0
    elif sl < 35:
        sl_score = max(0.0, 1.0 - (sl - 18) / 17.0)
    else:
        sl_score = 0.0
    # TTR sweet spot in academic prose is ~0.35-0.6.
    ttr = metrics.get("type_token_ratio", 0.0)
    if ttr <= 0:
        ttr_score = 0.0
    elif ttr < 0.35:
        ttr_score = ttr / 0.35
    elif ttr <= 0.6:
        ttr_score = 1.0
    else:
        ttr_score = max(0.0, 1.0 - (ttr - 0.6) / 0.4)
    weighted = (
        0.25 * cite
        + 0.20 * num
        + 0.30 * sec
        + 0.15 * sl_score
        + 0.10 * ttr_score
    )
    return round(weighted, 4)


# ---------------------------------------------------------------------------
# Reviewer adapter — persona-driven, no LLM
# ---------------------------------------------------------------------------


_PERSONAS_DIR = (
    Path(__file__).resolve().parents[3] / "assets" / "reviewer_personas"
)


def _load_persona(persona_id: str) -> dict[str, Any] | None:
    path = _PERSONAS_DIR / f"{persona_id}.yaml"
    if not path.exists():
        logger.warning("unknown persona: %s", persona_id)
        return None
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        logger.warning("persona %s parse failed: %s", persona_id, exc)
        return None


# Regex flags for each "red flag" persona phrase. The persona YAMLs
# describe critique themes in plain English; we treat each red_flag as
# a substring trigger AND apply a handful of programmatic checks below
# for the structural ones.
def _persona_findings(
    persona: dict[str, Any],
    text: str,
    evidence_paths: list[str],
) -> list[AuditFinding]:
    findings: list[AuditFinding] = []
    pid = str(persona.get("id") or "unknown_persona")
    lowered = text.lower()

    # 1. Red-flag phrase matches (warn-severity).
    for flag in persona.get("red_flags") or []:
        key = str(flag).lower()
        # Pull a 2-3 token marker out of the long-form flag for matching.
        marker = re.sub(r"[^a-z0-9 ]+", " ", key)
        marker = " ".join(w for w in marker.split() if len(w) > 3)[:40]
        if marker and marker in lowered:
            findings.append(
                _make_persona_finding(
                    persona_id=pid,
                    severity="warn",
                    dimension="reviewer_red_flag",
                    suggested_fix=str(flag),
                    evidence_paths=evidence_paths,
                )
            )

    # 2. Hard structural checks by persona.
    if pid == "presentation_critic":
        # Long paragraphs (> 250 words) → warn.
        paragraphs = [p for p in text.split("\n\n") if p.strip()]
        for i, p in enumerate(paragraphs):
            if len(_WORD_RE.findall(p)) > 250:
                findings.append(
                    _make_persona_finding(
                        persona_id=pid,
                        severity="warn",
                        dimension="prose_density",
                        suggested_fix=(
                            f"Paragraph #{i + 1} runs >250 words. Split into "
                            "≤3-sentence topic units; readers bail past 250."
                        ),
                        evidence_paths=evidence_paths,
                    )
                )
                break  # one warn per output is enough; don't spam
        # Missing quantitative anchor in abstract.
        m = re.search(r"##\s*Abstract([\s\S]+?)(?=^##\s+|\Z)", text, re.MULTILINE)
        if m:
            abstract_body = m.group(1)
            if not _count_numeric_claims(abstract_body):
                findings.append(
                    _make_persona_finding(
                        persona_id=pid,
                        severity="warn",
                        dimension="abstract_anchor",
                        suggested_fix=(
                            "Abstract lacks a quantitative headline number. "
                            "Add at least one finding-level statistic."
                        ),
                        evidence_paths=evidence_paths,
                    )
                )

    if pid == "scope_creep_critic":
        # Stacked hedges in discussion (could / may / might).
        m = re.search(r"##\s*Discussion([\s\S]+?)(?=^##\s+|\Z)", text, re.MULTILINE)
        if m:
            disc = m.group(1).lower()
            hedges = (
                disc.count(" may ")
                + disc.count(" might ")
                + disc.count(" could ")
                + disc.count("suggests")
            )
            if hedges >= 6:
                findings.append(
                    _make_persona_finding(
                        persona_id=pid,
                        severity="warn",
                        dimension="hedge_density",
                        suggested_fix=(
                            f"Discussion stacks {hedges} hedge markers "
                            "(could/may/might/suggests). Tighten to claims "
                            "the data supports."
                        ),
                        evidence_paths=evidence_paths,
                    )
                )

    if pid == "methodology_skeptic":
        # No Methods section at all → block.
        if not re.search(r"^##\s*Methods?\b", text, re.IGNORECASE | re.MULTILINE):
            findings.append(
                _make_persona_finding(
                    persona_id=pid,
                    severity="block",
                    dimension="methods_missing",
                    suggested_fix=(
                        "No Methods section detected. Add `## Methods` and "
                        "describe the analysis pipeline before submission."
                    ),
                    evidence_paths=evidence_paths,
                )
            )

    if pid == "novelty_critic":
        # No prior-work / related-work framing in introduction.
        m = re.search(r"##\s*Introduction([\s\S]+?)(?=^##\s+|\Z)", text, re.MULTILINE)
        if m:
            intro = m.group(1).lower()
            if "prior" not in intro and "previous" not in intro and "related" not in intro:
                findings.append(
                    _make_persona_finding(
                        persona_id=pid,
                        severity="warn",
                        dimension="novelty_framing",
                        suggested_fix=(
                            "Introduction does not name prior / previous / "
                            "related work. Add a one-paragraph delta vs the "
                            "closest published work."
                        ),
                        evidence_paths=evidence_paths,
                    )
                )

    return findings


def _make_persona_finding(
    *,
    persona_id: str,
    severity: str,
    dimension: str,
    suggested_fix: str,
    evidence_paths: list[str],
) -> AuditFinding:
    """Build a deterministic-id AuditFinding for a persona-derived issue."""
    key = "|".join([
        f"persona:{persona_id}",
        dimension,
        severity,
        suggested_fix,
        ",".join(sorted(evidence_paths or [])),
    ])
    stable_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, key))
    finding = AuditFinding(
        audit_name=f"drafter_loop_review:{persona_id}",
        severity=severity,
        dimension=dimension,
        id=stable_id,
        evidence_paths=list(evidence_paths or []),
        suggested_fix=suggested_fix,
    )
    validate_finding(finding.to_dict())
    return finding


def persona_reviewer(
    persona_ids: list[str],
) -> Callable[[Any, Path], list[AuditFinding]]:
    """Return a reviewer_fn that runs the named personas over a draft.

    The returned function has signature ``(output, root) -> list[AuditFinding]``
    and is suitable to pass directly into :func:`draft_with_review_rewrite`.
    """
    loaded: list[dict[str, Any]] = []
    for pid in persona_ids:
        p = _load_persona(pid)
        if p is not None:
            loaded.append(p)

    def _reviewer(output: Any, root: Path) -> list[AuditFinding]:
        text = _strip_text(output)
        # Best-effort evidence path. Drafter envelopes typically expose
        # the source file under one of these keys.
        evidence: list[str] = []
        if isinstance(output, dict):
            for k in (
                "paper_path", "paper_md_path", "typst_path", "typ_path",
                "html_path", "pdf_path",
            ):
                v = output.get(k)
                if isinstance(v, str) and v:
                    evidence.append(v)
        if not evidence:
            evidence.append(str(root))
        out: list[AuditFinding] = []
        for persona in loaded:
            out.extend(_persona_findings(persona, text, evidence))
        return out

    return _reviewer


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


def draft_with_review_rewrite(
    drafter_fn: Callable[..., dict[str, Any]],
    reviewer_fn: Callable[[Any, Path], list[AuditFinding]],
    *,
    drafter_name: str,
    root: Path,
    max_iter: int = 3,
    improvement_threshold: float = 0.10,
    expected_sections: list[str] | None = None,
) -> dict[str, Any]:
    """Run the review-rewrite loop and return a structured envelope.

    Parameters
    ----------
    drafter_fn
        Called as ``drafter_fn(prior_output=..., findings=..., root=root)``.
        First iteration passes ``prior_output=None, findings=[]``. Must
        return a dict (the drafter's normal success envelope).
    reviewer_fn
        Called as ``reviewer_fn(output, root)`` after each draft. Must
        return a list of :class:`AuditFinding` records.
    drafter_name
        Short name used for the log filenames (paper, slides, poster).
    root
        Project root. Logs land under ``workspace/logs/drafter_loops/``.
    max_iter
        Hard upper bound on iteration count. Clamped to ``>= 1``.
    improvement_threshold
        Minimum composite-quality-score delta required to keep iterating
        when no BLOCK findings remain. Defaults to 0.10 (i.e. 10 quality
        points on the 0..1 composite).
    expected_sections
        Optional list of section names used by the section-coverage
        metric. When ``None``, coverage is computed against whatever
        ``##`` headings are present.

    Returns
    -------
    dict
        ``{
            iterations: int,
            converged: bool,             # True iff stopped before max_iter
            final_output: dict,          # the last drafter envelope
            final_output_path: str|None, # most useful path on the final dict
            quality_progression: [
                {
                    iter: int,
                    metrics: {...},
                    quality_score: float,
                    delta_vs_prior: float,
                    block_finding_count: int,
                    total_finding_count: int,
                    log_md_path: str,
                    log_json_path: str,
                },
                ...
            ],
            stop_reason: str,
        }``
    """
    root = Path(root)
    max_iter = max(1, int(max_iter))
    log_dir = root / "workspace" / "logs" / "drafter_loops"
    log_dir.mkdir(parents=True, exist_ok=True)

    progression: list[dict[str, Any]] = []
    last_output: Any = None
    last_findings: list[AuditFinding] = []
    last_metrics: dict[str, float] = {}
    last_score = 0.0
    stop_reason = "max_iter_reached"
    converged = False

    for i in range(1, max_iter + 1):
        try:
            output = drafter_fn(
                prior_output=last_output,
                findings=last_findings,
                root=root,
            )
        except TypeError:
            # Drafter signatures that only accept (prior_output, root).
            output = drafter_fn(prior_output=last_output, root=root)
        last_output = output

        try:
            findings = reviewer_fn(output, root) or []
        except Exception as exc:
            logger.warning("reviewer crashed on iter %d: %s", i, exc)
            findings = []
        last_findings = findings

        metrics = compute_metrics(output, expected_sections=expected_sections)
        score = float(metrics.get("quality_score", 0.0))
        delta = score - last_score if i > 1 else score

        block_count = sum(1 for f in findings if f.severity == "block")
        log_md = log_dir / f"{drafter_name}_iter_{i}.md"
        log_json = log_dir / f"{drafter_name}_iter_{i}.json"
        _write_iter_logs(
            log_md=log_md,
            log_json=log_json,
            iter_num=i,
            drafter_name=drafter_name,
            output=output,
            findings=findings,
            metrics=metrics,
            delta=delta,
        )

        progression.append({
            "iter": i,
            "metrics": metrics,
            "quality_score": score,
            "delta_vs_prior": delta,
            "block_finding_count": block_count,
            "total_finding_count": len(findings),
            "log_md_path": str(log_md.relative_to(root)),
            "log_json_path": str(log_json.relative_to(root)),
        })

        # Stop logic: no blockers AND (first pass OR improvement plateau).
        if block_count == 0 and i >= 1:
            if i == 1:
                # Nothing to iterate on if the first pass was already clean.
                stop_reason = "no_blockers_first_pass"
                converged = True
                break
            if abs(delta) < improvement_threshold:
                stop_reason = "improvement_below_threshold"
                converged = True
                break

        last_metrics = metrics  # noqa: F841 - kept for future inspection
        last_score = score

    final_output_path = _pick_final_path(last_output)
    _write_progression_table(log_dir, drafter_name, progression)

    return {
        "iterations": len(progression),
        "converged": converged,
        "stop_reason": stop_reason,
        "final_output": last_output,
        "final_output_path": final_output_path,
        "quality_progression": progression,
        "drafter_name": drafter_name,
    }


def _pick_final_path(output: Any) -> str | None:
    """Return the most useful path on a drafter output dict."""
    if not isinstance(output, dict):
        return None
    for k in (
        "pdf_path",
        "html_path",
        "typst_path",
        "typ_path",
        "paper_path",
        "paper_md_path",
    ):
        v = output.get(k)
        if isinstance(v, str) and v:
            return v
    files = output.get("files") or []
    if isinstance(files, list) and files:
        return str(files[0])
    return None


def _write_iter_logs(
    *,
    log_md: Path,
    log_json: Path,
    iter_num: int,
    drafter_name: str,
    output: Any,
    findings: list[AuditFinding],
    metrics: dict[str, float],
    delta: float,
) -> None:
    """Persist the per-iteration output preview + findings JSON."""
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    text = _strip_text(output)
    # Cap the preview so a huge paper doesn't blow up the log.
    preview = text[:8000]
    truncated = len(text) > len(preview)
    md_lines = [
        f"# {drafter_name} — iteration {iter_num}",
        "",
        f"_Generated: {ts}_",
        "",
        "## Metrics",
        "",
        f"- quality_score: **{metrics.get('quality_score', 0.0):.4f}** "
        f"(Δ {delta:+.4f})",
        f"- citation_count: {int(metrics.get('citation_count', 0))}",
        f"- numeric_claim_count: {int(metrics.get('numeric_claim_count', 0))}",
        f"- section_coverage: {metrics.get('section_coverage', 0.0):.3f}",
        f"- avg_sentence_length: {metrics.get('avg_sentence_length', 0.0):.2f}",
        f"- type_token_ratio: {metrics.get('type_token_ratio', 0.0):.3f}",
        f"- text_length_chars: {int(metrics.get('text_length_chars', 0))}",
        "",
        f"## Findings ({len(findings)})",
        "",
    ]
    by_sev: dict[str, list[AuditFinding]] = {"block": [], "warn": [], "info": []}
    for f in findings:
        by_sev.setdefault(f.severity, []).append(f)
    for sev in ("block", "warn", "info"):
        group = by_sev.get(sev) or []
        if not group:
            continue
        md_lines.append(f"### {sev} ({len(group)})")
        md_lines.append("")
        for f in group:
            md_lines.append(
                f"- **[{f.dimension}] {f.audit_name}** — {f.suggested_fix}"
            )
        md_lines.append("")
    md_lines.append("## Output preview")
    md_lines.append("")
    md_lines.append("```")
    md_lines.append(preview if preview else "(no extractable source text)")
    md_lines.append("```")
    if truncated:
        md_lines.append(f"_…truncated; full text was {len(text)} chars._")
    log_md.write_text("\n".join(md_lines), encoding="utf-8")

    payload = {
        "iter": iter_num,
        "drafter_name": drafter_name,
        "generated_at": ts,
        "metrics": metrics,
        "quality_delta_vs_prior": delta,
        "findings": [f.to_dict() for f in findings],
        "output_envelope_keys": (
            sorted(output.keys()) if isinstance(output, dict) else None
        ),
    }
    log_json.write_text(json.dumps(payload, indent=2, sort_keys=True))


def _write_progression_table(
    log_dir: Path, drafter_name: str, progression: list[dict[str, Any]]
) -> None:
    """Rewrite the aggregate quality-progression table on every run.

    The table is APPEND-FRIENDLY: we read the existing file (if any),
    drop any rows whose drafter+timestamp matches what we're about to
    write, then re-append. This is intentionally idempotent for tests
    but persistent across reruns for the researcher.
    """
    table_path = log_dir / "quality_progression.md"
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")

    header = [
        "# Drafter loop quality progression",
        "",
        "Each row is one iteration of a drafter's review-rewrite loop.",
        "Track ``quality_score`` over iterations to see whether the loop",
        "is plateauing or still improving. ``block_findings`` > 0 means",
        "the loop will iterate again regardless of quality delta.",
        "",
        "| drafter | iter | quality_score | Δ vs prior | block | warn+info | "
        "citations | num_claims | sec_cov | run_at |",
        "|---------|------|---------------|------------|-------|-----------|"
        "-----------|------------|---------|--------|",
    ]
    rows: list[str] = []
    if table_path.exists():
        # Preserve prior content below the header. Strip the old header
        # block so we only carry forward the row body.
        prior = table_path.read_text(encoding="utf-8", errors="replace")
        for ln in prior.splitlines():
            if ln.startswith("| ") and not ln.startswith("| drafter") and not ln.startswith("|---"):
                rows.append(ln)

    for entry in progression:
        m = entry["metrics"]
        block = entry["block_finding_count"]
        warn_info = entry["total_finding_count"] - block
        rows.append(
            "| {drafter} | {iter} | {qs:.4f} | {d:+.4f} | {b} | {wi} | "
            "{c} | {nc} | {sc:.2f} | {ts} |".format(
                drafter=drafter_name,
                iter=entry["iter"],
                qs=entry["quality_score"],
                d=entry["delta_vs_prior"],
                b=block,
                wi=warn_info,
                c=int(m.get("citation_count", 0)),
                nc=int(m.get("numeric_claim_count", 0)),
                sc=m.get("section_coverage", 0.0),
                ts=ts,
            )
        )

    table_path.write_text("\n".join(header + rows) + "\n", encoding="utf-8")


__all__ = [
    "draft_with_review_rewrite",
    "persona_reviewer",
    "compute_metrics",
]
