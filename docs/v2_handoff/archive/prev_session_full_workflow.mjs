export const meta = {
  name: 'research-os-v2',
  description: 'Research-OS v2.0.0 release — Phases 4-16 + v1.11.1 known issues. Branch feat/v2.0.0, no remote push, no PyPI, no GH release. Stops at release-ready.',
  phases: [
    { title: 'Setup' },
    { title: 'Wave A: Foundations (parallel)' },
    { title: 'Wave A.2: Audit migration' },
    { title: 'Wave A.3: v1.11.1 known issues' },
    { title: 'Wave B: Dependent features' },
    { title: 'Wave B.2: Protocol body cleanup' },
    { title: 'Wave B.3: Pack completeness matrix' },
    { title: 'Wave C: Contract + audience-segmented docs' },
    { title: 'Wave C.2: Baseline validation (Phase 15a)' },
    { title: 'Wave D: Tool consolidation (Phase 9)' },
    { title: 'Wave D.2: Deprecation cleanup (Phase 14)' },
    { title: 'Wave D.3: Server refactor (Phase 10)' },
    { title: 'Wave E: Re-validation (Phase 15b)' },
    { title: 'Wave E.2: Release prep (no push)' },
  ],
}

const RO = '/scratch/vsetlur/Research-OS'
const ENV = 'source /scratch/vsetlur/anaconda3/etc/profile.d/conda.sh && conda activate research-os'

const PREAMBLE = `
You are a sub-agent in the Research-OS v2.0.0 release workflow.

HARD CONSTRAINTS — violating any of these is a failure:
- Working directory: ${RO}
- Always activate conda before any Python: \`${ENV}\`
- Work on branch \`feat/v2.0.0\` (already created). NEVER checkout main. NEVER commit to main.
- NEVER \`git push\`, \`gh pr create\`, \`gh pr merge\`, \`twine upload\`, \`python -m build\` upload, \`gh release create\`.
- NEVER use \`--no-verify\` on commits. Fix the hook if it complains.
- NEVER mock the database in tests.
- NEVER call real LLM APIs from inside RO tools (RO doesn't manage models).
- Local commits OK; remote operations forbidden.
- If a test was already failing on the base branch (e.g. theory_math known issues), do NOT mark your work as failed because of it — note it and continue.
- Use the dedicated Edit/Write tools for edits; reserve Bash for shell ops, builds, tests, git.

WORKING STYLE:
- Read first, then act. Don't guess at file contents.
- Commit your work when done with a conventional commit message: \`feat(v2): <thing> [phase-X]\` or \`fix(v2): ...\`.
- After your work: run \`${ENV} && ruff check src/ tests/ scripts/ && python -m pytest -q -x --timeout=60\` and report counts.
- Output a tight 150-300 word report at the end: what changed, files touched, tests passing (number/total), any blockers or skipped items, and one-line "DONE" or "BLOCKED" marker.

CONTEXT:
- v1.11.0 already shipped Phases 1, 2, 3 from the release spec. Don't redo them.
- Current baseline: version 1.11.0, 118 protocols, 344 tools, server.py 6813 lines.
- 5 in-tree packs: humanities, qualitative, theory_math, wet_lab, engineering (under src/research_os_<pack>/).
- 6 adapter packs: slurm, synapse, cytoscape, nextflow, redcap, snakemake.
- Bumping target: 2.0.0 (don't bump yet — release-prep phase does that).
`

// =========================================================================
// PHASE: SETUP
// =========================================================================
phase('Setup')

await agent(`${PREAMBLE}
PHASE: Setup. ONE-AGENT job.

Tasks:
1. Confirm you are on branch feat/v2.0.0 (\`git branch --show-current\`). If not, ERROR.
2. In pyproject.toml, change \`version = "1.11.0"\` to \`version = "2.0.0-dev"\` (dev marker so accidental wheel builds don't collide with shipped 1.11.0).
3. In src/research_os/__init__.py, sync __version__ to "2.0.0-dev".
4. In CITATION.cff, sync version to "2.0.0-dev".
5. Add a CHANGELOG.md placeholder at the top: \`## [Unreleased — v2.0.0]\` with empty Added/Changed/Deprecated/Removed/Fixed sections.
6. Create directory docs/v2_handoff/ if not present and write a short \`PLAN.md\` listing the 14 phase titles.
7. Commit: \`chore(v2): bump to 2.0.0-dev, scaffold CHANGELOG + handoff\`
8. Run tests and report.
`)

// =========================================================================
// PHASE: WAVE A FOUNDATIONS (parallel, mostly disjoint)
// =========================================================================
phase('Wave A: Foundations (parallel)')

const waveA = await parallel([
  () => agent(`${PREAMBLE}
PHASE 4a: Audit-finding schema + base class. Foundation for all of Phase 4.

Tasks:
1. Create src/research_os/schemas/audit_finding.schema.json (JSON Schema, draft-07) with fields:
   - id (uuid string), audit_name (string), severity (enum: block|warn|info)
   - dimension (string), evidence_paths (array of strings), suggested_fix (string)
   - override_kwarg (string|null), override_log_format (string|null)
   - generated_at (date-time), ro_version (string)
   Required: id, audit_name, severity, dimension, generated_at, ro_version.

2. Create src/research_os/tools/actions/audit/_base.py with:
   - dataclass AuditFinding (matches schema)
   - class AuditBase ABC with method run(self, root: Path, **kwargs) -> list[AuditFinding]
   - function write_audit_outputs(findings, gate_name, root) that:
     a) writes workspace/<gate>_audit.md (human-readable, grouped by severity)
     b) writes workspace/<gate>_audit.json (schema-validated, all fields)
     c) appends each finding as one JSON line to workspace/logs/.audit_findings.jsonl
   - function validate_finding(d: dict) -> AuditFinding raises ValueError on schema violation
   - Use uuid.uuid4(), datetime.now(UTC), read ro_version from src/research_os/__init__.py.__version__

3. Tests: tests/unit/test_audit_base.py
   - test schema validates a good finding, rejects a bad one (missing required field)
   - test write_audit_outputs writes both md + json + appends jsonl
   - test idempotent re-run replaces md/json but APPENDS jsonl

4. Commit: \`feat(v2): audit-finding JSON schema + AuditBase + write_audit_outputs [phase-4]\`
5. Tests + ruff. Report.

DO NOT migrate existing audits in this agent. That happens in Wave A.2 with multiple parallel agents off your base class.
`, { label: 'phase4a-base', schema: undefined }),

  () => agent(`${PREAMBLE}
PHASE 6: \`research-os doctor\` command. ONE-AGENT job.

Tasks:
1. Read src/research_os/cli.py to understand existing command pattern (init, start, ide subcommands).
2. Add a fourth top-level command: \`doctor\` with subparser. No required args. Flags: --verbose, --workspace-only, --json.
3. Implement in new module src/research_os/cli_doctor.py with check functions:
   - check_python_version() — require >= 3.10
   - check_conda_active() — warn if CONDA_DEFAULT_ENV not set
   - check_version_consistency() — pyproject + __init__.py + CITATION.cff agree
   - check_in_tree_packs_registered() — all 5 packs discoverable via plugin loader
   - check_external_pack_entrypoints() — enumerate via importlib.metadata.entry_points('research_os.packs')
   - check_embeddings_fresh() — _embeddings.npz mtime >= _router_index.yaml mtime
   - check_typst_on_path() — \`which typst\`
   - check_chromium_on_path() — optional, warn if missing
   - check_optional_deps() — pyvis present if researcher_config.synthesis.interactive_figures
   - check_mcp_configs_wired() — each declared IDE has its config file
   - check_workspace_integrity() — only if invoked inside a project: no orphan figures, no stale step_summary, no unresolved BLOCK in .audit_findings.jsonl
   - check_disk_space() — warn if workspace size > 5 GB
   - check_git_clean() — warn if dirty
   - check_gitignore_covers_state() — .gitignore matches .os_state/ + workspace/cache/

   Each returns (status: 'pass'|'warn'|'fail', message: str, fix: str|None).

4. Output: human-readable colored summary; \`--json\` emits {checks: [...], summary: {pass: N, warn: N, fail: N}}.
5. Exit codes: 0 pass+warn, 1 if any warn (no fail), 2 if any fail.
6. Tests: tests/unit/test_cli_doctor.py
   - test each check function in isolation with mocked filesystem where needed
   - test integration: \`research-os doctor --json\` outputs valid JSON
   - test exit codes
7. docs/CLI.md (or extend if exists): document \`doctor\`.
8. Commit: \`feat(v2): research-os doctor command [phase-6]\`
9. Tests + ruff. Report.
`, { label: 'phase6-doctor' }),

  () => agent(`${PREAMBLE}
PHASE 11a: Router output improvements + flat protocol/tool listers.

Tasks:
1. Read src/research_os/server.py to find tool_route handler and src/research_os/protocols/_router_index.yaml structure.
2. Add tool_protocols_list:
   - Input schema: {category: str|null (filter), pack: str|null (filter), include_pack_protocols: bool=true}
   - Output: flat list [{name, category, pack_or_'core', intent_class, tier|null, version, description_short}]
   - Use existing protocol loader; don't reinvent.
3. Add tool_tools_list:
   - Input: {scope: 'all'|'core'|'<pack-name>'='all', include_deprecated: bool=false, match_substring: str|null}
   - Output: flat list [{name, scope, summary_first_line, input_schema_required_fields, deprecated: bool, alias_of: str|null}]
   - Build from TOOL_DEFINITIONS at runtime + _DEPRECATED_ALIASES.
4. Improve tool_route output:
   - Always include \`why_matched\` line per result: which trigger phrase + which intent_class matched
   - Always include \`tier\` field (null for now; Phase 8 will populate)
   - Always include \`tier_transition\` field (null for now)
   - Add \`alternatives\` array: top 3 other candidates with their scores
5. Tests: tests/unit/test_protocols_list.py, tests/unit/test_tools_list.py, tests/unit/test_router_output_v2.py (assert new fields present).
6. Commit: \`feat(v2): tool_protocols_list + tool_tools_list + router why_matched/tier fields [phase-11a]\`
7. Tests + ruff. Report.
`, { label: 'phase11a-router' }),

  () => agent(`${PREAMBLE}
PHASE 13: CLI fresh-install validation across 8 IDE targets. ONE agent emulates all 8 sequentially (we can't truly install in parallel in /tmp without race).

Tasks:
For each IDE in [cursor, claude, antigravity, opencode, vscode, windsurf, continue, aider]:
  1. \`rm -rf /tmp/ro_v2_cli/<ide> && mkdir -p /tmp/ro_v2_cli/<ide>\`
  2. \`cd /tmp/ro_v2_cli/<ide> && ${ENV} && research-os init . --ide <name> --yes\` (or whatever the actual flag is — check cli.py first)
  3. Verify scaffold: workspace/, inputs/, docs/, .os_state/, researcher_config.yaml all exist.
  4. Read researcher_config.yaml and confirm defaults look sane.
  5. Verify MCP config: read the expected IDE config path, confirm RO is wired with correct command.
  6. \`research-os start &\` (background); sleep 3; \`kill %1\`. Capture stderr for any startup errors.
  7. \`research-os ide list\` — should show <ide>; \`research-os ide remove <ide>\`; \`research-os ide add <ide>\`; \`research-os ide list\` should still show <ide>.
  8. \`research-os doctor\` (depends on Phase 6 — may not exist yet; if not, skip with note).
  9. Record PASS / FAIL per IDE with details.

After all 8: write docs/v2_handoff/cli_validation.md with results matrix and list of bugs found.
Then FIX any CLI bugs you found that are clearly under our control (IDE config format drift, missing flags, etc.). Commit fixes as \`fix(v2): CLI <details> [phase-13]\`. Skip Phase-6-dependent failures.

Tests + ruff. Report.

Note: Phase 6 (doctor) and this phase run in parallel. If doctor isn't ready, doctor checks are skipped in this validation — don't block.
`, { label: 'phase13-cli', isolation: 'worktree' }),
])

log(`Wave A complete. Results: ${waveA.filter(Boolean).length}/${waveA.length} agents reported back.`)

// =========================================================================
// PHASE: WAVE A.2 — AUDIT MIGRATION (depends on 4a base class)
// =========================================================================
phase('Wave A.2: Audit migration')

// Migrate 10 existing audit tools to the new base class. Each gets its own agent.
const AUDIT_LIST = [
  'audit_master',
  'audit_synthesis',
  'audit_step_literature',
  'audit_completeness',
  'audit_code_quality',
  'audit_prose',
  'audit_claims',
  'audit_cross_deliverable_consistency',
  'audit_figure_coverage',
  'audit_reviewer_responses',
]

const auditMigration = await parallel(AUDIT_LIST.map((name) => () => agent(`${PREAMBLE}
PHASE 4b: Migrate audit tool \`tool_${name}\` to AuditBase (from Phase 4a, already landed).

Tasks:
1. Locate the existing handler. Likely under src/research_os/tools/actions/audit/ or audit/audit.py or synthesis/. Use grep to find: \`grep -rn "${name}" src/research_os/tools/actions/ src/research_os/server.py\`.
2. Read the current handler implementation thoroughly. Understand its inputs, outputs, and any audit-finding-equivalent data it currently produces.
3. Refactor: subclass AuditBase and emit a list[AuditFinding] from run(). Preserve existing behavior:
   - The current markdown output format must remain identical (regression test below).
   - Add JSON companion via write_audit_outputs.
   - Append to workspace/logs/.audit_findings.jsonl.
   - Severities: BLOCK/PASS/WARN findings in existing logic map to block/warn/info per the schema.
   - Each finding gets a stable uuid (derive deterministically from audit_name + dimension + evidence_paths so re-runs don't churn IDs; use uuid.uuid5(NAMESPACE_DNS, key)).
4. Update server handler to call the new class, then write_audit_outputs.
5. Tests: tests/unit/test_audit_${name}_v2.py:
   - test that running against a fixed fixture produces same markdown as before (snapshot)
   - test JSON companion is schema-valid
   - test jsonl roll-up gets new lines
6. Commit: \`refactor(v2): migrate tool_${name} to AuditBase [phase-4]\`
7. Tests + ruff. Report. If you can't find the handler, output BLOCKED with details.

If your specific audit doesn't exist in the codebase yet (audit_cross_deliverable_consistency and audit_figure_coverage shipped in v1.11.0 and audit_reviewer_responses may have shipped too; the others should exist), check carefully before declaring missing. If genuinely missing, output BLOCKED.
`, { label: `phase4-${name}` })))

log(`Wave A.2 audit migration: ${auditMigration.filter(Boolean).length}/${AUDIT_LIST.length} migrated.`)

// Downstream Phase 4 consumers — single agent, depends on all migrations done.
await agent(`${PREAMBLE}
PHASE 4c: Audit-findings downstream consumers. ONE-AGENT job, depends on Wave A.2 migrations being done.

Tasks:
1. Add tool_audit_findings_query(severity: str|null, dimension: str|null, step: str|null, since: timestamp|null) -> list[AuditFinding]:
   - Reads workspace/logs/.audit_findings.jsonl, filters, returns. Handler in src/research_os/tools/actions/audit/findings_query.py.
2. Add tool_audit_findings_diff(timestamp_a: str, timestamp_b: str) -> {added: [], resolved: [], changed: []}:
   - Snapshot findings at two timestamps from the jsonl, diff by stable uuid.
3. Modify tool_synthesize to read .audit_findings.jsonl and refuse to compile if any unresolved BLOCK findings present (unless override_unresolved_blocks=true kwarg passed, logged to override_log.md).
4. Tests: tests/unit/test_audit_findings_query.py, test_audit_findings_diff.py, test_synthesize_blocks_on_unresolved_findings.py.
5. Document in docs/TOOLS.md.
6. Commit: \`feat(v2): audit findings query/diff + synthesize block-gate [phase-4]\`
7. Tests + ruff. Report.
`, { label: 'phase4c-consumers' })

// =========================================================================
// PHASE: WAVE A.3 — v1.11.1 KNOWN ISSUES (parallel)
// =========================================================================
phase('Wave A.3: v1.11.1 known issues')

const knownIssues = await parallel([
  () => agent(`${PREAMBLE}
v1.11.1 ISSUE: theory_math path-coercion bugs.

Tasks:
1. Fix src/research_os/tools/actions/state/config.py at lines ~224 and ~356: add \`root = Path(root)\` coercion at entry point.
2. Fix src/research_os/tools/actions/audit/audit.py: find all ~16 sites that do \`root / 'workspace'\` and add coercion. Use grep \`grep -n "root / " src/research_os/tools/actions/audit/audit.py\`.
3. Add a test: tests/unit/test_path_coercion.py that calls handlers with str root and confirms no TypeError.
4. Commit: \`fix(v2): coerce root to Path in state/config + audit/audit [v1.11.1-known-issue]\`
5. Tests + ruff. Report.
`, { label: 'fix-path-coercion' }),

  () => agent(`${PREAMBLE}
v1.11.1 ISSUE: list_protocols pack-blindness.

Tasks:
1. Read src/research_os/tools/actions/protocol.py around line 502 (function list_protocols).
2. Modify to ALSO walk _pack_protocol_dirs_safe() output (already imported elsewhere; check imports).
3. Verify with a manual smoke: call sys_protocol_list(category='theory_math') and confirm it returns theory_math pack protocols, not just core.
4. Add test: tests/unit/test_list_protocols_pack_aware.py.
5. Commit: \`fix(v2): list_protocols includes pack protocols [v1.11.1-known-issue]\`
6. Tests + ruff. Report.
`, { label: 'fix-list-protocols' }),

  () => agent(`${PREAMBLE}
v1.11.1 ISSUE: DEG trigger false-positive on "maximum degree" in theory_math prompts.

Tasks:
1. Find DEG trigger in src/research_os/protocols/_router_index.yaml or wherever triggers live.
2. Tighten the trigger pattern so it requires word boundaries + biology-context tokens like "expression"|"genes"|"RNA"|"transcript". Use a more specific regex or phrase list.
3. Add test: tests/unit/test_router_no_deg_false_positive.py: route "maximum degree 3 in a graph" should NOT match DEG analysis intent; should route to theory_math/method/proof_strategy_selection.
4. Commit: \`fix(v2): tighten DEG trigger, no false-positive on graph theory [v1.11.1-known-issue]\`
5. Re-train embeddings if router uses them (\`python scripts/rebuild_embeddings.py\` or similar; check scripts/).
6. Tests + ruff. Report.
`, { label: 'fix-deg-false-positive' }),

  () => agent(`${PREAMBLE}
v1.11.1 ISSUE: tool_synthesize IMRAD-only output even for theory_math pack.

Tasks:
1. Read src/research_os/tools/actions/synthesis/ to find paper-section emission logic.
2. Add a hook: synthesis pipeline checks the active pack's preferred section schema via pack_api. Each pack can declare paper_sections in its PackRegistration.
3. Default sections (IMRAD) used if pack doesn't declare. theory_math pack should declare [introduction, preliminaries, main_theorems, proofs, discussion].
4. Update src/research_os_theory_math/pack.py (or whatever entry module) to declare paper_sections.
5. Test: tests/unit/test_synthesize_uses_pack_sections.py.
6. Commit: \`feat(v2): synthesis consults pack-supplied section schema, theory_math no longer IMRAD-forced [v1.11.1-known-issue]\`
7. Tests + ruff. Report.
`, { label: 'fix-imrad-only' }),

  () => agent(`${PREAMBLE}
v1.11.1 ISSUE: E2E manifest persona-name drift.

Tasks:
1. Edit tests/fixtures/projects/biology_genomics_mini/manifest.yaml: rename personas to canonical IDs:
   - skeptical_methodologist → methodology_skeptic
   - statistics_referee → statistician
   - domain_expert_neuroscience → domain_expert
   - bioinformatician_reviewer → reproducibility_advocate
   - ethics_irb_reviewer → scope_creep_critic
   - editor_in_chief → presentation_critic
2. Add a unit test: tests/unit/test_manifest_personas_canonical.py that walks tests/fixtures/**/manifest.yaml and asserts every persona ID exists in src/research_os/assets/reviewer_personas/.
3. Commit: \`fix(v2): canonical persona IDs in biology_genomics_mini manifest [v1.11.1-known-issue]\`
4. Tests + ruff. Report.
`, { label: 'fix-persona-drift' }),

  () => agent(`${PREAMBLE}
v1.11.1 ISSUE: handout naming inconsistency (slides_handout.pdf vs slides.handout.pdf).

Tasks:
1. Grep both naming styles: \`grep -rn "slides_handout\\|slides.handout\\|poster_handout\\|poster.handout" src/ tests/\`.
2. Pick the dot form (\`slides.handout.pdf\`, \`poster.handout.pdf\`) — it cleanly separates stem from variant suffix and matches existing \`.caption.md\` convention.
3. Update writers + manifest expectations + tests.
4. Add test: tests/unit/test_handout_naming.py asserting compile output filename.
5. Commit: \`fix(v2): unify handout naming as <stem>.handout.pdf [v1.11.1-known-issue]\`
6. Tests + ruff. Report.
`, { label: 'fix-handout-naming' }),

  () => agent(`${PREAMBLE}
v1.11.1 ISSUE: Typst font cascade warnings (missing Linux Libertine / Times).

Tasks:
1. Identify Typst template files under src/research_os/assets/typst_packages/.
2. Choose: ship a bundled font fallback (preferred: New Computer Modern, OFL-licensed) OR document the font install requirement.
   - Bundling: download NCM if not present, place under src/research_os/assets/fonts/, set Typst template to use it via #set text(font: "New Computer Modern Sans") or similar. Update pyproject.toml package-data.
   - If bundling fails due to download issues, fall back to documenting: add docs/FONTS.md with install instructions + suppress the warnings via Typst font path config.
3. Verify a paper compile no longer emits the font warning.
4. Test: tests/integration/test_typst_no_font_warning.py (compile a minimal fixture, assert no warning string in stderr).
5. Commit: \`fix(v2): vendor New Computer Modern font, eliminate Typst font warnings [v1.11.1-known-issue]\`
6. Tests + ruff. Report.

If font download is blocked by network, document-only is acceptable. Note clearly which path you took.
`, { label: 'fix-font-warnings' }),

  () => agent(`${PREAMBLE}
v1.11.1 ISSUE: tool_synthesize silent citation retrieval failure (list index out of range).

Tasks:
1. Reproduce: \`${ENV} && cd ${RO} && python -m pytest tests/integration/ -k "biology_genomics_mini" -x\` and check if it surfaces.
2. Grep for citation retrieval call sites: \`grep -rn "semantic_scholar\\|crossref\\|index out of range" src/research_os/tools/actions/synthesis/ src/research_os/tools/actions/research/\`.
3. Find the bare \`[0]\` or similar that's IndexError'ing on empty response.
4. Fix: defensive handling — return empty list / log structured warning to workspace/logs/citation_failures.jsonl rather than raising.
5. Surface failures in tool_synthesize output: include \`{citations_used: N, citation_retrieval_failures: M}\` in the structured return.
6. Test: tests/unit/test_citation_retrieval_empty_response.py with a mocked HTTP layer returning empty.
7. Commit: \`fix(v2): citation retrieval handles empty upstream response gracefully [v1.11.1-known-issue]\`
8. Tests + ruff. Report.
`, { label: 'fix-citation-silent-fail' }),
])

log(`Wave A.3 known issues: ${knownIssues.filter(Boolean).length}/${knownIssues.length} closed.`)

// =========================================================================
// PHASE: WAVE B — DEPENDENT FEATURES
// =========================================================================
phase('Wave B: Dependent features')

const waveB = await parallel([
  () => agent(`${PREAMBLE}
PHASE 5: Review-rewrite loops on paper/slides/poster drafters. Depends on Phase 4 (audit findings schema).

Tasks:
1. Create src/research_os/tools/actions/synthesis/drafter_loop.py:
   - def draft_with_review_rewrite(drafter_fn, reviewer_fn, *, max_iter=3, improvement_threshold=0.10, root: Path) -> dict
   - Each iteration: drafter_fn(prior_output=None or prior, root) -> output ; reviewer_fn(output, root) -> list[AuditFinding]
   - If no BLOCK findings AND quality improvement < threshold: stop.
   - Else: drafter_fn(prior_output=output, findings=findings, root) for next iter.
   - Cap at max_iter.
   - Log each iter to workspace/logs/drafter_loops/<drafter>_iter_<N>.md (the output) + .json (the findings).
   - Compute quality delta via simple metrics: citation count, numeric-claim count (regex \\d+%|\\d+\\.\\d+|p\\s*=\\s*0\\.\\d+ etc.), section coverage (% sections non-empty), prose fluency proxy (avg sentence length, type-token ratio).
   - Return: {iterations: N, converged: bool, final_output_path, quality_progression: [...]}.

2. Wire into tool_paper_compile_typst (or whatever the v1.11.0 paper compile is called):
   - If researcher_config.synthesis.drafter_loop_enabled (default true), wrap with draft_with_review_rewrite using a reviewer subset [presentation_critic, scope_creep_critic, methodology_skeptic].
   - In autopilot tier, max_iter = config.drafter_loop_max_iterations (default 3).
   - In throwaway project tier, force max_iter = 1.

3. Wire into tool_slides_create with [presentation_critic, scope_creep_critic], max_iter default 2.
4. Wire into tool_poster_create with [presentation_critic, novelty_critic], max_iter default 2.

5. Add researcher_config fields:
   - synthesis.drafter_loop_enabled: bool (default true)
   - synthesis.drafter_loop_max_iterations: int (default 3)
   - synthesis.drafter_loop_quality_threshold: float (default 0.10)
   Update validator + docs/CONFIG.md (or whichever doc).

6. Quality output: workspace/logs/drafter_loops/quality_progression.md table.

7. Tests: tests/unit/test_drafter_loop.py (mocks for drafter/reviewer); tests/integration/test_paper_drafter_loop.py (real flow on a minimal fixture).

8. Commit: \`feat(v2): review-rewrite loops on paper/slides/poster drafters [phase-5]\`
9. Tests + ruff. Report.
`, { label: 'phase5-drafter-loops' }),

  () => agent(`${PREAMBLE}
PHASE 8: Tier-aware router output. Depends on Phase 11a (router output already extended with tier field).

Tasks:
1. Define tier taxonomy in src/research_os/protocols/_tiers.py:
   - TIERS = ['intake', 'plan', 'execute', 'ground', 'synthesize', 'review', 'finalize']
2. Annotate every protocol YAML with a top-level \`tier:\` field. There are 118 protocols. Backfill via a script that infers tier from intent_class / category:
   - bootstrap/intake/research_overview → intake
   - hypothesis/methodology/decomposition → plan
   - analysis/code/data steps → execute
   - literature_gate/claim_grounding → ground
   - paper/slides/poster/dashboard drafting → synthesize
   - reviewer/drafter_loop → review
   - cross_deliverable/submission_prep → finalize
   Write the script at scripts/backfill_tiers.py, then run it. Verify YAML still parses for all 118.
3. Update tool_route handler to populate tier field (read from protocol metadata).
4. Add tool_route output field \`tier_transition: {from: <prev_tier>|null, to: <new_tier>}\` based on workspace/.os_state/current_tier.json.
5. tool_step_complete advances tier in current_tier.json when transitioning across categories.
6. tool_audit_master shows tier-based progress (textual or YAML summary).
7. Tests: tests/unit/test_router_tier.py, test_tier_transition.py, test_tier_advance_on_step_complete.py.
8. Commit: \`feat(v2): tier-aware router + protocol tier annotations + current_tier state [phase-8]\`
9. Tests + ruff. Report.
`, { label: 'phase8-tiers' }),
])

log(`Wave B core: ${waveB.filter(Boolean).length}/${waveB.length} done.`)

// =========================================================================
// PHASE: WAVE B.2 — PROTOCOL BODY CLEANUP (parallel by chunks)
// =========================================================================
phase('Wave B.2: Protocol body cleanup')

const PROTOCOL_CHUNKS = [
  'audit/', 'domain/', 'guidance/', 'literature/',
  'methodology/', 'reproducibility/', 'synthesis/',
  'visualization/+writing/',
]

const protocolCleanup = await parallel(PROTOCOL_CHUNKS.map((chunk) => () => agent(`${PREAMBLE}
PHASE 11b: Protocol body cleanup for src/research_os/protocols/${chunk}. Depends on Phase 8 (tier annotations).

Tasks:
1. List YAML files under your assigned chunk: \`find src/research_os/protocols/${chunk.replace('+', ' ')} -name '*.yaml' 2>/dev/null\`.
2. For each:
   - REMOVE version-history cruft from the body text. Strip phrases like:
     * "in v1.X.Y added"
     * "closing the gap between Y and Z"
     * "this used to be tool_old_name"
     * any explicit "v1.N.M" version references in prose
     git log preserves this history; the body should describe CURRENT behavior.
   - Confirm \`tier:\` annotation present (Phase 8 should have added; if missing, add inferred tier).
   - Confirm YAML still parses (yaml.safe_load).
3. Verify protocol still routes correctly: pick 2 representative protocols, manually trace router triggers and confirm they still match expected queries.
4. Commit: \`chore(v2): protocol body cleanup ${chunk} [phase-11b]\`
5. Tests + ruff. Report what you cleaned (count of files modified, sample diff snippet).
`, { label: `phase11b-${chunk.replace(/[\/+]/g, '')}` })))

log(`Wave B.2 protocol cleanup: ${protocolCleanup.filter(Boolean).length}/${PROTOCOL_CHUNKS.length} chunks done.`)

// =========================================================================
// PHASE: WAVE B.3 — PACK COMPLETENESS MATRIX
// =========================================================================
phase('Wave B.3: Pack completeness matrix')

const PACKS = ['humanities', 'qualitative', 'theory_math', 'wet_lab', 'engineering']

const packMatrix = await parallel(PACKS.map((pack) => () => agent(`${PREAMBLE}
PHASE 12: Pack completeness check for \`${pack}\` pack.

Subsystems to verify (8): literature_gate, paper_pdf, dashboard_story, dashboard_explore, slides, poster, reviewer_scaffold, drafter_loop.

For each subsystem:
1. Identify whether ${pack} pack supports it (read src/research_os_${pack}/* and its registered protocols).
2. If supported: run a tiny smoke check (4-turn mini-project pattern):
   - Use Python to invoke the relevant handler directly OR use a minimal fixture under tests/fixtures/packs/${pack}/.
   - Confirm output file is produced (e.g. for paper_pdf: confirm a .pdf appears).
3. If NOT supported but should be: classify as gap.
4. If N/A for this pack (e.g. theory_math doesn't need a wet_lab dashboard): mark N/A.

Write your row to docs/V2_PACK_COMPLETENESS_MATRIX.md (create with header row if it doesn't exist; use file lock pattern: try-acquire-write-release via a brief retry loop in case of concurrent access). Format:
\`\`\`
| Pack | LitGate | PaperPDF | Dash-Story | Dash-Explore | Slides | Poster | Reviewer | Drafter-Loop |
\`\`\`

For each GAP cell: open a fix in src/research_os_${pack}/ OR in core if it's a core gap exposed by the pack. Add regression test under tests/integration/packs/${pack}/.

Commit: \`feat(v2): close ${pack} pack completeness gaps [phase-12]\`
Tests + ruff. Report which cells passed / failed / N-A / fixed.
`, { label: `phase12-${pack}`, isolation: 'worktree' })))

log(`Wave B.3 pack matrix: ${packMatrix.filter(Boolean).length}/${PACKS.length} packs checked.`)

// =========================================================================
// PHASE: WAVE C — CONTRACT + AUDIENCE DOCS
// =========================================================================
phase('Wave C: Contract + audience-segmented docs')

await agent(`${PREAMBLE}
PHASE 7: CONTRACT.md + audience-segmented docs landing. ONE-AGENT job for coherence.

Tasks:
1. Create docs/CONTRACT.md with three sections:
   A. STABLE surface (MAJOR-bump required to change):
      - Public tool names + input schemas (refer to tool_tools_list output)
      - Audit-finding JSON schema (Phase 4)
      - researcher_config field names (additions OK; renames are MAJOR)
      - Workspace directory layout (workspace/, .os_state/, etc.)
      - Protocol routing intent_class enum
   B. MINOR-changeable (additions OK; renames PATCH):
      - Tool argument optional kwargs
      - Audit prose wording
      - Protocol body prose
      - New protocols + new tools
   C. PATCH-changeable / internal:
      - Internal module structure
      - Test fixtures, dev scripts
   D. OUT-OF-SCOPE (RO will NOT do):
      - LLM provider management
      - Cloud infrastructure provisioning
      - Long-running compute scheduling (use adapter pack)
      - Live collaboration

2. Rewrite docs/README.md as an audience router (not a content dump):
   - "I'm a researcher" → docs/RESEARCHER_GUIDE.md + docs/START.md
   - "I'm an AI agent" → docs/AI_GUIDE.md + docs/TOOLS.md
   - "I'm a plugin author" → docs/PLUGIN_AUTHORING.md (NEW)
   - "I'm a maintainer" → docs/MAINTAINER_GUIDE.md (NEW) + CONTRIBUTING.md
   - "I want to integrate" → docs/INTEGRATION.md (NEW) + docs/CONTRACT.md

3. Create the three NEW docs (substantive, not stubs; 400-800 words each):
   - docs/PLUGIN_AUTHORING.md: pack structure, entry-point registration, PackRegistration dataclass usage, tool decorator pattern, protocol YAML conventions, testing patterns. Reference existing 5 in-tree packs as examples.
   - docs/MAINTAINER_GUIDE.md: release flow, CI overview, audit cadence, plugin discovery internals, semver gating, CHANGELOG conventions.
   - docs/INTEGRATION.md: programmatic API for embedding RO (import paths, MCP transport, headless invocation), with a working code snippet.

4. Tests: tests/unit/test_contract_md_freshness.py asserts CONTRACT.md mentions every current public-tool prefix and every researcher_config top-level section.

5. Commit: \`docs(v2): CONTRACT.md + audience-router README + plugin/maintainer/integration guides [phase-7]\`
6. Tests + ruff. Report.
`, { label: 'phase7-contract' })

// =========================================================================
// PHASE: WAVE C.2 — BASELINE 20-AGENT VALIDATION
// =========================================================================
phase('Wave C.2: Baseline validation (Phase 15a)')

const SCENARIOS = [
  { key: 'biology_rnaseq', desc: 'Biology RNA-seq DE (R Bioconductor + Python scanpy + GEO accession)' },
  { key: 'humanities_close_reading', desc: 'Humanities close-reading (Gutenberg corpus, humanities_essay output)' },
  { key: 'qualitative_interviews', desc: 'Qualitative interviews (8 synthetic participants, PII redaction)' },
  { key: 'engineering_benchmark', desc: 'Engineering benchmark (3 algorithms x 5 sizes x 10 runs)' },
  { key: 'theory_math_proof', desc: 'Theory/math proof (graph-theory conjecture, theory_math pack)' },
]
const PERSPECTIVES = [
  { key: 'naive_ai', desc: 'Fresh AI agent, MCP-client surface only, no src/ access. Walk through the scenario as an AI would in production. Rate friction.' },
  { key: 'researcher', desc: 'Domain researcher, natural-language requests, observes AI behavior. Rate AI behavior quality.' },
  { key: 'auditor', desc: 'Reads every artifact + audit log + provenance. Checks rigor: literature gate, claim grounding, citation verification, reproducibility footers.' },
  { key: 'maintainer', desc: 'Watches for tool sprawl, unclear errors, protocol routing failures, performance issues, missing telemetry.' },
]

const VALIDATION_SCHEMA = {
  type: 'object',
  required: ['scenario', 'perspective', 'final_rating', 'high_friction_count', 'first_5_turns_high_friction', 'every_deliverable_produced', 'friction_items', 'recommendations'],
  properties: {
    scenario: { type: 'string' },
    perspective: { type: 'string' },
    final_rating: { type: 'number', minimum: 0, maximum: 10 },
    high_friction_count: { type: 'integer', minimum: 0 },
    first_5_turns_high_friction: { type: 'integer', minimum: 0 },
    every_deliverable_produced: { type: 'boolean' },
    friction_items: {
      type: 'array',
      items: {
        type: 'object',
        required: ['severity', 'category', 'description', 'suggested_fix'],
        properties: {
          severity: { type: 'string', enum: ['HIGH', 'MEDIUM', 'LOW'] },
          category: { type: 'string' },
          description: { type: 'string' },
          suggested_fix: { type: 'string' },
        },
      },
    },
    convoluted_tools: { type: 'array', items: { type: 'string' } },
    confusing_protocols: { type: 'array', items: { type: 'string' } },
    never_called_tools: { type: 'array', items: { type: 'string' } },
    recommendations: { type: 'array', items: { type: 'string' } },
  },
}

const baseline = await parallel(
  SCENARIOS.flatMap((s) => PERSPECTIVES.map((p) => () => agent(`${PREAMBLE}

PHASE 15a BASELINE VALIDATION — scenario \`${s.key}\` from perspective \`${p.key}\`.

This is a SIMULATED validation. You cannot spin up a real MCP client. Instead:
1. Read src/research_os/server.py to see the full tool surface.
2. Read relevant protocols for scenario "${s.desc}" — use tool_protocols_list output or grep src/research_os/protocols/.
3. Read the relevant pack: ${s.key === 'humanities_close_reading' ? 'src/research_os_humanities/' : s.key === 'qualitative_interviews' ? 'src/research_os_qualitative/' : s.key === 'theory_math_proof' ? 'src/research_os_theory_math/' : s.key === 'engineering_benchmark' ? 'src/research_os_engineering/' : 'src/research_os_wet_lab/ (closest to biology)'}.
4. Mentally walk through the scenario step-by-step (intake → plan → execute → ground → synthesize → review → finalize). At each step, note from the \`${p.key}\` perspective:
   - ${p.desc}
   - What would frustrate / confuse / fail / surprise this perspective?

Be ADVERSARIAL. Do not pad ratings. If the surface feels bloated (344 tools), say so. If a protocol description is jargon-heavy, say so. If an audit error message is opaque, say so.

Output schema (validated):
{
  scenario: "${s.key}",
  perspective: "${p.key}",
  final_rating: 0-10 (be honest; 7.8 is the current baseline, not a floor),
  high_friction_count: N (count of HIGH severity friction items),
  first_5_turns_high_friction: N,
  every_deliverable_produced: bool,
  friction_items: [{severity, category, description, suggested_fix}, ...],
  convoluted_tools: [tool names that are unclear/overloaded],
  confusing_protocols: [protocol names that are unclear],
  never_called_tools: [tools the scenario never needs — for Phase 9 consolidation input],
  recommendations: [actionable improvements],
}

Write your report to docs/v2_handoff/validation_baseline/${s.key}__${p.key}.json (create directory if needed). Also return the structured object as your tool result.
`, { label: `validate-base-${s.key}-${p.key}`, schema: VALIDATION_SCHEMA })))
)

// Synthesis agent for baseline
await agent(`${PREAMBLE}
PHASE 15a SYNTHESIS. Read all 20 JSON reports under docs/v2_handoff/validation_baseline/*.json.

Tasks:
1. Compute averages: avg final_rating, total high_friction_count, total first_5_turns_high_friction, deliverable_produced rate.
2. Per-perspective averages.
3. Per-scenario averages.
4. Union of never_called_tools across all 20 reports (this feeds Phase 9 consolidation — anything in this union AND with no production callers is a removal candidate).
5. Top 20 friction items by frequency (count how many reports flagged the same category).
6. Top 10 convoluted_tools (frequency).
7. Top 10 confusing_protocols (frequency).
8. Write docs/V2_VALIDATION_REPORT_BASELINE.md with all of the above as a structured report (markdown tables).
9. Write docs/v2_handoff/never_called_candidates.json with the list of candidate tools for removal.
10. Commit: \`docs(v2): Phase 15a baseline validation report + never-called candidates [phase-15a]\`
11. Report top-line findings: avg rating, total HIGH friction, # never-called candidates.
`, { label: 'phase15a-synthesis' })

log(`Wave C.2 baseline validation: ${baseline.filter(Boolean).length}/20 reports done.`)

// =========================================================================
// PHASE: WAVE D — TOOL CONSOLIDATION
// =========================================================================
phase('Wave D: Tool consolidation (Phase 9)')

// First: shared registry module lands serially.
await agent(`${PREAMBLE}
PHASE 9a: Tool consolidation registry module. ONE-AGENT serial job before parallel consolidations.

Tasks:
1. Read docs/v2_handoff/never_called_candidates.json (Phase 15a output).
2. Create src/research_os/server/consolidation_registry.py (yes, server/ subdir — may need to mkdir):
   - CONSOLIDATED_TOOLS: dict mapping new_tool_name → {old_names: [...], arg_transform: callable, schema: dict, handler: callable}
   - REMOVED_TOOLS: list of tool names being hard-removed in v2.0.0 (must have been deprecated for 3+ MINOR cycles)
   - Helper: register_consolidated(new_name, old_names, arg_transform, schema, handler) — wires both new tool AND legacy aliases that transform args + dispatch.
3. Document strategy in docs/V2_CONSOLIDATION_PLAN.md:
   - Cluster 1: audit_* (12 → 1) → tool_audit(scope, dimension, ...)
   - Cluster 2: viz_* (8 → 1) → tool_viz_figure(type, ...)
   - Cluster 3: export_* (5 → 1) → tool_export(format, ...)
   - Cluster 4: step_* (N → 1) → tool_step(action, ...)
   - Cluster 5: search/plan/path/mem (each cluster identified in v1.11.0 CHANGELOG as v2.0.0-deferred)
4. Initialize empty registry; populate via parallel Phase 9b agents.
5. Test: tests/unit/test_consolidation_registry.py (registry roundtrip, alias dispatch).
6. Commit: \`feat(v2): consolidation registry scaffold + plan [phase-9a]\`
7. Tests + ruff. Report.
`, { label: 'phase9a-registry' })

const CONSOLIDATION_CLUSTERS = [
  { name: 'audit', goal: 'collapse all tool_audit_* into tool_audit(scope, dimension, **kwargs); preserve every existing entry point as alias dispatching to new.' },
  { name: 'viz', goal: 'collapse tool_viz_volcano/heatmap/umap/network/time_series/etc into tool_viz_figure(type, **kwargs).' },
  { name: 'export', goal: 'collapse tool_export_csv/json/parquet/feather/arrow into tool_export(format, **kwargs).' },
  { name: 'step', goal: 'collapse step lifecycle tools (create/complete/audit/rollback) into tool_step(action, **kwargs).' },
  { name: 'search', goal: 'collapse search_* tools (deferred per v1.11.0 CHANGELOG) into tool_search(target, query, **kwargs).' },
  { name: 'plan', goal: 'collapse plan_* tools into tool_plan(action, **kwargs).' },
  { name: 'path', goal: 'collapse path_* tools into tool_path(operation, **kwargs).' },
  { name: 'mem', goal: 'collapse mem_* tools into tool_mem(operation, **kwargs).' },
]

const consolidations = await parallel(CONSOLIDATION_CLUSTERS.map((c) => () => agent(`${PREAMBLE}
PHASE 9b: Consolidate ${c.name}_* tool cluster. Depends on Phase 9a (registry).

Goal: ${c.goal}

Tasks:
1. Grep server.py for all tools matching the cluster: \`grep -n "tool_${c.name}" src/research_os/server.py\`.
2. For each tool in the cluster:
   - Add it to the alias mapping in consolidation_registry.py
   - Define the new unified handler that dispatches based on the dispatch kwarg (scope/type/format/action/etc.)
   - Map old args → new args via the arg_transform
3. Old tools remain callable; they emit DeprecationWarning at runtime ("tool_${c.name}_X is consolidated into tool_${c.name}; this alias will be removed in v3.0.0").
4. Tests: tests/unit/test_consolidate_${c.name}.py:
   - new tool with each dispatch value produces same output as old tool
   - old tools still callable (alias path)
   - DeprecationWarning emitted
5. Update docs/V2_MIGRATION_TABLE.md with one row per old tool → new equivalent:
   | Old | New (v2.0.0) | Args change | Output change | Status |
6. Commit: \`refactor(v2): consolidate ${c.name}_* into tool_${c.name} [phase-9]\`
7. Tests + ruff. Report counts: tools collapsed, tests added, lines saved.

Use isolation:worktree because clusters might touch overlapping bits of server.py (the tool registration dict). Coordinate via your worktree branch.
`, { label: `phase9-${c.name}`, isolation: 'worktree' })))

log(`Wave D consolidation: ${consolidations.filter(Boolean).length}/${CONSOLIDATION_CLUSTERS.length} clusters done.`)

// Merge worktree consolidations back. ONE agent to reconcile and re-test.
await agent(`${PREAMBLE}
PHASE 9c: Reconcile consolidation worktrees back into feat/v2.0.0.

Tasks:
1. List worktrees: \`git worktree list\`.
2. For each consolidation worktree, cherry-pick or merge its commits onto feat/v2.0.0. Resolve any conflicts in src/research_os/server.py registration dict (consolidations from different clusters add entries to the same dict; conflicts will be additive in nature).
3. Remove worktrees after merge: \`git worktree remove <path>\`.
4. Re-run full test suite: \`${ENV} && python -m pytest -q --timeout=120\`. Fix any cross-cluster breakage.
5. Confirm tool count dropped meaningfully (target ~120 from 344; report actual).
6. Commit any conflict-resolution as \`merge(v2): reconcile Phase 9 consolidation worktrees [phase-9c]\`.
7. Tests + ruff. Report tool count delta + test pass rate.
`, { label: 'phase9c-reconcile' })

// =========================================================================
// PHASE: WAVE D.2 — DEPRECATION CLEANUP
// =========================================================================
phase('Wave D.2: Deprecation cleanup (Phase 14)')

await agent(`${PREAMBLE}
PHASE 14: Deprecation cleanup. ONE-AGENT job.

Tasks:
1. Find the deprecation registry: \`grep -rn "_DEPRECATED_ALIASES\\|DEPRECATED_TOOLS" src/research_os/server.py\` (v1.11.0 CHANGELOG mentions 21 aliases queued for v2.0.0 removal).
2. Remove the 21 aliases. For each removal:
   - Confirm no caller via \`grep -rn "<old_name>" src/ tests/ docs/\`.
   - Confirm no plugin entry-point depends on it (check all 5 packs + 6 adapters).
   - Delete from server.py and any dispatcher.
   - CHANGELOG Migration table entry: old → new (point at Phase 9 consolidation entries).
3. Remove tikzposter LaTeX path (v1.11.0 made Typst default; v2.0.0 removes the legacy backend per spec).
4. Remove every tool tagged REMOVE in docs/V2_MIGRATION_TABLE.md.
5. Remove config fields flagged dead in v1.9.2 audit Lens 7 (check docs/AUDIT_v1.9.2.md if it exists).
6. Remove dead-code findings from v1.9.2 audit Lens 9.
7. Run tests after each removal batch — if a test breaks, the alias still had a caller; investigate before re-removing.
8. Commit: \`refactor(v2)!: remove 21 deprecated aliases + tikzposter + dead config fields [phase-14]\` (note the \`!\` for breaking).
9. Tests + ruff. Report counts.
`, { label: 'phase14-cleanup' })

// =========================================================================
// PHASE: WAVE D.3 — SERVER REFACTOR (single agent, holistic)
// =========================================================================
phase('Wave D.3: Server refactor (Phase 10)')

await agent(`${PREAMBLE}
PHASE 10: Server refactor. SINGLE-AGENT holistic job (not parallel — server.py needs coherent split).

Target layout:
\`\`\`
src/research_os/server.py              # entry point, ~300 lines (imports, run_server, top-level glue)
src/research_os/server/
  __init__.py                          # re-exports public API for backwards-compat
  tool_definitions/
    __init__.py
    audit.py
    synthesis.py
    viz.py
    research.py
    methodology.py
    grounding.py
    meta.py
    packs.py
  handlers/
    __init__.py
    audit.py
    synthesis.py
    viz.py
    research.py
    methodology.py
    grounding.py
    meta.py
    packs.py
  dispatch.py                          # tool dispatch + alias resolution
  pack_loader.py                       # plugin discovery
  aliases.py                           # legacy alias mappings
  registry.py                          # central tool/handler registration
\`\`\`

Constraints:
- Module size: ≤ 600 lines each.
- Public API preserved: \`from research_os.server import ...\` must work identically. server/__init__.py re-exports all previously-public names.
- Tool dispatch behavior must be identical to current.
- Tests must still pass without modification (no test imports change).

Tasks:
1. Read current src/research_os/server.py end-to-end.
2. Group existing code into the target modules.
3. Move code section-by-section. After each move, run pytest. Fix imports as you go.
4. server.py at end should be ~300 lines: imports + run_server + top-level CLI hooks.
5. server/__init__.py: re-export every previously top-level symbol.
6. Update src/research_os/__init__.py if it imports from server.py.
7. Run full suite: \`${ENV} && python -m pytest -q --timeout=120\`. Fix any breakage.
8. Commit: \`refactor(v2)!: split server.py into focused submodules [phase-10]\` (single commit at end; do NOT make 20 intermediate commits).
9. Tests + ruff. Report final line counts per module and total test pass rate.

If you cannot achieve ≤ 600 lines per module, document why in docs/v2_handoff/phase10_notes.md and accept up to 800 lines for the largest module — do not split arbitrarily.
`, { label: 'phase10-refactor' })

// =========================================================================
// PHASE: WAVE E — RE-VALIDATION (PHASE 15b)
// =========================================================================
phase('Wave E: Re-validation (Phase 15b)')

const revalidation = await parallel(
  SCENARIOS.flatMap((s) => PERSPECTIVES.map((p) => () => agent(`${PREAMBLE}

PHASE 15b RE-VALIDATION — scenario \`${s.key}\` from perspective \`${p.key}\`.

This is the FINAL validation pass. The system has changed since baseline:
- Tool consolidation (Phase 9): ~344 → ~120 tools.
- server.py refactored into modules.
- 21 aliases removed.
- CRAFT-inspired additions: structured audit JSON, review-rewrite loops, doctor command, CONTRACT.md, audience-segmented docs.
- Tier-aware router.
- v1.11.1 known issues fixed.

Read the baseline report at docs/v2_handoff/validation_baseline/${s.key}__${p.key}.json. Compare against current state.

Walk the scenario again (simulated, same as baseline). From the \`${p.key}\` perspective:
- ${p.desc}

Use the SAME schema as baseline (no rating padding, be adversarial). Targets for v2.0.0:
- avg final_rating ≥ 9.5
- total HIGH friction across all 20 runs ≤ 5
- first-5-turn HIGH friction = 0
- every deliverable produced in every scenario \xD7 perspective
- Naive AI rating ≥ 9.0, Researcher ≥ 9.0, Auditor ≥ 9.0, Maintainer ≥ 9.0
- No tool flagged "convoluted" in 3+ runs
- No protocol flagged "confused me" in 3+ runs

If targets are not met from your perspective for this scenario, say so clearly. Do NOT inflate to make the release look better.

Output the same schema as baseline. Write to docs/v2_handoff/validation_final/${s.key}__${p.key}.json.
`, { label: `validate-final-${s.key}-${p.key}`, schema: VALIDATION_SCHEMA })))
)

await agent(`${PREAMBLE}
PHASE 15b SYNTHESIS + delta vs 15a.

Tasks:
1. Read all docs/v2_handoff/validation_final/*.json.
2. Compute the same aggregates as the baseline synthesis (avg rating, HIGH friction totals, etc.).
3. Read docs/V2_VALIDATION_REPORT_BASELINE.md.
4. Compute deltas: baseline → final on every metric.
5. Determine whether v2.0.0 acceptance targets are met (avg ≥ 9.5, HIGH friction ≤ 5, etc.).
6. If NOT met: list which scenario\xD7perspective combos failed and what they flagged. Suggest a TARGETED v2.0.1 patch list rather than re-iterating now.
7. Write docs/V2_VALIDATION_REPORT.md (the final report) with sections:
   - Executive summary (acceptance: PASS / PARTIAL / FAIL)
   - Baseline → final delta table (per metric, per perspective, per scenario)
   - Top 10 improvements that moved the rating
   - Top 5 CRAFT-inspired additions and measured impact
   - Remaining gaps + recommended v2.0.1 / v2.1.0 deferrals
   - Verbatim quote of the most negative friction item per perspective (transparency)
8. Commit: \`docs(v2): Phase 15b final validation report + acceptance verdict [phase-15b]\`
9. Report executive summary.
`, { label: 'phase15b-synthesis' })

log(`Wave E re-validation: ${revalidation.filter(Boolean).length}/20 reports done.`)

// =========================================================================
// PHASE: WAVE E.2 — RELEASE PREP (NO PUSH)
// =========================================================================
phase('Wave E.2: Release prep (no push)')

await agent(`${PREAMBLE}
PHASE 16: Final docs + migration guide + release prep. ONE-AGENT job.

NO REMOTE OPERATIONS. NO PUSH. NO PR. NO PYPI. NO GH RELEASE.

Tasks:
1. Read docs/V2_VALIDATION_REPORT.md (Phase 15b synthesis).
2. Update README.md:
   - Post-consolidation tool counts (read from src/research_os/server.py at runtime if possible)
   - Updated badges (version 2.0.0, test count)
   - Quickstart that reflects v2.0.0 surface
3. Update docs/START.md with post-CLI-fix walkthroughs (Phase 13 fixes).
4. Update docs/AI_GUIDE.md with post-consolidation tool surface (use tool_tools_list output).
5. Update docs/RESEARCHER_GUIDE.md, docs/FAQ.md, docs/PROTOCOLS.md, docs/TOOLS.md.
6. Finalize docs/CONTRACT.md (freeze for v2.0.0).
7. Create docs/MIGRATION_v1_to_v2.md:
   - Section per cluster: tool old→new map
   - researcher_config field changes (renames + new fields)
   - Behavior changes (e.g. drafter loops on by default; figure auto-embed on by default; synthesis blocks on unresolved findings)
   - Upgrade steps for existing projects
8. docs/AUDIT_v1.9.2.md final appendix: "Closed in v2.0.0" listing every audit item closed.
9. Create docs/V2_RELEASE_NOTES.md (celebratory summary, links to all sub-docs).
10. Bump version: 2.0.0-dev → 2.0.0 in pyproject.toml, __init__.py, CITATION.cff.
11. Bump _router_index.yaml top-level version field (currently 15; bump to 16).
12. CHANGELOG: replace \`[Unreleased — v2.0.0]\` placeholder with \`[2.0.0] — (release-date-tbd)\` and populate sections:
    - Highlights (~3 sentences)
    - Added (~15 bullets from Phases 4, 5, 6, 7, 8)
    - Changed (~20 bullets from Phases 9, 11)
    - Deprecated (the new v2.0.x aliases that will be removed in v3.0.0)
    - Removed (link to MIGRATION table; list 21 aliases + tikzposter + dead config)
    - Fixed (~30 from Phase 15 deltas + v1.11.1 known issues closed)
    - Validation: 4\xD75 perspective\xD7scenario rating matrix with baseline→final
13. Build wheel locally and verify package data: \`${ENV} && python -m build && unzip -l dist/research_os-2.0.0-*.whl | grep assets/\`. Do NOT upload.
14. Run final preflight: \`${ENV} && python scripts/preflight.py && python -m pytest -q && ruff check src/ tests/ scripts/\`. If preflight script doesn't exist, run pytest + ruff alone.
15. Commit: \`release(v2): bump to 2.0.0 + CHANGELOG + MIGRATION + RELEASE_NOTES [phase-16]\`.
16. Write docs/v2_handoff/READY_FOR_RELEASE.md with:
    - Branch: feat/v2.0.0
    - Last commit SHA
    - Test pass count
    - Wheel built at: dist/research_os-2.0.0-*.whl
    - Acceptance verdict from Phase 15b
    - Suggested PR command (DO NOT EXECUTE): \`gh pr create --base dev --title "Release v2.0.0" --body-file docs/V2_RELEASE_NOTES.md\`
    - Suggested release commands (DO NOT EXECUTE): \`git tag v2.0.0 && git push origin v2.0.0\`
17. Report: SHA, test count, wheel name, acceptance verdict, next steps for the user to authorize manually.
`, { label: 'phase16-release-prep' })

log('Workflow complete. v2.0.0 branch is release-ready. Manual user authorization required for PR + PyPI + GH release.')

return {
  branch: 'feat/v2.0.0',
  release_ready: true,
  next_steps: [
    'Review docs/V2_VALIDATION_REPORT.md',
    'Review docs/V2_RELEASE_NOTES.md',
    'Review docs/MIGRATION_v1_to_v2.md',
    'Approve PR command to push',
    'Approve PyPI publish',
    'Approve GH release',
  ],
}
