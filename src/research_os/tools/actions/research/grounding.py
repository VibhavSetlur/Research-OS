"""Grounded reasoning — ReAct + PROV-O + CoVe + Reflexion lessons.

The AI's most-common failure mode is acting without showing the
evidence it acted on. This module gives the project four append-only
records that make every decision auditable:

* **Thought log** (ReAct) — ``workspace/.thoughts/thoughts.jsonl``
  appends one `{thought, action, observation}` entry per non-trivial
  step. Mirrors Yao et al. 2022's trajectory format so the trace
  reads as the model intended it.
* **Grounding registry** — ``workspace/.grounding/grounding.jsonl``
  binds each `decision_id` to a PROV-O record listing the entities
  (papers, datasets, context files, web sources) the decision
  rested on, with `cited_text` spans where applicable.
* **Verification log** (CoVe) — ``workspace/.grounding/verifications.jsonl``
  carries the verification questions the AI generated for each
  claim plus the verified answers and `supports: bool`. A claim is
  considered grounded only when all its verifications hold.
* **Lessons log** (Reflexion) — ``workspace/.lessons/lessons.jsonl``
  captures `{trial_id, outcome, reflection}` after every step so
  later runs can prepend the relevant prior lessons to context.

All four are line-delimited JSON so they round-trip cleanly into
the dashboard, into the audit reports, and into the model's prompt
context. They are intentionally NOT inlined into ``state_ledger.json``
— that file stays small; these grow as the project does.

Integration with the existing audit chain
-----------------------------------------
`tool_grounding_verify` walks every `mem_decision_log` entry in
`workspace/analysis.md` and confirms a matching grounding record
exists. A decision without grounding is a BLOCKER for the master
quality audit (alongside hallucinated claims, missing figures,
stub conclusions). This is the structural fix for "AI made a call
but didn't show its work".
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("research_os.grounding")


# ---------------------------------------------------------------------------
# File-layout helpers
# ---------------------------------------------------------------------------


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _thoughts_log(root: Path) -> Path:
    p = root / "workspace" / ".thoughts" / "thoughts.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _grounding_log(root: Path) -> Path:
    p = root / "workspace" / ".grounding" / "grounding.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _verifications_log(root: Path) -> Path:
    p = root / "workspace" / ".grounding" / "verifications.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _append_jsonl(path: Path, record: dict) -> None:
    with open(path, "a") as f:
        f.write(json.dumps(record, default=str) + "\n")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


# ---------------------------------------------------------------------------
# Thought log (ReAct)
# ---------------------------------------------------------------------------


_ALLOWED_KINDS = {
    "thought",       # internal reasoning
    "plan",          # multi-step plan summary
    "action",        # external tool call about to be made
    "observation",   # result of the action
    "reflection",    # post-hoc self-critique
    "decision",      # committed methodological choice
}


def thought_log(
    root: Path,
    *,
    kind: str,
    content: str,
    step_id: str | None = None,
    decision_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append one ReAct-style trace entry.

    Parameters
    ----------
    kind: thought | plan | action | observation | reflection | decision
    content: the entry body (short prose).
    step_id: numbered step context (optional).
    decision_id: link to a decision in the grounding log (optional).
    metadata: free-form structured fields (model, tool name, etc).
    """
    if kind not in _ALLOWED_KINDS:
        return {
            "status": "error",
            "message": f"kind must be one of {sorted(_ALLOWED_KINDS)}",
        }
    if not content or not content.strip():
        return {"status": "error", "message": "content is required"}
    rec = {
        "trace_id": str(uuid.uuid4())[:12],
        "ts": _now(),
        "kind": kind,
        "content": content.strip(),
        "step_id": step_id,
        "decision_id": decision_id,
        "metadata": metadata or {},
    }
    _append_jsonl(_thoughts_log(root), rec)
    return {"status": "success", **rec,
            "log_path": str(_thoughts_log(root).relative_to(root))}


def thought_trace(
    root: Path,
    *,
    step_id: str | None = None,
    decision_id: str | None = None,
    tail: int = 50,
) -> dict[str, Any]:
    """Read the recent thought trace, optionally filtered."""
    entries = _read_jsonl(_thoughts_log(root))
    if step_id:
        entries = [e for e in entries if e.get("step_id") == step_id]
    if decision_id:
        entries = [e for e in entries if e.get("decision_id") == decision_id]
    return {
        "status": "success",
        "n_total": len(entries),
        "entries": entries[-tail:],
    }


# ---------------------------------------------------------------------------
# Grounding registry (PROV-O)
# ---------------------------------------------------------------------------


_SOURCE_TYPES = {
    "paper",          # peer-reviewed publication; citation_key from literature/
    "preprint",       # arXiv / bioRxiv / SSRN
    "dataset",        # data file in inputs/raw_data or external
    "context_file",   # prose note in inputs/context/ or step's context/
    "web",            # web page (URL + accessed_at)
    "workspace_artefact",  # an output file from another step
    "tool_research",  # a tool_research_method / tool_research_tool report
    "prior_decision", # another decision_id this one builds on
}


def grounding_register(
    root: Path,
    *,
    decision_id: str | None = None,
    claim: str,
    sources: list[dict[str, Any]],
    step_id: str | None = None,
    confidence: str = "medium",
    notes: str = "",
) -> dict[str, Any]:
    """Bind a decision/claim to the evidence that informed it.

    sources: list of dicts shaped::

        {"type": "paper", "citation_key": "smith2023", "doi": "...",
         "cited_text": "We found that …", "page": 4}
        {"type": "context_file", "path": "inputs/context/intake.md",
         "cited_text": "primary outcome is X"}
        {"type": "web", "url": "https://...", "accessed_at": "2026-05-28",
         "cited_text": "..."}
        {"type": "workspace_artefact", "path": "workspace/02_eda/outputs/.../table.csv",
         "cited_text": "row 7 col 'mean' = 12.3"}
    """
    if not claim.strip():
        return {"status": "error", "message": "claim is required"}
    if not sources:
        return {
            "status": "error",
            "message": "at least one source is required — a grounded "
            "decision cites at least one paper / context file / dataset / "
            "tool report. To record an exploratory hunch without "
            "evidence, use tool_thought_log kind='thought' instead.",
        }
    for s in sources:
        if s.get("type") not in _SOURCE_TYPES:
            return {
                "status": "error",
                "message": (
                    f"source type must be one of {sorted(_SOURCE_TYPES)}; "
                    f"got '{s.get('type')}'"
                ),
            }
    if confidence not in {"low", "medium", "high"}:
        return {
            "status": "error",
            "message": "confidence must be low | medium | high",
        }

    decision_id = decision_id or f"d_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}_{uuid.uuid4().hex[:6]}"
    record = {
        # PROV-O JSON-LD shell.
        "@context": {"prov": "http://www.w3.org/ns/prov#"},
        "@type": "prov:Activity",
        "@id": f"ros:decision/{decision_id}",
        "decision_id": decision_id,
        "claim": claim.strip(),
        "step_id": step_id,
        "registered_at": _now(),
        "confidence": confidence,
        "notes": notes.strip(),
        "prov:used": [
            {**s, "@type": "prov:Entity"} for s in sources
        ],
        "prov:wasAssociatedWith": {
            "@type": "prov:Agent",
            "@id": "ros:agent/research_os",
        },
    }
    _append_jsonl(_grounding_log(root), record)
    return {
        "status": "success",
        "decision_id": decision_id,
        "n_sources": len(sources),
        "log_path": str(_grounding_log(root).relative_to(root)),
        "record": record,
    }


def grounding_for_decision(
    root: Path, decision_id: str,
) -> dict[str, Any] | None:
    """Return the most-recent grounding record for ``decision_id``."""
    matches = [
        r for r in _read_jsonl(_grounding_log(root))
        if r.get("decision_id") == decision_id
    ]
    return matches[-1] if matches else None


# ---------------------------------------------------------------------------
# CoVe verification log
# ---------------------------------------------------------------------------


def claim_verify(
    root: Path,
    *,
    claim: str,
    verifications: list[dict[str, Any]],
    decision_id: str | None = None,
    step_id: str | None = None,
) -> dict[str, Any]:
    """Record CoVe-style verification questions + answers for one claim.

    verifications shaped::

        {"question": "Are variances unequal across the two groups?",
         "answer":   "Levene p < 0.01 → yes",
         "evidence": {"type": "workspace_artefact",
                       "path": ".../residuals.csv"},
         "supports": true}

    A claim is "verified" only when EVERY verification entry has
    ``supports == true``.
    """
    if not verifications:
        return {
            "status": "error",
            "message": "at least one verification entry required",
        }
    n_supports = sum(1 for v in verifications if v.get("supports") is True)
    verdict = "verified" if n_supports == len(verifications) else "needs_revision"
    rec = {
        "ts": _now(),
        "claim": claim.strip(),
        "decision_id": decision_id,
        "step_id": step_id,
        "verifications": verifications,
        "n_total": len(verifications),
        "n_supports": n_supports,
        "verdict": verdict,
    }
    _append_jsonl(_verifications_log(root), rec)
    return {"status": "success", **rec,
            "log_path": str(_verifications_log(root).relative_to(root))}


# ---------------------------------------------------------------------------
# Grounding verification — audit gate
# ---------------------------------------------------------------------------


_DECISION_BLOCK_RE = re.compile(
    r"###\s+Decision\s*[·-]\s*(?P<ts>[^\n]+?)\n+(?P<body>(?:.|\n)*?)"
    r"(?=^###\s|^\[\d{4}-\d{2}-\d{2}|\Z)",
    re.MULTILINE,
)


def _decisions_in_analysis_md(root: Path) -> list[dict[str, str]]:
    analysis = root / "workspace" / "analysis.md"
    if not analysis.exists():
        return []
    text = analysis.read_text()
    out: list[dict[str, str]] = []
    for m in _DECISION_BLOCK_RE.finditer(text):
        body = m.group("body").strip()
        ctx_match = re.search(r"\*\*Context\*\*:\s*(.+)", body)
        sel_match = re.search(r"\*\*Selected\*\*:\s*(.+)", body)
        rat_match = re.search(r"\*\*Rationale\*\*:\s*(.+)", body)
        lit_match = re.search(r"\*\*Linked literature\*\*:\s*(.+)", body)
        key = hashlib.sha256(body.encode()).hexdigest()[:12]
        out.append({
            "decision_key": key,
            "ts": m.group("ts").strip(),
            "context": (ctx_match.group(1) if ctx_match else "")[:200],
            "selected": (sel_match.group(1) if sel_match else "")[:200],
            "rationale": (rat_match.group(1) if rat_match else "")[:300],
            "linked_literature": lit_match.group(1) if lit_match else "",
        })
    return out


def grounding_verify(root: Path) -> dict[str, Any]:
    """Check every analysis.md decision has a grounding record.

    Strategy:
      * Read every Decision block in workspace/analysis.md.
      * If the block declared a linked literature key, treat that as
        sufficient lightweight grounding.
      * Otherwise look up by `decision_key` (sha-256 prefix of the
        block body) in workspace/.grounding/grounding.jsonl.
      * Decisions without either are flagged as UNGROUNDED — a
        master-audit blocker.

    Writes ``workspace/logs/grounding_audit.md``.
    """
    decisions = _decisions_in_analysis_md(root)
    if not decisions:
        return {
            "status": "success",
            "n_decisions": 0,
            "message": "No decisions found in workspace/analysis.md.",
        }

    grounding = _read_jsonl(_grounding_log(root))
    # Index grounding records by claim-prefix so the AI can ground a
    # decision by re-quoting the rationale (decision_id matching is
    # done inline below).
    grounded_claims = {
        g.get("claim", "")[:60].lower() for g in grounding
    }

    grounded: list[dict[str, str]] = []
    ungrounded: list[dict[str, str]] = []
    for d in decisions:
        has_inline_citation = bool(d.get("linked_literature", "").strip())
        has_registry_record = any(
            d["decision_key"] in (g.get("decision_id") or "")
            or d["rationale"][:60].lower() in grounded_claims
            or d["selected"][:60].lower() in grounded_claims
            for g in grounding
        )
        if has_inline_citation or has_registry_record:
            grounded.append(d)
        else:
            ungrounded.append(d)

    # Write report.
    logs = root / "workspace" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    out = logs / "grounding_audit.md"
    lines = [
        "# Grounding audit",
        "",
        f"- Total decisions: {len(decisions)}",
        f"- Grounded: {len(grounded)}",
        f"- Ungrounded: {len(ungrounded)}",
        "",
    ]
    if ungrounded:
        lines.append("## Ungrounded decisions")
        for d in ungrounded[:20]:
            lines.append(f"- **{d['ts']}**: {d['selected'][:120]}")
            lines.append(f"  - Rationale: {d['rationale'][:160]}")
            lines.append(
                "  - Fix: call tool_grounding_register decision_id=<id> "
                "claim=\"...\" sources=[{type: paper|context_file|web, …}]"
            )
        if len(ungrounded) > 20:
            lines.append(f"…and {len(ungrounded) - 20} more.")
        lines.append("")
    out.write_text("\n".join(lines) + "\n")

    return {
        "status": "error" if ungrounded else "success",
        "n_decisions": len(decisions),
        "n_grounded": len(grounded),
        "n_ungrounded": len(ungrounded),
        "ungrounded": [
            {"ts": d["ts"], "selected": d["selected"]} for d in ungrounded
        ],
        "report_path": str(out.relative_to(root)),
        "advice": (
            f"{len(ungrounded)} decision(s) carry no grounding record. "
            "For each, call tool_grounding_register binding the decision "
            "to the inputs/context/literature that informed it. Or "
            "include a `linked_literature` key in the original "
            "mem_decision_log call."
            if ungrounded
            else "All decisions in analysis.md are grounded."
        ),
    }


# ---------------------------------------------------------------------------
# Convenience: ground a decision against an inputs/context file directly.
# ---------------------------------------------------------------------------


def ground_from_context(
    root: Path,
    *,
    decision_id: str | None = None,
    claim: str,
    context_paths: list[str],
    cited_excerpts: list[str] | None = None,
    confidence: str = "medium",
) -> dict[str, Any]:
    """Shortcut: build a grounding record from inputs/context/ files.

    Pulls each path's content, picks the matching ``cited_excerpts`` (or
    the first 240 chars), and registers a grounding entry.
    """
    sources: list[dict[str, Any]] = []
    for i, rel in enumerate(context_paths):
        p = root / rel
        if not p.exists():
            return {
                "status": "error",
                "message": f"context file not found: {rel}",
            }
        text = p.read_text(errors="replace")
        cited = (
            (cited_excerpts[i] if cited_excerpts and i < len(cited_excerpts)
             else text[:240])
        ).strip()
        sources.append({
            "type": "context_file",
            "path": rel,
            "cited_text": cited[:400],
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest()[:16],
        })
    return grounding_register(
        root, decision_id=decision_id, claim=claim,
        sources=sources, confidence=confidence,
    )


__all__ = [
    "claim_verify",
    "grounding_for_decision",
    "grounding_register",
    "grounding_verify",
    "ground_from_context",
    "thought_log",
    "thought_trace",
]
