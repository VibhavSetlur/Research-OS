"""Story-mode generator + editor.

The dashboard now has two reading modes:

* **Explore** — today's structure: sidebar nav, filter chips, search,
  per-figure toggles, reactive tables. For a reviewer who wants to
  verify a specific claim.
* **Story** — single-column narrative scroll in a serif font, with
  the headline up top, figures inline as you'd see in a long-form
  Distill.pub article, and DISAGREES / EXTENDS callouts surfaced as
  block-quote sidebars so the project's engagement with the
  literature is visible. For a reader new to the project.

This module owns the *content* of story mode — assembling
``synthesis/dashboard_story.md`` from workspace state — plus a
quality bar audit (reading time, figure-in-first-1000-words, at-least-
one adversarial callout). The dashboard renderer (``dashboard_v2``)
owns rendering that markdown into HTML when ``#mode=story``.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _read(p: Path) -> str:
    try:
        return p.read_text() if p.exists() else ""
    except OSError:
        return ""


def _step_summary(step_dir: Path) -> dict[str, Any]:
    """Pull the plain-language summary + key figure + verdicts for one step."""
    out: dict[str, Any] = {"id": step_dir.name}
    yaml_path = step_dir / "step_summary.yaml"
    if yaml_path.exists():
        try:
            import yaml  # type: ignore
            out["summary_yaml"] = yaml.safe_load(yaml_path.read_text()) or {}
        except Exception:
            out["summary_yaml"] = {}
    conc = _read(step_dir / "conclusions.md")
    out["conclusions"] = conc
    # Pull "Plain-language summary" or "Findings" headline.
    m = re.search(r"##\s*Plain-language summary\s*\n(.+?)(?=^##|\Z)",
                  conc, flags=re.MULTILINE | re.DOTALL | re.IGNORECASE)
    out["plain"] = m.group(1).strip() if m else ""
    m2 = re.search(r"##\s*Findings\s*\n(.+?)(?=^##|\Z)",
                   conc, flags=re.MULTILINE | re.DOTALL | re.IGNORECASE)
    out["findings"] = m2.group(1).strip() if m2 else ""
    # Key figure: prefer one whose stem starts with step number.
    out["key_figure"] = None
    out["key_caption"] = ""
    figs = step_dir / "outputs" / "figures"
    if figs.is_dir():
        num = step_dir.name.split("_", 1)[0]
        cands = sorted(p for p in figs.iterdir()
                       if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".svg"})
        focal = next((p for p in cands if p.name.startswith(f"{num}_")),
                     cands[0] if cands else None)
        if focal:
            out["key_figure"] = focal
            sm = focal.with_suffix(".summary.md")
            if sm.exists():
                out["key_caption"] = sm.read_text().strip()
            else:
                cm = focal.with_suffix(".caption.md")
                if cm.exists():
                    out["key_caption"] = cm.read_text().strip()
    # Adversarial verdicts: pull non-AGREES lines from findings_vs_literature.md.
    fvl_path = step_dir / "findings_vs_literature.md"
    callouts: list[dict[str, str]] = []
    if fvl_path.exists():
        for line in fvl_path.read_text().splitlines():
            m = re.match(
                r"^[-*]\s*\*{0,2}\s*(DISAGREES|EXTENDS|MIXED|CONTRADICTS)\s*\*{0,2}\s*:?\s*(.+)$",
                line.strip(), flags=re.IGNORECASE,
            )
            if m:
                callouts.append({"verdict": m.group(1).upper(),
                                  "text": m.group(2).strip()[:400]})
    out["callouts"] = callouts
    return out


def dashboard_story_generate(root: Path) -> dict[str, Any]:
    """Build ``synthesis/dashboard_story.md`` from workspace state.

    Idempotent — re-running regenerates from the current state. The
    researcher (or an AI in researcher's voice) can edit the resulting
    markdown via :func:`dashboard_story_edit`; the next dashboard
    render picks up the edits.
    """
    try:
        from research_os.tools.actions.synthesis.dashboard import _load_spec
        spec = _load_spec(root)
        ws = root / "workspace"
        steps: list[dict[str, Any]] = []
        if ws.is_dir():
            for d in sorted(ws.iterdir()):
                if d.is_dir() and re.match(r"^\d{2,3}_", d.name):
                    steps.append(_step_summary(d))

        title = spec.get("title") or "Research story"
        abstract = (spec.get("abstract") or "").strip()
        abstract_path = root / "synthesis" / "abstract.md"
        if not abstract and abstract_path.exists():
            abstract = abstract_path.read_text().strip()
            # Strip the leading "# Abstract" header if present.
            abstract = re.sub(r"^#\s+abstract\s*\n", "", abstract,
                              flags=re.IGNORECASE).strip()

        lines: list[str] = [f"# {title}", ""]
        if abstract:
            lines.extend([abstract, ""])
        for s in steps:
            lines.append(f"## {s['id']}")
            lines.append("")
            if s["plain"]:
                lines.extend([s["plain"], ""])
            if s["key_figure"]:
                rel = s["key_figure"]
                try:
                    rel = rel.relative_to(root)
                except ValueError:
                    pass
                cap = s["key_caption"] or s["key_figure"].stem
                lines.append(f"![{cap}]({rel})")
                lines.append("")
            for co in s["callouts"]:
                lines.append(f"> **{co['verdict']}**: {co['text']}")
                lines.append("")
        # Findings rollup
        findings = spec.get("findings") or []
        if findings:
            lines.append("## Headline findings")
            lines.append("")
            for f in findings:
                t = f.get("title", "Finding")
                body = f.get("summary") or f.get("text") or ""
                lines.extend([f"### {t}", "", body, ""])
        # Citations footer
        cit = root / "workspace" / "citations.md"
        if cit.exists():
            lines.append("## References")
            lines.append("")
            lines.append("See workspace/citations.md for the full bibliography.")
            lines.append("")
        story_md = "\n".join(lines).rstrip() + "\n"
        from research_os.project_ops import ensure_lazy_dir
        synth = ensure_lazy_dir(root, "synthesis")
        out = synth / "dashboard_story.md"
        out.write_text(story_md)
        word_count = len(re.findall(r"\w+", story_md))
        return {
            "status": "success",
            "path": str(out.relative_to(root)),
            "word_count": word_count,
            "reading_minutes": max(1, round(word_count / 220)),
            "steps": len(steps),
            "callouts": sum(len(s["callouts"]) for s in steps),
            "figures": sum(1 for s in steps if s["key_figure"]),
        }
    except Exception as e:
        logger.exception("dashboard_story_generate failed")
        return {"status": "error", "message": str(e)}


def dashboard_story_edit(root: Path, edits: str | None = None,
                          mode: str = "patch") -> dict[str, Any]:
    """Open or patch ``synthesis/dashboard_story.md``.

    Args:
        edits: when given AND ``mode == "patch"``, the string is treated
            as a unified-diff-style patch (one or more
            ``<<<<replace>>>>old\\n----with----\\nnew\\n<<<<end>>>>``
            blocks). When ``mode == "overwrite"``, ``edits`` becomes
            the full new file content. When None, the function just
            returns the current file contents (or a freshly generated
            one if missing) so an AI / researcher can read and rewrite.

    Returns the (new) file contents under ``content`` plus stats. The
    intent is that ``tool_dashboard_story_edit`` gives the AI an
    editable surface; ``tool_dashboard_create`` then re-renders the
    HTML using the polished story.
    """
    try:
        path = root / "synthesis" / "dashboard_story.md"
        if not path.exists():
            gen = dashboard_story_generate(root)
            if gen.get("status") != "success":
                return gen
        current = path.read_text()
        if edits is None:
            return {"status": "success", "path": str(path.relative_to(root)),
                    "content": current,
                    "word_count": len(re.findall(r"\w+", current))}
        if mode == "overwrite":
            new = edits
        else:
            new = _apply_patch_blocks(current, edits)
        path.write_text(new)
        return {
            "status": "success",
            "path": str(path.relative_to(root)),
            "content": new,
            "word_count": len(re.findall(r"\w+", new)),
            "delta_chars": len(new) - len(current),
        }
    except Exception as e:
        logger.exception("dashboard_story_edit failed")
        return {"status": "error", "message": str(e)}


_PATCH_RE = re.compile(
    r"<<<<replace>>>>\n(.*?)\n----with----\n(.*?)\n<<<<end>>>>",
    re.DOTALL,
)


def _apply_patch_blocks(text: str, patch: str) -> str:
    """Apply zero or more ``<<<<replace>>>>...<<<<end>>>>`` blocks.

    Each block names the exact ``old`` substring (must appear once)
    and its replacement ``new``. Missing/duplicate matches raise so
    the caller knows the patch didn't apply cleanly.
    """
    out = text
    for m in _PATCH_RE.finditer(patch):
        old, new = m.group(1), m.group(2)
        n = out.count(old)
        if n != 1:
            raise ValueError(
                f"patch block matched {n} times (need 1); "
                f"first 80 chars of old: {old[:80]!r}"
            )
        out = out.replace(old, new, 1)
    return out


def dashboard_story_quality_bar(root: Path) -> dict[str, Any]:
    """Check the story-mode quality bar.

    Three rules:
      * reading time between 5 and 20 minutes (too short = trivial,
        too long = won't finish)
      * at least one figure appears in the first 1000 words
      * at least one adversarial-grounding callout (DISAGREES /
        EXTENDS / CONTRADICTS) is present

    Failures → WARNINGs (not BLOCKERs); story mode is optional.
    """
    try:
        path = root / "synthesis" / "dashboard_story.md"
        if not path.exists():
            return {"status": "skipped", "reason": "dashboard_story.md missing"}
        text = path.read_text()
        words = re.findall(r"\w+", text)
        rt = max(1, round(len(words) / 220))
        warnings: list[str] = []
        if rt < 5:
            warnings.append(f"story is short ({rt} min read); aim for 5-20")
        if rt > 20:
            warnings.append(f"story is long ({rt} min read); aim for 5-20")
        fig_match = re.search(r"!\[[^\]]*\]\([^)]+\)", text)
        first_fig_pos = fig_match.start() if fig_match else -1
        first_1000_chars_end = sum(len(w) + 1 for w in words[:1000])
        if not fig_match or first_fig_pos > first_1000_chars_end:
            warnings.append("no figure in the first 1000 words (engagement risk)")
        adversarial = re.search(r"\*\*(DISAGREES|EXTENDS|CONTRADICTS|MIXED)\*\*",
                                 text, flags=re.IGNORECASE)
        if not adversarial:
            warnings.append(
                "no adversarial-grounding callout (DISAGREES / EXTENDS / "
                "CONTRADICTS / MIXED) — story risks reading as self-confirming"
            )
        return {
            "status": "success",
            "reading_minutes": rt,
            "word_count": len(words),
            "warnings": warnings,
            "has_adversarial_callout": bool(adversarial),
            "has_figure": bool(fig_match),
        }
    except Exception as e:
        logger.exception("dashboard_story_quality_bar failed")
        return {"status": "error", "message": str(e)}


__all__ = [
    "dashboard_story_generate",
    "dashboard_story_edit",
    "dashboard_story_quality_bar",
]
