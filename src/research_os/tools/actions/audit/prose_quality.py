"""Prose-quality audit for research writing.

Targets the writing the AI puts into ``synthesis/*.md``, per-step
``conclusions.md``, and any other Markdown deliverable. Flags:

* **Hedge / weasel language** — "substantial", "many", "tends to",
  "appears to", "clearly", "obviously", "essentially". Hedges are
  fine in moderation; a paper with ≥ 3 hedges per 100 words is
  imprecise.
* **Numbers without precision** — "many subjects", "a few patients",
  "several trials". Each is a vague quantifier with no number nearby;
  the auditor demands an explicit count.
* **Passive-voice overuse** — light heuristic via `to be` + past
  participle. Passive ratio > 30% is flagged.
* **Reading-level** — Flesch-Kincaid grade. Target 12-18 for science.
  Higher = harder; very high (>20) gets a warning to simplify.
* **Causal language on observational data** — already enforced
  elsewhere, but the auditor surfaces it as part of the unified
  report so reviewers see it in one place.
* **Reporting-standard compliance** — CONSORT, STROBE, PRISMA section
  checks based on the standard the project's `domain_analysis` step
  surfaced from the literature.

Output: ``workspace/logs/prose_audit.md`` (legacy markdown report,
preserved verbatim for backward compatibility) + a structured dict the
master quality auditor can consume. In Phase 4 the
:class:`ProseQualityAudit` class also emits a list of
:class:`AuditFinding` objects, which the server-side handler fans out
to ``workspace/prose_quality_audit.{md,json}`` and appends to
``workspace/logs/.audit_findings.jsonl`` via
:func:`write_audit_outputs`.
"""

from __future__ import annotations

import logging
import re
import uuid
from pathlib import Path
from typing import Any

from research_os.tools.actions.audit._base import (
    AuditBase,
    AuditFinding,
)

logger = logging.getLogger("research_os.audit.prose")


# Stable UUIDv5 namespace for prose-quality findings. Using NAMESPACE_DNS
# with a deterministic key (audit_name + dimension + evidence paths +
# severity + suggested fix) means re-running the same audit against the
# same workspace produces the same id — the jsonl ledger doesn't churn
# IDs across reruns, which makes diffing two runs trivial.
_FINDING_NAMESPACE = uuid.NAMESPACE_DNS


def _finding_uuid(
    *,
    audit_name: str,
    dimension: str,
    evidence_paths: list[str],
    severity: str,
    suggested_fix: str,
) -> str:
    """Derive a stable UUIDv5 from the finding's salient fields.

    Two runs over an unchanged workspace yield identical IDs, which is
    the point — Phase-4 dashboards diff findings by id, so churning UUIDs
    on every run would make every finding look "new". We include
    severity + suggested_fix in the key so a recategorisation (warn →
    block) registers as a different finding rather than silently
    overwriting the old one in any downstream id-keyed store.
    """
    key = "|".join([
        audit_name,
        dimension,
        severity,
        suggested_fix,
        ",".join(sorted(evidence_paths)),
    ])
    return str(uuid.uuid5(_FINDING_NAMESPACE, key))


# ---------------------------------------------------------------------------
# Phrase + pattern lists (synthesized from Proselint, Vale's write-good,
# Hemingway, and academic writing folklore).
# ---------------------------------------------------------------------------

HEDGES = [
    "appears to", "tends to", "seems to", "may suggest", "could be argued",
    "somewhat", "rather", "fairly", "quite", "relatively", "arguably",
    "perhaps", "possibly", "presumably", "it is thought that",
    "to some extent", "in some ways",
]

WEASELS = [
    "clearly", "obviously", "of course", "naturally", "simply",
    "just", "basically", "essentially", "virtually", "literally",
    "very", "really", "extremely",
]

VAGUE_QUANTIFIERS = [
    "many", "several", "numerous", "substantial", "considerable",
    "a number of", "various", "much", "most", "some", "a few",
    "a handful of", "a couple of",
]

CLICHES = [
    "the fact that", "in order to", "due to the fact that",
    "owing to the fact that", "despite the fact that",
    "at this point in time", "in close proximity",
    "for all intents and purposes", "needless to say",
]

CAUSAL_TERMS_OBSERVATIONAL = [
    r"\bcauses\b", r"\bcaused by\b", r"\bleads to\b",
    r"\bresults in\b", r"\bimpacts\b", r"\bdrives\b",
    r"\bproves\b", r"\bdemonstrates causality\b",
]


def _flesch_kincaid_grade(text: str) -> float:
    """Compute Flesch-Kincaid grade level — pure Python, no deps.

    Formula: 0.39 * (words / sentences) + 11.8 * (syllables / words) - 15.59
    """
    sentences = max(1, len(re.findall(r"[.!?]+", text)))
    words = re.findall(r"\b[a-zA-Z]+\b", text)
    word_count = max(1, len(words))
    syllable_count = sum(_count_syllables(w) for w in words)
    return round(
        0.39 * (word_count / sentences)
        + 11.8 * (syllable_count / word_count)
        - 15.59, 2,
    )


def _count_syllables(word: str) -> int:
    """Crude syllable counter — good enough for FK grade-level estimates."""
    word = word.lower()
    if len(word) <= 3:
        return 1
    vowels = "aeiouy"
    count = 0
    prev_vowel = False
    for ch in word:
        is_vowel = ch in vowels
        if is_vowel and not prev_vowel:
            count += 1
        prev_vowel = is_vowel
    if word.endswith("e") and count > 1:
        count -= 1
    return max(1, count)


def _passive_voice_ratio(text: str) -> tuple[float, list[str]]:
    """Light heuristic: any form of `to be` followed within 3 words by a
    past participle (-ed / -en). Returns (ratio, examples)."""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    n = 0
    examples: list[str] = []
    for s in sentences:
        if not s.strip():
            continue
        # Look for is/are/was/were/be/been/being + past participle within 3 words.
        pat = re.compile(
            r"\b(is|are|was|were|be|been|being)\s+(?:\w+\s+){0,3}(\w+ed|\w+en)\b",
            re.IGNORECASE,
        )
        if pat.search(s):
            n += 1
            if len(examples) < 4:
                examples.append(s.strip()[:140])
    ratio = round(n / max(1, len(sentences)), 3)
    return ratio, examples


def _find_hits(text: str, terms: list[str]) -> list[dict[str, Any]]:
    """Locate verbatim term hits with a 50-char context window."""
    hits: list[dict[str, Any]] = []
    lower = text.lower()
    for t in terms:
        for m in re.finditer(rf"\b{re.escape(t)}\b", lower):
            start = max(0, m.start() - 30)
            end = min(len(text), m.end() + 30)
            hits.append({
                "term": t,
                "context": text[start:end].replace("\n", " ").strip(),
                "offset": m.start(),
            })
    return hits


def _vague_quantifier_hits(text: str) -> list[dict[str, Any]]:
    """Vague quantifiers WITHOUT a number nearby (in the next 50 chars)."""
    hits: list[dict[str, Any]] = []
    for q in VAGUE_QUANTIFIERS:
        pat = re.compile(rf"\b{re.escape(q)}\b\s+(\w+)", re.IGNORECASE)
        for m in pat.finditer(text):
            window_end = min(len(text), m.end() + 60)
            window = text[m.start():window_end]
            # If a digit appears nearby, treat as anchored; otherwise flag.
            if re.search(r"\b\d", window):
                continue
            hits.append({
                "term": q,
                "noun": m.group(1),
                "context": text[max(0, m.start() - 20):window_end].strip(),
            })
    return hits


# ---------------------------------------------------------------------------
# Reporting-standard section checks
# ---------------------------------------------------------------------------


REPORTING_STANDARDS: dict[str, dict[str, Any]] = {
    "consort": {
        "name": "CONSORT 2010 (RCT)",
        "required_sections": [
            "Trial design", "Participants", "Interventions", "Outcomes",
            "Sample size", "Randomisation", "Blinding",
            "Statistical methods", "Participant flow", "Recruitment",
            "Baseline data", "Numbers analysed", "Outcomes and estimation",
            "Harms",
        ],
    },
    "strobe": {
        "name": "STROBE (observational)",
        "required_sections": [
            "Study design", "Setting", "Participants", "Variables",
            "Data sources", "Measurement", "Bias", "Study size",
            "Quantitative variables", "Statistical methods",
            "Descriptive data", "Outcome data", "Main results",
            "Other analyses", "Key results", "Limitations",
            "Interpretation", "Generalisability",
        ],
    },
    "prisma": {
        "name": "PRISMA 2020 (systematic review)",
        "required_sections": [
            "Eligibility criteria", "Information sources",
            "Search strategy", "Selection process", "Data collection",
            "Data items", "Study risk of bias", "Effect measures",
            "Synthesis methods", "Reporting bias", "Certainty assessment",
            "Study selection", "Study characteristics", "Risk of bias",
            "Results of individual studies", "Results of syntheses",
        ],
    },
    "arrive": {
        "name": "ARRIVE 2.0 (animal studies)",
        "required_sections": [
            "Study design", "Sample size", "Inclusion and exclusion criteria",
            "Randomisation", "Blinding", "Outcome measures",
            "Statistical methods", "Experimental animals",
            "Experimental procedures", "Results", "Interpretation",
        ],
    },
}


def _reporting_standard_for(domain: str) -> str | None:
    """Best-effort mapping from a project domain to a reporting standard."""
    d = (domain or "").lower()
    if "rct" in d or "clinical_trial" in d or "trial" in d:
        return "consort"
    if "epidem" in d or "observational" in d or "cohort" in d:
        return "strobe"
    if "systematic_review" in d or "meta" in d:
        return "prisma"
    if "animal" in d or "preclin" in d:
        return "arrive"
    return None


def _section_coverage(text: str, sections: list[str]) -> dict[str, bool]:
    """For each required section, check whether the text mentions it."""
    lower = text.lower()
    out: dict[str, bool] = {}
    for s in sections:
        key = s.lower()
        # Allow loose matches: "Participants" matches "## Participants",
        # "Study Participants:", etc.
        pat = re.compile(rf"\b{re.escape(key)}\b")
        out[s] = bool(pat.search(lower))
    return out


# ---------------------------------------------------------------------------
# Document-level audit
# ---------------------------------------------------------------------------


def audit_prose_document(
    path: Path,
    *,
    is_observational: bool = False,
    reporting_standard: str | None = None,
) -> dict[str, Any]:
    """Audit one Markdown document. Returns a structured report."""
    if not path.exists():
        return {"path": str(path), "status": "error",
                "message": "file not found"}

    text = path.read_text(errors="replace")
    # Strip code fences + YAML front matter so we don't lint code.
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    text = re.sub(r"^---\n.*?\n---\n", "", text, flags=re.DOTALL)

    word_count = len(re.findall(r"\b[a-zA-Z]+\b", text))
    fk_grade = _flesch_kincaid_grade(text)
    passive_ratio, passive_examples = _passive_voice_ratio(text)
    hedges = _find_hits(text, HEDGES)
    weasels = _find_hits(text, WEASELS)
    vague = _vague_quantifier_hits(text)
    cliches = _find_hits(text, CLICHES)

    # Causal language for observational designs.
    causal_hits: list[dict[str, str]] = []
    if is_observational:
        for pat in CAUSAL_TERMS_OBSERVATIONAL:
            for m in re.finditer(pat, text, flags=re.IGNORECASE):
                ctx_start = max(0, m.start() - 40)
                ctx_end = min(len(text), m.end() + 40)
                causal_hits.append({
                    "term": m.group(0),
                    "context": text[ctx_start:ctx_end].replace("\n", " ").strip(),
                })

    # Reporting-standard section coverage.
    coverage: dict[str, bool] = {}
    coverage_pct = None
    if reporting_standard and reporting_standard in REPORTING_STANDARDS:
        spec = REPORTING_STANDARDS[reporting_standard]
        coverage = _section_coverage(text, spec["required_sections"])
        present = sum(1 for v in coverage.values() if v)
        coverage_pct = round(100 * present / max(1, len(coverage)), 1)

    # Severity assessment.
    blockers: list[str] = []
    warnings: list[str] = []
    if causal_hits:
        blockers.append(
            f"{len(causal_hits)} causal-language hit(s) in observational "
            "writing — rewrite with associational phrasing "
            "('is associated with', 'is correlated with')."
        )
    if hedges and word_count and (len(hedges) / word_count) > 0.03:
        warnings.append(
            f"{len(hedges)} hedge phrases ({100 * len(hedges) / word_count:.1f} "
            "per 100 words) — over 3 per 100 reads as evasive."
        )
    if weasels:
        warnings.append(
            f"{len(weasels)} weasel words ({', '.join(sorted({h['term'] for h in weasels})[:5])}) "
            "— delete or replace with concrete language."
        )
    if vague:
        warnings.append(
            f"{len(vague)} vague-quantifier phrases without a nearby number. "
            "Replace 'many subjects' with 'N = 423 subjects'."
        )
    if cliches:
        warnings.append(
            f"{len(cliches)} cliché phrases (e.g. {cliches[0]['term']!r}) — "
            "tighten the prose."
        )
    if passive_ratio > 0.35:
        warnings.append(
            f"Passive-voice ratio {100 * passive_ratio:.0f}% of sentences "
            "(>35%) — convert some to active voice for clarity."
        )
    if fk_grade > 20:
        warnings.append(
            f"Flesch-Kincaid grade {fk_grade} — very dense; consider "
            "shortening sentences."
        )
    if coverage_pct is not None and coverage_pct < 60:
        blockers.append(
            f"Reporting-standard coverage {coverage_pct}% "
            f"({REPORTING_STANDARDS[reporting_standard]['name']}). "
            "Missing sections: "
            + ", ".join(s for s, v in coverage.items() if not v)[:300]
        )

    return {
        "path": str(path),
        "word_count": word_count,
        "fk_grade": fk_grade,
        "passive_ratio": passive_ratio,
        "passive_examples": passive_examples,
        "hedges": hedges[:20],
        "weasels": weasels[:20],
        "vague_quantifiers": vague[:20],
        "cliches": cliches[:10],
        "causal_hits": causal_hits[:10],
        "reporting_standard": reporting_standard,
        "section_coverage": coverage,
        "coverage_pct": coverage_pct,
        "blockers": blockers,
        "warnings": warnings,
        "ok": not blockers,
    }


def audit_prose(
    root: Path,
    *,
    targets: list[str] | None = None,
    is_observational: bool | None = None,
) -> dict[str, Any]:
    """Audit every research prose file (paper, abstract, per-step
    conclusions, methods, etc.) for hedging, vague quantifiers,
    passive voice, reading level, causal-language hits, and
    reporting-standard coverage.

    Parameters
    ----------
    targets:
        Optional list of file paths relative to project root. Default
        target set is synthesis/*.md + every workspace/<step>/conclusions.md.
    is_observational:
        Override the design type for causal-language gating. When None,
        the function reads researcher_config.yaml.
    """
    if not (root / "workspace").exists():
        return {"status": "error", "message": "workspace/ not found"}

    # Default target list.
    if not targets:
        targets = []
        synth = root / "synthesis"
        if synth.exists():
            for f in sorted(synth.glob("*.md")):
                targets.append(str(f.relative_to(root)))
        ws = root / "workspace"
        if ws.exists():
            for step in sorted(ws.iterdir()):
                if not (step.is_dir() and re.match(r"^\d{2,3}_", step.name)):
                    continue
                if step.name.endswith("__DEAD_END"):
                    continue
                conc = step / "conclusions.md"
                if conc.exists():
                    targets.append(str(conc.relative_to(root)))

    # Domain → reporting standard. Domain lives in state.json (written by
    # tool_intake_autofill); older workspaces may still carry it in
    # researcher_config.yaml under the legacy `domain:` key.
    domain = ""
    design = ""
    try:
        from research_os.project_ops import load_state
        domain = (load_state(root) or {}).get("domain", "") or ""
    except Exception:
        # State unreadable / not initialised — fall through to the cfg
        # fallback; domain stays empty if neither source has it.
        pass
    if not domain or is_observational is None:
        cfg_path = root / "inputs" / "researcher_config.yaml"
        if cfg_path.exists():
            try:
                import yaml  # type: ignore

                cfg = yaml.safe_load(cfg_path.read_text()) or {}
                if not domain:
                    domain = cfg.get("domain", "") or cfg.get("research_goal", {}).get("domain", "")
                design = (cfg.get("research_goal") or {}).get("design", "")
            except Exception:
                # Malformed YAML / unreadable — leave domain + design
                # empty; the observational heuristic below assumes
                # "experimental" by default.
                pass
    if is_observational is None:
        is_observational = (
            "observational" in (domain + design).lower()
            or "epidem" in (domain + design).lower()
            or "cohort" in (domain + design).lower()
        )
    standard = _reporting_standard_for(domain)

    per_doc: list[dict[str, Any]] = []
    any_blockers = False
    for rel in targets:
        p = root / rel
        if not p.exists():
            continue
        rep = audit_prose_document(
            p,
            is_observational=bool(is_observational),
            reporting_standard=standard,
        )
        if rep.get("blockers"):
            any_blockers = True
        per_doc.append(rep)

    logs = root / "workspace" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    out = logs / "prose_audit.md"
    lines = ["# Prose Quality Audit", ""]
    if standard:
        lines.append(f"_Reporting standard: {REPORTING_STANDARDS[standard]['name']}_")
        lines.append("")
    for d in per_doc:
        icon = "❌" if d.get("blockers") else "⚠️" if d.get("warnings") else "✅"
        lines.append(
            f"## {icon} `{d['path']}` "
            f"— {d['word_count']} words · "
            f"FK grade {d['fk_grade']} · "
            f"passive {int(d['passive_ratio'] * 100)}%"
        )
        if d.get("coverage_pct") is not None:
            lines.append(f"- Reporting-standard coverage: {d['coverage_pct']}%")
        if d.get("blockers"):
            lines.append("")
            lines.append("**Blockers**")
            for b in d["blockers"]:
                lines.append(f"- {b}")
        if d.get("warnings"):
            lines.append("")
            lines.append("Warnings")
            for w in d["warnings"]:
                lines.append(f"- {w}")
        # Show a sample of vague + hedge hits for actionability.
        if d.get("vague_quantifiers"):
            lines.append("")
            lines.append("Vague quantifier examples:")
            for h in d["vague_quantifiers"][:5]:
                lines.append(f"  - `{h['term']}` near `{h['noun']}`: \"…{h['context']}…\"")
        if d.get("hedges"):
            lines.append("")
            lines.append("Hedge examples:")
            for h in d["hedges"][:5]:
                lines.append(f"  - `{h['term']}`: \"…{h['context']}…\"")
        lines.append("")
    out.write_text("\n".join(lines) + "\n")

    return {
        "status": "error" if any_blockers else "success",
        "report_path": str(out.relative_to(root)),
        "n_documents": len(per_doc),
        "documents": per_doc,
        "reporting_standard": standard,
        "advice": (
            "Prose blockers found — fix before tool_synthesize. Causal "
            "language for observational designs is the most common; "
            "rewrite as associational. Reporting-standard sub-section "
            "gaps require adding the missing headings."
            if any_blockers
            else "Prose audit clean."
        ),
    }


# ---------------------------------------------------------------------------
# Phase-4 AuditBase subclass
# ---------------------------------------------------------------------------


# Map free-text blocker/warning strings (or causal-language flags) onto the
# stable ``dimension`` vocabulary the AuditFinding schema requires. We keep
# the dimension labels short + lowercase so dashboards can group on them.
def _dimension_for_blocker(blocker: str) -> str:
    """Classify a per-document blocker string into a dimension label."""
    lower = blocker.lower()
    if "causal-language" in lower or "causal language" in lower:
        return "causal_language"
    if "reporting-standard" in lower or "reporting standard" in lower:
        return "reporting_standard"
    return "prose"


def _dimension_for_warning(warning: str) -> str:
    """Classify a per-document warning string into a dimension label."""
    lower = warning.lower()
    if "hedge" in lower:
        return "hedging"
    if "weasel" in lower:
        return "weasel"
    if "vague-quantifier" in lower or "vague quantifier" in lower:
        return "vague_quantifier"
    if "cliché" in lower or "cliche" in lower:
        return "cliche"
    if "passive-voice" in lower or "passive voice" in lower:
        return "passive_voice"
    if "flesch-kincaid" in lower or "flesch kincaid" in lower:
        return "reading_level"
    return "prose"


def _findings_from_doc_report(rep: dict[str, Any]) -> list[AuditFinding]:
    """Convert one document's audit_prose_document() dict into AuditFindings.

    Mirrors the existing BLOCK/WARN split: anything in ``blockers`` becomes
    ``severity="block"``; anything in ``warnings`` becomes
    ``severity="warn"``. The evidence_paths list always contains the
    document's path so reviewers can jump straight to it.
    """
    findings: list[AuditFinding] = []
    path = rep.get("path", "")
    evidence = [path] if path else []
    audit_name = "prose_quality"

    for b in rep.get("blockers") or []:
        dim = _dimension_for_blocker(b)
        fix = b  # The blocker string IS the fix instruction in this module.
        fid = _finding_uuid(
            audit_name=audit_name,
            dimension=dim,
            evidence_paths=evidence,
            severity="block",
            suggested_fix=fix,
        )
        findings.append(AuditFinding(
            audit_name=audit_name,
            severity="block",
            dimension=dim,
            id=fid,
            evidence_paths=list(evidence),
            suggested_fix=fix,
        ))

    for w in rep.get("warnings") or []:
        dim = _dimension_for_warning(w)
        fix = w
        fid = _finding_uuid(
            audit_name=audit_name,
            dimension=dim,
            evidence_paths=evidence,
            severity="warn",
            suggested_fix=fix,
        )
        findings.append(AuditFinding(
            audit_name=audit_name,
            severity="warn",
            dimension=dim,
            id=fid,
            evidence_paths=list(evidence),
            suggested_fix=fix,
        ))

    return findings


class ProseQualityAudit(AuditBase):
    """Phase-4 wrapper around the prose-quality audit.

    Delegates the heavy lifting to :func:`audit_prose` (which preserves
    the legacy markdown report verbatim) and then folds the resulting
    per-document blockers + warnings into a flat ``list[AuditFinding]``
    that the orchestrator can persist via :func:`write_audit_outputs`.
    """

    name = "prose_quality"

    def run(self, root: Path, **kwargs: Any) -> list[AuditFinding]:
        """Run the prose audit and return structured findings.

        Accepts the same kwargs the legacy ``audit_prose`` accepts:
        ``targets`` and ``is_observational``. Returns an empty list when
        the workspace is missing (rather than raising) so the caller can
        treat "no workspace" as "no findings" — matching the behaviour
        of the legacy function that returns ``{"status": "error"}``
        without writing any artefacts.
        """
        report = audit_prose(
            root,
            targets=kwargs.get("targets"),
            is_observational=kwargs.get("is_observational"),
        )
        findings: list[AuditFinding] = []
        for doc in report.get("documents") or []:
            findings.extend(_findings_from_doc_report(doc))
        return findings


__all__ = [
    "audit_prose",
    "audit_prose_document",
    "ProseQualityAudit",
]
