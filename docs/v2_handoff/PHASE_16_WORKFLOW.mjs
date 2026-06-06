// Phase 16 — Final docs + migration guide + 2.0.0 release prep
// 4 parallel docs agents + 1 sequential version bump/release-prep agent

export const meta = {
  name: 'v2-phase-16-release-prep',
  description: 'Phase 16: refresh docs, write migration guide + release notes, finalize CHANGELOG, bump 2.0.0-dev → 2.0.0, verify wheel — NO PUSH',
  phases: [
    { title: 'Docs refresh + migration', detail: '4 parallel agents — README/START/AI_GUIDE, RESEARCHER/FAQ/PROTOCOLS/TOOLS/CONTRACT, MIGRATION_v1_to_v2, V2_RELEASE_NOTES' },
    { title: 'CHANGELOG + version bump + wheel sanity', detail: 'one final agent prepares the release artifact (no auto-push)' },
  ],
}

const REPO = '/scratch/vsetlur/Research-OS'
const CONDA = `source /scratch/vsetlur/anaconda3/etc/profile.d/conda.sh && conda activate research-os`

const COMMON = `
CWD: ${REPO}
Branch: feat/v2.0.0
Conda env: ${CONDA}

CONTEXT
=======
All of Phase 9, 10, 14, 15b have landed. The Phase 15b validation report at
docs/V2_VALIDATION_REPORT.md shows YELLOW recommendation (6.35 → 7.70 avg,
HIGH friction 124 → 63, all 20 cells improved, no regressions, but absolute
v3-grade targets not met — ship with caveats).

Scaffold drafts you can read (NOT publish as-is — refine them):
- docs/v2_handoff/CHANGELOG_v2_SCAFFOLD.diff
- docs/v2_handoff/MIGRATION_v1_to_v2_SCAFFOLD.md
- docs/v2_handoff/V2_RELEASE_NOTES_SCAFFOLD.md
- docs/v2_handoff/V2_MIGRATION_TABLE_SCAFFOLD.md
- docs/v2_handoff/PHASE_16_PLAN.md

Authoritative inputs to draw from:
- docs/V2_VALIDATION_REPORT.md (Phase 15b results)
- docs/V2_MIGRATION_TABLE.md (Phase 9 + 14 produced this)
- docs/V2_PACK_COMPLETENESS_MATRIX.md (Phase 12)
- docs/V2_IDE_VALIDATION_REPORT.md (Phase 13)
- docs/V2_VALIDATION_REPORT_BASELINE.md (Phase 15a baseline)
- CHANGELOG.md (Phase 9 + 14 agents added Added/Changed/Deprecated/Removed)
- git log --grep 'phase-' for the full per-phase commit history

GROUND RULES
============
- DO NOT auto-tag, push, or merge to main. This is release PREP, not release.
- DO NOT change tool surface or handler logic. Docs + version bump only.
- Single commit per agent at the end with a clear conventional message.
- After each commit, verify with: ${CONDA} && python scripts/preflight.py && python -m pytest -q -x --tb=no
- If preflight or pytest break, FIX or revert and report.
`

phase('Docs refresh + migration')

const AGENTS = [
  {
    id: '16a',
    label: '16a refresh README + START + AI_GUIDE',
    instructions: `Phase 16a — refresh top-of-funnel docs for v2.0.0.

YOUR DOCS (re-write each as if a fresh user just landed):
- README.md — post-consolidation badges, counts, quickstart with NEW tool names (tool_audit, tool_dashboard, etc.). Remove any v1.x narration.
- docs/START.md — fresh walkthrough using post-Phase-13 CLI surface (research-os init / start / ide list / doctor + new \`ide config-path\` subcommand). 4-step quickstart at top.
- docs/AI_GUIDE.md — post-consolidation tool surface; explain the MCP \`instructions\` field + sys_protocol_get summary default + tool_route recommended_action. Keep it terse and AI-friendly (this is what the AI loads on first turn).

CONTEXT KEYS TO REFLECT
=======================
- 146 live tools (down from 344)
- MCP initialize handshake now ships an \`instructions\` field with the boot sequence
- sys_protocol_get default format is \`summary\` (~3K chars vs ~12-25K)
- tool_route returns recommended_action + why_matched + tier
- Every tool has status: live|alias|deprecated + pack: core|<pack>
- Every protocol has scope_tags: {domain, audience, workflow_shape} + tier:

DO NOT update CHANGELOG (16d does that), MIGRATION_v1_to_v2.md (16b), or V2_RELEASE_NOTES.md (16c).
DO NOT touch other docs or src.

Commit: \`docs(v2): refresh README + START + AI_GUIDE for v2.0.0 [phase-16a]\`
${COMMON}
REPORT: paths of files edited, line-count deltas, any TBD items.`,
  },
  {
    id: '16b',
    label: '16b MIGRATION_v1_to_v2.md (from scaffold + table)',
    instructions: `Phase 16b — write docs/MIGRATION_v1_to_v2.md (final, replacing scaffold).

INPUTS:
- docs/v2_handoff/MIGRATION_v1_to_v2_SCAFFOLD.md (start here)
- docs/V2_MIGRATION_TABLE.md (full old→new rows from Phase 9 + 14)
- docs/V2_VALIDATION_REPORT.md (for the upgrade-impact summary)
- CHANGELOG.md (Removed section from Phase 14)

DELIVERABLE
===========
A single docs/MIGRATION_v1_to_v2.md (the scaffold sibling SCAFFOLD.md stays as draft). Shape:
1. "Upgrade in 5 steps" recipe at the top (concrete commands).
2. Breaking changes section with each MAJOR-bumped surface (sys_protocol_get default, consolidated tools, removed names) — copy + refine from CHANGELOG Changed/Removed.
3. Tool migration table — append the FULL table from docs/V2_MIGRATION_TABLE.md (don't just link; copy in for one-stop-shop reading).
4. Per-pack notes section (humanities / qualitative / theory_math / wet_lab / engineering) — flag any pack-specific call site changes.
5. Config field changes — anything Phase 14e removed.
6. New surface in v2.0.0 (additive — won't break) — bulleted from CHANGELOG Added.
7. Link to docs/V2_RELEASE_NOTES.md for the celebratory version.

DO NOT touch other docs or src.

Commit: \`docs(v2): MIGRATION_v1_to_v2.md final [phase-16b]\`
${COMMON}
REPORT: line count, number of migration table rows pulled in, anything TBD.`,
  },
  {
    id: '16c',
    label: '16c V2_RELEASE_NOTES.md (from scaffold + validation)',
    instructions: `Phase 16c — write docs/V2_RELEASE_NOTES.md (final, replacing scaffold).

INPUTS:
- docs/v2_handoff/V2_RELEASE_NOTES_SCAFFOLD.md (start here)
- docs/V2_VALIDATION_REPORT.md (Phase 15b numbers)
- docs/V2_VALIDATION_REPORT_BASELINE.md (Phase 15a numbers for delta)
- docs/V2_MIGRATION_TABLE.md
- CHANGELOG.md
- git log --grep 'phase-' --oneline (for the commit map)

DELIVERABLE
===========
A single docs/V2_RELEASE_NOTES.md. Shape:
1. TL;DR — 1 paragraph summary with the headline numbers (baseline 6.35 → revalidation 7.70 etc.)
2. Headline numbers table (baseline / v2.0.0 / delta).
3. 5 CRAFT-inspired additions (audit-as-data, drafter loops, doctor, CONTRACT.md, audience-segmented docs).
4. Tool surface consolidation table (family / old count / new dispatcher).
5. Cross-cutting wins (sys_protocol_get default, MCP instructions, tool_route fields, status/pack/scope_tags annotations).
6. server.py refactor summary (8061 → 32 modules ≤600 lines).
7. Validation matrix (4 perspectives × 5 scenarios; baseline → revalidation cells).
8. YELLOW caveat (link to V2_VALIDATION_REPORT.md for details + the v2.0.1 BLOCKER fixes that already landed).
9. Deferred to v2.0.1 / v2.1.0 / v3.0.0 (sourced from the V2_VALIDATION_REPORT remaining recommendations).
10. Upgrade pointer to docs/MIGRATION_v1_to_v2.md.

DO NOT touch other docs or src.

Commit: \`docs(v2): V2_RELEASE_NOTES.md final [phase-16c]\`
${COMMON}
REPORT: line count, anything TBD, headline numbers used.`,
  },
  {
    id: '16d',
    label: '16d refresh RESEARCHER_GUIDE + FAQ + PROTOCOLS + TOOLS + CONTRACT',
    instructions: `Phase 16d — refresh the second tier of docs for v2.0.0.

YOUR DOCS:
- docs/RESEARCHER_GUIDE.md — researcher-facing prose, post-consolidation tool names
- docs/FAQ.md — common questions, update tool names + add new v2.0.0 features
- docs/PROTOCOLS.md — post-router improvements + tier annotations + scope_tags
- docs/TOOLS.md — post-consolidation list, alphabetical by canonical name; aliases as cross-references
- docs/CONTRACT.md — finalize for v2.0.0 stable surface; freeze for the release

CONTEXT KEYS
============
- Live tools: 146 (down from 344)
- 117 protocols, all tier-annotated, all scope_tags
- New consolidated entry points: tool_audit, tool_dashboard, tool_step, tool_step_pipeline,
  tool_lessons, tool_reliability, tool_sensitivity, tool_preregister, tool_reviewer,
  tool_data, tool_figure, tool_thought
- Existing consolidated entry points (kept from v1.6.x): tool_search, tool_plan, tool_ground,
  tool_verify, mem_log, sys_path
- New discovery tools: tool_protocols_list, tool_tools_list
- New diagnostic: research-os doctor

DO NOT update README/START/AI_GUIDE (16a), MIGRATION (16b), RELEASE_NOTES (16c), or CHANGELOG (16e).

Commit: \`docs(v2): refresh RESEARCHER_GUIDE + FAQ + PROTOCOLS + TOOLS + CONTRACT for v2.0.0 [phase-16d]\`
${COMMON}
REPORT: paths edited, line-count deltas, anything TBD.`,
  },
]

const docsResults = []
for (const a of AGENTS) {
  const r = await agent(a.instructions, { label: a.id, phase: 'Docs refresh + migration' })
  docsResults.push(r)
  log(`${a.id} complete`)
}

phase('CHANGELOG + version bump + wheel sanity')

const releaseResult = await agent(
  `Phase 16e — finalize CHANGELOG + version bump 2.0.0-dev → 2.0.0 + wheel sanity + PR-prep summary. NO PUSH.

CWD: ${REPO}
Branch: feat/v2.0.0
Conda env: ${CONDA}

CONTEXT
=======
All of Phase 16a–16d have landed (4 docs commits). CHANGELOG.md has been
populated by Phase 9 + 14 agents but you should finalize the [Unreleased — v2.0.0]
header → [2.0.0] — (2026-06-06) header AND verify the Highlights paragraph
matches the V2_RELEASE_NOTES.md tone.

TASKS (in this order)
======================

1. **CHANGELOG finalize**: bump \`[Unreleased — v2.0.0]\` to \`[2.0.0] — release-prep (2026-06-06)\`. Ensure the Highlights, Added, Changed, Deprecated, Removed, Fixed, and Validation sections are filled in coherently. Cross-link \`docs/V2_VALIDATION_REPORT.md\` and \`docs/MIGRATION_v1_to_v2.md\` and \`docs/V2_RELEASE_NOTES.md\`. Add a short note that the 2 v2.0.1 BLOCKERS from Phase 15b were fixed in commits 0c45b79 + b3b24a0.

2. **Version bump**: edit these three files to set version 2.0.0:
   - \`pyproject.toml\`: \`version = "2.0.0"\`
   - \`src/research_os/__init__.py\`: \`__version__ = "2.0.0"\`
   - \`CITATION.cff\`: \`version: 2.0.0\` AND \`date-released: 2026-06-06\`
   Verify all three agree.

3. **Protocol version bump (MAJOR-affected)**: for any protocol yaml that had structural changes (review which were edited in Phase 9 + 14 + 16a-d), bump its top-level \`version:\` field to \`'2.0.0'\`. Don't blanket-bump every protocol — only ones genuinely affected by structural change.

4. **Router index version bump**: edit \`src/research_os/protocols/_router_index.yaml\` top-level \`version:\` to a new integer (current is 15; bump to 16) and update \`generated_at\` if present.

5. **Rebuild embeddings**: \`${CONDA} && python scripts/build_embeddings.py\`

6. **Full release gate**:
   - \`${CONDA} && python scripts/preflight.py\` (must be 24/24 OR 23/24 with only embeddings-stale failing then re-rebuild)
   - \`${CONDA} && python -m pytest -q --tb=no\` (must be >= 1583 passing; the 3 pre-existing flakies remain documented)
   - \`${CONDA} && ruff check src/ tests/ scripts/\` (must be clean modulo pre-existing F541 in cli.py:520)

7. **Wheel build sanity**:
   \`\`\`
   ${CONDA} && rm -rf dist/ && python -m build 2>&1 | tail -5
   unzip -l dist/research_os-2.0.0-*.whl | grep assets/ | wc -l
   unzip -l dist/research_os-2.0.0-*.whl | grep typst/ | wc -l
   unzip -l dist/research_os-2.0.0-*.whl | grep -c '\.npz\|_router_index.yaml'
   \`\`\`
   Verify the wheel contains typst templates + fonts + reveal.js + Touying + poster Typst packages + pack registrations + embeddings.

8. **Commit**:
   \`feat(v2): release 2.0.0 — version bump + CHANGELOG + protocol-version bumps [phase-16e]\`

9. **Final report**: write to \`docs/v2_handoff/PHASE_16_FINAL_REPORT.md\` containing:
   - Phase 0 → Phase 16 deltas (tools, server.py, ratings, HIGH friction)
   - Total commits in feat/v2.0.0 since baseline
   - 4×5 perspective × scenario rating matrix
   - Top 10 improvements (from V2_VALIDATION_REPORT.md)
   - Top 5 CRAFT additions
   - Remaining v2.0.1 / v2.1.0 work
   - Wheel-build PASS/FAIL
   - **Manual next steps for the user** (concrete commands they need to run):
     - \`git push -u origin feat/v2.0.0\` (or whatever remote setup exists)
     - \`gh pr create --base dev --head feat/v2.0.0 --title "Release v2.0.0" --body "$(cat docs/V2_RELEASE_NOTES.md)"\`
     - After dev → main release PR + merge: \`git tag -a v2.0.0 -m "v2.0.0" && git push origin v2.0.0\`
     - Verify PyPI: \`curl -sL https://pypi.org/simple/research-os/ | grep 2.0.0\`
   - Total agent invocations across the whole v2.0.0 push.

DO NOT push, tag, or merge. User owns release decisions.
${COMMON}`,
  { label: '16e', phase: 'CHANGELOG + version bump + wheel sanity' }
)

return {
  docs: docsResults.filter(Boolean),
  release: releaseResult,
}
