"""Tool definitions for the synthesis domain.

The AI authors synthesis outputs directly (paper.typ, slides.typ,
poster.typ, essay.typ, dashboard.html). These tools support that
workflow — they plan, validate, scaffold, and compile, but never
generate the prose / layout themselves.
"""
from __future__ import annotations

from typing import Any


SYNTHESIS_TOOL_DEFINITIONS: dict[str, dict[str, Any]] = {
    "tool_figure_palette": {
        "short": "Return a colour-blind-safe palette (Okabe-Ito / viridis / PuOr / accent).",
        "description": "Returns a palette suitable for paper figures: qualitative (Okabe-Ito, 8 hues, CVD-safe), sequential (viridis, monotonic luminance), diverging (PuOr, perceptually balanced), accent (the 5 cohesive RO_PALETTE colours that apply_research_os_style applies — so a hand-coloured figure matches an auto-styled one), or diverging_emphasis (the oxblood/forest delta pair). Call when authoring a plotting script. Does NOT modify any file.",
        "category": "viz",
        "inputSchema": {
            "type": "object",
            "properties": {
                "kind": {
                    "type": "string",
                    "enum": ["qualitative", "sequential", "diverging", "accent", "diverging_emphasis"],
                    "description": "qualitative (default) | sequential | diverging | accent | diverging_emphasis.",
                },
                "n": {
                    "type": "number",
                    "description": "Number of colours (default 8).",
                },
            },
        },
    },
    "tool_synthesize_plan": {
        "short": "Inspect workspace + report what's ready to draft (read-only).",
        "description": "Inspect available sources (methods.md, conclusions per step, citations) and return the recommended section ordering. Call BEFORE authoring synthesis/paper.typ so you know what's in the workspace. Read-only; writes nothing.",
        "category": "synthesis",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "tool_synthesis_preview": {
        "short": "Predict word/page/figure/citation counts for a synthesis target — without drafting.",
        "description": "Cheap deterministic dry-run (~1 sec). Reads workspace/<step>/conclusions.md + step_summary.yaml + findings_vs_literature.md + workspace/citations.md but does NOT call the AI to draft prose. Returns predicted_word_count_per_section, predicted_total_word_count, predicted_page_count or slide_count, predicted_figures_embedded, predicted_citations, predicted_steps_drawn_from, detected_gaps, estimated_render_time_seconds. mode='diff' compares against the existing deliverable on disk.",
        "category": "synthesis",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "paper | dashboard | poster | slides | grant | report. Default 'paper'."},
                "venue": {"type": "string"},
                "mode": {"type": "string", "description": "'fresh' (default) or 'diff' against existing deliverable."},
            },
        },
    },
    "tool_synthesis_scaffold": {
        "short": "Write a tiny skeleton .typ/.html for the AI to author into. Gates on researcher_config.yaml output_types.",
        "description": "Writes a ≤80-line skeleton with section headers + `// AI: author this` markers. Refuses to overwrite an existing file unless overwrite=true. Kinds: paper, slides, poster, essay, dashboard, grant, handout. After scaffolding, AUTHOR the content directly (follow the matching synthesis protocol), then tool_synthesis_check, then tool_typst_compile (or open the HTML for dashboards). Output-types intent gate: if the researcher has declared `research_goal.output_types` in `inputs/researcher_config.yaml` and the requested `kind` is NOT in that list, the call returns status='ask' instead of writing — surface the returned message to the researcher and re-call with `confirmed=true` only if they actually want this deliverable. Prevents auto-creating papers / dashboards / posters the user never asked for.",
        "category": "synthesis",
        "inputSchema": {
            "type": "object",
            "properties": {
                "kind": {
                    "type": "string",
                    "enum": ["paper", "slides", "poster", "handout", "grant", "essay", "dashboard"],
                    "description": "Which artefact to scaffold. Default 'paper'.",
                },
                "overwrite": {
                    "type": "boolean",
                    "description": "Replace an existing file. Default false (idempotent). Implies confirmed=true.",
                },
                "confirmed": {
                    "type": "boolean",
                    "description": "Bypass the output_types intent gate after confirming with the researcher. Default false. Use ONLY after the researcher has explicitly OK'd this kind.",
                },
            },
        },
    },
    "tool_synthesis_check": {
        "short": "Quality-check an AI-authored synthesis file (paper/slides/poster/dashboard/essay).",
        "description": "Audit a synthesis file against the standards for its artefact type. Auto-detects file type from path. Modes: 'all' (default), 'substantiveness' (per-section content depth), 'structure' (section presence/ordering/references), 'accessibility' (HTML alt-text + semantic), 'cliches' (banned-phrase detection). For paper.typ / essay.typ: checks abstract (≥1 number + method + conclusion verb), introduction (≥3 citations + 'in this study, we' pivot), methods (every workspace step's primary method named; <50% BLOCKS), results (≥1 statistic per finding; focal figures referenced), discussion (limitations + future-work + verdict coverage), references (every cited key in bibliography). For slides.typ: slide count, speaker notes present, ≤12 citations, no path leaks. For poster.typ: section count ≥3, ≤8 citations. For dashboard.html: offline (no http: scripts), alt-text on every <img>, semantic <section id=...>, no TODO/Lorem ipsum placeholders, no path leaks. Returns blockers (errors) + warnings.",
        "category": "audit",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file": {
                    "type": "string",
                    "description": "Path to synthesis file (default: first existing of synthesis/{paper,slides,poster,essay}.typ or dashboard.html).",
                },
                "mode": {
                    "type": "string",
                    "enum": ["all", "substantiveness", "structure", "accessibility", "cliches"],
                    "description": "Which audit to run. Default 'all' (every check appropriate to the file type).",
                },
            },
        },
    },
    "tool_typst_compile": {
        "short": "Compile a Typst source (.typ) to PDF. Use after authoring synthesis/<kind>.typ.",
        "description": "Generic Typst compiler. Takes a .typ source the AI has authored (paper.typ, slides.typ, poster.typ, essay.typ, cover_letter.typ, response.typ) and renders it to PDF via the `typst` CLI. Resolves citations against a Hayagriva biblio.yml (auto-generated from workspace/citations.md if missing). Returns pdf_path, page_count, citation_count, typst_warnings, typst_errors (with line numbers on failure so the AI can iterate on the source).",
        "category": "synthesis",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": "Path to .typ source (relative to project root or absolute). Default: first existing of synthesis/{paper,slides,poster,essay}.typ.",
                },
                "output": {
                    "type": "string",
                    "description": "Path to output PDF (default: source with .pdf extension).",
                },
                "biblio": {
                    "type": "string",
                    "description": "Path to Hayagriva biblio.yml (default: synthesis/biblio.yml, auto-generated from workspace/citations.md if absent).",
                },
            },
        },
    },
    "tool_latex_compile": {
        "short": "Compile synthesis/paper.tex → PDF (pdflatex + bibtex). Use when LaTeX submission is required.",
        "description": "Compile synthesis/paper.tex to PDF (pdflatex + bibtex). Use only for journals that require .tex submission (most journals accept Typst-generated PDFs — call tool_typst_compile instead).",
        "category": "synthesis",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "tool_writing_discussion_from_verdicts": {
        "short": "Append one Discussion paragraph per non-AGREES verdict in any step's findings_vs_literature.md.",
        "description": "Reads every workspace/<step>/literature/findings_vs_literature.md, finds DISAGREES + EXTENDS verdicts that carry a Discussion implication block, and appends one paragraph per verdict to synthesis/discussion.md under HTML-comment-delimited markers (idempotent — re-runs replace the block; hand-edits outside the markers are preserved). Closes the audit gap where verdicts never reached the Discussion. The AI is expected to fold the appended paragraphs into the actual Discussion section of paper.typ.",
        "category": "synthesis",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "tool_discussion_coverage_audit": {
        "short": "BLOCK gate: every non-AGREES literature verdict must have a Discussion paragraph.",
        "description": "Companion to tool_writing_discussion_from_verdicts. Walks every step's findings_vs_literature.md and verifies synthesis/discussion.md (or paper.typ Discussion section) mentions each DISAGREES/EXTENDS claim (>=50% key-word overlap). Returns status='error' + a blocker list if any verdict is uncovered. Acts as a hard BLOCK unless override_discussion_coverage=true (logged to override_log.md with override_rationale).",
        "category": "audit",
        "inputSchema": {
            "type": "object",
            "properties": {
                "override_discussion_coverage": {
                    "type": "boolean",
                    "description": "Set true to bypass the BLOCK when verdicts are intentionally not in the Discussion (e.g. the section is being rewritten). Requires override_rationale under interaction.quality_gate_policy=enforce. Logged to override_log.md.",
                },
                "override_rationale": {
                    "type": "string",
                    "description": "Short justification for the override. Required when quality_gate_policy=enforce.",
                },
            },
        },
    },
    "tool_reviewer": {
        "short": "Reviewer-response tool. operation=response|rebuttal|compile.",
        "description": "Reviewer-response dispatcher. operation='response' produces synthesis/response_to_reviewers.md with one heading per reviewer comment (Mn, mn), pre-formatted for line-referenced rebuttal text. operation='rebuttal' writes a single rebuttal scaffold under workspace/reviewer/rebuttals/<slug>.md given a verbatim reviewer comment + the persona id (+ optional evidence_paths); the scaffold surfaces methods record, per-step findings_vs_literature.md, outputs (figures/tables/reports), and paper sections so the AI can ground the response. operation='compile' concatenates every rebuttal markdown under workspace/reviewer/rebuttals/ (grouped by persona) into workspace/reviewer/response_to_reviewers.md; best-effort PDF compile via the bundled Typst generic_two_column template (status='skipped' for the PDF leg when typst is not on PATH; the markdown is always produced). Returns rebuttal_count, personas_addressed, response_md path, response_pdf path (or null). Use synthesis/reviewer_response protocol for the full multi-turn flow on a real external review.",
        "category": "synthesis",
        "inputSchema": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["response", "rebuttal", "compile"],
                    "description": "Which reviewer sub-operation to invoke.",
                },
                "review_path": {
                    "type": "string",
                    "description": "operation='response' — optional path to the red-team review markdown to pair with the response template.",
                },
                "comment": {
                    "type": "string",
                    "description": "operation='rebuttal' — REQUIRED. Verbatim reviewer comment.",
                },
                "persona": {
                    "type": "string",
                    "description": "operation='rebuttal' — REQUIRED. Persona id that raised the comment (e.g. statistician, novelty_critic).",
                },
                "evidence_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "operation='rebuttal' — optional workspace-relative paths the rebuttal will cite.",
                },
            },
            "required": ["operation"],
        },
    },
}
