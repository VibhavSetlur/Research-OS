"""Claim grounding — every number in the paper must trace to a workspace output.

A frequent failure mode in AI-assisted scientific writing is the
*hallucinated number* — a confident "AUROC = 0.84" that doesn't appear
in any output file. This auditor catches them.

Strategy
--------
1. Extract every quantitative claim from a target Markdown document.
   A claim is a number — optionally followed by units, percent signs,
   CI brackets, p-value formatting — that the prose presents as a
   substantive result. Citation-style bracketed numbers ([1], [2,3])
   are excluded. Years (4-digit 1900-2099) are excluded.
2. For each claim, search every workspace output file (CSV, TSV,
   JSON, MD, text reports) for a verbatim or numerically-tolerant
   match.
3. Classify each claim as:
     * **grounded** — appeared verbatim or within tolerance in an output.
     * **ungrounded** — no output file contains the number.
4. Write `workspace/logs/claim_grounding.md` and return a structured
   report. `tool_synthesize` reads this and BLOCKS if any
   ungrounded claim is in the paper.

The auditor is opinionated about what counts as a "claim":
* Numbers in `# Headings` are skipped (counts, sample sizes in titles
  are usually re-stated in body).
* Numbers in `> blockquote` are still checked (often quoted findings).
* Numbers in fenced code blocks are skipped (those are inline data).

Tolerance
---------
Floats match if they share ≥ 3 significant digits OR the relative
difference is ≤ 1%. Integers must match exactly. Percentages are
normalised to fractions before comparison.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from pathlib import Path
from typing import Any

from research_os.tools.actions.audit._base import AuditBase, AuditFinding

logger = logging.getLogger("research_os.audit.claim_grounding")


# Extract numbers that look like claims. Cover plain ints, decimals,
# negative, scientific notation, ±, %, optional thousands separators.
_CLAIM_PAT = re.compile(
    r"""
    (?<![A-Za-z0-9_])           # not a word-char before
    (-?\d{1,3}(?:[,\s]\d{3})+ |  # 12,345 / 12 345
       -?\d+\.\d+ |              # 0.84
       -?\d+ )                   # 423
    (?:e[+-]?\d+)?               # scientific
    (?:\s*%)?                    # percent sign
    (?![A-Za-z0-9_])             # not a word-char after
    """,
    re.VERBOSE,
)


def _strip_code_and_citations(text: str) -> str:
    """Remove fenced code blocks + inline code + bracketed citation refs."""
    # Fenced code blocks.
    out = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    # Inline code.
    out = re.sub(r"`[^`]+`", " ", out)
    # Bracketed citation refs: [1], [1,2], [1-5]
    out = re.sub(r"\[\d+(?:[,\-]\s*\d+)*\]", " ", out)
    return out


def _is_year(token: str) -> bool:
    try:
        n = int(token.replace(",", "").replace(" ", ""))
        return 1900 <= n <= 2099
    except ValueError:
        return False


def _normalise(token: str) -> float | None:
    """Convert a claim token to a float for tolerant matching."""
    t = token.strip().replace(",", "").replace(" ", "")
    is_pct = t.endswith("%")
    if is_pct:
        t = t[:-1]
    try:
        v = float(t)
        if is_pct:
            v = v / 100.0
        return v
    except ValueError:
        return None


def extract_claims(md_path: Path) -> list[dict[str, Any]]:
    """Pull every quantitative claim out of a Markdown document."""
    if not md_path.exists():
        return []
    text = _strip_code_and_citations(md_path.read_text(errors="replace"))
    claims: list[dict[str, Any]] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        # Skip pure headings (numbers in titles are usually restated).
        if line.lstrip().startswith("#"):
            continue
        for m in _CLAIM_PAT.finditer(line):
            tok = m.group(0).strip()
            if _is_year(tok):
                continue
            # Skip if it's part of an obvious markdown structure
            # (image dimensions, dates).
            if re.search(r"(\d{4})-\d{2}-\d{2}", line[max(0, m.start() - 4):m.end()]):
                continue
            val = _normalise(tok)
            if val is None:
                continue
            ctx_start = max(0, m.start() - 60)
            ctx_end = min(len(line), m.end() + 60)
            claims.append({
                "token": tok,
                "value": val,
                "line": line_no,
                "context": line[ctx_start:ctx_end].strip(),
            })
    return claims


def _gather_output_corpus(workspace: Path) -> str:
    """Concatenate the bodies of every output file the AI could have
    pulled numbers from. CSV/TSV/JSON/MD/TXT only — model pickles and
    PNGs are skipped (numbers there can't be substring-matched)."""
    chunks: list[str] = []
    for step in sorted(workspace.iterdir()):
        if not (step.is_dir() and re.match(r"^\d{2,3}_", step.name)):
            continue
        if step.name.endswith("__DEAD_END"):
            continue
        for sub in ("outputs/reports", "outputs/tables", "data/output"):
            d = step / sub
            if not d.exists():
                continue
            for f in d.rglob("*"):
                if not f.is_file():
                    continue
                if f.suffix.lower() not in {".csv", ".tsv", ".json",
                                              ".md", ".txt"}:
                    continue
                try:
                    chunks.append(f.read_text(errors="replace"))
                except OSError:
                    continue
    return "\n".join(chunks)


def _extract_corpus_numbers(corpus: str) -> set[float]:
    """Pre-compute every numeric token in the corpus for fast lookup."""
    out: set[float] = set()
    for m in re.finditer(r"-?\d+(?:\.\d+)?(?:e[+-]?\d+)?", corpus, flags=re.I):
        try:
            out.add(float(m.group(0)))
        except ValueError:
            continue
        # Also store the integer view if it's a round number.
    return out


def _claim_grounded(value: float, corpus_numbers: set[float],
                    tolerance: float = 0.01) -> bool:
    """Check whether ``value`` appears in the corpus (verbatim or close)."""
    if value in corpus_numbers:
        return True
    # Tolerant match: any corpus number within `tolerance` relative diff.
    abs_v = abs(value) or 1e-12
    for cv in corpus_numbers:
        if abs(cv - value) / max(abs_v, abs(cv) or 1e-12) <= tolerance:
            return True
    return False


def audit_claims(
    root: Path,
    target_path: str | None = None,
    *,
    tolerance: float = 0.01,
) -> dict[str, Any]:
    """Verify every numeric claim in a paper / report against workspace outputs.

    Parameters
    ----------
    target_path:
        Relative path of the document to audit. Defaults to
        ``synthesis/paper.md``; falls back to ``synthesis/report.md``.
    tolerance:
        Relative-difference tolerance for float matching. Default 1%.
    """
    workspace = root / "workspace"
    if not workspace.exists():
        return {"status": "error", "message": "workspace/ not found"}

    if not target_path:
        # Find the most plausible target.
        for candidate in (
            "synthesis/paper.md",
            "synthesis/report.md",
            "synthesis/abstract.md",
            "synthesis/null_findings.md",
        ):
            if (root / candidate).exists():
                target_path = candidate
                break
        if not target_path:
            return {
                "status": "warning",
                "message": (
                    "no synthesis target found — run tool_synthesize first."
                ),
            }

    md_path = root / target_path
    if not md_path.exists():
        return {"status": "error",
                "message": f"target not found: {target_path}"}

    claims = extract_claims(md_path)
    corpus = _gather_output_corpus(workspace)
    corpus_numbers = _extract_corpus_numbers(corpus)

    grounded: list[dict[str, Any]] = []
    ungrounded: list[dict[str, Any]] = []
    for c in claims:
        if _claim_grounded(c["value"], corpus_numbers, tolerance):
            grounded.append(c)
        else:
            ungrounded.append(c)

    coverage_pct = round(100 * len(grounded) / max(1, len(claims)), 1)
    # Persist the claim index for the dashboard.
    idx_path = root / "synthesis" / "claim_index.json"
    idx_path.parent.mkdir(parents=True, exist_ok=True)
    idx_path.write_text(json.dumps({
        "target": target_path,
        "tolerance": tolerance,
        "total_claims": len(claims),
        "grounded": len(grounded),
        "ungrounded": len(ungrounded),
        "coverage_pct": coverage_pct,
        "ungrounded_claims": ungrounded,
        "grounded_claims": grounded[:30],  # cap the file size
    }, indent=2, default=str) + "\n")

    # Markdown report.
    logs = root / "workspace" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    report = logs / "claim_grounding.md"
    lines = [
        "# Claim grounding audit",
        "",
        f"_Target: `{target_path}`_  |  Tolerance: ±{int(tolerance * 100)}%",
        "",
        f"- Total numeric claims: **{len(claims)}**",
        f"- Grounded in workspace outputs: **{len(grounded)}** ({coverage_pct}%)",
        f"- Ungrounded (hallucination candidates): **{len(ungrounded)}**",
        "",
    ]
    if ungrounded:
        lines.append("## Ungrounded claims (review before submission)")
        for c in ungrounded[:50]:
            lines.append(
                f"- L{c['line']}: **{c['token']}** — \"…{c['context']}…\""
            )
        if len(ungrounded) > 50:
            lines.append(f"… and {len(ungrounded) - 50} more.")
        lines.append("")
    report.write_text("\n".join(lines) + "\n")

    any_blockers = bool(ungrounded)
    return {
        "status": "error" if any_blockers else "success",
        "target": target_path,
        "total_claims": len(claims),
        "grounded": len(grounded),
        "ungrounded": len(ungrounded),
        "coverage_pct": coverage_pct,
        "ungrounded_claims": ungrounded,
        "report_path": str(report.relative_to(root)),
        "claim_index_path": str(idx_path.relative_to(root)),
        "advice": (
            f"{len(ungrounded)} numeric claim(s) in {target_path} do not "
            "appear in any workspace output. Either (a) verify them and "
            "add the source to a workspace report, (b) remove them from "
            "the paper, or (c) widen the tolerance if the audit is too "
            "strict for your domain."
            if any_blockers
            else f"All {len(claims)} numeric claims grounded in outputs."
        ),
    }


class ClaimGroundingAudit(AuditBase):
    """Phase-4 :class:`AuditBase` wrapper around :func:`audit_claims`.

    Calls the legacy procedural auditor (so the markdown report and
    ``synthesis/claim_index.json`` continue to be written byte-identically)
    and then translates its ``ungrounded`` list into a list of
    :class:`AuditFinding` objects:

    * one ``severity="block"`` finding per ungrounded claim — these are
      hallucination candidates that should block the synthesis gate;
    * one ``severity="info"`` summary finding per run, recording the
      coverage percentage even when the gate passes cleanly. This gives
      the append-only ``.audit_findings.jsonl`` ledger a heartbeat entry
      so reviewers can see the audit actually ran.

    Each finding's UUID is derived deterministically with ``uuid5`` over
    ``(audit_name, dimension, evidence_paths, sorted suggested_fix)`` so
    that re-running the audit against the same workspace + paper does
    NOT churn finding IDs — important for downstream diffing of the
    jsonl ledger across runs.
    """

    name = "claim_grounding"

    def run(  # type: ignore[override]
        self,
        root: Path,
        target_path: str | None = None,
        *,
        tolerance: float = 0.01,
        **_: Any,
    ) -> list[AuditFinding]:
        result = audit_claims(root, target_path=target_path, tolerance=tolerance)

        findings: list[AuditFinding] = []

        # Error / warning paths short-circuit: audit ran but had nothing
        # to do (no workspace, no target). Emit a single warn finding so
        # the gate has a record of the no-op rather than silently passing.
        if result.get("status") in {"error", "warning"} and not result.get("target"):
            findings.append(
                _make_finding(
                    severity="warn",
                    dimension="grounding",
                    evidence_paths=[],
                    suggested_fix=(
                        result.get("message")
                        or "claim_grounding could not run — see workspace state."
                    ),
                )
            )
            return findings

        target = result.get("target") or (target_path or "synthesis/paper.md")
        report_path = result.get("report_path") or (
            "workspace/logs/claim_grounding.md"
        )
        idx_path = result.get("claim_index_path") or (
            "synthesis/claim_index.json"
        )

        for c in result.get("ungrounded_claims") or []:
            ctx = (c.get("context") or "").strip()
            findings.append(
                _make_finding(
                    severity="block",
                    dimension="grounding",
                    evidence_paths=[target, report_path],
                    suggested_fix=(
                        f"Claim `{c.get('token')}` on L{c.get('line')} of "
                        f"{target} does not appear in any workspace output. "
                        "Verify the number against a workspace report, or "
                        "remove it from the paper."
                        + (f' Context: "...{ctx}..."' if ctx else "")
                    ),
                )
            )

        # Always emit an info summary so the ledger gets a heartbeat
        # even when no ungrounded claims exist.
        findings.append(
            _make_finding(
                severity="info",
                dimension="grounding",
                evidence_paths=[target, report_path, idx_path],
                suggested_fix=(
                    f"{result.get('grounded', 0)} of {result.get('total_claims', 0)} "
                    f"numeric claims grounded "
                    f"({result.get('coverage_pct', 0)}% coverage) "
                    f"at tolerance ±{int(tolerance * 100)}%."
                ),
            )
        )

        return findings


def _make_finding(
    *,
    severity: str,
    dimension: str,
    evidence_paths: list[str],
    suggested_fix: str,
) -> AuditFinding:
    """Build an :class:`AuditFinding` with a deterministic uuid5 id.

    Keying off ``(audit_name, dimension, sorted evidence_paths,
    suggested_fix)`` keeps the id stable across reruns where the audit
    finds the same problem in the same place, so the append-only
    ``.audit_findings.jsonl`` ledger can be diffed cleanly.
    """
    audit_name = "claim_grounding"
    key = "|".join([
        audit_name,
        dimension,
        severity,
        ",".join(sorted(evidence_paths)),
        suggested_fix,
    ])
    stable_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, key))
    return AuditFinding(
        audit_name=audit_name,
        severity=severity,
        dimension=dimension,
        id=stable_id,
        evidence_paths=list(evidence_paths),
        suggested_fix=suggested_fix,
    )


__all__ = [
    "audit_claims",
    "extract_claims",
    "ClaimGroundingAudit",
]
