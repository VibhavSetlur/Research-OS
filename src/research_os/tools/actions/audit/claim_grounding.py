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
   report. The synthesis gate reads this and BLOCKS if any ungrounded
   claim is in the paper.

The auditor is opinionated about what counts as a "claim":
* Numbers in `# Headings` (Markdown) / `= Headings` (Typst) are skipped
  (counts, sample sizes in titles are usually re-stated in body).
* Numbers in `> blockquote` are still checked (often quoted findings).
* Numbers in fenced code blocks are skipped (those are inline data).

Tolerance
---------
Floats match if the relative difference is ≤ 1%. Integers (counts /
sample sizes) must match EXACTLY — a relative tolerance there would
"ground" a hallucinated N=2456 to a real 2469. Percentages are
normalised to fractions before comparison. Canonical CI confidence
levels (90/95/99% in CI context) and p-value thresholds (p/α < x) are
excluded — they are reporting conventions, not values in an output table.
"""

from __future__ import annotations

import logging
import re
import uuid
from pathlib import Path
from typing import Any

from research_os.tools.actions.audit._base import AuditBase, AuditFinding
from research_os.tools.actions.audit._paper import is_typst, resolve_paper_path

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


def _strip_code_and_citations(text: str, typst: bool = False) -> str:
    """Remove fenced code blocks + inline code + bracketed citation refs.

    When ``typst`` is set, also strip Typst ``// line`` and ``/* block */``
    comments — a .typ scaffold is mostly authoring comments, and the
    numbers inside them ("400-800 words", "≥3 cited works") are not
    claims.
    """
    out = text
    if typst:
        # Block comments first, then line comments (whole-line + trailing).
        out = re.sub(r"/\*.*?\*/", " ", out, flags=re.DOTALL)
        out = re.sub(r"//[^\n]*", " ", out)
    # Fenced code blocks.
    out = re.sub(r"```.*?```", " ", out, flags=re.DOTALL)
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


# Canonical CI confidence levels + p-value thresholds are reporting
# conventions, not estimates that appear in an output table — extracting them
# as "claims" produces false ungrounded BLOCKERS on well-reported papers.
_CI_LEVELS = {"90%", "95%", "99%", "99.5%", "99.9%"}
_CI_CTX = re.compile(r"\b(?:CI|confidence|interval)\b", re.I)
# A number immediately preceded by p / P / alpha / α + a comparator is a
# p-value (or significance) threshold, not a substantive estimate. Word
# boundaries keep "step < 5" / "group = 3" from matching the bare "p".
_PVAL_CTX = re.compile(
    r"(?:\bp[\s.\-]?val(?:ue)?\b|\bp\b|\balpha\b|α)\s*[<>=≤≥]\s*$", re.I
)


def _is_ci_level(tok: str, ctx: str) -> bool:
    return tok.replace(" ", "") in _CI_LEVELS and bool(_CI_CTX.search(ctx))


def _is_pvalue_threshold(before: str) -> bool:
    return bool(_PVAL_CTX.search(before))


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
    """Pull every quantitative claim out of a Markdown or Typst document."""
    if not md_path.exists():
        return []
    typst = is_typst(md_path)
    text = _strip_code_and_citations(
        md_path.read_text(errors="replace"), typst=typst
    )
    heading_char = "=" if typst else "#"
    claims: list[dict[str, Any]] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        # Skip pure headings (numbers in titles are usually restated).
        if line.lstrip().startswith(heading_char):
            continue
        for m in _CLAIM_PAT.finditer(line):
            tok = m.group(0).strip()
            if _is_year(tok):
                continue
            # Skip if it's part of an obvious markdown structure
            # (image dimensions, dates).
            if re.search(r"(\d{4})-\d{2}-\d{2}", line[max(0, m.start() - 4):m.end()]):
                continue
            # Skip canonical CI levels (in CI context) + p-value thresholds
            # (in p/α context) — reporting conventions, never in an output table.
            before = line[max(0, m.start() - 12):m.start()]
            ctx_local = line[max(0, m.start() - 12):min(len(line), m.end() + 12)]
            if _is_ci_level(tok, ctx_local) or _is_pvalue_threshold(before):
                continue
            val = _normalise(tok)
            if val is None:
                continue
            is_pct = tok.rstrip().endswith("%")
            # An integer claim (no decimal point / scientific form, not a %) is
            # a count / sample size — it must match an output value EXACTLY, not
            # within ±tolerance (else a hallucinated N=2456 "grounds" to 2469).
            is_int = not is_pct and "." not in tok and "e" not in tok.lower()
            ctx_start = max(0, m.start() - 60)
            ctx_end = min(len(line), m.end() + 60)
            claims.append({
                "token": tok,
                "value": val,
                "is_pct": is_pct,
                "is_int": is_int,
                "line": line_no,
                "context": line[ctx_start:ctx_end].strip(),
            })
    return claims


def _gather_output_corpus(workspace: Path) -> list[tuple[str, bool]]:
    """Collect the bodies of every output file the AI could have pulled
    numbers from, tagged with whether the file is comma/tab-DELIMITED.

    Returns a list of ``(text, is_delimited)`` chunks. CSV/TSV are
    delimited — a comma there is a field separator, NOT a thousands
    grouping, so the number extractor must not glue ``12,345`` (two cells)
    into ``12345``. Prose files (.md/.txt/.json) are non-delimited, where
    ``12,345`` IS a grouped integer the paper may legitimately cite.
    """
    chunks: list[tuple[str, bool]] = []
    for step in sorted(workspace.iterdir()):
        if not (step.is_dir() and re.match(r"^\d{2,3}_", step.name)):
            continue
        if step.name.endswith("__DEAD_END"):
            continue
        # Scan both the 3.2 output dir name and the pre-3.2 legacy name.
        for sub in ("outputs/reports", "outputs/tables",
                    "data/next_step_output", "data/output"):
            d = step / sub
            if not d.exists():
                continue
            for f in d.rglob("*"):
                if not f.is_file():
                    continue
                suffix = f.suffix.lower()
                if suffix not in {".csv", ".tsv", ".json", ".md", ".txt"}:
                    continue
                try:
                    chunks.append((f.read_text(errors="replace"),
                                   suffix in {".csv", ".tsv"}))
                except OSError:
                    continue
    return chunks


def _extract_corpus_numbers(corpus: list[tuple[str, bool]] | str) -> set[float]:
    """Pre-compute every numeric token in the corpus for fast lookup.

    Must recognise the SAME numeric forms the claim extractor normalises —
    in particular thousands-separated integers (``12,345`` / ``12 345``).
    A naive ``\\d+`` would split ``12,345`` in a prose output report into
    ``12`` and ``345``, so a paper claim of ``12,345`` (which
    :func:`_normalise` turns into ``12345.0``) would NEVER find its
    verbatim source and get flagged as an ungrounded hallucination — a
    false ship-gate BLOCKER on a correctly-sourced sample size.

    But a comma in a CSV/TSV cell is a field SEPARATOR, not a grouping, so
    comma-grouping is applied ONLY to non-delimited (prose) chunks. For
    delimited files we additionally keep the per-cell components, so a
    grouped claim never silently grounds to two unrelated adjacent cells.
    Accepts the legacy ``str`` form (treated as non-delimited prose) for
    backward compatibility with direct callers / tests.
    """
    if isinstance(corpus, str):
        corpus = [(corpus, False)]

    out: set[float] = set()
    # Space-grouping (12 345) is safe everywhere — neither CSV nor TSV use a
    # space as a field separator. Comma-grouping (12,345) is prose-only.
    grouped_prose = re.compile(
        r"""
        (?<![A-Za-z0-9_])
        (-?\d{1,3}(?:[,\s]\d{3})+(?:\.\d+)?)
        (?![A-Za-z0-9_])
        """,
        re.VERBOSE,
    )
    grouped_space_only = re.compile(
        r"""
        (?<![A-Za-z0-9_])
        (-?\d{1,3}(?:\ \d{3})+(?:\.\d+)?)
        (?![A-Za-z0-9_])
        """,
        re.VERBOSE,
    )
    plain = re.compile(r"-?\d+(?:\.\d+)?(?:e[+-]?\d+)?", re.IGNORECASE)

    for text, is_delimited in corpus:
        grouped_pat = grouped_space_only if is_delimited else grouped_prose
        for m in grouped_pat.finditer(text):
            try:
                out.add(float(m.group(1).replace(",", "").replace(" ", "")))
            except ValueError:
                continue
        # Plain pass captures bare ints/decimals AND the per-cell
        # components of any grouped form (so CSV cells stay individually
        # grounded).
        for m in plain.finditer(text):
            try:
                out.add(float(m.group(0)))
            except ValueError:
                continue
    return out


def _claim_grounded(value: float, corpus_numbers: set[float],
                    tolerance: float = 0.01, *, is_pct: bool = False,
                    is_int: bool = False) -> bool:
    """Check whether ``value`` appears in the corpus (verbatim or close).

    An integer (count / sample size) must match EXACTLY — applying a relative
    tolerance there would silently "ground" a hallucinated N=2456 to a real
    2469. Only genuine floats get the ±tolerance match.

    A percentage claim ("84%") is normalised to a fraction (0.84) by
    :func:`_normalise`, but the corpus often stores the same figure as the
    raw percent (``84``) — or, for an already-fractional source, as
    ``0.84``. So for a %-derived claim we test the normalised value AND its
    ``×100`` / ``÷100`` variants before declaring it ungrounded."""
    if is_int and not is_pct:
        return float(value) in corpus_numbers
    candidates = [value]
    if is_pct:
        candidates.extend([value * 100.0, value / 100.0])
    for v in candidates:
        if v in corpus_numbers:
            return True
        abs_v = abs(v) or 1e-12
        for cv in corpus_numbers:
            if abs(cv - v) / max(abs_v, abs(cv) or 1e-12) <= tolerance:
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
        Relative path of the document to audit. Defaults to the resolved
        paper (``synthesis/paper.typ`` if present, else the Markdown
        forms); falls back to abstract / null-findings drafts.
    tolerance:
        Relative-difference tolerance for float matching. Default 1%.
    """
    workspace = root / "workspace"
    if not workspace.exists():
        return {"status": "error", "message": "workspace/ not found"}

    if not target_path:
        # Find the most plausible target — the resolved paper first
        # (.typ preferred), then the lighter standalone drafts.
        for candidate in (
            resolve_paper_path(root),
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
                    "no synthesis target found — author synthesis/paper.typ "
                    "first."
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
        if _claim_grounded(
            c["value"], corpus_numbers, tolerance,
            is_pct=c.get("is_pct", False), is_int=c.get("is_int", False),
        ):
            grounded.append(c)
        else:
            ungrounded.append(c)

    coverage_pct = round(100 * len(grounded) / max(1, len(claims)), 1)
    # NB: the legacy ``synthesis/claim_index.json`` sidecar is no longer
    # written — it was write-only infrastructure that cluttered the user's
    # synthesis/ folder and nothing ever read it. The structured findings
    # in ``workspace/logs/.audit_findings.jsonl`` are the source of truth.
    # Migration: remove a stale copy left by a pre-3.2 release.
    _stale_idx = root / "synthesis" / "claim_index.json"
    try:
        if _stale_idx.exists():
            _stale_idx.unlink()
    except OSError:
        pass

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
    """:class:`AuditBase` wrapper around :func:`audit_claims`.

    Calls the procedural auditor (so the markdown report at
    ``workspace/logs/claim_grounding.md`` continues to be written)
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

        target = result.get("target") or (target_path or resolve_paper_path(root))
        report_path = result.get("report_path") or (
            "workspace/logs/claim_grounding.md"
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
                evidence_paths=[target, report_path],
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
