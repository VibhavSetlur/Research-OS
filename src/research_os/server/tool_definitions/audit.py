"""Tool definitions for the audit domain."""
from __future__ import annotations

from typing import Any


AUDIT_TOOL_DEFINITIONS: dict[str, dict[str, Any]] = {
    "tool_audit": {
        "short": "Unified per-dimension audit. scope=step|project|synthesis|tool|active_gates; dimension picks the gate.",
        "do_not": "Set override_* params only when researcher explicitly authorizes. Without a substantive override_rationale (>=20 chars, multi-word), the override is rejected.",
        "description": "Unified audit dispatcher. Pick (scope, dimension): scope='step' for per-step gates (completeness, literature, code_quality, evalue, figure, figure_full, figure_interactivity, power, assumptions, reproducibility); scope='project' for project-wide gates (citations, claims, cliches, coherence, cross_deliverable, prose, version_coherence); scope='synthesis' for synthesis-side gates (all, dashboard_content, figure_coverage, reviewer_responses); scope='tool' for tool_build-mode gates (tests, git_hygiene, build) — the analog of the figure/literature gates, mode-aware (a no-op outside workspace.mode='tool_build'); scope='active_gates' (no dimension required) returns the live armed-gate state on this project — which audit gates have emitted findings in the cross-audit ledger, with per-gate counts by severity, so the AI can see what's actively enforced without grepping audit code. Per-dimension kwargs are accepted on the same call (e.g. step_id, paper_path, filepath, target_path, override_no_pdfs, override_rationale, ...). Output schema matches the legacy per-dimension tool for the chosen (scope, dimension). Use tool_audit_quality_full to run all primary gates in one shot. Use tool_audit_findings to read the cross-audit findings ledger after one or more audits have written to it. Use sys_help(topic='gates') for the full gate vocabulary.",
        "category": "audit",
        "inputSchema": {
            "type": "object",
            "properties": {
                "scope": {
                    "type": "string",
                    "enum": ["step", "project", "synthesis", "tool", "active_gates"],
                    "description": "Audit scope. step = per-step gate. project = project-wide gate (paper / repo / citations). synthesis = synthesis-side gate (paper / dashboard / reviewer responses). tool = tool_build-mode gate (tests / git_hygiene / build; no-op outside tool_build). active_gates = introspect which gates are armed on this project (no dimension required).",
                },
                "dimension": {
                    "type": "string",
                    "description": "What to audit. See the description for the full (scope, dimension) matrix. Not required when scope='active_gates'.",
                },
                # Common per-dimension kwargs (all optional; consumed by the
                # downstream legacy handler). Listed here so MCP clients can
                # auto-complete; extra unknown kwargs are forwarded verbatim.
                "step_id": {"type": "string", "description": "scope='step' dimensions — optional step folder, default = all active steps."},
                "paper_path": {"type": "string", "description": "scope='synthesis' dimension='all' — manuscript to audit (default 'synthesis/paper.md')."},
                "filepath": {"type": "string", "description": "scope='step' dimensions ∈ {figure, power, assumptions} — file to audit."},
                "figure_path": {"type": "string", "description": "scope='step' dimension='figure_full' — figure to audit."},
                "target_path": {"type": "string", "description": "scope='project' dimension='claims' — manuscript to audit (default 'synthesis/paper.md')."},
                "tolerance": {"type": "number", "description": "scope='project' dimension='claims' — numeric tolerance (default 0.01 = 1%)."},
                "dashboard_path": {"type": "string", "description": "scope='synthesis' dimension='dashboard_content' — dashboard file path."},
                "effect_size": {"type": "number"},
                "alpha": {"type": "number"},
                "n": {"type": "number"},
                "risk_ratio": {"type": "number"},
                "ci_lower": {"type": "number"},
                "ci_upper": {"type": "number"},
                "run_ruff": {"type": "boolean"},
                "run_mypy": {"type": "boolean"},
                "targets": {"type": "array", "items": {"type": "string"}},
                "is_observational": {"type": "boolean"},
                "strictness": {"type": "string"},
                "autogen": {"type": "boolean"},
                "override_no_pdfs": {"type": "boolean"},
                "override_dashboard_content_gate": {"type": "boolean"},
                "override_cross_deliverable": {"type": "boolean"},
                "override_rationale": {"type": "string"},
                "confirmed": {"type": "boolean", "description": "Required in autopilot mode for scope='step' dimension='reproducibility' (slow + expensive; server-enforced autopilot floor gate — see guidance/autopilot.yaml)."},
            },
            "required": ["scope"],
        },
    },
    "tool_audit_findings": {
        "short": "Read cross-audit findings ledger. operation='query'|'diff'|'explain'|'timeline'. Use when triaging findings.",
        "description": "Unified read interface for workspace/logs/.audit_findings.jsonl (the append-only ledger every audit writes to via write_audit_outputs). operation='query' (default) reduces to the latest snapshot per stable finding id and filters by severity ('block' | 'warn' | 'info'), dimension, step (matches evidence_paths containing '/<step>/'), and since (ISO-8601 cutoff). operation='diff' snapshots the ledger as of timestamp_a (EARLIER) and timestamp_b (LATER) and reports {added: [...], resolved: [...], changed: [...]} keyed by stable finding id. operation='explain' (REQUIRES id) walks the ledger chronologically and returns every snapshot of that finding id (full suggested_fix text without 160-char truncation, full evidence_paths, originating audit_name + dimension + severity), so the AI can see when the finding was first raised, when overridden, when re-raised, and what the originating audit's full remediation guidance says. operation='timeline' returns the FULL append-only ledger in chronological order (no dedup, every emission preserved) so long-context models can spot recurrence patterns ('this finding keeps coming back') and override loops; optional gate_name / scope filters. Read-only — never mutates the ledger. operation defaults to 'diff' when both timestamps are supplied without an explicit operation, otherwise 'query'.",
        "category": "audit",
        "inputSchema": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["query", "diff", "explain", "timeline"],
                    "description": "Default 'query'. Use 'diff' to compare two ledger snapshots. Use 'explain' (with id=...) to get full chronological history + untruncated suggested_fix for one finding. Use 'timeline' to read the FULL append-only ledger (no dedup) for long-context recurrence-pattern analysis.",
                },
                # query kwargs
                "severity": {
                    "type": "string",
                    "enum": ["block", "warn", "info"],
                    "description": "operation='query' — optional severity filter.",
                },
                "dimension": {
                    "type": "string",
                    "description": "operation='query' — optional dimension filter (e.g. 'completeness', 'prose').",
                },
                "step": {
                    "type": "string",
                    "description": "operation='query' — optional step folder filter (e.g. '02_eda').",
                },
                "since": {
                    "type": "string",
                    "description": "operation='query' — optional ISO-8601 cutoff; returns findings on/after this timestamp.",
                },
                # diff kwargs
                "timestamp_a": {
                    "type": "string",
                    "description": "operation='diff' — ISO-8601 timestamp for the EARLIER snapshot.",
                },
                "timestamp_b": {
                    "type": "string",
                    "description": "operation='diff' — ISO-8601 timestamp for the LATER snapshot; must be on/after timestamp_a.",
                },
                # explain kwargs
                "id": {
                    "type": "string",
                    "description": "operation='explain' — REQUIRED. Stable finding id (UUID) to fetch full chronological history for. Use ids surfaced by operation='query', operation='diff', or a tool_synthesis_check BLOCK envelope.",
                },
                # timeline kwargs
                "gate_name": {
                    "type": "string",
                    "description": "operation='timeline' — optional filter on the originating audit's name (audit_name field, e.g. 'step_completeness', 'cross_deliverable_consistency').",
                },
                "scope": {
                    "type": "string",
                    "description": "operation='timeline' — optional evidence-path scope filter (matches a step folder like '02_eda' or any path token).",
                },
            },
        },
    },
    "tool_audit_quality_full": {
        "short": "Run every quality gate in one call — completeness + code + prose + claims + prereg diff + grounding.",
        "description": "Master auditor. Runs all 6 quality gates: tool_audit_step_completeness + tool_audit_code_quality + tool_audit_prose + tool_audit_claims + tool_preregister_diff + tool_ground (grounding_verify) in one shot; aggregates the blocker set; writes workspace/logs/audit_master.md. tool_synthesis_check calls this as part of the substantiveness pass on an AI-authored synthesis file. Grounding blockers surface as `[grounding] N decision(s) without grounding records`. NB: this master audit does NOT run the per-step literature gate — call `tool_audit_step_literature` per step (or rely on `tool_step_complete` to have caught it). The per-step literature check is run separately at synthesis time by `tool_audit_synthesis` / `tool_path_finalize`; if you skip it during the run, expect blockers at synthesis.",
        "category": "audit",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target_path": {"type": "string"},
                "skip": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
    "tool_state_freshness_check": {
        "short": "Detect stale workspace state (state.json > 30d, citations older than newest PDF, orphan provenance).",
        "description": "Auto-called by sys_boot. If state.json mtime > stale_after_days (default 30), OR workspace/citations.md older than the newest inputs/literature/*.pdf, OR any per-step .prov.json points to a script that no longer exists, returns is_stale=true + a prompt_for_ai string the AI surfaces as a 'reconfirm before continuing?' question. Cheap; safe to call at every boot.",
        "category": "state",
        "inputSchema": {
            "type": "object",
            "properties": {
                "stale_after_days": {"type": "integer"},
            },
        },
    },
    "tool_intake_freshness": {
        "short": "Return recommended intake depth (full | refresh-only | skip) based on intake.md freshness + step count.",
        "description": "Decides whether project_startup should fully autofill intake or skip / refresh-only. inputs/intake.md missing or stub → full. Exists with >500 substantive chars + edited in last fresh_window_days → skip. Older than fresh_window_days but substantive → refresh-only. Also reports mid_pipeline_entry_recommended=true when >=1 numbered step has conclusions.md.",
        "category": "data",
        "inputSchema": {
            "type": "object",
            "properties": {
                "fresh_window_days": {"type": "integer"},
            },
        },
    },
    "tool_rigor_signals_scan": {
        "short": "Score project rigor 0-100 from methods.md, citations, git, preregistration, scripts, prior step summaries.",
        "description": "Infers rigor signals across 6 dimensions and returns trust_score 0-100 + per-signal breakdown + recommended_strictness (light when >=75, normal when >=50, strict when <50). Audits can scale strictness via tool_resolve_gate_strictness.",
        "category": "state",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "tool_resolve_gate_strictness": {
        "short": "Resolve effective gate strictness (light | normal | strict) from researcher_config + trust_score.",
        "description": "researcher_config.gate_strictness can be light | normal | strict | auto. auto follows the rigor_signals_scan trust_score. Returns the resolved value + source (config | auto | default). Light downgrades most blockers to notes; strict keeps full enforcement.",
        "category": "state",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "tool_self_certify": {
        "short": "Persist a researcher self-certification (domain + scope + rationale).",
        "description": "Researcher with deep expertise can self-certify equivalent work was done outside RO. Domains: literature_loop (alias lit_loop), stack_plan, preregistration, sensitivity_analysis, code_review, reproducibility. Persisted to workspace/researcher_certifications.yaml; audits downgrade matching blockers to notes (still surfaced for transparency).",
        "category": "state",
        "inputSchema": {
            "type": "object",
            "properties": {
                "domain": {"type": "string"},
                "scope": {"type": "string"},
                "rationale": {"type": "string"},
            },
            "required": ["domain", "scope", "rationale"],
        },
    },
    "tool_list_certifications": {
        "short": "List active researcher self-certifications.",
        "description": "Return the list of currently-active researcher_certifications.yaml entries. Use when an audit blocker says 'consider tool_self_certify' to see whether a cert already exists.",
        "category": "state",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "tool_quick_route": {
        "short": "Detect throwaway / sanity-check / exploratory intent and short-circuit protocol load.",
        "compare_to": "tool_route (full hybrid router; call this BEFORE tool_route to catch quick-mode short-circuit).",
        "description": "Call before tool_route on every prompt. If the prompt matches a quick trigger ('just make me a plot', 'sanity check', 'exploratory only', 'quick look', 'throwaway viz', 'quick check', 'scratch'), returns is_quick=true + complexity='quick' + recommended_tool='tool_scratch_write'. Quick mode bypasses protocols + audit gates; results land under workspace/scratch/. Researcher can later promote via tool_promote_to_step.",
        "category": "state",
        "inputSchema": {
            "type": "object",
            "properties": {"prompt": {"type": "string"}},
            "required": ["prompt"],
        },
    },
    "tool_promote_to_step": {
        "short": "Retroactively wrap a scratch result in proper provenance (new numbered step + sidecar + summary).",
        "description": "Promote a workspace/scratch/ artifact into a proper numbered step. Creates the next workspace/NN_<slug>/ folder, copies the scratch file into outputs/figures/ (or step root for non-image files), emits .prov.json sidecar pointing back to the original scratch, writes minimal conclusions.md + step_summary.yaml. By default literature_required=false on the promoted step.",
        "category": "state",
        "inputSchema": {
            "type": "object",
            "properties": {
                "scratch_path": {"type": "string"},
                "step_slug": {"type": "string"},
                "rationale": {"type": "string"},
            },
            "required": ["scratch_path", "step_slug"],
        },
    },
    "tool_project_tier_strictness": {
        "short": "Map researcher_config.project_tier (throwaway | sketch | production) -> default gate_strictness.",
        "description": "researcher_config.project_tier sets the default audit strictness across a whole project. throwaway -> light, sketch -> normal, production -> strict. Returns the resolved tier + strictness.",
        "category": "state",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "tool_dry_run": {
        "short": "Preview a protocol's tool-call sequence without executing — for supervised review.",
        "description": "Wraps sys_protocol_get format='dryrun'. Returns the protocol's full step sequence with predicted tool calls inferred from each step's description body. No tool is actually invoked; no files are written. Useful before committing in supervised / coaching autonomy modes. Pass optional simulated_args to annotate expected per-step args; ignored if not provided.",
        "category": "protocol",
        "inputSchema": {
            "type": "object",
            "properties": {
                "protocol_name": {"type": "string"},
                "simulated_args": {"type": "object", "additionalProperties": True},
            },
            "required": ["protocol_name"],
            "additionalProperties": False,
        },
    },
    "tool_step_complete": {
        "short": "Bundle: path_finalize + completeness + literature + revision_options. Use at end of every step.",
        "then": "tool_route on next prompt OR sys_protocol_next",
        "description": "One-shot end-of-step bundle. Calls (in order) tool_path_finalize, tool_audit_step_completeness, tool_audit_step_literature, then tool_step_revision_options on the named step. Returns a merged result {finalize, completeness, literature, revision} with overall_status='success' | 'warning' | 'error'. Reduces 4 tool calls to 1 — eliminates small-model drift between calls and halves the round-trip latency. The AI should still surface the revision options verbatim per the anti-one-shot doctrine.",
        "category": "audit",
        "inputSchema": {
            "type": "object",
            "properties": {
                "step_id": {"type": "string"},
                "override_literature_gate": {"type": "boolean"},
                "override_rationale": {"type": "string"},
            },
            "required": ["step_id"],
            "additionalProperties": False,
        },
    },
    "tool_finalize_project": {
        "short": "Server-enforced ship gate. operation='check'|'finalize'. The one gate that can REFUSE 'done'.",
        "do_not": "Set override=true only when the researcher explicitly authorizes shipping despite blockers. Without a substantive override_rationale (>=20 chars, multi-word) the override is rejected.",
        "then": "If clear, deliverable may ship. If blocked, resolve the listed blockers OR obtain a researcher override.",
        "description": "The single final pre-ship gate that can actually refuse to mark a deliverable done — every other gate is advisory. Aggregates BLOCK-severity findings across the whole project: (1) unresolved audit blockers in the cross-audit ledger, (2) cited-but-invalid PDFs (files named *.pdf that fail the %PDF- magic check — renamed 403/HTML/paywall pages), (3) ungrounded numeric claims in the resolved deliverable (numbers appearing in no workspace output), and (4) stub/placeholder deliverable sections (TODO/TBD/FIXME/lorem ipsum/<placeholder>/authoring comments). operation='check' (default) is report-only: it lists blockers without refusing. operation='finalize' enforces: any unresolved blocker returns a hard error (refusing 'done') unless override=true + a substantive override_rationale clears it (logged to workspace/logs/override_log.md). Writes workspace/logs/ship_gate.md. Reference this as the LAST step before shipping a paper/dashboard/poster.",
        "category": "audit",
        "inputSchema": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["check", "finalize"],
                    "description": "check = report-only (advisory). finalize = enforce; blockers refuse 'done' unless overridden.",
                },
                "override": {
                    "type": "boolean",
                    "description": "operation='finalize' — ship despite blockers. Requires a substantive override_rationale. Only set when the researcher explicitly authorizes.",
                },
                "override_rationale": {
                    "type": "string",
                    "description": "Required when override=true. >=20 chars, multi-word, non-placeholder. Logged to workspace/logs/override_log.md.",
                },
            },
            "additionalProperties": False,
        },
    },
}
