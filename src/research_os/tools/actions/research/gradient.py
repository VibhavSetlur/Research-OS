"""Beginner↔PI gradient tools — the on-ramps that meet a researcher at
whatever level they walk in at.

Two public functions back the gradient MCP tools:

* ``explain_scaffold`` — a plain-language tutor for any topic / method /
  concept. Returns a LAYERED reasoning scaffold (intuition → mechanics →
  assumptions/caveats → when NOT to use it → reading list) WITHOUT
  answering from training memory. Doctrine-compliant: it hands back the
  questions to answer and tells the AI to GROUND the answers via
  ``tool_research_method`` / ``tool_search`` first. Serves a beginner
  learning a method for the first time AND a PI onboarding a new one.

* ``deliverable_chooser`` — the "I'm done, what now?" on-ramp. Inspects
  what the project has ready (steps with conclusions, figures, citations)
  AND reads ``researcher_config.yaml#research_goal.output_types``, then
  recommends which deliverable(s) to build with rationale. CRUCIALLY it
  respects output_types gating: it never pushes a deliverable the
  researcher didn't opt into, and when output_types is empty it ASKS
  rather than assuming a paper.

Both are read-mostly. ``explain_scaffold`` has no side effects.
``deliverable_chooser`` only reads state + config (no writes), so it is
safe to call at any point.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("research_os.tools.research.gradient")


# ---------------------------------------------------------------------------
# tool_explain — layered, grounded tutor scaffold
# ---------------------------------------------------------------------------

# The five layers, beginner → expert. Each layer carries the QUESTIONS the
# AI must answer (grounded), never the answers themselves — that is the
# doctrine line: scaffolds for reasoning, not canned facts from memory.
_DEPTH_LAYERS: dict[str, dict[str, Any]] = {
    "intuition": {
        "label": "Intuition — what it is, in plain words",
        "audience": "a curious beginner with no background",
        "questions": [
            "In one sentence a non-expert could repeat, what problem does this solve?",
            "What is the everyday-language analogy (and where does the analogy break)?",
            "What does a correct result let you say that you couldn't say before?",
        ],
    },
    "mechanics": {
        "label": "How it works — the mechanism",
        "audience": "someone who will actually run it",
        "questions": [
            "What are the inputs, the transformation, and the outputs?",
            "What is the minimal worked example (smallest case that shows the mechanism)?",
            "What are the key parameters / choices, and what does each one trade off?",
        ],
    },
    "caveats": {
        "label": "Assumptions & caveats — what has to be true",
        "audience": "a careful analyst",
        "questions": [
            "What assumptions must hold for the result to be valid?",
            "How do you CHECK each assumption against this project's data?",
            "What are the common failure modes / ways people misuse it?",
            "How is it commonly mis-reported or over-interpreted?",
        ],
    },
    "when_not": {
        "label": "When NOT to use it — and what to use instead",
        "audience": "a researcher deciding between methods",
        "questions": [
            "Under what data shapes / questions is this the WRONG tool?",
            "What are the 1-3 standard alternatives, and when does each win?",
            "What is the cheapest sanity check that would tell you you've picked wrong?",
        ],
    },
    "reading": {
        "label": "Grounded reading list — sources to cite",
        "audience": "anyone who needs to defend the choice",
        "questions": [
            "Which 3-6 sources (canonical + recent) actually ground this explanation?",
            "Which source does a beginner read first, and which does a referee expect to see?",
            "Do these sources AGREE, or is there live disagreement to flag?",
        ],
    },
}

# Canonical depth presets the caller can pass for `depth`.
_DEPTH_PRESETS: dict[str, list[str]] = {
    "intuition": ["intuition"],
    "mechanics": ["intuition", "mechanics"],
    "caveats": ["intuition", "mechanics", "caveats"],
    "all": ["intuition", "mechanics", "caveats", "when_not", "reading"],
}


def _normalise_depth(depth: str | None) -> str:
    if not isinstance(depth, str):
        return "all"
    d = depth.strip().lower().replace("-", "_").replace(" ", "_")
    return d if d in _DEPTH_PRESETS else "all"


def explain_scaffold(
    topic: str,
    *,
    depth: str | None = "all",
    audience: str | None = None,
) -> dict[str, Any]:
    """Return a layered, GROUNDED explanation scaffold for ``topic``.

    This is the on-demand sibling of the ``methodology/
    methodological_consultation`` protocol, collapsed into a single tool
    call. It does NOT explain the topic from training memory — that would
    violate the grounding doctrine and risk teaching a confident-but-wrong
    fact. Instead it returns:

      * the ordered layers (intuition → … → reading list) appropriate to
        the requested ``depth``, each with the questions the AI must
        answer;
      * an explicit grounding instruction naming ``tool_research_method``
        and ``tool_search`` as the way to fill those answers;
      * a short "how to deliver this" note so the AI presents it at the
        right altitude for the audience.

    Args:
      topic:    The concept / method / term to explain (free text).
      depth:    intuition | mechanics | caveats | all (default 'all').
                Presets are cumulative: 'mechanics' includes 'intuition',
                'caveats' includes both, 'all' adds when-not + reading.
      audience: Optional free-text audience hint (e.g. 'first-year grad
                student', 'PI new to causal inference'). Tunes only the
                delivery note; the layers are level-agnostic by design.

    Never raises — bad input degrades to depth='all'.
    """
    topic_clean = (topic or "").strip()
    if not topic_clean:
        return {
            "status": "error",
            "message": (
                "tool_explain needs a topic/method/concept to explain. "
                "Pass topic='<thing to explain>'."
            ),
        }

    preset = _normalise_depth(depth)
    layer_keys = _DEPTH_PRESETS[preset]
    layers = [
        {
            "layer": key,
            "label": _DEPTH_LAYERS[key]["label"],
            "default_audience": _DEPTH_LAYERS[key]["audience"],
            "questions_to_answer": list(_DEPTH_LAYERS[key]["questions"]),
        }
        for key in layer_keys
    ]

    grounding_instruction = (
        "DO NOT answer these questions from memory. First GROUND them: call "
        f"tool_research_method(query='{topic_clean}') to gather 5-10 sources "
        "and write a method report, and/or tool_search for targeted facts. "
        "Then fill each layer's questions FROM those sources, citing them. "
        "If grounding turns up disagreement, present the disagreement rather "
        "than papering over it."
    )

    delivery_note = (
        "Present the layers IN ORDER, stopping at the depth the researcher "
        "actually needs — a beginner may only want 'intuition'; a referee "
        "expects 'caveats' + 'when_not' + the reading list. Lead with the "
        "plain-language layer no matter who is asking."
    )
    if audience and audience.strip():
        delivery_note = (
            f"Audience: {audience.strip()}. " + delivery_note
        )

    return {
        "status": "success",
        "topic": topic_clean,
        "depth": preset,
        "layers": layers,
        "layer_count": len(layers),
        "grounding_instruction": grounding_instruction,
        "delivery_note": delivery_note,
        "related_protocol": "methodology/methodological_consultation",
        "advice": (
            "This is a reasoning scaffold, not the answer. Ground first "
            "(tool_research_method / tool_search), then fill the layers."
        ),
    }


# ---------------------------------------------------------------------------
# tool_deliverable_chooser — output_types-gated "what now?" recommender
# ---------------------------------------------------------------------------

# Human-readable rationale for each deliverable kind, keyed by the same
# normalised vocabulary SYNTHESIS_OUTPUT_TYPE_MAP uses. Kept here (not in
# protocol.py) so this tool owns its own copy of the UX prose.
_DELIVERABLE_BLURB: dict[str, str] = {
    "paper": "A full manuscript — the archival, peer-review-ready writeup.",
    "dashboard": "An interactive HTML dashboard — best for exploring the full evidence base.",
    "poster": "A conference poster — one-glance visual summary for a session.",
    "slides": "A slide deck — for a talk or lab meeting.",
    "report": "A structured report — internal / stakeholder readout, lighter than a paper.",
    "lay_summary": "A plain-language summary — for non-specialist audiences.",
    "grant": "A grant-style writeup — framed around aims + significance.",
    "abstract": "A standalone abstract — submission or quick share.",
    "essay": "A long-form argumentative essay (humanities-shaped).",
    "handout": "A printable one/two-page handout.",
}


def _count_artifacts(root: Path) -> dict[str, int]:
    """Tally what's actually on disk — steps w/ conclusions, figures, citations.

    Reuses the same conventions as ``progress_digest`` so the two tools
    agree on what 'ready' means. Best-effort; never raises.
    """
    counts = {
        "steps_total": 0,
        "steps_with_conclusions": 0,
        "figures": 0,
        "tables": 0,
        "citations": 0,
    }
    try:
        from research_os.tools.actions.state.path import list_paths

        paths = (list_paths(root).get("paths", []) or [])
        counts["steps_total"] = len(paths)
        for p in paths:
            ed = Path(
                p.get("experiment_dir")
                or (root / "workspace" / p.get("path_id", ""))
            )
            conc = ed / "conclusions.md"
            try:
                if conc.exists() and conc.stat().st_size > 50:
                    counts["steps_with_conclusions"] += 1
            except OSError:
                # Unreadable path → just don't count it.
                pass
            fig_dir = ed / "outputs" / "figures"
            if fig_dir.exists():
                try:
                    counts["figures"] += sum(
                        1 for f in fig_dir.iterdir()
                        if f.suffix.lower() in
                        {".png", ".jpg", ".jpeg", ".pdf", ".svg", ".tiff"}
                    )
                except OSError:
                    # Unreadable figures dir → leave the count as-is.
                    pass
            tab_dir = ed / "outputs" / "tables"
            if tab_dir.exists():
                try:
                    counts["tables"] += sum(
                        1 for f in tab_dir.iterdir()
                        if f.suffix.lower() in {".csv", ".tsv", ".md", ".html"}
                    )
                except OSError:
                    # Unreadable tables dir → leave the count as-is.
                    pass
    except Exception:
        logger.debug("deliverable_chooser: path walk failed", exc_info=True)

    citations_md = root / "workspace" / "citations.md"
    if citations_md.exists():
        try:
            counts["citations"] = sum(
                1 for ln in citations_md.read_text().splitlines()
                if ln.strip().startswith(("- ", "* ", "["))
            )
        except OSError:
            # Unreadable citations file → leave citations at 0.
            pass
    return counts


def _readiness(counts: dict[str, int]) -> dict[str, Any]:
    """Turn raw counts into a coarse readiness verdict + the gaps to close."""
    gaps: list[str] = []
    if counts["steps_with_conclusions"] == 0:
        gaps.append(
            "No step has a conclusions.md yet — finish at least one analysis "
            "step before building any deliverable."
        )
    if counts["figures"] == 0:
        gaps.append(
            "No figures produced yet — most deliverables read better with at "
            "least one figure."
        )
    if counts["citations"] == 0:
        gaps.append(
            "workspace/citations.md is empty — a paper/report will need "
            "citations (run literature_search)."
        )
    ready = counts["steps_with_conclusions"] >= 1
    return {
        "ready_to_synthesize": ready,
        "gaps": gaps,
    }


def deliverable_chooser(root: Path) -> dict[str, Any]:
    """Recommend which deliverable(s) to build — gated on output_types.

    The "I'm done, what now?" on-ramp. Inspects project readiness (steps
    with conclusions, figures, citations) and reads the researcher's
    declared ``research_goal.output_types``. Then:

      * If output_types is NON-EMPTY: recommends exactly those deliverables
        (in declared order), each with a one-line rationale + the synthesis
        protocol that builds it + whether it's already done on disk. It
        NEVER suggests a deliverable outside the declared set — that is the
        anti-scope-creep gate.

      * If output_types is EMPTY: it does NOT assume a paper. It returns
        ``decision='ask_researcher'`` with a menu of options + the exact
        ``sys_config`` call to record the choice, so the AI asks instead of
        guessing.

    Read-only — touches state + config, writes nothing. Never raises.
    """
    try:
        from research_os.tools.actions.protocol import (
            SYNTHESIS_OUTPUT_TYPE_MAP,
            _declared_output_types,
        )
    except Exception as e:  # pragma: no cover — import guard
        return {"status": "error", "message": f"deliverable_chooser import failed: {e}"}

    root = Path(root)
    counts = _count_artifacts(root)
    readiness = _readiness(counts)
    declared = _declared_output_types(root)

    # ── output_types EMPTY → ask, never assume (anti-scope-creep) ────────
    if not declared:
        options = [
            {
                "kind": kind,
                "what_it_is": _DELIVERABLE_BLURB.get(kind, ""),
            }
            for kind in SYNTHESIS_OUTPUT_TYPE_MAP
        ]
        return {
            "status": "success",
            "decision": "ask_researcher",
            "readiness": readiness,
            "artifact_counts": counts,
            "declared_output_types": [],
            "options": options,
            "ask_user": (
                "No deliverable is declared in researcher_config.yaml "
                "(research_goal.output_types is empty). What would you like "
                "me to produce? Options include: "
                + ", ".join(SYNTHESIS_OUTPUT_TYPE_MAP) + "."
            ),
            "record_choice_with": (
                "sys_config(operation='set', "
                "key='research_goal.output_types', value='<paper|dashboard|...>')"
            ),
            "advice": (
                "Do NOT pick a deliverable for the researcher. output_types "
                "is empty, which means no preference was recorded — ask, then "
                "persist the answer to the config before synthesising."
            ),
        }

    # ── output_types DECLARED → recommend exactly those, in order ────────
    recommendations: list[dict[str, Any]] = []
    for kind in declared:
        entry = SYNTHESIS_OUTPUT_TYPE_MAP.get(kind)
        if not entry:
            # Declared an unknown string — surface it without inventing a
            # protocol for it.
            recommendations.append({
                "kind": kind,
                "what_it_is": _DELIVERABLE_BLURB.get(kind, "(unrecognised deliverable type)"),
                "protocol": None,
                "already_done": False,
                "rationale": (
                    f"'{kind}' is declared but maps to no known synthesis "
                    "protocol — confirm the spelling with the researcher."
                ),
            })
            continue
        protocol_name, done_predicate = entry
        try:
            done = bool(done_predicate(root))
        except Exception:
            done = False
        recommendations.append({
            "kind": kind,
            "what_it_is": _DELIVERABLE_BLURB.get(kind, ""),
            "protocol": protocol_name,
            "already_done": done,
            "rationale": (
                "Declared in research_goal.output_types. "
                + ("Already present on disk — refresh only if inputs changed."
                   if done else
                   "Not built yet — this is a recommended next deliverable.")
            ),
        })

    pending = [r for r in recommendations if r.get("protocol") and not r["already_done"]]
    return {
        "status": "success",
        "decision": "recommend",
        "readiness": readiness,
        "artifact_counts": counts,
        "declared_output_types": declared,
        "recommendations": recommendations,
        "pending_count": len(pending),
        "next_deliverable": (pending[0]["kind"] if pending else None),
        "scope_note": (
            "Recommendations are LIMITED to the researcher's declared "
            "output_types — no other deliverable is suggested. Building "
            "something outside this set is scope creep; ask + update the "
            "config first if the researcher wants more."
        ),
        "advice": (
            ("Project isn't ready to synthesise yet: " + "; ".join(readiness["gaps"]))
            if not readiness["ready_to_synthesize"]
            else (
                f"Build the pending deliverable(s) via their synthesis "
                f"protocol(s). Next: {pending[0]['protocol']}."
                if pending else
                "All declared deliverables are already present — nothing to build."
            )
        ),
    }
