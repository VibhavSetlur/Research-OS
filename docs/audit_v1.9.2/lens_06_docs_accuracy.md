# Lens 06 — Docs Accuracy + Currency

Audit of `docs/` + `README.md` + `CONTRIBUTING.md` against the live surface at v1.9.1.

## Ground truth (live surface, recomputed)

| Quantity | Source of truth | Value |
|---|---|---|
| Protocols (yaml, excluding `_router_index`) | `find src/research_os/protocols -name '*.yaml' \| grep -v _router_index \| wc -l` | **114** |
| MCP tools | `len(research_os.server.TOOL_DEFINITIONS)` at runtime | **212** |
| Tests | `pytest --collect-only` | **872 collected** |
| Test files | `find tests -name 'test_*.py'` | 56 |

Per-category protocol breakdown:

| Category | Actual | What docs/PROTOCOLS.md stated (before fix) |
|---|---|---|
| audit | 3 | 3 |
| domain | 2 | 2 |
| guidance | 19 | 19 |
| literature | 5 | 5 |
| methodology | 42 | 42 |
| reproducibility | 1 | 1 |
| **synthesis** | **18** | **17 (DRIFT — undercount by 1)** |
| visualization | 14 | 14 |
| writing | 10 | 10 |
| **Total** | **114** | **113 (DRIFT — undercount by 1)** |

The single new synthesis protocol that pushed the total from 113 → 114 is
unaccounted for in the PROTOCOLS.md narrative. Four synthesis protocols
(`defense_prep`, `journal_selection`, `manuscript_outline`, `printable`)
exist on disk but were entirely absent from the PROTOCOLS.md per-protocol
mention list (see §"PROTOCOLS.md drift" below).

---

## 1. Count drift (file → stated → actual)

All count claims found via `grep -rEn '[0-9]+ ?(protocols|tools|audit gates|adapters|packs)'`:

| File:line | Stated | Actual | Fix applied? |
|---|---|---|---|
| docs/README.md:19 | 113 protocols | 114 | YES → 114 |
| docs/README.md:20 | 146 MCP tools | 212 | YES → 212 |
| docs/FAQ.md:61 | 113 protocols | 114 | YES → 114 |
| docs/PROTOCOLS.md:3 | 113 YAML protocols | 114 | YES → 114 |
| docs/PROTOCOLS.md:13 | synthesis 17 | 18 | YES → 18 |
| docs/PROTOCOLS.md:20 | Total 113 | 114 | YES → 114 |
| docs/START.md:133 | 113 protocols | 114 | YES → 114 |
| docs/START.md:141 | 146 MCP tools | 212 | YES → 212 |
| docs/AI_GUIDE.md:84 | 113 protocols | 114 | YES → 114 |
| docs/AI_GUIDE.md:95 | synthesis 17 protocols | 18 | YES → 18 (and listed the 4 missing names) |
| docs/AI_GUIDE.md:336 | sys_protocol_list → 113 | 114 | YES → 114 |
| docs/TOOLS.md:3 | 146 MCP tools | 212 | YES → 212 |
| docs/RESEARCHER_GUIDE.md:6 | 113 protocols / 146 tools | 114 / 212 | YES → 114 / 212 |
| docs/RESEARCHER_GUIDE.md:249 | 113 total | 114 | YES → 114 |
| docs/RESEARCHER_GUIDE.md:315 | 146 total | 212 | YES → 212 |
| docs/RESEARCHER_GUIDE.md:648 | 113 protocols | 114 | YES → 114 |
| docs/RESEARCHER_GUIDE.md:649 | 146 MCP tools | 212 | YES → 212 |
| CONTRIBUTING.md:10 | 146 MCP tools, 113 YAML protocols | 212 / 114 | YES → 212 / 114 |
| CONTRIBUTING.md:36 | 438+ tests | 872 | YES → 872+ |

`docs/ROADMAP.md` references (146→90 tools, 113→75 protocols) are
**roadmap aspirations** describing pre-consolidation state, NOT live
claims — left untouched. `CHANGELOG.md` historical lines (e.g. v1.8.x
"207 tools + 150 protocols") are release-time snapshots and must not be
back-edited.

**Severity:** HIGH before fix (docs lie to users about surface size).
All instances fixed inline. Remaining risk: counts will drift again on
v1.9.2 release (current v1.9.1 stats themselves not yet reflected in
CHANGELOG.md - that's lens 05 territory).

---

## 2. Broken markdown links

`Broken: 0`

Every relative markdown link in `README.md`, `CONTRIBUTING.md`,
`CHANGELOG.md`, and `docs/*.md` resolves to an existing file in the repo
(script: extract `[label](path)`, skip `http(s)://`, `mailto:`, `#`-only
fragments; resolve relative to the source file's directory; check
existence). No HIGH severity findings in this dimension.

---

## 3. Orphan tool names mentioned in user-facing docs

Tools referenced in docs that are NOT in `TOOL_DEFINITIONS` at runtime
(212 tools registered):

| Mentioned name | First location | Verdict |
|---|---|---|
| `tool_audit_statistical_power` | docs/TOOLS.md:5 | **OK** — explicitly named as a legacy alias example |
| `tool_figure_create` | docs/TOOLS.md:250 | **OK** — explicitly marked "Removed in v1.3.0" |
| `sys_guidance_get` | docs/FAQ.md:223 | **OK** — named as a legacy alias that auto-rewrites |
| `tool_alias` | docs/MIGRATION.md:133 | **OK** — `kind='tool_alias'` parameter-value reference, not a tool name |
| `tool_mypack_my_action` | docs/PLUGIN_AUTHORING.md:98 | **OK** — placeholder example in plugin tutorial |
| `tool_name` | docs/AI_GUIDE.md:79 | **OK** — placeholder for `sys_tool_describe(tool_name)` argument |
| `tool_discovery` | docs/PROTOCOLS.md:138 | **OK** — actually a protocol path `methodology/tool_discovery`, false-positive from tool-name regex |
| `tool_audit_master`, `tool_audit_deliverable_consistency`, `tool_canonicalize_claims`, `tool_domain_detect`, `tool_failures`, `tool_plan_grounded`, `tool_poster_compile_typst`, `tool_rebuttal_draft`, `tool_reviewer_simulate`, `tool_revision_diff`, `tool_slides_compile` | docs/ROADMAP.md (multiple) | **OK** — all in ROADMAP.md describing future-state tools that don't ship yet. ROADMAP is forward-looking by nature; not a docs-accuracy bug. |

**No real orphan tool mentions in user-facing docs after analysis.**
Every "missing" name is either a legacy alias being explicitly called
out, a tutorial placeholder, or a roadmap-future tool.

---

## 4. Orphan protocol names

Protocol paths referenced in docs that don't exist on disk: **0**.
All `category/name` references in docs resolve to real protocol YAMLs.

False-positive matches caught by the regex (filesystem paths like
`synthesis/paper.md`, `synthesis/biblio.yml`, `synthesis/dashboard.html`,
`synthesis/_typst_templates/`, `synthesis/figures/`,
`literature/findings_vs_literature.md`) are all legitimate file
references, not protocol references.

---

## 5. START.md issues

START.md walkthrough is current as of v1.9.1 EXCEPT:

- **L133, L141**: stale 113 protocols / 146 tools counts (FIXED).
- Wizard step count: `init` is described as "7-step interactive wizard"
  (L41). Lens 02 should sanity-check whether `wizard.py` still has 7
  steps — out of scope for this lens but flagged for cross-lens lookup.
- IDE list at L57 covers Claude Code, OpenCode, Antigravity, Cursor,
  Claude Desktop, VS Code, Windsurf, Continue, Aider. Cross-check
  against `templates/` directory contents is a lens 04 (templates)
  concern.

No critical START.md drift after fix.

---

## 6. AI_GUIDE.md drift

| Issue | Severity | Location | Fixed? |
|---|---|---|---|
| 113 protocols stated, actual 114 | HIGH | L84, L336 | YES |
| Synthesis stated 17, actual 18 | HIGH | L95 | YES — appended `manuscript_outline / journal_selection / defense_prep / printable` to the parenthesized list |
| Visualization category table (L313-321) lists only 6 of 14 protocols | MEDIUM | L310-320 | NOT FIXED — would require enumerating 8 more (`animation_design`, `distribution_comparison`, `geospatial_visualization`, `interactive_dashboard_design`, `interactive_figure_design`, `network_visualization`, `showcase_visualization`, `uncertainty_visualization`). Defer to v1.9.3 doc refresh. |
| Methodology stated 42 — matches actual | OK | L91 | n/a |
| Categories table is missing **synthesis 18** explicitness | MEDIUM | L95 | partially mitigated by fix |

---

## 7. RESEARCHER_GUIDE.md drift

### Count drift
| L6 | "113 protocols and 146 MCP tools" | FIXED → 114 / 212 |
| L249 | "113 total" | FIXED → 114 |
| L315 | "146 total" | FIXED → 212 |
| L648, L649 | "113 protocols" / "146 MCP tools" | FIXED |

### Config schema drift (HIGH — researcher-facing lie)

RESEARCHER_GUIDE.md §8 (L388-440) shows the `researcher_config.yaml`
schema. Comparing to `templates/researcher_config.yaml`, **the docs are
missing several fields that the template now ships**:

| Field | In template? | In RESEARCHER_GUIDE §8? |
|---|---|---|
| `researcher.*`, `project_name`, `research_goal.*` | YES | YES |
| `interaction.autonomy_level: coaching` (4th option) | YES — `manual \| supervised \| autopilot \| coaching` | NO — guide lists only `manual \| supervised \| autopilot` |
| `interaction.quality_gate_policy` | YES | YES |
| `interaction.ambiguity_posture` | YES | YES |
| `gate_strictness` | YES — `light \| normal \| strict \| auto` | **MISSING** |
| `project_tier` | YES — `throwaway \| sketch \| production` | **MISSING** |
| `model_profile` | YES | YES |
| `writing_preferences.citation_style`, `language` | YES | YES |
| `writing_preferences.venue_template` | YES — nature/science/nejm/cell/ieee_conf/neurips/acl/plos/generic_two_column/generic_thesis | **MISSING** |
| `writing_preferences.pdf_compile_engine` | YES — typst/latex/both | **MISSING** |
| `runtime.*` | YES | YES |
| `tool_stack.*` (preferred_languages, allow_mixed_language_steps, field_practice_overrides_preference, cite_field_practice_when_choosing) | YES — entire subsystem | **MISSING** |
| `api_keys.*` | YES | YES |

Five new researcher-facing knobs (`gate_strictness`, `project_tier`,
`writing_preferences.venue_template`, `writing_preferences.pdf_compile_engine`,
and the entire `tool_stack:` block) ship in the template but are
absent from the guide. The `coaching` autonomy level is also missing.
Not fixed inline — the rewrite is multi-paragraph and beyond a "trivial
fix" scope. **Flagged as HIGH for v1.9.3.**

### Internal layout drift (LOW)

`docs/RESEARCHER_GUIDE.md` L583-590 sketches the source tree with
`tools/actions/{...}` categories. Actual subdirs of
`src/research_os/tools/actions/`:
`semantic.py, protocol.py, router.py, viz/, state/, ...` — should be
cross-checked against the guide's `audit / data / exec / memory /
research / search / state / synthesis / viz` enumeration (it's
out-of-date — `data`, `exec`, `memory`, `research`, `search` are not
the actual subdirectory names). Not fixed (touches a code-tree diagram,
risk of misrepresentation). Flagged LOW for v1.9.3.

---

## 8. PROTOCOLS.md drift

### Counts (FIXED)
- Total 113 → 114
- Synthesis 17 → 18

### 34 protocols on disk that are NEVER mentioned in PROTOCOLS.md

These exist as YAMLs but PROTOCOLS.md (which is supposed to be the
researcher-facing protocol catalogue) does not mention them in any
backtick-quoted form:

**audit/** (2 missing of 3):
- `audit/pre_submission_checklist`
- `audit/provenance_completeness`

**guidance/** (2 missing of 19):
- `guidance/constructive_disagreement`
- `guidance/revise_and_resubmit`

**literature/** (1 missing of 5):
- `literature/literature_per_step`

**methodology/** (12 missing of 42):
- `methodology/bootstrapping_design`
- `methodology/coding_scheme_development`
- `methodology/cox_ph_diagnostics`
- `methodology/data_management_plan`
- `methodology/deep_domain_research`
- `methodology/external_tool_setup`
- `methodology/fairness_audit`
- `methodology/inter_rater_reliability`
- `methodology/interview_guide_design`
- `methodology/mcp_ecosystem_integration`
- `methodology/missing_data_strategy`
- `methodology/mixed_language_orchestration`
- `methodology/multiple_comparisons`
- `methodology/pick_tool_stack`
- `methodology/qualitative_quality_audit`
- `methodology/survey_design`
- `methodology/uncertainty_quantification`

**synthesis/** (4 missing of 18 — the protocols invisible to readers):
- `synthesis/defense_prep`
- `synthesis/journal_selection`
- `synthesis/manuscript_outline`
- `synthesis/printable`

**visualization/** (8 missing of 14 — half the category):
- `visualization/animation_design`
- `visualization/distribution_comparison`
- `visualization/geospatial_visualization`
- `visualization/interactive_dashboard_design`
- `visualization/interactive_figure_design`
- `visualization/network_visualization`
- `visualization/showcase_visualization`
- `visualization/uncertainty_visualization`

PROTOCOLS.md is supposed to be the "catalogue of all 114 protocols" but
**80 of 114 are actually enumerated; 34 are silently absent** despite
shipping in the package and being routable via `tool_route`. The
researcher reading PROTOCOLS.md is misled into thinking the catalog is
exhaustive — researchers won't know to ask for, say, "geospatial
visualization" or "Cox PH diagnostics" because there's no signal those
protocols exist.

### Alphabetization

PROTOCOLS.md per-protocol sections (audit/, guidance/, etc.) are NOT
strictly alphabetized — they cluster thematically. This is a deliberate
authoring choice (group related protocols together for readability),
not drift. The task instruction said "alphabetized + accurate" — partial:
not alphabetized, and not accurate per the 34 omissions above.

**Severity:** HIGH for v1.9.3. Cannot trivially fix — requires writing
short blurbs for 34 protocols.

---

## 9. FAQ.md issues

- L61 stale count (FIXED → 114).
- L223 references `sys_guidance_get` as a legacy alias — verified
  intentional (it's NOT in TOOL_DEFINITIONS by design; auto-rewrites to
  canonical form).
- L141-145 references `tool_external_tool_instructions`. Verified live
  in TOOL_DEFINITIONS.
- L152 references `tool_branch_recommendation`. Verified live.
- L159 references `mem_hypothesis_list`. Verified live.
- L208, L231 reference `tool_workspace_repair`. Verified live.
- L133, L138, L200 reference `tool_synthesize`, `tool_citations_verify`,
  `tool_latex_compile`. All verified live.

**FAQ is accurate** apart from the now-fixed count.

---

## 10. Other docs (sweep)

- `docs/ADAPTERS.md` — no count drift; no orphan tool refs.
- `docs/MIGRATION.md` — `tool_alias` reference is a parameter value,
  not a tool name; correct.
- `docs/PLUGIN_AUTHORING.md` — `tool_mypack_my_action` is an
  intentional placeholder. Pack stats (`humanities` 8/3, `qualitative`
  5/2, `theory_math` 8/3, `wet_lab` 8/3, `engineering` 7/3) should be
  cross-checked against actual pack contents in v1.9.3 (lens 04
  territory, not lens 06).
- `docs/SETUP.md` — references to optional tools (`tool_r_exec`,
  `tool_julia_exec`, `tool_rmarkdown_render`, `tool_notebook_exec`,
  `tool_audit_reproducibility`, `tool_workspace_repair`) all verified
  live in TOOL_DEFINITIONS.
- `docs/RELIABILITY.md` — no count claims.
- `docs/SHARING.md` — `synthesis/dashboard.html`, `synthesis/figures/`
  are filesystem paths, correct.
- `docs/VENUE_TEMPLATES.md` — `synthesis/_typst_templates/`,
  `synthesis/biblio.yml`, `synthesis/paper.md` are filesystem paths,
  correct. `tool_paper_compile_typst`, `tool_latex_compile` both
  verified live.
- `docs/ROADMAP.md` — counts described are pre-consolidation
  aspirations; LEFT AS-IS.
- `docs/RELEASING.md` — no count drift.
- `docs/USE_CASES.md` — no count drift detected.
- `docs/PROTOCOL_DOCTRINE.md` — no count claims.
- `README.md` (root) — no numeric drift (the README leans into
  qualitative claims, not counts).

---

## Summary table of severity findings

| ID | Severity | File | Title |
|---|---|---|---|
| 06-A | HIGH | RESEARCHER_GUIDE.md §8 (L388-440) | Config schema docs missing `gate_strictness`, `project_tier`, `writing_preferences.venue_template`, `writing_preferences.pdf_compile_engine`, entire `tool_stack:` block, and `coaching` autonomy level |
| 06-B | HIGH | PROTOCOLS.md | 34 protocols (30% of catalog) silently absent from the per-protocol mention list, despite shipping. Researchers cannot discover them from the docs. |
| 06-C | MEDIUM | AI_GUIDE.md L313-320 | Visualization category table lists only 6 of 14 protocols |
| 06-D | LOW | RESEARCHER_GUIDE.md L583-590 | Source-tree diagram lists subdirectories that don't match the actual `tools/actions/` layout |
| 06-E | LOW | docs/ROADMAP.md | Counts cited (146 tools, 113 protocols) describe the pre-consolidation target — could confuse first-time readers but is contextually correct in roadmap framing |
| 06-F | (fixed inline) | multiple | 19 count-drift lines across 11 files all fixed to 114 protocols / 212 tools / 872+ tests |

---

## Suggested release targets

- **v1.9.2** (this sprint): count fixes already applied. No more docs
  work strictly needed for the v1.9.2 release.
- **v1.9.3** (docs polish patch): rewrite RESEARCHER_GUIDE.md §8 to
  match `templates/researcher_config.yaml` 1:1 (06-A). Enumerate the
  34 missing protocols in PROTOCOLS.md with a 1-line blurb each
  (06-B). Update AI_GUIDE.md visualization table (06-C). Sync
  RESEARCHER_GUIDE.md source-tree diagram (06-D).
- **v2.0.0**: no doc-accuracy issues warrant a MAJOR.
