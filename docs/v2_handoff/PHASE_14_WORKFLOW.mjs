// Phase 14 — Deprecation Cleanup
// Runs AFTER Phase 9. Removes alias runways that have expired + dead code.

export const meta = {
  name: 'v2-phase-14-deprecation-cleanup',
  description: 'Phase 14: remove v1.6.1-era deprecated aliases, dead code, tikzposter LaTeX path, dead config fields',
  phases: [
    { title: 'Deprecation removal', detail: '4 parallel removal agents (alias expiration, orphan/tikzposter, migration REMOVE rows, dead fields/code)' },
  ],
}

const REPO = '/scratch/vsetlur/Research-OS'
const CONDA = `source /scratch/vsetlur/anaconda3/etc/profile.d/conda.sh && conda activate research-os`

const COMMON = `
CWD: ${REPO}
Branch: feat/v2.0.0
Conda env: ${CONDA}

GROUND RULES
============
- Run AFTER Phase 9 consolidation (so V2_MIGRATION_TABLE.md exists and the new alias surface is finalized).
- Read docs/v2_handoff/PHASE_14_PLAN.md for context.
- For EVERY removal:
  1. \`grep -rn '<symbol>' src/ tests/ docs/ templates/\` — must show ZERO real callers (excluding test that asserts removal).
  2. Check pyproject.toml entry_points — no plugin depends on it.
  3. Delete the symbol or file.
  4. If it was a tool: add \`_REMOVED_TOOLS[<name>]\` entry with a helpful migration message naming the new path.
  5. Add a CHANGELOG \`### Removed\` entry under v2.0.0.
  6. Run \`python scripts/preflight.py && python -m pytest -q\`. If any test fails, the removal had a hidden dep — REVERT and document.
- Single commit at end: \`chore(v2): remove <category> [phase-14<letter>]\`.
- If you cannot safely remove something, DOCUMENT the blocker (caller path, why removal is unsafe) and SKIP. Do NOT force a removal that breaks tests.
- DO NOT touch Phase 9's new consolidated tools, aliases, or _DEPRECATED_ALIASES additions.
`

const AGENTS = [
  {
    id: '14a',
    label: '14a alias expiration sweep',
    instructions: `Phase 14a — alias expiration sweep.

Find aliases in _ALIASES whose v1.x.y introduction date is ≥ 3 minor versions old (i.e. ≤ v1.6.x). These have expired their deprecation runway and should be hard-removed in v2.0.0.

WORKFLOW
========
1. List the contents of \`_DEPRECATED_ALIASES\` set in src/research_os/server.py.
2. For each alias \`a\`, find its introduction commit:
   \`git log --diff-filter=A -S '"'\${a}'"' -- src/research_os/server.py | tail -1\`
3. If introduction commit is in a release ≤ v1.6.x AND v2.0.0 is now ≥ 4 minor cycles later: REMOVE.
4. To remove: delete from _ALIASES, _DEPRECATED_ALIASES, _ALIAS_PARAM_INJECTION; add to _REMOVED_TOOLS with a redirect message "<old>: renamed to <new> in v1.X.Y, removed in v2.0.0; call <new> instead".
5. Verify with \`grep -rn '"<old_name>"' src/ tests/ docs/ templates/\` — must show ZERO callers.
6. If grep finds a real caller, the alias is still needed — SKIP and document.

DO NOT remove aliases introduced in Phase 9 (those are v2.0.x).

${COMMON}
REPORT BACK
===========
- Number of aliases inspected.
- Number actually removed.
- Number skipped (with reason).
- Pytest + preflight status.
- Commit SHA.`,
  },
  {
    id: '14b',
    label: '14b orphan tools + tikzposter dead code',
    instructions: `Phase 14b — orphan tools + tikzposter LaTeX dead-code removal.

(1) ORPHAN TOOLS: tools whose handler is defined but is never called by any protocol/doc/test, and whose alias entry is also dead.
- \`grep -rn '_handle_tool_<X>' src/research_os/server.py\` — definition exists
- \`grep -rn '"tool_<X>"\` src/ tests/ docs/ templates/ — should be only the definition site
- If truly orphan: remove handler + TOOL_DEFINITIONS entry + add _REMOVED_TOOLS entry.

(2) TIKZPOSTER LATEX PATH (v1.11.0 replaced with Typst poster):
- Find \`tools/actions/synthesis/poster_latex_*\` modules
- Find \`templates/poster_latex/*\` directory
- Find any \`tool_poster_create\` branch dispatching to LaTeX (vs Typst)
- Remove all of it.
- Add _REMOVED_TOOLS entry for any tool name a caller might still try.

${COMMON}
REPORT BACK
===========
- Number of orphan tools removed.
- Tikzposter modules/templates removed (file paths).
- Pytest + preflight status.
- Commit SHA.`,
  },
  {
    id: '14c',
    label: '14c V2_MIGRATION_TABLE.md REMOVE rows',
    instructions: `Phase 14c — execute the REMOVE rows in docs/V2_MIGRATION_TABLE.md.

Phase 9 will have populated V2_MIGRATION_TABLE.md with rows like:
\`| old_name | new_name | kwarg | value | status |\`
where status ∈ {aliased v2.0.x, removed v2.0.0, removed v2.1.0}.

Your job:
1. Read V2_MIGRATION_TABLE.md
2. For every row marked "removed v2.0.0": execute the removal (delete from _ALIASES/_DEPRECATED_ALIASES/etc., add to _REMOVED_TOOLS).
3. Skip rows marked "aliased v2.0.x" or "removed v2.1.0".
4. Verify no real callers via grep.

If V2_MIGRATION_TABLE.md doesn't exist yet (Phase 9 still running): SKIP this agent and report "blocked on Phase 9".

${COMMON}
REPORT BACK
===========
- Number of rows processed.
- Number actually removed.
- Pytest + preflight status.
- Commit SHA.`,
  },
  {
    id: '14d',
    label: '14d dead config fields + dead code (v1.9.2 audit Lens 7 + 9)',
    instructions: `Phase 14d — dead config fields + dead code removal.

The v1.9.2 audit (closed in v1.9.3) identified:
- Lens 7: config fields declared in researcher_config but never read
- Lens 9: unreferenced functions/classes (dead code)

WORKFLOW
========
1. Read CHANGELOG.md for the v1.9.3 section to find the lens 7 and lens 9 audit references.
2. \`git log --grep "v1.9.2" --all -- docs/audit_v1.9.2/\` to find the original audit docs (they were committed at some point even if deleted now).
3. If audit docs aren't accessible, fall back to:
   - \`grep -rn "<field>" src/\` on every field in researcher_config to find unused ones
   - \`python -c "import vulture; ..."\` or manual grep to find dead code candidates
4. For each candidate: grep ALL of src/ tests/ docs/ for any reference. If zero references: remove.
5. For removed config fields: also remove from any docs that mention them.

DO NOT remove config fields that ARE referenced but only via dynamic dict lookup (\`config.get("<field>")\`). Grep with care.

${COMMON}
REPORT BACK
===========
- Number of config fields removed (with names).
- Number of functions/classes removed (with names + file paths).
- Pytest + preflight status.
- Commit SHA.`,
  },
]

phase('Deprecation removal')

// 14a, 14b, 14d are independent (different removal categories, different file regions).
// 14c depends on V2_MIGRATION_TABLE.md from Phase 9 — but Phase 9 already ran by the time Phase 14 starts.
// Still, run them sequentially to avoid alias-dict edit collisions.
const results = []
for (const a of AGENTS) {
  const r = await agent(a.instructions, { label: a.id, phase: 'Deprecation removal' })
  results.push(r)
  log(`${a.id} complete`)
}

return { agents: results.filter(Boolean) }
