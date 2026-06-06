"""Tool definitions for the synthesis domain.

Extracted from server/_core.py as part of the Phase-10 server.py modular split.
"""
from __future__ import annotations

from typing import Any


SYNTHESIS_TOOL_DEFINITIONS: dict[str, dict[str, Any]] = {
    "tool_figure": {
        "short": "Unified figure helper. operation=palette|caption_synthesise|interactive_autogen|paper_autoembed.",
        "description": "Unified figure dispatcher. operation='palette' returns colour-blind-safe palettes — Okabe-Ito (qualitative), viridis (sequential), PuOr (diverging), or the dashboard primary/gold/green/red accent set. operation='caption_synthesise' generates a 2-3 sentence plain-language description (<name>.summary.md sidecar) next to a figure for non-expert / accessibility audiences (W3C two-part guidance); reads the figure's existing <name>.caption.md + the step's conclusions.md Findings section; idempotent (pass overwrite=true to replace). operation='interactive_autogen' writes an interactive HTML companion (Vega-Lite for scatter/heatmap/time-series, vis-network for graphml) next to a static figure; offline-capable (inlines vendored Vega/vis-network bundles); tagged <meta name='ro-auto-generated' content='true'>; idempotent (returns status='exists' when companion is already there). operation='paper_autoembed' walks every step's outputs/figures/ where step_summary.yaml.figures_for_paper is true, reads each figure's <stem>.caption.md frontmatter (section_hint, figure_priority, alt_text, ...), and inserts markdown image blocks into synthesis/paper.md; three modes (append_to_section | explicit_map | reorder); idempotent — stems already present are never re-inserted; calls rewrite_figure_xrefs automatically unless override_xref_rewrite is set. Every legacy tool_figure_palette / tool_figure_caption_synthesise / tool_figure_interactive_autogen / tool_paper_figures_autoembed name aliases to this entry point with operation injected via _ALIAS_PARAM_INJECTION so callers using the older per-operation names keep working unchanged.",
        "category": "viz",
        "inputSchema": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["palette", "caption_synthesise", "interactive_autogen", "paper_autoembed"],
                    "description": "Which figure sub-operation to invoke.",
                },
                # operation='palette' kwargs
                "kind": {
                    "type": "string",
                    "description": "operation='palette' — qualitative (default) | sequential | diverging | accent.",
                },
                "n": {
                    "type": "number",
                    "description": "operation='palette' — Number of colours (default 8).",
                },
                # operation='caption_synthesise' / 'interactive_autogen' kwargs
                "figure_path": {
                    "type": "string",
                    "description": "operation='caption_synthesise' / 'interactive_autogen' — Path relative to project root (e.g. workspace/03_baseline/outputs/figures/03_calibration.png). REQUIRED for both.",
                },
                "technical_caption": {
                    "type": "string",
                    "description": "operation='caption_synthesise' — Optional technical caption text to anchor the plain-language summary.",
                },
                "findings_context": {
                    "type": "string",
                    "description": "operation='caption_synthesise' — Optional findings context from conclusions.md.",
                },
                "overwrite": {
                    "type": "boolean",
                    "description": "operation='caption_synthesise' — Overwrite an existing summary sidecar (default false).",
                },
                # operation='paper_autoembed' kwargs
                "mode": {
                    "type": "string",
                    "description": "operation='paper_autoembed' — Placement mode: append_to_section (default) | explicit_map | reorder.",
                },
                "section_map": {
                    "type": "object",
                    "description": "operation='paper_autoembed' — Only used when mode='explicit_map'. {figure_stem: section_name}. Overrides each figure's section_hint frontmatter.",
                    "additionalProperties": {"type": "string"},
                },
                "override_xref_rewrite": {
                    "type": "boolean",
                    "description": "operation='paper_autoembed' — When true, skip the figure-xref rewrite pass even if researcher_config.synthesis.figure_xref_rewrite=true. Use when paper.md has pre-formatted Pandoc cross-refs the AI must not touch.",
                },
            },
            "required": ["operation"],
        },
    },
    "tool_synthesize_plan": {
        "description": "Inspect available sources (methods.md, conclusions per step, citations) and return the recommended section ordering. Call BEFORE tool_synthesize.",
        "category": "synthesis",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "tool_synthesize": {
        "description": "Compile workspace findings into a publishable output. Without `section`, builds the full paper/poster/etc with numbered figures + tables + verified citations. With `section`, builds one section at a time (abstract | introduction | methods | results | discussion | conclusion | references). `output_type` drives the citation cap and section structure. Quality gate: refuses to build a full document if tool_audit_quality_full reports BLOCKERS. Phase-4c BLOCK-finding gate: ALSO refuses to compile when any unresolved BLOCK finding sits in workspace/logs/.audit_findings.jsonl (latest-snapshot semantics — a BLOCK from an earlier audit run that the latest rerun no longer reproduces is treated as resolved). The researcher (NOT the AI) can authorise a partial / WIP deliverable by passing override_completeness_gate=true (master quality gate bypass) or override_unresolved_blocks=true (BLOCK-finding ledger bypass) with a one-line override_rationale — both are logged to workspace/logs/override_log.md for the audit trail.",
        "category": "synthesis",
        "inputSchema": {
            "type": "object",
            "properties": {
                "output_format": {
                    "type": "string",
                    "description": "markdown | latex | both (default: markdown)",
                },
                "section": {
                    "type": "string",
                    "description": "Specific section to build, else full output.",
                },
                "output_type": {
                    "type": "string",
                    "description": "paper | abstract | poster | dashboard | report | grant (default: paper). Drives citation cap and section structure.",
                },
                "citation_style": {
                    "type": "string",
                    "description": "vancouver (default) | apa",
                },
                "override_completeness_gate": {
                    "type": "boolean",
                    "description": "Bypass the master quality gate for a partial / WIP deliverable. ONLY set when the researcher has explicitly authorised it. Logged.",
                },
                "override_unresolved_blocks": {
                    "type": "boolean",
                    "description": "Phase-4c: bypass the unresolved-BLOCK-findings gate (workspace/logs/.audit_findings.jsonl). ONLY set when the researcher has explicitly authorised compiling with active BLOCK findings on record. Logged to workspace/logs/override_log.md with the blocker ids.",
                },
                "override_rationale": {
                    "type": "string",
                    "description": "Required when override_completeness_gate=true OR override_unresolved_blocks=true. One-line reason the researcher authorised the bypass (e.g. 'reviewer asked for a preview of the discussion section before the final figures are in').",
                },
                "skip_gates": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of specific audit names to skip (e.g. ['claims', 'prose']). Defaults to ['claims'] on first synthesis since paper.md doesn't exist yet.",
                },
                "auto_proceed": {
                    "type": "boolean",
                    "description": "AUTOPILOT-ONLY short-circuit (AUDIT-063). When true AND interaction.autonomy_level == 'autopilot', tool_synthesize processes ALL sections (methods → results → discussion → introduction → abstract) AND runs the full assembly in ONE call. Each per-section file is still written exactly as the multi-turn flow would write it. Passing true in manual/supervised/coaching modes returns an error — the multi-turn cadence is the deliberation pace those modes exist to provide. Default false.",
                },
            },
        },
    },
    "tool_latex_compile": {
        "description": "Compile synthesis/paper.tex to PDF (pdflatex + bibtex).",
        "category": "synthesis",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "tool_poster_create": {
        "description": "Compile a conference poster from the curated synthesis spec via Typst (academic_36x48 portrait, light theme, US-letter handout by default). Hero figures land on the poster sorted by `poster_priority` in each figure's .caption.md frontmatter (top 3). Optional QR PNG renders when qr_url is set + the qrcode package is installed (degrades gracefully). The legacy tikzposter LaTeX engine was removed in v2.0.0; the `engine` kwarg is accepted for back-compat but only `typst` is supported.",
        "category": "synthesis",
        "inputSchema": {
            "type": "object",
            "properties": {
                "template": {
                    "type": "string",
                    "description": "academic_36x48 (default) | academic_48x36 | academic_a0_portrait | academic_a1_landscape | public_24x36.",
                },
                "theme": {
                    "type": "string",
                    "description": "light (default) | dark | institution_branded.",
                },
                "qr_url": {
                    "type": "string",
                    "description": "URL to encode in the footer QR code. Omitted gracefully if `qrcode` package is missing.",
                },
                "handout_pdf": {
                    "type": "boolean",
                    "description": "Also emit synthesis/poster.handout.pdf (US-letter text-only condensed). Default true.",
                },
                "engine": {
                    "type": "string",
                    "description": "Back-compat only. Must be 'typst' (default). Any other value is rejected — the tikzposter LaTeX renderer was removed in v2.0.0.",
                },
            },
        },
    },
    "tool_dashboard": {
        "short": "Unified dashboard tool. operation=create|story_generate|story_edit|story_quality_bar|reviewer_sim|test_generate|test_run.",
        "description": "Unified dashboard dispatcher. operation='create' (default) renders the standalone offline HTML dashboard at synthesis/dashboard.html (v2 single-page-app by default; pass dashboard_legacy=true for the v1 long-scroll renderer; dashboard_default_mode='story' for narrative-first reading; audience ∈ {academic, executive, technical, teaching}; override_completeness_gate=true + override_rationale='<why>' suppresses the soft completeness warning panel for the FINAL deliverable). operation='story_generate' builds synthesis/dashboard_story.md (Theme 21 story-mode source) from workspace state. operation='story_edit' reads (no args) or patches synthesis/dashboard_story.md via `edits` (default mode='patch' diff-style payload, or mode='overwrite' to replace whole file). operation='story_quality_bar' WARNs when reading time falls outside 5-20 min, no figure in first 1000 words, or no DISAGREES/EXTENDS callout (no BLOCKERs — story mode is optional). operation='reviewer_sim' walks synthesis/dashboard.html top-to-bottom and returns whether a 5-minute skimmer would extract the headline finding. operation='test_generate' scaffolds tests/dashboard/ with the baseline Playwright + axe-core suite (pass overwrite=true to replace). operation='test_run' subprocesses pytest under tests/dashboard/ and returns structured failures + trace.zip paths (kwargs: only, visual, update_snapshots, timeout).",
        "category": "synthesis",
        "inputSchema": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": [
                        "create",
                        "story_generate",
                        "story_edit",
                        "story_quality_bar",
                        "reviewer_sim",
                        "test_generate",
                        "test_run",
                    ],
                    "description": "Which dashboard sub-operation to invoke. Defaults to 'create' when omitted.",
                },
                # operation='create' kwargs
                "title": {"type": "string", "description": "operation='create' — dashboard title."},
                "audience": {
                    "type": "string",
                    "description": "operation='create' — academic (default) | executive | technical | teaching.",
                },
                "dashboard_legacy": {
                    "type": "boolean",
                    "description": "operation='create' — use the v1 long-scroll renderer (back-compat). Default false (v2 single-page app).",
                },
                "dashboard_default_mode": {
                    "type": "string",
                    "description": "operation='create' — explore (default) | story. URL hash #mode=... and localStorage override at view time.",
                },
                "dashboard_search_enabled": {
                    "type": "boolean",
                    "description": "operation='create' — inline the MiniSearch full-text index. Default true.",
                },
                "dashboard_print_optimized": {
                    "type": "boolean",
                    "description": "operation='create' — include the print stylesheet that hides chrome + paginates sections. Default true.",
                },
                "override_completeness_gate": {
                    "type": "boolean",
                    "description": "operation='create' — suppress the step-completeness warning panel. Set only on explicit researcher approval. Logged.",
                },
                "override_rationale": {
                    "type": "string",
                    "description": "operation='create' — one-line reason for the bypass; logged to workspace/logs/override_log.md.",
                },
                # operation='story_edit' kwargs
                "edits": {
                    "type": "string",
                    "description": "operation='story_edit' — patch payload (`<<<<replace>>>>...----with----...<<<<end>>>>` blocks) OR full file content (with mode='overwrite').",
                },
                "mode": {
                    "type": "string",
                    "description": "operation='story_edit' — patch (default) | overwrite.",
                },
                # operation='reviewer_sim' kwargs
                "dashboard_path": {
                    "type": "string",
                    "description": "operation='reviewer_sim' — dashboard file path (default synthesis/dashboard.html).",
                },
                # operation='test_generate' kwargs
                "overwrite": {
                    "type": "boolean",
                    "description": "operation='test_generate' — overwrite existing test suite. Default false.",
                },
                # operation='test_run' kwargs
                "only": {"type": "string", "description": "operation='test_run' — pytest node-id filter."},
                "visual": {"type": "boolean", "description": "operation='test_run' — enable visual regression."},
                "update_snapshots": {"type": "boolean", "description": "operation='test_run' — update snapshot baselines."},
                "timeout": {"type": "number", "description": "operation='test_run' — timeout in seconds."},
            },
        },
    },
    "tool_writing_discussion_from_verdicts": {
        "short": "Append one Discussion paragraph per non-AGREES verdict in any step's findings_vs_literature.md.",
        "description": "Reads every workspace/<step>/literature/findings_vs_literature.md, finds DISAGREES + EXTENDS verdicts that carry a Discussion implication block, and appends one paragraph per verdict to synthesis/discussion.md under HTML-comment-delimited markers (idempotent — re-runs replace the block; hand-edits outside the markers are preserved). Closes the audit gap where verdicts never reached the Discussion.",
        "category": "synthesis",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "tool_discussion_coverage_audit": {
        "short": "BLOCK gate: every non-AGREES literature verdict must have a Discussion paragraph.",
        "description": "Companion to tool_writing_discussion_from_verdicts. Walks every step's findings_vs_literature.md and verifies synthesis/discussion.md mentions each DISAGREES/EXTENDS claim (>=50% key-word overlap). Returns status='error' + a blocker list if any verdict is uncovered — tool_writing_discussion's validate step honours this as a hard BLOCK unless override_discussion_coverage=true (logged to override_log.md with override_rationale).",
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
    "tool_paper_compile_typst": {
        "short": "Compile synthesis/paper.md → paper.typ → paper.pdf via Typst.",
        "description": "Markdown → Typst → PDF using a per-venue template (nature | science | nejm | cell | ieee_conf | neurips | acl | plos | generic_two_column | generic_thesis). Generates synthesis/paper.typ + synthesis/biblio.yml (Hayagriva) and runs `typst compile`. Returns pdf_path, page_count, citation_count, typst_warnings/errors. Reads researcher_config.writing_preferences.venue_template if `venue` not given. The LaTeX path (tool_latex_compile) remains available for journals that require .tex submission.",
        "category": "synthesis",
        "inputSchema": {
            "type": "object",
            "properties": {
                "paper_path": {"type": "string", "description": "Default 'synthesis/paper.md'."},
                "venue": {"type": "string", "description": "One of: nature, science, nejm, cell, ieee_conf, neurips, acl, plos, generic_two_column, generic_thesis. Falls back to researcher_config or 'generic_two_column'."},
                "output": {"type": "string", "description": "Default 'synthesis/paper.pdf'."},
            },
        },
    },
    "tool_synthesis_preview": {
        "short": "Predict what tool_synthesize will produce — word counts, page count, figures, citations, gaps — without drafting.",
        "description": "Cheap deterministic dry-run (~1 sec vs ~30s for full synthesis). Reads workspace/<step>/conclusions.md + step_summary.yaml + findings_vs_literature.md + workspace/citations.md but does NOT call the AI to draft prose. Returns predicted_word_count_per_section, predicted_total_word_count, predicted_page_count or slide_count, predicted_figures_embedded, predicted_citations, predicted_steps_drawn_from, detected_gaps, estimated_render_time_seconds. mode='diff' compares against the existing deliverable on disk.",
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
    "tool_section_substantiveness": {
        "short": "Content depth audit for synthesis/paper.md — per-section checks beyond word counts.",
        "description": "Runs per-IMRAD-section audits: Abstract (≥1 number + ≥1 method + ≥1 conclusion verb), Introduction (≥3 cited prior works + 'in this study, we' pivot), Methods (every workspace step's primary method/tool named; coverage <50% BLOCKS, <80% WARNS), Results (≥1 statistic per finding; focal figures referenced), Discussion (Limitations paragraph + future-work direction + ≥1 paragraph per non-AGREES verdict), References (every cited key in bibliography, BLOCKER for missing). Returns blockers, warnings, sub_reports per section, cliché hits.",
        "category": "audit",
        "inputSchema": {
            "type": "object",
            "properties": {
                "paper_path": {"type": "string", "description": "Default 'synthesis/paper.md'."},
            },
        },
    },
    "tool_humanities_essay_scaffold": {
        "short": "Scaffold a non-IMRAD humanities essay.",
        "description": "Write synthesis/paper.md with the six interpretive section headings + one-paragraph stubs the synthesis/humanities_essay_structure protocol prescribes (introduction+thesis, contextual framing, three close readings, critical conversation, counter-argument+reply, conclusion+stakes). Idempotent: re-running on a partially drafted paper.md preserves substantive content (>200 non-stub chars under a heading) and only fills missing sections. Pairs with humanities_essay.typ for the venue layer (1.25in margins, 12pt serif, MLA-style unnumbered headings, footnote apparatus, 0.5in block-quote indent). No arguments — operates on the current project root.",
        "category": "synthesis",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "tool_slides_create": {
        "short": "Compile a real presentation deck — Reveal.js HTML or Touying-compatible Typst PDF — from workspace findings + slides_spec.yaml.",
        "description": "Two production engines. engine='reveal' writes synthesis/slides.html — a single self-contained file backed by the vendored Reveal.js v5 runtime with stock speaker-notes plugin (press 's' for presenter view). engine='touying' writes synthesis/slides.typ against the bundled touying-mini.typ template and shells out to the typst CLI to produce synthesis/slides.pdf (requires typst on PATH). Five stock templates: conference_15min (12 slides), conference_5min_lightning (6 slides), lab_meeting_30min (16 slides + backup section), defense_45min (35 slides chapter-arc), public_outreach (12 slides, no jargon). theme='' picks per-engine default (white). speaker_notes_enabled=True (default) embeds the per-slide notes. print_handout=True (default) also emits synthesis/slides.handout.pdf — a 2-up A4 condensed PDF with speaker notes printed beneath each slide. Prereq: at least one workspace/<step>/conclusions.md OR synthesis/slides_spec.yaml; missing both returns a structured error. Back-compat: legacy output_format='reveal'|'beamer'|'pdf' and audience= kwargs are accepted and mapped to engine= silently.",
        "category": "synthesis",
        "inputSchema": {
            "type": "object",
            "properties": {
                "engine": {
                    "type": "string",
                    "description": "reveal (default — single-file HTML, Reveal.js v5) | touying (Typst → PDF, requires typst CLI)",
                },
                "template": {
                    "type": "string",
                    "description": "conference_15min (default) | conference_5min_lightning | lab_meeting_30min | defense_45min | public_outreach",
                },
                "theme": {
                    "type": "string",
                    "description": "'' (default = white) | white | black. Reveal engine swaps the vendored theme CSS; touying engine flips the background/foreground in touying-mini.typ.",
                },
                "speaker_notes_enabled": {
                    "type": "boolean",
                    "description": "Default true. Embed per-slide speaker_notes from the template + slides_spec. Reveal surfaces via the notes plugin ('s' key opens presenter view); touying renders them only in handout mode.",
                },
                "print_handout": {
                    "type": "boolean",
                    "description": "Default true. Also emit synthesis/slides.handout.pdf — a 2-up A4 condensed PDF with speaker notes printed beneath each slide. Requires typst on PATH (reveal engine uses the touying handout path).",
                },
                "audience": {
                    "type": "string",
                    "description": "Back-compat: legacy callers passed audience= alongside template=. Accepted as a meta-hint; the template= argument is authoritative.",
                },
                "output_format": {
                    "type": "string",
                    "description": "Back-compat: legacy kwarg. 'reveal'/'html' maps to engine='reveal'; 'beamer'/'pdf'/'typst'/'touying' maps to engine='touying'.",
                },
            },
        },
    },
    "tool_reviewer": {
        "short": "Unified reviewer-response tool. operation=simulate|response|rebuttal|compile.",
        "description": "Unified reviewer-response dispatcher. operation='simulate' loads N reviewer personas (default: all 7 — methodology_skeptic, domain_expert, statistician, reproducibility_advocate, scope_creep_critic, novelty_critic, presentation_critic) and the paper, then writes workspace/reviewer/simulation_brief.md with each persona's lens + red flags + typical questions + signature phrasings. operation='response' produces synthesis/response_to_reviewers.md with one heading per reviewer comment (Mn, mn), pre-formatted for line-referenced rebuttal text, paired with the latest red-team report. operation='rebuttal' writes a single rebuttal scaffold under workspace/reviewer/rebuttals/<slug>.md given a verbatim reviewer comment + the persona id (+ optional evidence_paths); the scaffold surfaces methods record, per-step findings_vs_literature.md, outputs (figures/tables/reports), and paper sections so the AI can ground the response. operation='compile' concatenates every rebuttal markdown under workspace/reviewer/rebuttals/ (grouped by persona) into workspace/reviewer/response_to_reviewers.md; best-effort PDF compile via the bundled Typst generic_two_column template (status='skipped' for the PDF leg when typst is not on PATH; the markdown is always produced). Returns rebuttal_count, personas_addressed, response_md path, response_pdf path (or null). Internal companion to guidance/peer_review_response (which handles ACTUAL external reviewer reports).",
        "category": "synthesis",
        "inputSchema": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["simulate", "response", "rebuttal", "compile"],
                    "description": "Which reviewer sub-operation to invoke.",
                },
                # operation='simulate' kwargs
                "personas": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "operation='simulate' — subset of persona ids to load. Default: all 7 ship and run.",
                },
                # operation='response' kwargs
                "review_path": {
                    "type": "string",
                    "description": "operation='response' — optional path to the red-team review markdown to pair with the response template.",
                },
                # operation='rebuttal' kwargs
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
                # operation='compile' takes no extra kwargs.
            },
            "required": ["operation"],
        },
    },
}
