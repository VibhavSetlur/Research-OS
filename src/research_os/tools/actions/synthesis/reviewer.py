"""Reviewer-response scaffold — pre-submission adversarial review simulation.

Four tools work together as a self-review pass BEFORE the paper goes out:

  * reviewer_simulate(root, personas=None)
      Loads N persona YAMLs and the paper, writes
      workspace/reviewer/simulation_brief.md — the AI in the host IDE
      reads the brief, then walks the paper section-by-section through
      each persona's lens and writes per-persona comment lists into
      workspace/reviewer/<persona_id>_comments.md.

  * rebuttal_draft(root, comment, persona, evidence_paths=None)
      Pulls evidence from workspace/<step>/findings_vs_literature.md,
      workspace/methods.md, outputs/, and synthesis/paper.md, then
      writes a single rebuttal markdown file at
      workspace/reviewer/rebuttals/<slug>.md.

  * reviewer_response_compile(root)
      Assembles every rebuttal markdown under workspace/reviewer/rebuttals/
      into workspace/reviewer/response_to_reviewers.md and compiles to
      PDF via the bundled Typst generic_two_column template.

  * audit_reviewer_responses(root)
      Walks every rebuttal and WARNs on hand-waving language ("we
      believe", "future work will address"), unaddressed comments
      (rebuttals with no evidence reference), and any rebuttal whose
      cited evidence paths do not exist on disk.

The server never calls an LLM. These tools write READING INSTRUCTIONS
that the AI in the host IDE drives.
"""

from __future__ import annotations

import logging
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger("research_os.tools.synthesis.reviewer")


PERSONAS_DIR = Path(__file__).resolve().parents[3] / "assets" / "reviewer_personas"

# The default persona roster. All 7 ship and all 7 run unless the
# caller restricts via `personas=`.
DEFAULT_PERSONAS: tuple[str, ...] = (
    "methodology_skeptic",
    "domain_expert",
    "statistician",
    "reproducibility_advocate",
    "scope_creep_critic",
    "novelty_critic",
    "presentation_critic",
)

# Hand-waving phrases that should never appear in a rebuttal. Each
# matches case-insensitively as a substring.
HAND_WAVING_PHRASES: tuple[str, ...] = (
    "we believe",
    "we feel",
    "we are confident",
    "in our opinion",
    "it is clear that",
    "obviously",
    "clearly,",
    "as is well known",
    "future work will address",
    "this is beyond the scope",
    "we leave this for future work",
    "this concern is unfounded",
    "the reviewer misunderstands",
    "the reviewer is mistaken",
)


# ---------------------------------------------------------------------------
# Persona loading
# ---------------------------------------------------------------------------


def load_persona(persona_id: str) -> dict[str, Any]:
    """Load a single persona YAML from the bundled assets dir.

    Raises FileNotFoundError if the persona is unknown.
    """
    path = PERSONAS_DIR / f"{persona_id}.yaml"
    if not path.exists():
        raise FileNotFoundError(
            f"unknown reviewer persona: {persona_id} (looked at {path})"
        )
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_all_personas(persona_ids: list[str] | None = None) -> list[dict[str, Any]]:
    """Load all personas (or a filtered subset). Skips unknown ids with a warning."""
    ids = list(persona_ids) if persona_ids else list(DEFAULT_PERSONAS)
    out: list[dict[str, Any]] = []
    for pid in ids:
        try:
            out.append(load_persona(pid))
        except FileNotFoundError as exc:
            logger.warning("skipping unknown persona %s: %s", pid, exc)
    return out


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def _slugify(text: str, max_len: int = 60) -> str:
    """Lowercase a-z0-9 + underscores, truncated. Stable for filenames."""
    s = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return s[:max_len] or "comment"


def _ensure_reviewer_dirs(root: Path) -> tuple[Path, Path]:
    """Create workspace/reviewer/ + workspace/reviewer/rebuttals/."""
    root = Path(root)
    reviewer_dir = root / "workspace" / "reviewer"
    rebuttals_dir = reviewer_dir / "rebuttals"
    rebuttals_dir.mkdir(parents=True, exist_ok=True)
    return reviewer_dir, rebuttals_dir


def _paper_path(root: Path) -> Path:
    return Path(root) / "synthesis" / "paper.md"


# ---------------------------------------------------------------------------
# reviewer_simulate
# ---------------------------------------------------------------------------


def reviewer_simulate(
    root: Path | str,
    personas: list[str] | None = None,
) -> dict[str, Any]:
    """Build a reading brief for the AI to walk through each persona.

    Returns a dict with personas (full payloads), the paper path, and
    the brief path. Writes workspace/reviewer/simulation_brief.md as
    the durable artefact.
    """
    root = Path(root)
    reviewer_dir, _ = _ensure_reviewer_dirs(root)
    paper = _paper_path(root)
    paper_exists = paper.exists()

    loaded = load_all_personas(personas)
    if not loaded:
        return {
            "status": "error",
            "message": (
                "No personas loaded. Pass a non-empty list, or use the "
                "defaults (7 personas ship with Research-OS)."
            ),
        }

    lines: list[str] = []
    lines.append("# Pre-submission reviewer simulation — reading brief\n")
    lines.append(
        f"_Generated {datetime.now(timezone.utc).isoformat(timespec='seconds')}_\n"
    )
    lines.append(
        "This brief is the entry point for an adversarial self-review "
        "pass. The AI in the host IDE walks the paper through each "
        "persona's lens, writes per-persona comments, then uses "
        "`tool_rebuttal_draft` for every comment that requires a response.\n"
    )
    if not paper_exists:
        lines.append(
            "> **WARNING**: `synthesis/paper.md` does not exist yet. Run "
            "`tool_synthesize` first; the personas need a paper to attack.\n"
        )
    lines.append(f"## Target paper\n\n`{paper.relative_to(root) if paper_exists else 'synthesis/paper.md (missing)'}`\n")

    lines.append("## Reading procedure (run for each persona below)\n")
    lines.append(
        "1. Re-read the paper with the persona's `lens` in mind.\n"
        "2. For every concern, append a numbered comment to\n"
        "   `workspace/reviewer/<persona_id>_comments.md` in the format:\n"
        "   `N. <one-line concern>` followed by the relevant paper "
        "   section / line citation.\n"
        "3. Cross-check against `red_flags` — any hit is an automatic "
        "   comment.\n"
        "4. After all personas are walked, run `tool_rebuttal_draft` "
        "   for every comment that requires substantive evidence; "
        "   minor / presentation comments may be batched into a single "
        "   editorial-pass rebuttal.\n"
        "5. Run `tool_reviewer_response_compile` to assemble.\n"
        "6. Run `tool_audit_reviewer_responses` to gate on hand-waving "
        "   + missing evidence + unaddressed comments before submission.\n"
    )

    lines.append("## Personas\n")
    for p in loaded:
        lines.append(f"### {p.get('name', p.get('id'))}  (`id: {p.get('id')}`)\n")
        lens = p.get("lens", "").strip()
        if lens:
            lines.append(f"**Lens**: {lens}\n")
        attacks = p.get("what_they_attack") or []
        if attacks:
            lines.append("**What they attack**:")
            lines.extend(f"  - {a}" for a in attacks)
            lines.append("")
        values = p.get("what_they_value") or []
        if values:
            lines.append("**What they value**:")
            lines.extend(f"  - {v}" for v in values)
            lines.append("")
        qs = p.get("typical_questions") or []
        if qs:
            lines.append("**Typical questions to ask of the paper**:")
            lines.extend(f"  - {q}" for q in qs)
            lines.append("")
        rfs = p.get("red_flags") or []
        if rfs:
            lines.append("**Red flags (auto-comment if any appear)**:")
            lines.extend(f"  - {r}" for r in rfs)
            lines.append("")
        phrasings = p.get("signature_phrasings") or []
        if phrasings:
            lines.append("**Signature phrasings to draft comments in**:")
            lines.extend(f"  - {s}" for s in phrasings)
            lines.append("")

    brief_path = reviewer_dir / "simulation_brief.md"
    brief_text = "\n".join(lines).rstrip() + "\n"
    brief_path.write_text(brief_text, encoding="utf-8")

    return {
        "status": "success",
        "brief_path": str(brief_path.relative_to(root)),
        "paper_path": str(paper.relative_to(root)) if paper_exists else None,
        "paper_exists": paper_exists,
        "personas": [
            {"id": p.get("id"), "name": p.get("name")} for p in loaded
        ],
        "persona_count": len(loaded),
        "next_step": (
            "Read the brief, then per-persona walk the paper and write "
            "workspace/reviewer/<persona_id>_comments.md."
        ),
    }


# ---------------------------------------------------------------------------
# rebuttal_draft
# ---------------------------------------------------------------------------


def _collect_findings_vs_literature(root: Path) -> list[Path]:
    out: list[Path] = []
    ws = root / "workspace"
    if not ws.exists():
        return out
    for step in sorted(ws.iterdir()):
        if not step.is_dir():
            continue
        fvl = step / "literature" / "findings_vs_literature.md"
        if fvl.exists():
            out.append(fvl)
    return out


def _evidence_index(root: Path) -> dict[str, list[str]]:
    """Best-effort inventory of evidence the rebuttal can cite."""
    idx: dict[str, list[str]] = {
        "methods": [],
        "findings_vs_literature": [],
        "outputs": [],
        "paper_sections": [],
    }
    methods = root / "workspace" / "methods.md"
    if methods.exists():
        idx["methods"].append(str(methods.relative_to(root)))
    for fvl in _collect_findings_vs_literature(root):
        idx["findings_vs_literature"].append(str(fvl.relative_to(root)))
    ws = root / "workspace"
    if ws.exists():
        for step in sorted(ws.iterdir()):
            if not step.is_dir():
                continue
            out_dir = step / "outputs"
            if not out_dir.exists():
                continue
            for sub in ("figures", "tables", "reports"):
                d = out_dir / sub
                if d.exists():
                    for p in sorted(d.iterdir()):
                        if p.is_file():
                            idx["outputs"].append(str(p.relative_to(root)))
    paper = _paper_path(root)
    if paper.exists():
        for m in re.finditer(r"^##\s+(.+)$", paper.read_text(encoding="utf-8"), re.M):
            idx["paper_sections"].append(m.group(1).strip())
    return idx


def rebuttal_draft(
    root: Path | str,
    comment: str,
    persona: str,
    evidence_paths: list[str] | None = None,
) -> dict[str, Any]:
    """Scaffold a single rebuttal markdown file under workspace/reviewer/rebuttals/.

    The AI in the host IDE then fills in the response body using the
    evidence inventory the scaffold supplies.
    """
    root = Path(root)
    if not comment or not comment.strip():
        return {"status": "error", "message": "comment is required and must be non-empty"}
    if not persona or not persona.strip():
        return {"status": "error", "message": "persona is required"}
    try:
        persona_payload = load_persona(persona)
    except FileNotFoundError as exc:
        return {"status": "error", "message": str(exc)}

    _, rebuttals_dir = _ensure_reviewer_dirs(root)
    slug = _slugify(f"{persona}_{comment}")
    out_path = rebuttals_dir / f"{slug}.md"

    inventory = _evidence_index(root)
    user_evidence = [p for p in (evidence_paths or []) if p]

    # Track which user-supplied evidence paths actually exist.
    existing_evidence: list[str] = []
    missing_evidence: list[str] = []
    for p in user_evidence:
        if (root / p).exists():
            existing_evidence.append(p)
        else:
            missing_evidence.append(p)

    lines: list[str] = []
    lines.append(f"# Rebuttal — {persona_payload.get('name', persona)}\n")
    lines.append(
        f"_Drafted {datetime.now(timezone.utc).isoformat(timespec='seconds')}_\n"
    )
    lines.append("## Reviewer comment\n")
    lines.append(f"> {comment.strip()}\n")
    lines.append("## Response posture\n")
    lines.append(
        "Pick one and remove the others: **ACCEPT** (revise the paper) | "
        "**ACCEPT WITH CLARIFICATION** (add a sentence / footnote) | "
        "**PUSH BACK** (with evidence, never with assertion).\n"
    )
    lines.append("## Response\n")
    lines.append(
        "<!-- Fill this in. Match the reviewer's framing. Cite concrete "
        "evidence (script, figure, table, prior-art citation). Avoid "
        "hand-waving language. End with the specific revision made + "
        "section/line ref. -->\n"
    )

    lines.append("## Evidence\n")
    if existing_evidence:
        lines.append("**Researcher-supplied evidence paths**:")
        lines.extend(f"  - `{p}`" for p in existing_evidence)
        lines.append("")
    if missing_evidence:
        lines.append(
            "> **WARNING**: the following supplied evidence paths do "
            "not exist on disk and will NOT be cited unless created:"
        )
        lines.extend(f"  - `{p}`" for p in missing_evidence)
        lines.append("")
    lines.append("**Auto-discovered evidence available in the workspace**:")
    if inventory["methods"]:
        lines.append("  - Methods record:")
        lines.extend(f"    - `{p}`" for p in inventory["methods"])
    if inventory["findings_vs_literature"]:
        lines.append("  - Per-step adversarial verdicts:")
        lines.extend(f"    - `{p}`" for p in inventory["findings_vs_literature"])
    if inventory["outputs"]:
        # Truncate so the rebuttal stays readable.
        sample = inventory["outputs"][:25]
        lines.append("  - Outputs (figures / tables / reports, first 25):")
        lines.extend(f"    - `{p}`" for p in sample)
        if len(inventory["outputs"]) > 25:
            lines.append(
                f"    - ... and {len(inventory['outputs']) - 25} more"
            )
    if inventory["paper_sections"]:
        lines.append("  - Paper sections to cross-reference:")
        lines.extend(f"    - {s}" for s in inventory["paper_sections"])
    if not any(inventory.values()):
        lines.append(
            "> **WARNING**: no auto-discovered evidence. The rebuttal "
            "will need researcher-supplied citations or new analysis."
        )
    lines.append("")

    lines.append("## Persona reminder\n")
    lines.append(
        f"_{persona_payload.get('name')}_ values: "
        + "; ".join(persona_payload.get("what_they_value") or [])
        + "\n"
    )

    out_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    return {
        "status": "success",
        "rebuttal_path": str(out_path.relative_to(root)),
        "persona": persona,
        "evidence_supplied": existing_evidence,
        "evidence_missing": missing_evidence,
        "evidence_discovered": {
            k: len(v) for k, v in inventory.items()
        },
        "next_step": (
            "Fill the Response section, then run "
            "tool_reviewer_response_compile to assemble all rebuttals."
        ),
    }


# ---------------------------------------------------------------------------
# reviewer_response_compile
# ---------------------------------------------------------------------------


def reviewer_response_compile(root: Path | str) -> dict[str, Any]:
    """Concatenate every rebuttal .md into response_to_reviewers.md and
    compile to PDF via the bundled Typst generic_two_column template.
    """
    root = Path(root)
    reviewer_dir, rebuttals_dir = _ensure_reviewer_dirs(root)

    rebuttals = sorted(p for p in rebuttals_dir.glob("*.md") if p.is_file())
    if not rebuttals:
        return {
            "status": "error",
            "message": (
                "No rebuttals found under workspace/reviewer/rebuttals/. "
                "Run tool_rebuttal_draft first."
            ),
            "rebuttals_dir": str(rebuttals_dir.relative_to(root)),
        }

    # Group rebuttals by persona (derived from the filename prefix).
    grouped: dict[str, list[Path]] = {}
    for r in rebuttals:
        # filenames start with the persona id slug
        prefix = r.stem.split("_", 1)[0]
        # The persona id may itself contain underscores
        # (methodology_skeptic, presentation_critic). Try to recognise
        # the full known set first.
        matched = None
        for pid in DEFAULT_PERSONAS:
            if r.stem.startswith(pid):
                matched = pid
                break
        key = matched or prefix
        grouped.setdefault(key, []).append(r)

    lines: list[str] = []
    lines.append("# Response to reviewers\n")
    lines.append(
        f"_Compiled {datetime.now(timezone.utc).isoformat(timespec='seconds')}_\n"
    )
    lines.append(
        "This document responds to every comment from the simulated "
        "(or actual) reviewer pass. Each section groups rebuttals by "
        "the reviewer persona that raised the concern.\n"
    )
    for persona_id in sorted(grouped):
        try:
            persona_name = load_persona(persona_id).get("name", persona_id)
        except FileNotFoundError:
            persona_name = persona_id
        lines.append(f"## Reviewer — {persona_name}\n")
        for r in grouped[persona_id]:
            body = r.read_text(encoding="utf-8")
            # Demote H1 (#) inside the rebuttal so the assembled doc keeps a clean hierarchy.
            body = re.sub(r"^# ", "### ", body, flags=re.M)
            lines.append(body.rstrip() + "\n")
    response_md = reviewer_dir / "response_to_reviewers.md"
    md_text = "\n".join(lines).rstrip() + "\n"
    response_md.write_text(md_text, encoding="utf-8")

    # PDF compile via Typst — best-effort, optional dependency.
    pdf_result: dict[str, Any] = {"status": "skipped", "message": "typst not available"}
    pdf_path: Path | None = None
    try:
        from research_os.tools.actions.synthesis.typst import (
            compile_typst,
            md_to_typst,
        )

        typst_text = md_to_typst(md_text, venue_template="generic_two_column")
        # Rewrite import to a local copy (matches paper_compile_typst behaviour).
        typst_src = reviewer_dir / "response_to_reviewers.typ"
        local_templates = reviewer_dir / "_typst_templates"
        local_templates.mkdir(exist_ok=True)
        # Copy template if available.
        from research_os.tools.actions.synthesis.typst import _find_templates_dir

        templates_src = _find_templates_dir()
        if templates_src is not None:
            for name in ("generic_two_column.typ", "common.typ"):
                src = templates_src / name
                if src.exists():
                    shutil.copyfile(src, local_templates / name)
        typst_text = typst_text.replace(
            '#import "../templates/typst/generic_two_column.typ":',
            '#import "_typst_templates/generic_two_column.typ":',
        )
        typst_src.write_text(typst_text, encoding="utf-8")
        # Hayagriva biblio stub so the template doesn't choke on a missing file.
        biblio = reviewer_dir / "biblio.yml"
        if not biblio.exists():
            biblio.write_text(
                'placeholder:\n  type: misc\n  title: "No citations"\n',
                encoding="utf-8",
            )
        pdf_path = reviewer_dir / "response_to_reviewers.pdf"
        if shutil.which("typst"):
            pdf_result = compile_typst(typst_src, pdf_path)
        else:
            pdf_result = {
                "status": "skipped",
                "message": "typst binary not on PATH; markdown produced but PDF not compiled",
            }
    except Exception as exc:  # pragma: no cover - best-effort PDF
        logger.debug("typst compile for response failed: %s", exc)
        pdf_result = {"status": "error", "message": str(exc)}

    return {
        "status": "success",
        "response_md": str(response_md.relative_to(root)),
        "response_pdf": (
            str(pdf_path.relative_to(root))
            if pdf_path is not None and pdf_path.exists()
            else None
        ),
        "rebuttal_count": len(rebuttals),
        "personas_addressed": sorted(grouped),
        "pdf_compile": pdf_result,
    }


# ---------------------------------------------------------------------------
# audit_reviewer_responses
# ---------------------------------------------------------------------------


def audit_reviewer_responses(root: Path | str) -> dict[str, Any]:
    """Walk every rebuttal under workspace/reviewer/rebuttals/ and WARN on:

      * hand-waving language ('we believe', 'future work will address', ...)
      * unaddressed comments (rebuttals with no evidence reference)
      * supplied evidence paths that do not exist on disk
    """
    root = Path(root)
    _, rebuttals_dir = _ensure_reviewer_dirs(root)
    rebuttals = sorted(p for p in rebuttals_dir.glob("*.md") if p.is_file())
    if not rebuttals:
        return {
            "status": "warning",
            "message": "No rebuttals found to audit.",
            "warnings": [],
            "audited": 0,
            "passed": 0,
            "failed": 0,
        }

    warnings: list[dict[str, Any]] = []
    passed = 0
    for r in rebuttals:
        text = r.read_text(encoding="utf-8")
        rel = str(r.relative_to(root))
        per_file: list[str] = []

        # 1. Hand-waving — case-insensitive substring search.
        lower = text.lower()
        for phrase in HAND_WAVING_PHRASES:
            if phrase in lower:
                per_file.append(f"hand-waving language detected: '{phrase}'")

        # 2. Unaddressed: the Response section is empty or only contains the comment-stub.
        # Look for the body between "## Response" and the next H2.
        m = re.search(r"^##\s+Response\s*$(.*?)(?=^##\s+|\Z)", text, re.M | re.S)
        resp_body = (m.group(1).strip() if m else "").strip()
        # Strip comment markers.
        stripped = re.sub(r"<!--.*?-->", "", resp_body, flags=re.S).strip()
        if not stripped:
            per_file.append(
                "unaddressed: Response section is empty (only scaffold "
                "comment present)"
            )

        # 3. Evidence: must reference at least one backtick path or workspace/synthesis path
        # Count backticked paths that look like real workspace artefacts in the *response* too.
        path_hits = re.findall(r"`([^`]+\.(?:md|csv|tsv|png|svg|pdf|yaml|yml|py|R|ipynb))`", text)
        if not path_hits:
            per_file.append(
                "no evidence path cited in the rebuttal (response should "
                "name a script / figure / table / report)"
            )

        # 4. Researcher-supplied missing paths get warned by the scaffold;
        # re-flag here so the audit catches stale rebuttals that were edited
        # without removing the warning block.
        if "WARNING" in text and "do not exist on disk" in text:
            per_file.append(
                "rebuttal still contains 'supplied evidence path missing' "
                "warning from the scaffold"
            )

        if per_file:
            warnings.append({"file": rel, "issues": per_file})
        else:
            passed += 1

    failed = len(rebuttals) - passed

    # Persist a human-readable audit report next to the rebuttals.
    report_path = root / "workspace" / "reviewer" / "audit_report.md"
    report_lines = [
        "# Reviewer-response audit\n",
        f"_Audited {datetime.now(timezone.utc).isoformat(timespec='seconds')}_\n",
        f"- rebuttals audited: {len(rebuttals)}",
        f"- passed: {passed}",
        f"- failed: {failed}\n",
    ]
    if warnings:
        report_lines.append("## Findings")
        for w in warnings:
            report_lines.append(f"\n### {w['file']}")
            for issue in w["issues"]:
                report_lines.append(f"- {issue}")
    report_path.write_text("\n".join(report_lines).rstrip() + "\n", encoding="utf-8")

    status = "warning" if failed else "success"
    return {
        "status": status,
        "audited": len(rebuttals),
        "passed": passed,
        "failed": failed,
        "warnings": warnings,
        "report_path": str(report_path.relative_to(root)),
    }
