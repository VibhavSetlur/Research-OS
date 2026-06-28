"""Project-hygiene watch — the daemon watching the WHOLE project surface.

The structure audit (``structure_audit.py``) verifies the numbered-step spine.
The mode-health module (``mode_health.py``) verifies the active mode's work
dirs. This module is the third leg: it watches the governance, communication,
documentation, literature, context, and per-step environment surfaces that a
research project carries — the parts a human reviewer reads to TRUST the work,
and the parts that keep it reproducible and resumable.

The point (Research-OS is a GUIDANCE system): none of these block. Each is a
by-shape, fail-open signal the daemon surfaces so the AI can self-correct
mid-prompt and tell the researcher what it fixed — rather than a hard gate.
They answer "is this project still legible, grounded, and reproducible, or has
the reasoning layer drifted away from the record?".

Surfaces watched (all best-effort; a missing surface is simply skipped):

  * DECISIONS.md       — are design choices being logged as ADRs as the project
                         makes them? (a project with finalized steps but one
                         seed ADR has stopped recording its reasoning).
  * STATE.md           — is the status file stale relative to the latest step
                         work? (a reviewer reads STATE.md first).
  * GETTING_STARTED.md — still the untouched seed after real work exists?
  * CONTRIBUTORS.md    — present (provenance of who touched the workspace).
  * communication/     — for collaborative projects, is the comms log being
                         kept (handoffs, PI threads) once steps exist?
  * docs/              — does the project carry generated docs beyond the seed
                         (glossary populated, an overview/workflow doc)?
  * literature/        — is the root corpus-of-record keeping pace with the
                         per-step literature + inputs literature (the daemon's
                         job to flag when aggregation has fallen behind)?
  * per-step context/  — is the step's context drop-zone being used / read?
  * per-step environment/ — does a step that ran scripts carry its OWN env
                         snapshot so it is independently reproducible /
                         containerizable, not just relying on the global one?

stdlib only. Pure inspection. Never raises. Each finding:
``{severity, source='project_hygiene', message, code}``.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_STEP_RE = re.compile(r"^\d{2,3}_")

# Markers that mean a seeded governance/doc file is still untouched.
_SEED_MARKERS = (
    "Updated automatically by",          # CONTRIBUTORS seed line
    "Drop transcripts, Slack threads",   # communication/ seed
    "*(list inputs used)*",
)

_LIT_EXTS = {".pdf", ".epub"}


def _f(sev: str, code: str, msg: str) -> dict[str, Any]:
    return {"severity": sev, "source": "project_hygiene", "message": msg, "code": code}


def _live_steps(workspace: Path) -> list[Path]:
    """Numbered steps that aren't dead-ends / incompletes."""
    if not workspace.is_dir():
        return []
    out = []
    for d in sorted(workspace.iterdir()):
        if not (d.is_dir() and _STEP_RE.match(d.name)):
            continue
        if d.name.endswith("__DEAD_END") or d.name.endswith(".incomplete"):
            continue
        out.append(d)
    return out


def _has_real_conclusions(step: Path) -> bool:
    """True if a step has a non-trivially-sized conclusions.md (started work)."""
    c = step / "conclusions.md"
    try:
        return c.is_file() and c.stat().st_size > 80
    except OSError:
        return False


def _step_ran_scripts(step: Path) -> bool:
    """True if a step has at least one runnable script — i.e. it computed
    something whose environment matters for reproducibility."""
    sdir = step / "scripts"
    if not sdir.is_dir():
        return False
    try:
        return any(
            f.is_file() and f.suffix.lower() in
            {".py", ".r", ".jl", ".sh", ".ipynb", ".rmd", ".qmd"}
            for f in sdir.iterdir()
        )
    except OSError:
        return False


def _step_has_outputs(step: Path) -> bool:
    for sub in ("outputs", "data/next_step_output"):
        d = step / sub
        try:
            if d.is_dir() and any(p.is_file() for p in d.rglob("*")):
                return True
        except OSError:
            continue
    return False


def _newest_mtime(p: Path, pattern: str = "*") -> float:
    try:
        return max(
            (f.stat().st_mtime for f in p.rglob(pattern) if f.is_file()),
            default=0.0,
        )
    except OSError:
        return 0.0


def _file_is_seed(p: Path) -> bool:
    """A governance/doc file that still carries only its seed text."""
    try:
        if not p.is_file():
            return False
        txt = p.read_text(encoding="utf-8")
    except OSError:
        return False
    if len(txt) < 40:
        return True
    return any(m in txt for m in _SEED_MARKERS)


# --------------------------------------------------------------------------
# Governance: DECISIONS / STATE / GETTING_STARTED / CONTRIBUTORS
# --------------------------------------------------------------------------


def _check_governance(root: Path, steps: list[Path]) -> list[dict]:
    out: list[dict] = []
    n_started = sum(1 for s in steps if _has_real_conclusions(s))

    # DECISIONS.md — once the project has made real progress (≥2 started
    # steps), it should be logging design choices as ADRs. Count the ADR
    # headings; a project deep into execution with only the seed ADR has
    # stopped recording its reasoning (a reviewer can't reconstruct WHY).
    dec = root / "DECISIONS.md"
    if dec.is_file() and n_started >= 2:
        try:
            adr_count = len(re.findall(r"^##\s*ADR-", dec.read_text(encoding="utf-8"),
                                       re.MULTILINE))
        except OSError:
            adr_count = 0
        if adr_count <= 1:
            out.append(_f(
                "info", "decisions_not_logged",
                f"{n_started} steps have real conclusions but DECISIONS.md has "
                f"only {adr_count} ADR — log the key design choices made along "
                "the way (metric pick, branch/dead-end calls) as ADRs so a "
                "reviewer can reconstruct WHY, not just what.",
            ))

    # STATE.md — the status file a fresh reader / collaborator opens first.
    # If the newest step work is much newer than STATE.md, it's stale.
    state = root / "STATE.md"
    if state.is_file() and steps:
        try:
            state_mtime = state.stat().st_mtime
        except OSError:
            state_mtime = 0.0
        newest_step = max((_newest_mtime(s) for s in steps), default=0.0)
        # 1 hour grace so a normal edit cadence doesn't nag.
        if newest_step > state_mtime + 3600:
            out.append(_f(
                "info", "state_md_stale",
                "STATE.md is older than the latest step work — refresh it "
                "(sys_state_refresh / sys_status) so the status a collaborator "
                "reads first reflects where the project actually is.",
            ))

    # GETTING_STARTED.md — still the untouched seed after real work exists?
    gs = root / "GETTING_STARTED.md"
    if gs.is_file() and n_started >= 1 and _file_is_seed(gs):
        out.append(_f(
            "info", "getting_started_unfilled",
            "GETTING_STARTED.md is still the seed but the project has real "
            "work — update it so a new collaborator can actually get oriented.",
        ))

    # CONTRIBUTORS.md — provenance of who touched the workspace.
    contrib = root / "CONTRIBUTORS.md"
    if steps and not contrib.is_file():
        out.append(_f(
            "info", "contributors_missing",
            "No CONTRIBUTORS.md — the provenance of who set up / worked on "
            "this workspace isn't recorded.",
        ))
    return out


# --------------------------------------------------------------------------
# Communication log
# --------------------------------------------------------------------------


def _check_communication(root: Path, steps: list[Path]) -> list[dict]:
    out: list[dict] = []
    comm = root / "communication"
    if not comm.is_dir():
        return out
    n_started = sum(1 for s in steps if _has_real_conclusions(s))
    # If the project has substantive progress and the comms log is only the
    # seed README, a collaborative project has stopped recording handoffs.
    # (Solo projects legitimately leave it light — hence info, never block.)
    readme = comm / "README.md"
    other = [p for p in comm.rglob("*")
             if p.is_file() and p.name.lower() != "readme.md"]
    if n_started >= 3 and readme.is_file() and _file_is_seed(readme) and not other:
        out.append(_f(
            "info", "communication_log_empty",
            "communication/ is still just the seed after several steps — if "
            "this project has collaborators / PI threads / handoffs, keep the "
            "log current so the human record matches the work.",
        ))
    return out


# --------------------------------------------------------------------------
# Docs the AI generates
# --------------------------------------------------------------------------


def _check_docs(root: Path, steps: list[Path]) -> list[dict]:
    out: list[dict] = []
    docs = root / "docs"
    if not docs.is_dir():
        return out

    # Glossary populated? (reuse the existing context_watch helper if present.)
    try:
        from research_os.tools.actions.state.context_watch import glossary_unfilled
        if glossary_unfilled(root) and any(_has_real_conclusions(s) for s in steps):
            out.append(_f(
                "info", "glossary_unfilled",
                "docs/glossary.md has no terms yet — add the domain terms the "
                "project uses so a cross-field reader can follow the work.",
            ))
    except Exception:
        pass
    return out


# --------------------------------------------------------------------------
# Literature: root corpus keeping pace with per-step + inputs literature
# --------------------------------------------------------------------------


def _count_lit(p: Path) -> int:
    try:
        return sum(1 for f in p.rglob("*")
                   if f.is_file() and f.suffix.lower() in _LIT_EXTS)
    except OSError:
        return 0


def _check_literature(root: Path, steps: list[Path]) -> list[dict]:
    out: list[dict] = []

    corpus = root / "literature"
    if not corpus.is_dir():
        return out

    # 1. Root corpus should aggregate the inputs literature + each step's
    #    literature. If a step or inputs/ has papers the root corpus is
    #    missing, aggregation has fallen behind (the daemon's nudge to run
    #    finalize / aggregation, or for the AI to mirror them now).
    behind: list[str] = []
    inputs_lit = root / "inputs" / "literature"
    if _count_lit(inputs_lit) > _count_lit(corpus / "inputs"):
        behind.append("inputs/literature")
    for s in steps:
        step_lit = s / "literature"
        if _count_lit(step_lit) > _count_lit(corpus / "steps" / s.name):
            behind.append(f"{s.name}/literature")
    if behind:
        out.append(_f(
            "warn", "literature_corpus_behind",
            "The root literature/ corpus-of-record is behind its sources "
            f"({', '.join(behind[:5])}{'…' if len(behind) > 5 else ''}) — "
            "aggregate the new papers into literature/ (tool_path_finalize "
            "mirrors a step's papers; mirror inputs/literature too) so the "
            "single corpus stays complete.",
        ))

    # 2. Grounding: a step with real numeric conclusions and ZERO literature
    #    of its own (and no inputs corpus to lean on) is ungrounded — the AI
    #    should pull literature DURING the step, not rely only on what the
    #    researcher pre-loaded. info, not block (some steps are pure
    #    engineering — the step can mark literature_required: false).
    have_inputs_corpus = _count_lit(inputs_lit) > 0
    if not have_inputs_corpus:
        ungrounded: list[str] = []
        for s in steps:
            if not _has_real_conclusions(s):
                continue
            if _count_lit(s / "literature") == 0:
                # Respect an explicit opt-out in the step summary.
                ss = s / "step_summary.yaml"
                opted_out = False
                try:
                    if ss.is_file() and "literature_required: false" in \
                            ss.read_text(encoding="utf-8"):
                        opted_out = True
                except OSError:
                    pass
                if not opted_out:
                    ungrounded.append(s.name)
        if ungrounded:
            out.append(_f(
                "info", "step_ungrounded_no_literature",
                f"{len(ungrounded)} step(s) with real conclusions pulled no "
                f"literature of their own ({', '.join(ungrounded[:5])}"
                f"{'…' if len(ungrounded) > 5 else ''}) and there's no inputs "
                "corpus to lean on. Pull supporting papers DURING the step "
                "(research/literature_per_step) to ground the claims, or set "
                "literature_required: false for pure-engineering steps.",
            ))
    return out


# --------------------------------------------------------------------------
# Per-step context drop-zone usage
# --------------------------------------------------------------------------


def _check_step_context(root: Path, steps: list[Path]) -> list[dict]:
    out: list[dict] = []
    # The per-step context/ folder is where step-local briefing material goes.
    # We don't require it (info only): a step deep in work with material in
    # inputs/context but an empty step context/ is fine. We only nudge when a
    # step has NO context dir at all AND the project relies on context (the
    # inputs/context drop-zone is in active use) — so the per-step zone exists
    # to be used.
    inputs_ctx = root / "inputs" / "context"
    project_uses_context = False
    try:
        project_uses_context = inputs_ctx.is_dir() and any(
            p.is_file() and p.name.lower() != "readme.md"
            for p in inputs_ctx.rglob("*")
        )
    except OSError:
        project_uses_context = False
    if not project_uses_context:
        return out
    missing_ctx = [s.name for s in steps
                   if _has_real_conclusions(s) and not (s / "context").is_dir()]
    if missing_ctx:
        out.append(_f(
            "info", "step_context_dir_missing",
            f"{len(missing_ctx)} step(s) have no context/ drop-zone "
            f"({', '.join(missing_ctx[:5])}{'…' if len(missing_ctx) > 5 else ''}) "
            "though the project uses context material. The per-step context/ "
            "folder lets the researcher drop step-local briefing the AI reads — "
            "create it so step-scoped material has a home.",
        ))
    return out


# --------------------------------------------------------------------------
# Per-step environment snapshot — reproducibility / containerization
# --------------------------------------------------------------------------


def _step_has_env_snapshot(step: Path) -> bool:
    """True if a step carries its OWN environment capture (not the global one)."""
    env = step / "environment"
    if not env.is_dir():
        return False
    try:
        for f in env.iterdir():
            if not f.is_file():
                continue
            n = f.name.lower()
            if n in ("readme.md", ".gitkeep", ".gitignore"):
                continue
            # requirements.txt / session.yaml / environment.yml / Dockerfile /
            # any non-placeholder capture file counts.
            return True
    except OSError:
        return False
    return False


def _check_step_environment(root: Path, steps: list[Path]) -> list[dict]:
    out: list[dict] = []
    no_env: list[str] = []
    for s in steps:
        # Only steps that actually RAN code need their own reproducible env.
        if not (_step_ran_scripts(s) and _step_has_outputs(s)):
            continue
        if not _step_has_env_snapshot(s):
            no_env.append(s.name)
    if no_env:
        out.append(_f(
            "warn", "step_no_env_snapshot",
            f"{len(no_env)} step(s) ran scripts + produced outputs but carry no "
            f"per-step environment snapshot ({', '.join(no_env[:5])}"
            f"{'…' if len(no_env) > 5 else ''}). A global env isn't enough to "
            "re-run ONE step in isolation (or build a per-step container). "
            "Snapshot the exact packages THIS step used: "
            "sys_env(operation='snapshot', step_id='<NN_slug>'). Each step "
            "should be independently reproducible / containerizable.",
        ))
    return out


# --------------------------------------------------------------------------
# Public entry point
# --------------------------------------------------------------------------


def project_hygiene_findings(root: Path) -> list[dict]:
    """Return whole-project hygiene findings (governance, communication, docs,
    literature, context, per-step environment). Read-only, fail-open."""
    try:
        root = Path(root)
        if not root.is_dir():
            return []
        steps = _live_steps(root / "workspace")
        findings: list[dict] = []
        for check in (
            _check_governance,
            _check_communication,
            _check_docs,
            _check_literature,
            _check_step_context,
            _check_step_environment,
        ):
            try:
                findings.extend(check(root, steps))
            except Exception:
                continue
        return findings
    except Exception:
        return []
