"""Self-improving skill distillation.

Research OS already records Reflexion-style lessons after each step
(``research/lessons.py`` → ``workspace/.lessons/lessons.jsonl``) and
surfaces the top-K relevant ones on future turns. That loop is
*per-project* and *per-turn*: it never crystallizes a recurring pattern
into a durable, reusable procedure, and it never carries what the AI
learned about THIS researcher into the NEXT project.

This module closes both gaps:

  1. ``distill_skills(root)`` — cluster the project's lessons by tag,
     find patterns that recur at or above a frequency threshold, and
     crystallize each cluster into a reusable SKILL.md under
     ``workspace/.skills/``. A skill is a distilled "when you hit X,
     do Y (it worked) / avoid Z (it didn't)" card — procedural memory,
     not a one-off lesson.

  2. ``promote_skills(root)`` — lift the project-wide / methodology
     skills into the cross-project profile
     (``~/.config/research-os/profile.yaml`` → ``learned_skills``), so
     the SAME researcher starting a NEW project inherits what RO learned.
     This is the two-way learning surface: lessons flow up into the
     profile; ``research-os init`` reads the profile back down.

Design constraints (mirrors lessons.py):
  * Pure stdlib + yaml. No network, no model call — distillation is a
    deterministic aggregation the AI can trigger and then narrate.
  * Idempotent: re-running updates existing skill cards in place
    (keyed by a stable slug) instead of duplicating them.
  * Conservative: only patterns seen ``min_occurrences`` times become
    skills, so noise doesn't pollute the registry.
"""
from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("research_os.skills")

_DEFAULT_MIN_OCCURRENCES = 2
_SKILL_VERSION = "1.0"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _lessons_log(root: Path) -> Path:
    return root / "workspace" / ".lessons" / "lessons.jsonl"


def _skills_dir(root: Path) -> Path:
    p = root / "workspace" / ".skills"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _read_lessons(root: Path) -> list[dict[str, Any]]:
    p = _lessons_log(root)
    if not p.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:48] or "general"


def _cluster_lessons(
    lessons: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Group lessons by their primary tag (first tag), or 'general'.

    Tag-based clustering matches how lessons_consult ranks by tag overlap,
    so a distilled skill aligns with the retrieval key the AI already uses.
    """
    clusters: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for lesson in lessons:
        tags = lesson.get("tags") or []
        key = tags[0] if tags else "general"
        clusters[key].append(lesson)
    return clusters


def _render_skill_md(
    tag: str,
    cluster: list[dict[str, Any]],
) -> tuple[str, str]:
    """Render a SKILL.md (frontmatter + body) for a tag cluster.

    Returns (slug, markdown). The format is Hermes-compatible
    (YAML frontmatter: name / description / version / metadata) so the
    same file can be installed into a Hermes skills dir verbatim.
    """
    slug = _slug(tag)
    worked = [c.get("what_worked", "").strip() for c in cluster if c.get("what_worked", "").strip()]
    didnt = [c.get("what_didnt", "").strip() for c in cluster if c.get("what_didnt", "").strip()]
    recs = [c.get("recommendation", "").strip() for c in cluster if c.get("recommendation", "").strip()]
    n_fail = sum(1 for c in cluster if c.get("outcome") == "failure")
    # Dedupe while preserving order.
    def _uniq(items: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for it in items:
            k = it.lower()
            if k not in seen:
                seen.add(k)
                out.append(it)
        return out

    worked, didnt, recs = _uniq(worked), _uniq(didnt), _uniq(recs)
    desc = (
        f"Distilled from {len(cluster)} lesson(s) ({n_fail} failure) tagged "
        f"'{tag}'. When working on {tag}-related steps, apply these."
    )
    fm = [
        "---",
        f"name: ro-{slug}",
        f"description: {json.dumps(desc)}",
        f"version: {_SKILL_VERSION}",
        "author: research-os (auto-distilled)",
        "license: project-local",
        "metadata:",
        "  source: research-os/lessons",
        f"  tag: {json.dumps(tag)}",
        f"  lessons_count: {len(cluster)}",
        f"  failures: {n_fail}",
        f"  distilled_at: {json.dumps(_now())}",
        "  hermes:",
        f"    tags: {json.dumps([tag, 'research-os', 'distilled'])}",
        "---",
    ]
    body = [f"# Skill: {tag}", ""]
    body.append(
        f"Crystallized from {len(cluster)} recorded lesson(s) on '{tag}'. "
        "This is procedural memory — consult it before repeating the pattern.\n"
    )
    if recs:
        body.append("## Do this")
        body.extend(f"- {r}" for r in recs)
        body.append("")
    if worked:
        body.append("## What worked")
        body.extend(f"- {w}" for w in worked)
        body.append("")
    if didnt:
        body.append("## What to avoid")
        body.extend(f"- {d}" for d in didnt)
        body.append("")
    return slug, "\n".join(fm) + "\n\n" + "\n".join(body).rstrip() + "\n"


def distill_skills(
    root: Path,
    *,
    min_occurrences: int = _DEFAULT_MIN_OCCURRENCES,
) -> dict[str, Any]:
    """Crystallize recurring lessons into reusable SKILL.md cards.

    A tag cluster becomes a skill when it has >= ``min_occurrences``
    lessons. Idempotent: rewrites the slug's card each run.
    """
    lessons = _read_lessons(root)
    if not lessons:
        return {
            "status": "success",
            "skills_written": 0,
            "skills": [],
            "advice": "No lessons recorded yet — nothing to distill. "
            "Record lessons with tool_lessons(operation='record') as you work.",
        }
    clusters = _cluster_lessons(lessons)
    skills_dir = _skills_dir(root)
    written: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for tag, cluster in sorted(clusters.items()):
        if len(cluster) < min_occurrences:
            skipped.append({"tag": tag, "count": len(cluster)})
            continue
        slug, md = _render_skill_md(tag, cluster)
        path = skills_dir / f"{slug}.SKILL.md"
        path.write_text(md)
        written.append({
            "tag": tag,
            "slug": slug,
            "path": str(path.relative_to(root)),
            "lessons_count": len(cluster),
        })
    return {
        "status": "success",
        "skills_written": len(written),
        "skills": written,
        "skipped_below_threshold": skipped,
        "min_occurrences": min_occurrences,
        "skills_dir": str(skills_dir.relative_to(root)),
        "advice": (
            f"Distilled {len(written)} skill(s) into {skills_dir.name}/. "
            "Call tool_skills(operation='promote') to lift the durable ones "
            "into your cross-project profile so future projects inherit them."
            if written
            else "No tag cluster reached the threshold yet. Keep recording "
            f"lessons — patterns seen {min_occurrences}+ times become skills."
        ),
    }


def promote_skills(
    root: Path,
    *,
    min_occurrences: int = _DEFAULT_MIN_OCCURRENCES,
) -> dict[str, Any]:
    """Promote project-wide / methodology skills into the cross-project profile.

    Lessons scoped ``project`` or ``methodology`` are the ones worth
    carrying across projects (a ``step``-scoped lesson is usually too
    local). Their distilled cards are stored under ``learned_skills`` in
    ``~/.config/research-os/profile.yaml`` keyed by slug, so
    ``research-os init`` can surface them in the next project.
    """
    from research_os.tools.actions.state.config import (
        load_profile,
        save_profile,
    )

    lessons = [
        lesson for lesson in _read_lessons(root)
        if lesson.get("scope") in {"project", "methodology"}
    ]
    if not lessons:
        return {
            "status": "success",
            "promoted": 0,
            "advice": "No project/methodology-scoped lessons to promote. "
            "Cross-project learning lifts durable lessons (scope='project' "
            "or 'methodology'), not step-local ones.",
        }
    clusters = _cluster_lessons(lessons)
    profile = load_profile()
    learned = profile.get("learned_skills")
    if not isinstance(learned, dict):
        learned = {}
    promoted: list[dict[str, Any]] = []
    for tag, cluster in sorted(clusters.items()):
        if len(cluster) < min_occurrences:
            continue
        slug = _slug(tag)
        recs = sorted({
            c.get("recommendation", "").strip()
            for c in cluster
            if c.get("recommendation", "").strip()
        })
        entry = {
            "tag": tag,
            "recommendations": recs,
            "lessons_count": len(cluster),
            "updated_at": _now(),
        }
        # Merge: accumulate the max lessons_count seen, union recs.
        prior = learned.get(slug)
        if isinstance(prior, dict):
            prior_recs = prior.get("recommendations") or []
            entry["recommendations"] = sorted(set(recs) | set(prior_recs))
            entry["lessons_count"] = max(
                len(cluster), int(prior.get("lessons_count", 0) or 0)
            )
        learned[slug] = entry
        promoted.append({"slug": slug, "tag": tag, "lessons_count": len(cluster)})
    profile["learned_skills"] = learned
    save_res = save_profile(profile)
    return {
        "status": "success",
        "promoted": len(promoted),
        "skills": promoted,
        "profile_path": save_res.get("profile_path"),
        "advice": (
            f"Promoted {len(promoted)} skill(s) to your cross-project profile. "
            "New projects (research-os init) now inherit them."
            if promoted
            else "No project/methodology cluster reached the threshold yet."
        ),
    }


def list_skills(root: Path) -> dict[str, Any]:
    """List distilled project-local skills + promoted cross-project skills."""
    from research_os.tools.actions.state.config import load_profile

    local: list[dict[str, Any]] = []
    sdir = root / "workspace" / ".skills"
    if sdir.exists():
        for f in sorted(sdir.glob("*.SKILL.md")):
            local.append({"slug": f.stem.replace(".SKILL", ""),
                          "path": str(f.relative_to(root))})
    profile = load_profile()
    learned = profile.get("learned_skills")
    cross = []
    if isinstance(learned, dict):
        cross = [
            {"slug": k, "tag": v.get("tag"),
             "lessons_count": v.get("lessons_count")}
            for k, v in learned.items()
            if isinstance(v, dict)
        ]
    return {
        "status": "success",
        "project_skills": local,
        "cross_project_skills": cross,
        "n_project": len(local),
        "n_cross_project": len(cross),
    }


__all__ = ["distill_skills", "promote_skills", "list_skills"]
