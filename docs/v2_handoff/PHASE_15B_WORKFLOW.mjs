// Phase 15b — Re-validation (20-agent multi-perspective)
// Same 5 scenarios × 4 perspectives as Phase 15a baseline. Measures improvement.

export const meta = {
  name: 'v2-phase-15b-revalidation',
  description: 'Phase 15b: 20-agent multi-perspective re-validation against post-Phase-9/10/14 surface',
  phases: [
    { title: 'Re-validation runs', detail: '20 parallel agents (5 scenarios × 4 perspectives)' },
    { title: 'Synthesis', detail: '1 agent compiles V2_VALIDATION_REPORT.md with delta vs baseline' },
  ],
}

const REPO = '/scratch/vsetlur/Research-OS'
const CONDA = `source /scratch/vsetlur/anaconda3/etc/profile.d/conda.sh && conda activate research-os`

const SCENARIOS = [
  { id: 'biology_rnaseq', desc: 'Biology RNA-seq DE (R Bioconductor + Python scanpy, GEO accession)' },
  { id: 'humanities_close_reading', desc: 'Humanities close-reading (Gutenberg corpus, humanities_essay output)' },
  { id: 'qualitative_interviews', desc: 'Qualitative interviews (8 synthetic participants, PII redaction)' },
  { id: 'engineering_benchmark', desc: 'Engineering benchmark (3 algorithms × 5 sizes × 10 runs)' },
  { id: 'theory_math_proof', desc: 'Theory/math proof (graph-theory conjecture, theory_math pack)' },
]

const PERSPECTIVES = [
  { id: 'naive_ai', desc: 'Fresh agent, MCP-client surface only, no src/ access' },
  { id: 'researcher', desc: 'Natural-language requests, observes AI behavior' },
  { id: 'auditor', desc: 'Reads every artifact + audit log, checks rigor' },
  { id: 'maintainer', desc: 'Watches for tool sprawl, unclear errors, protocol routing failures' },
]

const SCHEMA = {
  type: 'object',
  required: ['scenario','perspective','final_rating','high_friction_count','first_5_turns_high_friction','every_deliverable_produced'],
  properties: {
    scenario: {type:'string'},
    perspective: {type:'string'},
    final_rating: {type:'number', minimum:0, maximum:10},
    high_friction_count: {type:'integer'},
    first_5_turns_high_friction: {type:'integer'},
    every_deliverable_produced: {type:'boolean'},
    friction_items: {type:'array', items:{type:'object',properties:{severity:{type:'string'},category:{type:'string'},description:{type:'string'}},required:['severity','category','description']}},
    convoluted_tools: {type:'array', items:{type:'string'}},
    confusing_protocols: {type:'array', items:{type:'string'}},
    never_called_tools: {type:'array', items:{type:'string'}},
    improvements_vs_baseline: {type:'array', items:{type:'string'}},
    remaining_recommendations: {type:'array', items:{type:'string'}},
  },
}

phase('Re-validation runs')

const runs = []
for (const s of SCENARIOS) {
  for (const p of PERSPECTIVES) {
    runs.push({ s, p })
  }
}

const reports = await parallel(
  runs.map(({s,p}) => () =>
    agent(
      `You are running Phase 15b re-validation for scenario="${s.id}" + perspective="${p.id}".

CWD: ${REPO}
Branch: feat/v2.0.0
Conda env: ${CONDA}

CONTEXT
=======
Phase 15a baseline measured this same (scenario, perspective) and saved a JSON report at:
  \`docs/v2_handoff/validation_baseline/${s.id}__${p.id}.json\`
Read it FIRST to understand prior friction and prior rating.

Phase 9 has since CONSOLIDATED 80-100 tools into ~15 unified tools, with backward-compat aliases. Phase 10 has REFACTORED server.py into a modular package. Phase 14 has REMOVED dead code. The MCP surface should now be substantially leaner.

The CURRENT TOOL SURFACE (as the AI client sees it) should reflect:
- Fewer top-level tool names (consolidation)
- New \`status: live|alias|deprecated\` field on every tool def
- New \`pack: core|<pack>\` field on every tool def
- \`scope_tags: {domain, audience, workflow_shape}\` on every protocol
- \`sys_protocol_get\` default format now "summary" (was "full")
- MCP \`instructions\` field naming the boot sequence
- \`recommended_action\` field in \`tool_route\` output
- \`why_matched\` field (from Phase 11a, already present)

YOUR JOB
========
Run the same 4-turn mini-project for \`${s.id}\` from the perspective of \`${p.id}\`:
  ${s.desc}
  ${p.desc}

Run in /tmp/ro_v2_validation/${s.id}_${p.id}/.

The 4-turn structure (same as Phase 15a):
1. Discover (e.g. tool_route, sys_protocol_get) — observe surface-area friction
2. Plan / Methodology — observe protocol guidance friction
3. Execute (e.g. tool_step, analyses) — observe tool execution friction
4. Synthesize / Audit — observe synthesis pipeline friction (if perspective reaches synthesis)

REPORT BACK (StructuredOutput)
==============================
A SINGLE JSON object matching this schema:
${JSON.stringify(SCHEMA, null, 2)}

WRITE the JSON object to: \`docs/v2_handoff/validation_revalidation/${s.id}__${p.id}.json\` (mkdir -p first).

CONSTRAINTS
===========
- NO RATING PADDING. If the surface still feels bloated, rate it accordingly. If consolidation moved the needle, the rating should reflect that — but only as much as the actual experience supports.
- \`improvements_vs_baseline\`: explicit list of what got BETTER vs the Phase 15a baseline you read first.
- \`remaining_recommendations\`: what STILL needs work in v2.1.0.
- Run in /tmp, do not modify the repo.
- DO NOT commit anything.`,
      { label: `${s.id}:${p.id}`, phase: 'Re-validation runs' }
    )
  )
)

phase('Synthesis')

const synth = await agent(
  `Phase 15b synthesis pass — write the consolidated validation report.

CWD: ${REPO}
Branch: feat/v2.0.0
Conda env: ${CONDA}

CONTEXT
=======
20 agents have just completed Phase 15b re-validation, each writing one JSON file to:
  \`docs/v2_handoff/validation_revalidation/<scenario>__<perspective>.json\`

Phase 15a baseline JSONs are at:
  \`docs/v2_handoff/validation_baseline/<scenario>__<perspective>.json\`

YOUR JOB
========
Write \`docs/V2_VALIDATION_REPORT.md\` with:

1. **Executive summary** (1 paragraph): baseline avg rating → re-validation avg rating; baseline HIGH-friction total → re-validation HIGH-friction total; pass/fail vs v2.0.0 targets (avg ≥9.5, HIGH ≤5 total, first-5-turn HIGH = 0, every deliverable produced, all 4 perspectives ≥9.0).

2. **Matrix table** (4×5 perspective × scenario): cell = "baseline → revalidation" rating delta.

3. **Improvements** (bulleted list): unique items from \`improvements_vs_baseline\` across all 20 runs.

4. **Remaining gaps** (bulleted list): unique items from \`remaining_recommendations\` across all 20 runs. Tag each with [v2.0.1 patch] | [v2.1.0 minor] | [v3.0.0 major] based on severity.

5. **Target check**: were the v2.0.0 release gate targets met?
   - Avg final_rating ≥ 9.5? (yes/no, actual value)
   - Total HIGH friction ≤ 5? (yes/no, actual value)
   - First-5-turn HIGH = 0? (yes/no, actual value)
   - Every deliverable produced? (yes/no)
   - All 4 perspectives ≥ 9.0? (yes/no, actual)
   - No tool flagged convoluted in 3+ runs? (yes/no, list)
   - No protocol flagged confusing in 3+ runs? (yes/no, list)

6. **Recommendation**:
   - If ALL targets met: GREEN — proceed to Phase 16 release.
   - If 1-2 targets missed by small margins: YELLOW — proceed with a documented caveat in CHANGELOG.
   - If many targets missed: RED — recommend a targeted fix pass + re-run.

REPORT BACK (to me, the parent)
================================
- Path to V2_VALIDATION_REPORT.md (you wrote it).
- Headline numbers (baseline → revalidation).
- GREEN/YELLOW/RED recommendation.
- Top 5 improvements + top 5 remaining gaps.`,
  { label: 'synthesis', phase: 'Synthesis' }
)

return {
  per_run_reports: reports.filter(Boolean).length,
  synthesis: synth,
}
