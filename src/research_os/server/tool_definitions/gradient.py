"""Tool definitions for the beginner↔PI gradient domain.

Two on-ramp tools that meet a researcher wherever they walk in:

* ``tool_explain`` — a plain-language, grounded tutor for any concept /
  method. Returns a LAYERED reasoning scaffold (not a memorised answer).
* ``tool_deliverable_chooser`` — the "I'm done, what now?" recommender,
  gated on ``research_goal.output_types`` so it never pushes a deliverable
  the researcher didn't opt into.
"""
from __future__ import annotations

from typing import Any


GRADIENT_TOOL_DEFINITIONS: dict[str, dict[str, Any]] = {
    "tool_explain": {
        "short": "Plain-language tutor for any concept/method. Returns a grounded, layered explanation scaffold (not a memorised answer).",
        "compare_to": "tool_research_method (gathers sources + writes the report this tool tells you to ground against); methodology/methodological_consultation (the multi-step protocol this collapses into one call).",
        "description": (
            "On-demand tutor for ANY researcher level — a beginner meeting a "
            "method for the first time, or a PI onboarding a new one. Given a "
            "topic/method/concept (+ optional depth), returns a LAYERED "
            "explanation scaffold: intuition (plain words + analogy) → "
            "mechanics (inputs/transform/outputs + minimal example + "
            "parameter trade-offs) → assumptions & caveats (what must hold, "
            "how to check it, failure modes) → when NOT to use it (wrong "
            "data shapes + standard alternatives) → a grounded reading list. "
            "DOCTRINE: it does NOT answer from training memory. Each layer "
            "carries the QUESTIONS to answer plus an explicit instruction to "
            "GROUND them first via tool_research_method(query=<topic>) and/or "
            "tool_search, then fill the layers FROM those cited sources. The "
            "single-call sibling of the methodology/methodological_"
            "consultation protocol. depth presets are cumulative: "
            "intuition < mechanics < caveats < all."
        ),
        "category": "research",
        "inputSchema": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "The concept / method / term to explain (free text).",
                },
                "depth": {
                    "type": "string",
                    "enum": ["intuition", "mechanics", "caveats", "all"],
                    "description": (
                        "How deep to go (cumulative). 'intuition' = plain-words only; "
                        "'mechanics' adds how-it-works; 'caveats' adds assumptions; "
                        "'all' (default) adds when-NOT-to-use + reading list."
                    ),
                },
                "audience": {
                    "type": "string",
                    "description": (
                        "Optional audience hint (e.g. 'first-year grad student', "
                        "'PI new to causal inference'). Tunes the delivery note only."
                    ),
                },
            },
            "required": ["topic"],
        },
    },
    "tool_deliverable_chooser": {
        "short": "'I'm done, what now?' — recommends deliverable(s) to build, gated on research_goal.output_types (asks if none declared).",
        "compare_to": "sys_protocol_next (next protocol in the pipeline); tool_progress_digest (one-page status without a deliverable recommendation).",
        "description": (
            "The on-ramp for a researcher who has results but doesn't know "
            "what to produce. Inspects project readiness (steps with "
            "conclusions, figures, citations) AND reads "
            "researcher_config.yaml#research_goal.output_types, then "
            "recommends which deliverable(s) to build (paper / dashboard / "
            "poster / slides / report / lay_summary / grant / abstract / …) "
            "with a rationale and the synthesis protocol that builds each, "
            "plus whether it already exists on disk. GATING (anti-scope-"
            "creep): when output_types is declared, recommendations are "
            "LIMITED to exactly that set — it never pushes a deliverable the "
            "researcher didn't opt into. When output_types is EMPTY it does "
            "NOT assume a paper — it returns decision='ask_researcher' with a "
            "menu + the exact sys_config call to record the choice. Read-only "
            "(reads state + config, writes nothing)."
        ),
        "category": "interaction",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
}
