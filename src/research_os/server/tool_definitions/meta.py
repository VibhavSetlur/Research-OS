"""Tool definitions for the meta domain.

Extracted from server/_core.py as part of the Phase-10 server.py modular split.
"""
from __future__ import annotations

from typing import Any


META_TOOL_DEFINITIONS: dict[str, dict[str, Any]] = {
    "sys_boot": {
        "short": "One-call session bootstrap — state + config + history + dep inventory + next protocol. Replaces 4-5 separate calls.",
        "description": "Single-call session bootstrap. Returns state + researcher config + protocol history tail + optional-dep inventory + recommended next protocol + pause classification + any active plan from a previous turn. Call this ONCE per session instead of sys_state_get + sys_config_get + sys_protocol_history + sys_protocol_next + sys_dep_inventory separately. Cuts a typical boot from ~5K tokens to ~800.",
        "category": "routing",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "tool_route": {
        "short": "Prompt → protocol + decomposition + recommended_action. Call after every researcher message.",
        "description": "Hybrid router. Tries SEMANTIC search first (embeddings cosine over protocol descriptions + triggers) — best for fuzzy intent + as the protocol catalog grows. Falls back to the hierarchical L1→L2→L3 trigger picker when semantic confidence is low / unavailable. Returns primary_protocol, shortcut_tool, decomposition, complexity, ask_user, alternatives, method (=semantic|trigger), confidence (=high|medium|low|none), and `recommended_action` — a single-string hint naming the exact next tool to call (typically `sys_protocol_get(protocol_name='<primary>', format='summary')`, or the shortcut tool, or an `ask_user:` prompt, or a `tool_semantic_route` fallback when nothing resolved). High-complexity prompts get an active_plan persisted to .os_state/.",
        "category": "routing",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string"},
                "persist_plan": {"type": "boolean"},
            },
            "required": ["prompt"],
        },
    },
    "tool_semantic_route": {
        "short": "Direct semantic search over protocol embeddings. Returns top-k candidates with scores.",
        "description": "Embed the prompt with BAAI/bge-small-en-v1.5 (local ONNX, no network) and return the top-k protocols by cosine similarity, with the length-weighted trigger-phrase boost applied. Use this when you want to SEE the ranked candidates yourself — tool_route picks a primary; tool_semantic_route surfaces the alternatives so you can route deliberately. Requires the `semantic` extra (`pip install 'research-os[semantic]'`); falls back to status='unavailable' otherwise.",
        "category": "routing",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string"},
                "top_k": {"type": "integer", "default": 5, "minimum": 1, "maximum": 25},
            },
            "required": ["prompt"],
        },
    },
    "sys_semantic_tool_search": {
        "short": "Find tools by what they do — semantic search over tool descriptions.",
        "description": "Given a natural-language description of what you want to do (e.g. 'compute kappa for inter-rater agreement on transcript codes'), return the top-k matching tool names ranked by semantic similarity to each tool's short + description + category. Useful when sys_active_tools doesn't surface the right tool because the active protocol's decomposition is narrow. Requires the `semantic` extra; falls back to status='unavailable' otherwise.",
        "category": "system",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "top_k": {"type": "integer", "default": 5, "minimum": 1, "maximum": 25},
            },
            "required": ["query"],
        },
    },
    "sys_tool_describe": {
        "short": "Return the full description + schema + status + pack for one tool.",
        "description": "list_tools ships only short descriptions to keep context lean. When you genuinely need the full detail (parameter semantics, longer rationale, examples) for one tool, call this. Returns name, category, short, description, inputSchema, plus the Phase-9 introspection fields: status ('live' = canonical | 'alias' = legacy name dispatched to a consolidated tool | 'deprecated' = removed but still tagged) and pack ('core' = built-in | '<pack_name>' = contributed by an installed protocol pack or adapter). Cheaper than re-listing every tool.",
        "category": "routing",
        "inputSchema": {
            "type": "object",
            "properties": {"tool_name": {"type": "string"}},
            "required": ["tool_name"],
        },
    },
    "sys_active_tools": {
        "short": "Active tool shortlist for a protocol (essentials + decomposition tools).",
        "description": "Given a protocol name, return the tight set of tools the AI should prefer while executing it: ~10-15 tools = essentials + everything the protocol's decomposition actually calls. Use after sys_protocol_get to scope your working set instead of triaging all 212 tools per turn.",
        "category": "routing",
        "inputSchema": {
            "type": "object",
            "properties": {"protocol_name": {"type": "string"}},
            "required": ["protocol_name"],
        },
    },
    "sys_active_project": {
        "short": "Return the project root the server resolved for THIS request (global-server mode).",
        "description": "Returns the currently-resolved project root + how it was resolved (env var / cwd walk / fallback). The Research OS MCP server is GLOBAL — one process serves multiple projects. Each request resolves a project per the rules: (1) RESEARCH_OS_WORKSPACE env var (the IDE MCP config typically sets this to ${workspaceFolder}); (2) the current working directory walked up for `.os_state/`; (3) the current working directory itself. Call this when you need to confirm which project this session is operating on, OR when a tool surprised you and you want to verify the root.",
        "category": "routing",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "sys_help": {
        "short": "AI orientation — how to use Research OS efficiently (protocols + tools + routing).",
        "description": "Returns a compact orientation block for the AI: the session-start sequence (every turn is triggered by a researcher message — on the first turn, sys_boot is your 1st MCP call and tool_route(prompt=their message) is your 2nd, followed by sys_protocol_get / sys_active_tools as needed), the protocol categories with one-line summaries, and the tool namespaces (sys_* / tool_* / mem_*). Use this when starting cold (no prior session memory), when a new AI takes over from a handoff, or when a tool / protocol mention is ambiguous and the orientation block clarifies it.",
        "category": "routing",
        "inputSchema": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "Optional — a topic to focus the orientation on (e.g. 'synthesis', 'methodology', 'audit'). Returns category-specific guidance.",
                },
            },
        },
    },
    "sys_protocol_get": {
        "short": "Load a protocol — defaults to format='summary' (cheap). Use 'step' (one step), 'lean' (small-model), 'dryrun' (preview), or 'full' explicitly.",
        "description": "Load a protocol YAML by name (e.g. 'guidance/project_startup'). Five formats — summary (the default) returns id + step headings + quality_bar + expected outputs in ~300 tokens; step returns one specific step body (requires step_id); full returns the entire YAML (~1.5-3K tokens) and requires opt-in; lean serves the protocol's explicit lean_variant block if present, else auto-distils (cap 3 steps, drop optional sub-steps, trim step descriptions to 200 chars) for small/fast models; dryrun returns the full tool-call sequence with predicted args without executing — for supervised review. Prefer summary first then step on demand; use lean when researcher_config.model_profile=='small'; use dryrun in supervised mode to preview before commit. Routing tip: call tool_route(prompt) BEFORE this to pick the right protocol_name.",
        "category": "protocol",
        "inputSchema": {
            "type": "object",
            "properties": {
                "protocol_name": {"type": "string"},
                "format": {
                    "type": "string",
                    "enum": ["summary", "step", "full", "lean", "dryrun"],
                    "default": "summary",
                    "description": "summary | step | full | lean | dryrun (default: summary, ~300 tokens — pass 'full' explicitly when you actually need the whole YAML).",
                },
                "step_id": {
                    "type": "string",
                    "description": "Required when format='step'.",
                },
            },
            "required": ["protocol_name"],
            "additionalProperties": False,
        },
    },
    "sys_protocol_list": {
        "short": "Full catalog dump across core + all packs (~100+ items). Optional `category` filter (pack name or first path segment). Prefer tool_route / tool_semantic_route — semantic routing scales as the catalog grows.",
        "description": "Returns every protocol name + one-line summary + pack_or_core source, walking both the in-tree core protocols and every registered pack (humanities, qualitative, theory_math, wet_lab, engineering, plus any externally-installed packs). Pass `category` (e.g. 'theory_math', 'audit', 'guidance') to narrow to one pack or one core category. Designed for debugging + maintainer browsing; not the primary entrypoint at runtime. For routing a user prompt, call tool_route (hybrid semantic + trigger). For inspecting ranked alternatives, call tool_semantic_route. For finding tools by what they do, call sys_semantic_tool_search. As the catalog grows beyond ~150 protocols, dumping the full list every turn wastes context — semantic retrieval is the AI-friendly path.",
        "category": "protocol",
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Filter to a single category. For core protocols this matches the first path segment (e.g. 'guidance', 'audit'). For pack protocols it matches the pack name (e.g. 'theory_math') or the pack-internal category.",
                },
            },
        },
    },
    "tool_protocols_list": {
        "short": "Flat protocol catalog with category + pack + intent_class. Filterable.",
        "description": "Returns a flat list of every protocol with structured metadata: name, category, pack_or_'core', intent_class, tier (null until Phase 8), version, description_short. Filter with `category` (e.g. 'audit', 'guidance'), `pack` ('core' or a pack name), and `include_pack_protocols` (default true). Cheaper for the AI to scan than sys_protocol_list when it only needs the protocols in one category or one pack. Use this when a researcher asks 'what audit protocols do you have?' — narrower than dumping the full catalog.",
        "category": "protocol",
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Filter to a single category (first path segment, e.g. 'guidance', 'audit', 'synthesis').",
                },
                "pack": {
                    "type": "string",
                    "description": "Filter to a single source: 'core' or a pack name ('humanities', 'qualitative', etc.).",
                },
                "include_pack_protocols": {
                    "type": "boolean",
                    "description": "When false, skip every pack-contributed protocol. Default true.",
                },
            },
        },
    },
    "tool_tools_list": {
        "short": "Flat tool catalog with scope + summary + required-fields. Filterable.",
        "description": "Returns a flat list of every registered MCP tool: name, scope ('core' or pack name), summary_first_line, input_schema_required_fields, deprecated, alias_of. Filter with `scope` ('all'|'core'|<pack-name>'), `include_deprecated` (default false), and `match_substring` (case-insensitive needle against name + summary). Use this to discover the tool surface at a glance without pulling every full description; call sys_tool_describe for one tool's full body when you actually need it.",
        "category": "system",
        "inputSchema": {
            "type": "object",
            "properties": {
                "scope": {
                    "type": "string",
                    "description": "'all' | 'core' | a pack name. Default 'all'.",
                },
                "include_deprecated": {
                    "type": "boolean",
                    "description": "When true, include alias entries flagged as deprecated. Default false.",
                },
                "match_substring": {
                    "type": "string",
                    "description": "Restrict to tools whose name or summary contains this substring (case-insensitive).",
                },
            },
        },
    },
    "sys_protocol_next": {
        "description": "Recommend the next protocol to run based on current workspace state and the pipeline.",
        "category": "protocol",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "sys_protocol_validate": {
        "description": "Check whether the expected outputs of a protocol are present in the workspace.",
        "category": "protocol",
        "inputSchema": {
            "type": "object",
            "properties": {"protocol_name": {"type": "string"}},
            "required": ["protocol_name"],
        },
    },
    "sys_protocol_log": {
        "description": "Record a protocol execution (started|completed|failed|skipped) to the pipeline log.",
        "category": "protocol",
        "inputSchema": {
            "type": "object",
            "properties": {
                "protocol_name": {"type": "string"},
                "status": {"type": "string"},
                "details": {"type": "string"},
            },
            "required": ["protocol_name", "status"],
        },
    },
    "sys_protocol_history": {
        "description": "Return the most recent protocol execution log entries.",
        "category": "protocol",
        "inputSchema": {
            "type": "object",
            "properties": {"limit": {"type": "number"}},
        },
    },
    "sys_state_get": {
        "description": "Return the full workspace state: project name, pipeline stage, current path, all experiment paths, and active hypotheses.",
        "category": "state",
        "inputSchema": {
            "type": "object",
            "properties": {
                "format": {
                    "type": "string",
                    "description": "full | minimal | markdown — controls verbosity (default: full).",
                }
            },
        },
    },
    "sys_workspace_scaffold": {
        "description": "Create the standard Research OS directory layout. Used by `research-os init`; only call from inside the MCP if the researcher explicitly asks for a re-scaffold.",
        "category": "workspace",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_name": {"type": "string"},
                "ide": {
                    "type": "string",
                    "description": "all | cursor | claude | antigravity | opencode | vscode",
                    "default": "all",
                },
            },
        },
    },
    "sys_workspace_tree": {
        "description": "Return a structured tree of workspace/ — experiment paths, scripts, outputs. Call at session start for orientation.",
        "category": "workspace",
        "inputSchema": {
            "type": "object",
            "properties": {
                "depth": {"type": "number"},
                "include_files": {"type": "boolean"},
            },
        },
    },
    "sys_file_read": {
        "description": "Read a workspace file. Up to 50 MB; use tool_data_sample for larger datasets.",
        "category": "file",
        "inputSchema": {
            "type": "object",
            "properties": {"filepath": {"type": "string"}},
            "required": ["filepath"],
        },
    },
    "sys_file_write": {
        "description": "Write a file. Refuses to write into inputs/raw_data/ or inputs/literature/ (immutable). Use force=true to overwrite a file in synthesis/.",
        "category": "file",
        "inputSchema": {
            "type": "object",
            "properties": {
                "filepath": {"type": "string"},
                "content": {"type": "string"},
                "force": {"type": "boolean"},
            },
            "required": ["filepath", "content"],
        },
    },
    "sys_file_list": {
        "description": "List files in a workspace directory (recursive).",
        "category": "file",
        "inputSchema": {
            "type": "object",
            "properties": {"directory": {"type": "string"}},
            "required": ["directory"],
        },
    },
    "sys_file_delete": {
        "description": "Delete a workspace file or an empty directory.",
        "category": "file",
        "inputSchema": {
            "type": "object",
            "properties": {"filepath": {"type": "string"}},
            "required": ["filepath"],
        },
    },
    "sys_file_validate_md": {
        "description": "Validate a markdown file against the headings/sections expected by a writing protocol.",
        "category": "file",
        "inputSchema": {
            "type": "object",
            "properties": {
                "filepath": {"type": "string"},
                "protocol_name": {"type": "string"},
            },
            "required": ["filepath", "protocol_name"],
        },
    },
    "sys_export_share_archive": {
        "description": (
            "Build a share-safe zip of this project (default: "
            "<project>_share_<YYYY-MM-DD>.zip in the project root). "
            "Excludes AI-internal files (AGENTS.md, CLAUDE.md, .os_state/, "
            ".claude/, MCP configs, GETTING_STARTED.md) and — unless "
            "include_raw_data=true — inputs/raw_data/. Includes inputs/ "
            "(minus raw_data), workspace/, synthesis/, docs/, environment/, "
            "and a top-level README.md if present. Equivalent to running "
            "`python scripts/export_share_archive.py` from the project root."
        ),
        "category": "interaction",
        "inputSchema": {
            "type": "object",
            "properties": {
                "out": {"type": "string",
                        "description": "Optional explicit output zip path."},
                "include_raw_data": {
                    "type": "boolean",
                    "description": "Set true to bundle inputs/raw_data/ (default false to keep archives small and avoid PII)."
                },
            },
        },
    },
    "tool_synthesis_curate_figures": {
        "description": (
            "Collect each step's focal figure into synthesis/figures/ with "
            "stable, ordered names (fig01_<slug>.png, fig02_<slug>.png, …) "
            "so the dashboard + paper can embed them deterministically. "
            "Copies the figure's existing .caption.md sidecar if present, "
            "or seeds a placeholder explaining how to write one. Returns the "
            "list of curated figures plus any step that produced no figures "
            "(to flag in the audit) and any figure missing a caption. Run "
            "BEFORE tool_dashboard / tool_synthesize so the deliverables "
            "use a single canonical figure set rather than scanning the "
            "workspace anew each time."
        ),
        "category": "synthesis",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "tool_path_finalize": {
        "description": (
            "Rewrite a step's stub README + every subfolder README from what "
            "actually got produced. Call this BEFORE marking a step complete: "
            "(a) `environment/README.md` is normalised to either 'used the "
            "project-global env' or a list of bespoke requirements, (b) "
            "`literature/README.md` either points at the global corpus + the "
            "step's decision log or lists the step-specific sources + the "
            "decisions they informed, (c) `data/output/README.md` lists every "
            "persisted artefact and which downstream step consumes it, (d) "
            "`outputs/README.md` enumerates produced figures / tables / "
            "reports, and (e) any stub sections in the step's main `README.md` "
            "are populated from `conclusions.md` + `analysis.md` decisions. "
            "Idempotent — running it a second time is a no-op if nothing "
            "changed. Defaults to the current path."
        ),
        "category": "path",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path_name": {
                    "type": "string",
                    "description": "Step folder name (e.g. '03_replicate_attitude_demographics'). Defaults to current_path.",
                },
            },
        },
    },
    "sys_checkpoint_create": {
        "description": "Snapshot the current workspace (hardlinked, fast). Returns checkpoint_id.",
        "category": "checkpoint",
        "inputSchema": {
            "type": "object",
            "properties": {"description": {"type": "string"}},
        },
    },
    "sys_checkpoint_rollback": {
        "description": "Restore the workspace to a checkpoint. The current state is backed up first.",
        "category": "checkpoint",
        "inputSchema": {
            "type": "object",
            "properties": {"checkpoint_id": {"type": "string"}},
            "required": ["checkpoint_id"],
        },
    },
    "sys_checkpoint_list": {
        "description": "List all checkpoints with descriptions and timestamps.",
        "category": "checkpoint",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "sys_config": {
        "short": "Unified researcher-config tool. operation=get|set|validate.",
        "description": "Unified researcher-config dispatcher for inputs/researcher_config.yaml. operation='get' reads the full config (autonomy level, expertise, model profile, research goal, API keys masked). operation='set' writes a single value via dot notation (e.g. key='researcher.expertise_level', value='advanced'). operation='validate' checks the schema and reports which API keys are present. Every legacy sys_config_get / sys_config_set / sys_config_validate name aliases to this entry point with operation injected via _ALIAS_PARAM_INJECTION so callers using the older per-operation names keep working unchanged.",
        "category": "config",
        "inputSchema": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["get", "set", "validate"],
                    "description": "Which config sub-operation to invoke.",
                },
                # operation='set' kwargs
                "key": {
                    "type": "string",
                    "description": "operation='set' — REQUIRED. Dot-notation key (e.g. 'researcher.expertise_level').",
                },
                "value": {
                    "type": "string",
                    "description": "operation='set' — REQUIRED. New value as a string.",
                },
            },
            "required": ["operation"],
        },
    },
    "sys_notify": {
        "description": "Notify the researcher (logged to workspace/logs/notifications.log).",
        "category": "interaction",
        "inputSchema": {
            "type": "object",
            "properties": {
                "message": {"type": "string"},
                "level": {"type": "string", "description": "info|warn|action_required"},
            },
            "required": ["message", "level"],
        },
    },
    "sys_session_handoff": {
        "description": "Generate a structured markdown handoff describing the project state, last action, and next step. Use at session end.",
        "category": "interaction",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "sys_env": {
        "short": "Unified environment tool. operation=snapshot|docker_generate.",
        "description": "Unified environment dispatcher. operation='snapshot' captures the current Python (and optionally R/Julia) environment — target by step_id='NN_slug' for a per-step snapshot, scope='project' for the eager-scaffolded project-global environment/ folder, or omit both for the legacy default (most-recent numbered step, or project-global when none exist). operation='docker_generate' generates a Dockerfile from the environment snapshot for full reproducibility (run snapshot first). Every legacy sys_env_snapshot / sys_env_docker_generate name aliases to this entry point with operation injected via _ALIAS_PARAM_INJECTION so callers using the older per-operation names keep working unchanged.",
        "category": "environment",
        "inputSchema": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["snapshot", "docker_generate"],
                    "description": "Which environment sub-operation to invoke.",
                },
                # operation='snapshot' kwargs
                "step_id": {
                    "type": "string",
                    "description": "operation='snapshot' — optional. NN_slug of the numbered step to snapshot into. Mutually exclusive with scope.",
                },
                "scope": {
                    "type": "string",
                    "enum": ["project"],
                    "description": "operation='snapshot' — optional. Set to 'project' to snapshot into the project-global environment/ folder.",
                },
            },
            "required": ["operation"],
        },
    },
    "mem_citations_generate": {
        "description": "Refresh workspace/citations.md from inputs/literature_index.yaml.",
        "category": "memory",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "mem_intake_regenerate": {
        "description": "Regenerate inputs/intake.md (file inventory with SHA-256 hashes).",
        "category": "memory",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "sys_dep_inventory": {
        "description": "Report which optional dependencies (search, viz, audit, ml, notebook, literature, web) failed to import. Call once at session start so you know which tools will work.",
        "category": "state",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "tool_cache_clear": {
        "short": "Wipe cached search results (optionally per-provider or older-than-N-days).",
        "description": "Manage the file-backed search cache at .os_state/cache/search/<provider>/. Call when you suspect stale results, or after a long break to free disk. Cache TTL defaults to 24h (configurable via runtime.cache_ttl_seconds).",
        "category": "search",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": "Restrict to one provider (semantic_scholar | crossref | pubmed | arxiv | web). Omit for all.",
                },
                "older_than_days": {
                    "type": "number",
                    "description": "Only delete entries older than this many days. Omit for all entries.",
                },
            },
        },
    },
    "tool_workflow_dag": {
        "short": "Build a DAG of numbered steps + their data dependencies; write docs/workflow_dag.mermaid.",
        "description": "Walks each numbered step's data/input symlinks to derive cross-step dependencies, then writes docs/workflow_dag.mermaid with colour-coded nodes (active / completed / dead_end). Pass render_png=true to also emit a PNG (requires mmdc — npm install -g @mermaid-js/mermaid-cli). Auto-refreshed by sys_path(operation='create') and sys_path(operation='abandon') so the DAG stays in sync without manual calls.",
        "category": "state",
        "inputSchema": {
            "type": "object",
            "properties": {
                "render_png": {"type": "boolean"},
                "output_dir": {
                    "type": "string",
                    "description": "Where to write (default: docs).",
                },
            },
        },
    },
    "sys_path": {
        "short": "Unified path dispatcher. operation='create'|'abandon'|'list'. Replaces sys_path_{create,abandon,list}.",
        "description": "One entry for the three path-lifecycle tools. operation='create' (was sys_path_create) takes name + hypothesis + branch_of. operation='abandon' (was sys_path_abandon) takes path_name + rationale. operation='list' (was sys_path_list) returns all paths with status.",
        "category": "state",
        "inputSchema": {
            "type": "object",
            "properties": {
                "operation": {"type": "string", "enum": ["create", "abandon", "list"]},
                "name": {"type": "string"},
                "hypothesis": {"type": "string"},
                "branch_of": {"type": "string"},
                "from_step": {"type": "string"},
                "allow_unfinalized_predecessor": {"type": "boolean"},
                "override_rationale": {"type": "string"},
                "path_name": {"type": "string"},
                "rationale": {"type": "string"},
            },
            "required": ["operation"],
        },
    },
    "tool_deprecations_summary": {
        "short": "Aggregate counts from .os_state/deprecations.log — which deprecated aliases / redirects this project is still hitting.",
        "description": "Reads .os_state/deprecations.log (populated whenever a deprecated alias is invoked OR a redirect-stub protocol is loaded) and returns aggregated counts by kind/source/target. Use to audit which deprecated names the project still relies on before the next major (when aliases hard-remove).",
        "category": "state",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    "sys_packs_installed": {
    "short": "List installed protocol packs (name, version, tool count, router entries, errors).",
    "description": "Returns the set of protocol packs currently registered with the server — both bundled (humanities, qualitative) and externally pip-installed via the `research_os.protocol_pack` entry-point group. Use to confirm a pack is loadable, to see its tool / router contributions, and to surface any registration errors (full traceback in `workspace/logs/pack_errors.log`).",
    "category": "routing",
    "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
},
    "sys_adapters_installed": {
    "short": "List installed infrastructure adapters (Slurm / Snakemake / Nextflow / Cytoscape / REDCap / Synapse / external).",
    "description": "Returns the set of infrastructure adapters currently registered via the `research_os.adapter` entry-point group. Adapters are pluggable detectors + provenance extractors for HPC schedulers, workflow engines, analysis platforms, and data systems. Use to confirm an adapter is loaded; pair with tool_adapters_list to check detection on the current project.",
    "category": "routing",
    "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
},
    "tool_adapter_extract": {
    "short": "Run one adapter's extract() + write provenance YAML to workspace/<step>/provenance/<adapter>.yaml.",
    "description": "Executes a specific installed adapter against the current project (or one step within it) and persists the extracted provenance as a structured YAML file. Returns the path to the YAML plus a small summary of cardinalities. Idempotent — re-running overwrites the YAML so it always reflects the current filesystem state.",
    "category": "state",
    "inputSchema": {
        "type": "object",
        "properties": {
            "adapter_name": {"type": "string"},
            "step_id": {"type": "string"},
        },
        "required": ["adapter_name"],
    },
},
    "tool_adapters_list": {
    "short": "List adapters + their detection status on the current project (e.g. 'slurm: detected_in_project=true').",
    "description": "Walks every installed adapter, calls its detect(root) callable, and returns the combined status. Detect is cheap (filesystem-only; no network). Use to surface which adapters are relevant before deciding whether to run tool_adapter_extract / tool_adapters_run_all.",
    "category": "state",
    "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
},
    "tool_adapters_run_all": {
    "short": "Run every detected adapter's extract() and write per-adapter provenance YAMLs.",
    "description": "Bulk version of tool_adapter_extract — walks every installed adapter, calls detect(), and runs extract() only on the matches. Writes one provenance/<adapter>.yaml per match. Returns a per-adapter status list.",
    "category": "state",
    "inputSchema": {
        "type": "object",
        "properties": {"step_id": {"type": "string"}},
        "additionalProperties": False,
    },
},
}
