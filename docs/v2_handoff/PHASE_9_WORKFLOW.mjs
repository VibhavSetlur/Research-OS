// Phase 9 — Tool Consolidation
// Run 9 parallel cluster agents, then 1 cross-cutting agent for annotations.

export const meta = {
  name: 'v2-phase-9-consolidation',
  description: 'Tool consolidation: 9 cluster agents (audit, dashboard, step, lessons/reliability, sensitivity, preregister, reviewer, slurm, data/figure/thought) + cross-cutting annotations',
  phases: [
    { title: 'Cluster consolidation', detail: '9 parallel family-collapse agents' },
    { title: 'Cross-cutting annotations', detail: 'status + pack + scope_tags + MCP instructions + recommended_action + summary defaults' },
  ],
}

const REPO = '/scratch/vsetlur/Research-OS'
const CONDA = `source /scratch/vsetlur/anaconda3/etc/profile.d/conda.sh && conda activate research-os`

const COMMON_RULES = `
CWD: ${REPO}
Branch: feat/v2.0.0
Conda env: ${CONDA}

GROUND-RULES (apply to EVERY consolidation agent)
=================================================
1. The codebase already has consolidation machinery:
   - \`TOOL_DEFINITIONS\` (line ~204 of server.py): dict {tool_name: schema}
   - \`_HANDLERS\` (~line 2985): dict {tool_name: handler_fn}
   - \`_ALIASES\` (~line 6968): {old_name: canonical_name}
   - \`_DEPRECATED_ALIASES\` (set, ~line 7009): old names that should fire telemetry on use
   - \`_ALIAS_PARAM_INJECTION\` (~line 7020): {old_name: (kwarg, value)}
   - \`_REMOVED_TOOLS\` (~line 7104): {old_name: error_message}
2. PRESERVE every legacy behavior. Each old tool's exact (name, args, output) MUST keep working through the alias dispatch.
3. The new unified tool gets a clear inputSchema with the dispatch kwarg first, then all the other kwargs as a union. Old positional args MUST still work via injection.
4. For each old → new mapping:
   a. Add \`_ALIASES["old_name"] = "new_name"\`
   b. Add \`"old_name"\` to \`_DEPRECATED_ALIASES\`
   c. Add \`_ALIAS_PARAM_INJECTION["old_name"] = ("kwarg", "value")\`
   d. REMOVE the old TOOL_DEFINITIONS entry
   e. REMOVE the old _HANDLERS entry (handler fn can stay if it's the new dispatcher's worker)
5. Update \`docs/V2_MIGRATION_TABLE.md\` (create if absent) with one row per consolidation:
   \`| old_name | new_name | dispatch_kwarg | value | status |\` where status = "aliased v2.0.x, removed v2.1.0".
6. Add a CHANGELOG \`### Changed\` bullet under v2.0.0 for this consolidation.
7. Run after every edit batch:
   \`${CONDA} && python scripts/preflight.py && python -m pytest -q\`
8. ONE commit at the end with a tight conventional message: \`feat(v2): consolidate <family> [phase-9-c<N>]\`.
9. DO NOT touch any other family's tools.
10. DO NOT touch pack-installed tools (research_os_humanities/qualitative/theory_math/wet_lab/engineering or adapters). Those are owned by their packs.
11. Read the PHASE_9_PLAN.md at \`docs/v2_handoff/PHASE_9_PLAN.md\` for context.

REPORT BACK
===========
- Old tool count, new tool count, net reduction.
- Sample 2 of the new tool calls (e.g. \`tool_audit(scope="step", dimension="completeness")\`)
- Number of \`_ALIASES\` rows added.
- Pytest + preflight results.
- The commit SHA.
- Any legacy tool that genuinely could NOT be aliased (would need a deprecation path) — list with rationale.
`

const CLUSTERS = [
  {
    id: 'c1-audit',
    label: 'C1 audit family (26 → 3)',
    instructions: `
CLUSTER C1 — AUDIT FAMILY (26 → 3)
====================================
Consolidate ALL \`tool_audit_*\` into:
- \`tool_audit(scope, dimension, **kwargs)\` — the workhorse single-dimension audit
- \`tool_audit_findings(operation="query"|"diff", **kwargs)\` — the findings query/diff tool (already mostly there)
- \`tool_audit_quality_full(**kwargs)\` — KEEP as the canonical aggregator (don't fold in)

The 23 to alias into tool_audit:
- tool_audit_assumptions  → tool_audit(scope="step", dimension="assumptions")
- tool_audit_citations    → tool_audit(scope="project", dimension="citations")
- tool_audit_claims       → tool_audit(scope="project", dimension="claims")
- tool_audit_cliches      → tool_audit(scope="project", dimension="cliches")
- tool_audit_code_quality → tool_audit(scope="step", dimension="code_quality")
- tool_audit_coherence    → tool_audit(scope="project", dimension="coherence")
- tool_audit_cross_deliverable_consistency → tool_audit(scope="project", dimension="cross_deliverable")
- tool_audit_dashboard_content → tool_audit(scope="synthesis", dimension="dashboard_content")
- tool_audit_evalue       → tool_audit(scope="step", dimension="evalue")
- tool_audit_figure       → tool_audit(scope="step", dimension="figure")
- tool_audit_figure_coverage → tool_audit(scope="synthesis", dimension="figure_coverage")
- tool_audit_figure_full  → tool_audit(scope="step", dimension="figure_full")
- tool_audit_figure_interactivity → tool_audit(scope="step", dimension="figure_interactivity")
- tool_audit_figure_quality (already alias of figure_full — leave as-is)
- tool_audit_power        → tool_audit(scope="step", dimension="power")
- tool_audit_prose        → tool_audit(scope="project", dimension="prose")
- tool_audit_reproducibility → tool_audit(scope="step", dimension="reproducibility")
- tool_audit_reviewer_responses → tool_audit(scope="synthesis", dimension="reviewer_responses")
- tool_audit_statistical_power (already alias of power — leave as-is)
- tool_audit_step_completeness → tool_audit(scope="step", dimension="completeness")
- tool_audit_step_literature → tool_audit(scope="step", dimension="literature")
- tool_audit_synthesis    → tool_audit(scope="synthesis", dimension="all")
- tool_audit_version_coherence → tool_audit(scope="project", dimension="version_coherence")

The 2 to alias into tool_audit_findings:
- tool_audit_findings_query → tool_audit_findings(operation="query")
- tool_audit_findings_diff  → tool_audit_findings(operation="diff")

Implementation note: the new \`_handle_tool_audit\` dispatcher simply reads scope+dimension and routes to the existing per-dimension handler functions (which become private). Don't rewrite the audit logic; just unify the entry point.
${COMMON_RULES}`,
  },
  {
    id: 'c2-dashboard',
    label: 'C2 dashboard (7 → 1)',
    instructions: `
CLUSTER C2 — DASHBOARD (7 → 1)
================================
Consolidate ALL \`tool_dashboard_*\` into \`tool_dashboard(operation, **kwargs)\`:
- tool_dashboard_create        → tool_dashboard(operation="create")
- tool_dashboard_story_generate → tool_dashboard(operation="story_generate")
- tool_dashboard_story_edit    → tool_dashboard(operation="story_edit")
- tool_dashboard_story_quality_bar → tool_dashboard(operation="story_quality_bar")
- tool_dashboard_reviewer_sim  → tool_dashboard(operation="reviewer_sim")
- tool_dashboard_test_generate → tool_dashboard(operation="test_generate")
- tool_dashboard_test_run      → tool_dashboard(operation="test_run")
${COMMON_RULES}`,
  },
  {
    id: 'c3-step',
    label: 'C3 step + step_pipeline (10 → 2)',
    instructions: `
CLUSTER C3 — STEP + STEP_PIPELINE (10 → 2)
============================================
Consolidate \`tool_step_*\` into:
- \`tool_step(operation, **kwargs)\` — for create/complete/iterate/env_lock/promote_to_step/iterations_list/revision_options
- \`tool_step_pipeline(operation, **kwargs)\` — for define/run/status/diagram

EXCLUDE: tool_step_complete (it's already a top-level workflow primitive; keep its name).
EXCLUDE: tool_step_env_lock (consider whether to fold — if it's called frequently as a standalone, keep it; otherwise fold into tool_step(operation="env_lock")).

Read \`grep -n '"tool_step_' src/research_os/server.py\` to enumerate. Cluster accordingly.
${COMMON_RULES}`,
  },
  {
    id: 'c4-lessons-reliability',
    label: 'C4 lessons + reliability + failure + dead_end + mistake (≈10 → 2)',
    instructions: `
CLUSTER C4 — LESSONS + RELIABILITY (≈10 → 2)
==============================================
Consolidate the entire "what went wrong / what did we learn" family.

Already aliased: tool_lessons_record/consult → tool_lessons. KEEP and extend.
Extend \`tool_lessons(operation, **kwargs)\` to cover:
- tool_lessons_record (existing alias) → tool_lessons(operation="record")
- tool_lessons_consult (existing alias) → tool_lessons(operation="consult")
- tool_failure_record  → tool_lessons(operation="failure_record")
- tool_failure_check   → tool_lessons(operation="failure_check")
- tool_failure_list    → tool_lessons(operation="failure_list")
- tool_dead_end_lessons → tool_lessons(operation="dead_end")
- tool_mistake_replay  → tool_lessons(operation="mistake_replay")

Keep \`tool_reliability(operation, **kwargs)\` separate:
- tool_reliability_log_event → tool_reliability(operation="log_event")
- tool_reliability_report    → tool_reliability(operation="report")
${COMMON_RULES}`,
  },
  {
    id: 'c5-sensitivity-preregister',
    label: 'C5 sensitivity + preregister (4 → 2)',
    instructions: `
CLUSTER C5 — SENSITIVITY + PREREGISTER (4 → 2)
================================================
- tool_sensitivity_define → tool_sensitivity(operation="define")
- tool_sensitivity_run    → tool_sensitivity(operation="run")
- tool_preregister_freeze → tool_preregister(operation="freeze")
- tool_preregister_diff   → tool_preregister(operation="diff")
${COMMON_RULES}`,
  },
  {
    id: 'c6-reviewer',
    label: 'C6 reviewer (4 → 1)',
    instructions: `
CLUSTER C6 — REVIEWER (4 → 1)
==============================
Consolidate the reviewer family into \`tool_reviewer(operation, **kwargs)\`:
- tool_reviewer_simulate         → tool_reviewer(operation="simulate")
- tool_response_to_reviewers     → tool_reviewer(operation="response")
- tool_rebuttal_draft            → tool_reviewer(operation="rebuttal")
- tool_reviewer_response_compile → tool_reviewer(operation="compile")
${COMMON_RULES}`,
  },
  {
    id: 'c7-data-figure-thought',
    label: 'C7 data + figure + thought (7 → 3)',
    instructions: `
CLUSTER C7 — DATA + FIGURE + THOUGHT (7 → 3)
==============================================
- tool_data_convert  → tool_data(operation="convert")
- tool_data_profile  → tool_data(operation="profile")
- tool_data_sample   → tool_data(operation="sample")

- tool_figure_palette            → tool_figure(operation="palette")
- tool_figure_caption_synthesise → tool_figure(operation="caption_synthesise")
- tool_figure_interactive_autogen → tool_figure(operation="interactive_autogen")
- tool_paper_figures_autoembed   → tool_figure(operation="paper_autoembed")  // OR keep separate if it's actually a paper-level concept; use judgment.

- tool_thought_log   → tool_thought(operation="log")
- tool_thought_trace → tool_thought(operation="trace")
${COMMON_RULES}`,
  },
  {
    id: 'c8-search-quick-scratch-task',
    label: 'C8 search + quick + scratch + task (already partly done; finalize misc)',
    instructions: `
CLUSTER C8 — MISC FAMILIES (audit remaining clusters)
=======================================================
search is already consolidated. quick/scratch/task families have 2-4 tools each.

For each \`*_<verb>\` family with ≥2 tools:
1. Inspect with \`grep -oP '"tool_<family>_[a-z_]+"' src/research_os/server.py | sort -u\`
2. If it's a natural family with a shared concept (e.g. tool_quick_*), consolidate into one with operation kwarg.
3. If it's truly heterogeneous (e.g. tool_search_* covers different providers — already consolidated), skip.

Specifically address:
- tool_quick_* (2): check if consolidatable
- tool_scratch_* (4): consolidate into tool_scratch(operation=...)
- tool_task_* (4): consolidate into tool_task(operation=...)

DO NOT touch search, plan, ground, lessons, path, mem (already consolidated).
${COMMON_RULES}`,
  },
  {
    id: 'c9-sys-cross-cutting',
    label: 'C9 sys_* consolidation (read+report; do not over-collapse)',
    instructions: `
CLUSTER C9 — SYS_* CONSOLIDATION (judgment pass)
==================================================
\`sys_*\` tools are MCP-level / project-state primitives. They should mostly stay separate because each is a distinct operation type. But review for over-fragmentation:

- sys_state_*: state read/write — keep separate (already consolidated)
- sys_protocol_*: protocol metadata — keep separate; these are the discovery surface
- sys_workspace_*: workspace scaffolding — review for consolidation
- sys_active_tools, sys_boot, sys_protocol_get, sys_tool_describe, sys_help: KEEP — top-of-funnel discovery, AIs need clarity
- sys_env_*: env snapshot/docker — consolidate if ≥2 with shared semantics
- sys_session_handoff, sys_checkpoint_rollback, sys_export_share_archive: KEEP separate (distinct operations)

For each candidate family:
1. Inspect.
2. If consolidation reduces friction without hiding discovery, DO IT.
3. If consolidation would hide a primitive the AI needs to find, LEAVE IT.

Report your judgment + rationale per family. DO NOT consolidate just to reduce count.
${COMMON_RULES}`,
  },
]

phase('Cluster consolidation')

// SERIAL: each cluster touches the same dict literals in server.py
// (TOOL_DEFINITIONS, _HANDLERS, _ALIASES, _DEPRECATED_ALIASES, _ALIAS_PARAM_INJECTION).
// Running them in parallel would cause edit collisions. We trade wall-clock for safety.
const clusterResults = []
for (const c of CLUSTERS) {
  const result = await agent(c.instructions, { label: c.id, phase: 'Cluster consolidation' })
  clusterResults.push(result)
  log(`cluster ${c.id} complete — moving to next`)
}

// Cross-cutting annotations + cheap MCP wins — run sequentially after clusters
phase('Cross-cutting annotations')

const annotationsReport = await agent(
  `Phase 9 cross-cutting pass — runs AFTER the 9 cluster consolidations.

CWD: ${REPO}
Branch: feat/v2.0.0
Conda env: ${CONDA}

CONTEXT
=======
The 9 cluster agents have just collapsed ~80-100 tools into ~15 consolidated tools via the existing _ALIASES / _DEPRECATED_ALIASES / _ALIAS_PARAM_INJECTION machinery. The TOOL_DEFINITIONS dict is now ~80 entries smaller.

YOUR JOB — 6 INDEPENDENT EDITS
================================
1. **Add \`status: live|alias|deprecated\` field** to every TOOL_DEFINITIONS entry.
   - Active canonical tools: status="live"
   - Any name in _DEPRECATED_ALIASES that ALSO has a TOOL_DEFINITIONS entry: status="alias"
   - Anything tagged in _REMOVED_TOOLS but somehow still in TOOL_DEFINITIONS: status="deprecated" (and fix the bug)
   - Add the field to the inputSchema docs string too.

2. **Add \`pack: <name>\` field** to every TOOL_DEFINITIONS entry.
   - Core tools (defined in server.py before pack discovery): pack="core"
   - Pack tools registered via _discover_packs_once: the pack registration code should set pack=<pack_name> at registration time. Patch \`src/research_os/plugins.py\` (or wherever discover_packs lives) to inject the pack name.

3. **Add \`scope_tags: {domain: [...], audience: [...], workflow_shape: [...]}\` to every protocol YAML.**
   - Iterate every yaml under \`src/research_os/protocols/\` (~117 files).
   - Infer scope_tags from filename + content + existing tier annotation:
     - domain: ["biology","humanities","qualitative","theory_math","wet_lab","engineering"] or ["any"]
     - audience: ["naive_ai","researcher","auditor","maintainer"] or ["any"]
     - workflow_shape: ["experiment_pipeline","linear_essay","systems_benchmark","proof","interview_study"] or ["any"]
   - Best-effort inference; default "any" when uncertain. The router will use these to filter.

4. **Flip \`sys_protocol_get\` default \`format\` from "full" to "summary"** (single biggest token-cost win per the baseline).
   - Edit the inputSchema default + the handler default.
   - Add a CHANGELOG \`### Changed\` bullet noting this MAJOR-breaking change.
   - Update docs/AI_GUIDE.md to mention the new default.

5. **Add MCP \`instructions\` field** to the server initialization handshake.
   Content: "On every turn: (1) call sys_boot once per session, (2) call tool_route(prompt=<user_message>) to identify the right protocol, (3) load returned protocol with sys_protocol_get format=summary, (4) call sys_active_tools to scope your working tool set. Pack tools are loaded on-demand via tool_route routing."
   - Find the MCP \`Server\` instantiation in server.py (or in the new server/entry.py post-Phase-10).
   - Set the \`instructions=...\` arg.

6. **Add \`recommended_action\` field to \`tool_route\` output.**
   - Currently tool_route returns method/confidence/matched_protocols. Add a top-level \`recommended_action\` string that names exactly which next tool to call (typically sys_protocol_get for the top match).
   - Edit \`_handle_tool_route\` and \`_handle_tool_semantic_route\` if separate.

CONSTRAINTS
===========
- DO NOT touch the consolidated tools — those just landed via cluster agents.
- DO NOT modify any handler logic. This is annotation + 2 cheap MCP wins.
- Single commit at end: \`feat(v2): status+pack+scope_tags annotations + MCP instructions + summary default [phase-9-cross-cutting]\`.
- Verify with \`${CONDA} && python scripts/preflight.py && python -m pytest -q\`.

REPORT BACK
===========
- Count of TOOL_DEFINITIONS entries annotated with status + pack.
- Count of protocol yamls annotated with scope_tags.
- Was the MCP instructions field added? Which file?
- Was sys_protocol_get default flipped? Did any test break?
- Was recommended_action added to tool_route output?
- Pytest + preflight status.
- The commit SHA.`,
  { label: 'cross-cutting', phase: 'Cross-cutting annotations' }
)

return {
  clusters: clusterResults.filter(Boolean),
  crossCutting: annotationsReport,
  counts: {
    clusters_completed: clusterResults.filter(Boolean).length,
  },
}
