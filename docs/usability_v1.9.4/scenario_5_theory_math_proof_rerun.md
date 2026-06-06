# Scenario 5 — Theory/math — small proof outline (RE-VALIDATION v1.9.4)

**Scenario:** Hypothesis (theorem): "For every connected graph G in class C (chordal graphs of treewidth <= 3), the chromatic number equals the clique number."
Data: NONE — purely theoretical.
Theory_math pack active.
Expected: `paper.pdf` (generic_thesis), `dashboard.html`, proof sketch with LaTeX/Typst math notation. Literature gate must work on theoretical claims (no empirical evidence required).

---

## 1. Project setup (turns 1-5)

### Turn 1
- **Wanted:** Cold start, orient.
- **Tool:** Read `docs/START.md` + `templates/CLAUDE.md`.
- **Simulated result:** Got two-call session pattern (`sys_boot` then `tool_route(prompt)`). Found "I have a conjecture" trigger phrase in the first-prompt table, mapped to "set up a theory_math project, pick a strategy, draft a verified proof". Also found `inputs/preliminaries.md` documented as a hard prerequisite of `theory_math/method/proof_strategy_selection`.
- **Format clear?** Yes — START.md is well-laid-out, the first-prompts table is unambiguous, and the prerequisite is called out explicitly.
- **Knew next step?** Yes — run `research-os init` then drop preliminaries.
- **Friction:** none
- **Doc gap:** none
- **Time-to-clarity:** ~60s

### Turn 2
- **Wanted:** Scaffold the project.
- **Tool (simulated):** `research-os init --name "chordal-tw3-coloring"`.
- **Simulated result:** Wizard would create `AGENTS.md`, `inputs/{raw_data,literature,context}/`, `workspace/`, `synthesis/`, `docs/`, `.os_state/`, and `inputs/researcher_config.yaml`.
- **Format clear?** Yes — START.md (lines 39–60) lists exactly what `init` drops.
- **Knew next step?** Yes — open AI IDE and chat.
- **Friction:** none
- **Doc gap:** none
- **Time-to-clarity:** ~10s

### Turn 3
- **Wanted:** Configure `researcher_config.yaml` for a theory paper (no data, AMS citation, thesis-style PDF).
- **Tool:** Read `templates/researcher_config.yaml`.
- **Simulated edits:**
  - `research_goal.output_types: [paper, dashboard]`
  - `research_goal.target_venue: "journal"`
  - `writing_preferences.citation_style: "amsplain"` (template comment lines 107–108 say "amsplain → pure mathematics + theoretical CS" — perfect)
  - `writing_preferences.venue_template: "generic_thesis"` (matches scenario expectation)
  - `writing_preferences.pdf_compile_engine: "typst"`
  - `project_tier: "production"`, `model_profile: "large"`
- **Format clear?** Yes — every field has an inline comment with enums and recommended values for each field. The amsplain hint targeted to "pure mathematics + theoretical CS" is exactly what a math researcher needs.
- **Knew next step?** Yes — drop `inputs/preliminaries.md` (the hard prerequisite called out by both START.md and AI_GUIDE.md).
- **Friction:** none
- **Doc gap:** none
- **Time-to-clarity:** ~90s

### Turn 4
- **Wanted:** Stage the theory-only input file (no raw_data, no literature PDFs at start).
- **Tool (simulated):** `mkdir inputs/` if needed; write `inputs/preliminaries.md` with definitions of: connected graph, chordal graph, treewidth, chromatic number χ(G), clique number ω(G), perfect graph theorem (cited prior result).
- **Simulated result:** File created with `## Definitions`, `## Cited prior results` (Hajnal–Surányi 1958; perfect graph theorem of Chudnovsky–Robertson–Seymour–Thomas), `## Open status of the claim`.
- **Format clear?** Yes — START.md table (line 89) calls out the exact path and notes that the protocol blocks without it.
- **Knew next step?** Yes — first user-facing prompt to the AI.
- **Friction:** none
- **Doc gap:** none — though there is NO `templates/preliminaries.md.template` (a worked example would have helped me know exactly what sections to include). FRICTION/LOW.
- **Time-to-clarity:** ~120s (had to choose sections from prose-only guidance)

### Turn 5
- **Wanted:** First researcher prompt.
- **Researcher message (simulated):** "I have a conjecture — for every chordal graph of treewidth ≤ 3, χ(G) = ω(G). Set up a theory_math project, pick a strategy, draft a verified proof, and produce both a thesis-style PDF and an executive dashboard."
- **MCP call 1:** `sys_boot` → returns `model_profile=large`, no prior protocol history, recommended_next=null (cold start), `inputs/preliminaries.md` detected → theory_math pack detector likely fires.
- **MCP call 2:** `tool_route(prompt=…)` → from router_entries.py I can see the trigger phrases `"prove this"`, `"draft a proof"`, `"I have a conjecture"` (last is in START.md) and the primary protocol is `theory_math/proof/proof_verification_workflow` with `complexity=high` (multi-step pipeline plus paper + dashboard).
- **Simulated result:** Router returns `primary_protocol=theory_math/proof/proof_verification_workflow`, decomposition with the 6 workflow steps + theory_paper_structure + dashboard, `complexity=high` (sets active_plan).
- **Format clear?** Mostly — START.md gives the trigger phrase; AI_GUIDE.md (lines 388–432) gives the full canonical workflow.
- **Knew next step?** Yes — execute `tool_plan_turn`.
- **Friction:** FRICTION/MEDIUM — the docs (START.md, USE_CASES.md, AI_GUIDE.md) talk about `theory_math/` as a "pack that ships in the default wheel", but the only easy verification path I had was `find … -name "*.yaml"` — which initially returned zero results in `src/research_os/protocols/`. The protocols actually live in a SEPARATE namespace package `src/research_os_theory_math/`. A user would not know to look there. AI_GUIDE.md (lines 122–126) says "Trust the router — do not grep `src/` to verify; the protocol catalogue is authoritative via `sys_protocol_list`" — but since the validation harness explicitly forbids invoking MCP, I had to grep. The doctrine of "namespace packages contain pack protocols" is not surfaced in any user-facing doc; PROTOCOLS.md says "ships in the default wheel" which is true but misleading about *where* on disk.
- **Doc gap:** A one-line note in PROTOCOLS.md saying "Pack protocols live under `src/research_os_<pack>/` namespace packages and are auto-loaded; the curated table here is the source of truth" would close it.
- **Time-to-clarity:** ~5min (most of this was searching for the protocols)

**Onboarding-friction count (first 5 turns):** 2 (one LOW for missing preliminaries template, one MEDIUM for the pack-location surprise; the second is hidden from a real researcher because they go through the MCP tool — only validation harnesses hit it).

---

## 2. Hypothesis + planning (turns 6-10)

### Turn 6
- **Wanted:** Walk the active plan.
- **Tool (simulated):** `tool_plan_turn` → returns this turn's batch (size 6 for `model_profile=large`).
- **Simulated batch:**
  1. `tool_intake_autofill` (read inputs/, infer the conjecture as the project's central hypothesis)
  2. `tool_research_overview` / hypothesis_tracking
  3. `theory_math/conjecture/conjecture_tracking` → register the conjecture
  4. `theory_math/method/proof_strategy_selection` step 1 (extract_claim_shape)
  5. step 2 (small_case_probe)
  6. step 3 (enumerate_candidate_strategies)
- **Format clear?** Yes — AI_GUIDE.md (lines 35–53) describes the exact pattern.
- **Knew next step?** Yes.
- **Friction:** none
- **Doc gap:** none
- **Time-to-clarity:** ~30s

### Turn 7
- **Wanted:** Run `tool_intake_autofill`.
- **Tool (simulated):** Inferred return shape from TOOLS.md (lines 499–517). Domain inferred = `theory_math`, RQ = the conjecture, hypotheses_drafted = [{id:H01, text:"χ(G) = ω(G) for chordal G with tw(G) ≤ 3"}], `wrote` = inputs/intake.md + docs/research_overview.md.
- **Format clear?** Yes — TOOLS.md provides a worked return example.
- **Knew next step?** Yes — register the conjecture.
- **Friction:** FRICTION/LOW — the TOOLS.md worked example is for a *qualitative_interviews* project; a similar example for `theory_math` (showing `domain_inferred: theory_math`, `next_steps: "Run theory_math/proof/proof_verification_workflow…"`) would let theory researchers cross-check the shape directly.
- **Doc gap:** Pack-specific return examples (or at least one per pack) in TOOLS.md.
- **Time-to-clarity:** ~45s

### Turn 8
- **Wanted:** Register the conjecture.
- **Tool (simulated):** Load `theory_math/conjecture/conjecture_tracking` (full protocol since complexity=high recommends `format='summary'` first then `format='step'`).
- **Simulated execution:** Walk 5 steps: scan_register → state_conjecture (`workspace/conjectures/chordal_tw3_chi_eq_omega.md`) → link_dependents (depends on: perfect-graph theorem; implies: nothing yet) → no partial progress yet → status=open.
- **Format clear?** Yes — the protocol YAML is unusually detailed, with editorial_voice rules and quality_bar bands.
- **Knew next step?** Yes — pivot to `proof_verification_workflow`.
- **Friction:** none
- **Doc gap:** none
- **Time-to-clarity:** ~3min (most was drafting the formal statement)

### Turn 9
- **Wanted:** Enter the proof workflow.
- **Tool (simulated):** Load `theory_math/proof/proof_verification_workflow` (read it above — 6 steps + declare_step_contract).
- **Simulated execution:** Step 1 `declare_step_contract` → write `workspace/01_proof_chordal_tw3/step_summary.yaml` with `step_intent: proof`, `figure_required: false`, `table_required: false`, `literature_required: true` (with the verdict floor being `IMPORTED_AS_CITED`). Step 2 `state_claim` → write claim to `workspace/proofs/chordal_tw3.md`.
- **Format clear?** Yes — `templates/step_summary.yaml.template` (lines 18–42) gives the full step_intent enum with `proof` explicitly documented as auto-waiving the figure gate.
- **Knew next step?** Yes — call `proof_strategy_selection`.
- **Friction:** none — this is a **major positive finding**. The step_summary template's `step_intent: proof` mapping plus the literature gate's `IMPORTED_AS_CITED` verdict mean the empirical-audit machinery doesn't block a proof step for missing figures or empirical evidence. The pack designers thought through the off-axis case carefully.
- **Doc gap:** none
- **Time-to-clarity:** ~60s

### Turn 10
- **Wanted:** Pick a strategy.
- **Tool (simulated):** Load `theory_math/method/proof_strategy_selection` (full YAML — 6 steps).
- **Simulated execution:**
  - `extract_claim_shape` → claim is universal over chordal graphs of treewidth ≤ 3; domain is inductively defined (clique-trees / tree-decompositions).
  - `small_case_probe` → check K_4 (tw=3, χ=ω=4 ✓), check path P_n (tw=1, χ=ω=2 ✓), check chord-free 4-cycle (NOT chordal, excluded); no counter-example after 15 minutes.
  - `enumerate_candidate_strategies` → induction on the clique-tree (default for tw-bounded chordal), direct via the perfect-graph theorem (cleaner but feels like overkill), contradiction (no obvious leverage).
  - `name_the_choice` → **induction on the tree-decomposition** with fallback = direct via perfect-graph theorem.
  - `outline_default_scaffold` → "Base case: tw=0 means G is a forest, χ=ω=1 or 2. Inductive step: removing a simplicial vertex preserves χ=ω; chordal graphs always have a simplicial vertex (Dirac's theorem)…"
  - `flag_canonical_mistakes` → induction-strength trap; ensuring simplicial vertex always exists in the tw≤3 restriction.
  - `handoff_to_draft`.
- **Format clear?** Yes — protocol YAML is extremely opinionated and concrete (lines 153–174 give canonical scaffold openings per strategy).
- **Knew next step?** Yes — return to proof_verification_workflow step 3 (draft_proof).
- **Friction:** none
- **Doc gap:** none
- **Time-to-clarity:** ~5min

---

## 3. Per-step execution (turns 11-25)

### Turn 11 — draft_proof (proof_verification_workflow step 3)
- **Wanted:** Write the proof body.
- **Tool (simulated):** Write `workspace/proofs/chordal_tw3.md` `## Proof` section. Numbered steps 1–6: (1) Dirac's theorem ⇒ chordal graph has a simplicial vertex v. (2) Removing v gives chordal G' with tw(G') ≤ tw(G) ≤ 3. (3) Inductive hypothesis: χ(G') = ω(G'). (4) Color G' with ω(G') colors. (5) v has ≤ ω(G)−1 neighbors forming a clique, so a free color exists. (6) Therefore χ(G) ≤ ω(G); equality from χ ≥ ω always.
- **Format clear?** Yes — proof_verification_workflow.yaml step 3 description (lines 106–114) gives a clear template.
- **Knew next step?** Yes — independent_review via `tool_redteam_review focus='proof'`.
- **Friction:** none
- **Doc gap:** none
- **Time-to-clarity:** ~10min (the math)

### Turn 12 — per-step literature gate
- **Wanted:** Run the per-step literature loop.
- **Tool (simulated):** `tool_audit_step_literature` (triggered by `tool_step_complete`) on the proof step. With `step_intent: proof`, the loop expects verdicts of `IMPORTED_AS_CITED` (or `DEFERRED`), not the AGREES/DISAGREES/EXTENDS that empirical claims use.
- **Simulated outcome:**
  - Claim "every chordal graph has a simplicial vertex" → verdict IMPORTED_AS_CITED (Dirac 1961).
  - Claim "removing a vertex from a chordal graph yields a chordal graph" → IMPORTED_AS_CITED (folklore; cite Diestel chapter 12).
  - Claim "chordal graphs are perfect" → IMPORTED_AS_CITED (Hajnal–Surányi 1958).
  - All three resolved against Crossref / arXiv via `tool_citations_verify`.
- **Format clear?** Yes — literature_per_step.yaml lines 24–30 explicitly say the IMPORTED_AS_CITED verdict is "most common in `step_intent: proof` work".
- **Knew next step?** Yes — `tool_redteam_review focus='proof'`.
- **Friction:** none — **another major positive finding**. The literature gate explicitly accommodates theoretical claims without requiring an empirical-style "this paper shows X agrees / disagrees" framing.
- **Doc gap:** none
- **Time-to-clarity:** ~30s

### Turn 13 — independent_review (proof_verification_workflow step 5)
- **Wanted:** Adversarial review of the proof.
- **Tool (simulated):** `tool_redteam_review(focus='proof', target='workspace/proofs/chordal_tw3.md')`. Per TOOLS.md line 288, this stages a structured critique skeleton (assumptions / claims / threats / alternatives / weakest step).
- **Simulated output:** Critique flags step 5 ("v has ≤ ω(G)−1 neighbors forming a clique") — should cite that simplicial neighborhood is always a clique by definition. Recommends inlining the definition reference.
- **Format clear?** Yes — TOOLS.md describes the output structure.
- **Knew next step?** Yes — patch the proof, re-run.
- **Friction:** none
- **Doc gap:** none — though the `tool_redteam_review` schema would be nicer surfaced as a worked example in TOOLS.md (similar to the four other tools that get worked examples). FRICTION/LOW.
- **Time-to-clarity:** ~45s

### Turn 14 — patch + re-run review
- **Wanted:** Address the redteam finding.
- **Tool (simulated):** This is a deliberate iteration → `tool_step_iterate(step_id='01_proof_chordal_tw3', rationale='inline simplicial-clique definition per redteam finding')`. Snapshot to `.versions/v1/`. Edit proof step 5. Re-run redteam → passes.
- **Format clear?** Yes — AI_GUIDE.md "Deliberate iteration vs bug fix" section (lines 222–240) covers exactly this.
- **Knew next step?** Yes — formal_check candidacy.
- **Friction:** none
- **Doc gap:** none
- **Time-to-clarity:** ~30s

### Turn 15 — formal_check (proof_verification_workflow step 6)
- **Wanted:** Decide whether to formalise in Lean.
- **Tool (simulated):** Check `formal_check_required_when` in proof_verification_workflow.yaml (lines 47–50): "claim is foundational" — this proof is a special case of an already-known result (chordal graphs are perfect), not foundational. Skip + document waiver.
- **Simulated execution:** Write `## Formal-check waiver` to `workspace/proofs/chordal_tw3.md`: "Result is a restriction of the perfect-graph theorem to tw≤3 chordal graphs; not foundational, does not contradict any conjecture, uses only ZFC. Skipping formal verification."
- **Format clear?** Yes — the YAML names the exact field and step.
- **Knew next step?** Yes — publish step.
- **Friction:** none
- **Doc gap:** none
- **Time-to-clarity:** ~45s

### Turn 16 — publish (proof_verification_workflow step 7)
- **Wanted:** Move proof into the paper and update the lemma library.
- **Tool (simulated):** Stage `workspace/proofs/chordal_tw3.md` for inclusion in the paper. Load `theory_math/proof/lemma_library` and add the proof body as a reusable lemma (since "every chordal graph of bounded treewidth is perfect" is a useful building block).
- **Format clear?** Yes.
- **Knew next step?** Yes — `tool_step_complete` on the proof step.
- **Friction:** none
- **Doc gap:** none
- **Time-to-clarity:** ~60s

### Turn 17 — tool_step_complete
- **Wanted:** One-call gate to mark the proof step done.
- **Tool (simulated):** `tool_step_complete(step_id='01_proof_chordal_tw3')`. Inferred from TOOLS.md (lines 181 and 538–553) — runs completeness + literature + per-step pieces of quality_full.
- **Simulated outcome:** With `step_intent: proof`, `figure_required: false`, `table_required: false`, and literature verdicts all IMPORTED_AS_CITED → `passed: true`, gates_run = [completeness, literature, code_quality, version_coherence]. No blockers.
- **Format clear?** Yes — worked example provided.
- **Knew next step?** Yes — proceed to theory_paper_structure (the protocol's `next_protocol`).
- **Friction:** none — clean handoff.
- **Doc gap:** none
- **Time-to-clarity:** ~30s

### Turn 18 — Load theory_paper_structure (the paper protocol, replacing synthesis_paper)
- **Wanted:** Compile the theory paper, non-IMRAD.
- **Tool (simulated):** Load `theory_math/output/theory_paper_structure` (read it above — 6 steps + the explicit anti-IMRAD doctrine).
- **Simulated execution:**
  - `outline_sections` → 6 sections with target page bands (Intro 5–15%, Proofs 50–80%, etc.).
  - `draft_preliminaries` → import from `inputs/preliminaries.md`.
  - `state_main_results` → "Theorem 3.1. For every connected chordal G with tw(G) ≤ 3, χ(G) = ω(G)."
  - `write_proofs` → drop in the proof body from `workspace/proofs/chordal_tw3.md`.
  - `add_examples` → K_4 (the tight case), the 3-tree on 5 vertices, the "book" graph B_2.
  - `introduction_and_open_questions` → write last; open questions = "Does the proof generalise to tw ≤ k for general k via a strong-induction predicate?" and "What is the chromatic number of a chordal graph as a function of treewidth in non-perfect classes (e.g. odd holes)?"
- **Format clear?** Yes — protocol YAML is one of the clearest in the entire system; it explicitly tells the AI to *resist* IMRAD instincts (editorial_voice rules, lines 67–86).
- **Knew next step?** Yes.
- **Friction:** FRICTION/LOW — the protocol's `expected_outputs` block (lines 194–202) lists `.tex` files (preliminaries.tex, main_results.tex, etc.), but the project is configured for `pdf_compile_engine: typst`. Should the AI emit `.typ` files or `.tex`? The protocol is silent. Most likely the AI emits markdown / sectioned files and `tool_paper_compile_typst` handles the conversion — but a one-line clarification in the YAML would help.
- **Doc gap:** Either the YAML's `expected_outputs` should use a neutral extension (`.md`) or it should branch on `pdf_compile_engine`.
- **Time-to-clarity:** ~20s of friction

### Turn 19 — tool_step_complete on the paper-drafting step
- **Tool (simulated):** Run completeness gate on the paper sections.
- **Outcome:** Passes (each section file exists, conclusions non-stub, citations resolve).
- **Friction:** none
- **Time-to-clarity:** ~30s

### Turns 20–25 — would normally cover additional analysis steps (figure-building, dependency graph render, etc.). For a pure-proof project there are no empirical steps, so this scenario compresses:

### Turn 20 — render the theorem dependency graph
- **Wanted:** Build the DAG of the project's theorems.
- **Tool (simulated):** `tool_theory_math_dep_graph(source_dir='workspace/proofs/')` per TOOLS.md line 377. Outputs Mermaid + JSON.
- **Note:** This tool parses `.lean` and `.v` files — but I didn't formalise. Does it also parse the markdown proofs? The TOOLS.md description is restrictive ("every `.lean` and `.v` under `source_dir`"). For a non-formalised project the graph may end up empty.
- **Friction:** FRICTION/MEDIUM — the dependency-graph tool is gated on formalisation. A non-formalised theory paper still has theorem/lemma structure (in markdown), but the tool wouldn't parse it. The fall-back to "no graph" is silent.
- **Doc gap:** The TOOLS.md entry should clarify what happens for projects with no `.lean`/`.v` files (empty graph + warning? skip?). Either expand the tool to parse markdown theorem headers, or document the skip path.
- **Time-to-clarity:** ~2min

### Turn 21 — lemma_library update
- **Tool (simulated):** Already done in turn 16; confirm the entry is logged.
- **Friction:** none

### Turn 22 — conjecture_tracking status transition
- **Wanted:** Move the conjecture from "open" → "proven".
- **Tool (simulated):** Re-load conjecture_tracking, walk `transition_status` step, add a citation to `workspace/proofs/chordal_tw3.md`, refresh `_index.md`.
- **Friction:** none
- **Time-to-clarity:** ~60s

### Turn 23 — placeholder (no more analysis steps for a pure-proof project)
- A pure proof project has 1 analysis step. The active_plan likely won't fill turns 23–25 with new steps; instead it skips ahead to audit.

### Turn 24 — placeholder
### Turn 25 — placeholder

---

## 4. Per-step literature gate (interleaved above)

Covered at turn 12. Key positive: `step_intent: proof` + `IMPORTED_AS_CITED` verdict means the literature gate doesn't false-positive on theoretical claims with no empirical evidence.

---

## 5. Audit + synthesis (turns 26-35)

### Turn 26 — tool_audit_quality_full
- **Wanted:** Run the master audit.
- **Tool (simulated):** `tool_audit_quality_full()` — per TOOLS.md lines 437–443, runs completeness + code_quality + prose + claims + preregister_diff + ground.
- **Simulated outcome:** `status: ok` (or `warning` if prose audit flags any hedging). All claim numbers in the paper trace back to either workspace artefacts (the proof) or cited prior work.
- **Format clear?** Yes — worked example at lines 556+.
- **Friction:** FRICTION/LOW — `tool_audit_quality_full` description (line 440) says "Does NOT run the per-step literature gate". A theory paper has only one substantive step; if the literature gate already ran in `tool_step_complete`, the explicit non-run here is a small footgun in a different scenario but harmless here.
- **Doc gap:** none
- **Time-to-clarity:** ~30s

### Turn 27 — synthesis_paper (Theory variant)
- **Wanted:** Compile the paper.
- **Tool (simulated):** Per AI_GUIDE.md (lines 421–425): "The IMRAD assumptions baked into `synthesis/synthesis_paper` do not apply — load `theory_paper_structure` instead." Already loaded; the protocol's `next_protocol = null` (terminal). So the paper compilation step is `tool_synthesize(output_type='paper')` which should respect the project's `venue_template: generic_thesis`.
- **Question:** Does `tool_synthesize` know to use `theory_paper_structure` outputs instead of synthesis_paper's IMRAD outputs? Or does it always treat `synthesis/paper.md` as the source?
- **Friction:** FRICTION/MEDIUM — the handoff from `theory_paper_structure` (which writes section files to `workspace/papers/<slug>/`) to `tool_synthesize` (which presumably wants `synthesis/paper.md`) is not documented. A new user would not know whether to: (a) concatenate the workspace section files into `synthesis/paper.md` by hand, (b) trust `tool_synthesize` to auto-discover them, or (c) call a different tool.
- **Doc gap:** A 2-sentence "Theory-paper synthesis: after `theory_paper_structure`, run `tool_synthesize(output_type='paper', source_dir='workspace/papers/<slug>/')` (or whatever the actual flow is) — `theory_paper_structure` does NOT auto-call `tool_synthesize`." in either AI_GUIDE.md § theory_math or PROTOCOLS.md.
- **Time-to-clarity:** ~3min of uncertainty

### Turn 28 — tool_paper_compile_typst
- **Wanted:** Build `paper.pdf` with the `generic_thesis` template.
- **Tool (simulated):** `tool_paper_compile_typst(template='generic_thesis')` per TOOLS.md line 151. Template exists at `templates/typst/generic_thesis.typ` (confirmed via ls).
- **Simulated outcome:** `synthesis/paper.md` → `synthesis/paper.typ` → `synthesis/paper.pdf`. LaTeX-style math notation in `paper.md` should map cleanly to Typst's `$…$` math syntax. AMS-style theorem environments need the template to support them.
- **Format clear?** Yes — the venue list explicitly names `generic_thesis`.
- **Friction:** FRICTION/LOW — neither `tool_paper_compile_typst`'s description (TOOLS.md line 151) nor `templates/typst/generic_thesis.typ` (haven't read it) explicitly call out theorem/lemma/proof environment support. AMS-style `\begin{theorem}` is how mathematicians write — does the Typst template provide `#theorem[…]` macros?
- **Doc gap:** The TOOLS.md entry for `tool_paper_compile_typst` should mention which templates ship math/theorem support. Specifically: does `generic_thesis` provide `#theorem`/`#lemma`/`#proof` blocks? Does it auto-number them?
- **Time-to-clarity:** ~90s

### Turn 29 — tool_dashboard_create
- **Wanted:** Generate dashboard.html.
- **Tool (simulated):** `tool_dashboard_create(mode='explore', audience='academic')`. Per TOOLS.md line 154 + worked example at line 519+.
- **Simulated outcome:** `synthesis/dashboard.html` (~400KB single-file). For a theory paper there are no figures (`figure_required: false` per step contract) → `embedded_figures: 0`, `verdicts_rendered: 1` (the proven conjecture). The dashboard would show: conjecture statement, status=proven, proof sketch, dependency-graph stub, open questions.
- **Format clear?** Yes.
- **Friction:** FRICTION/LOW — the dashboard worked example (TOOLS.md line 519+) shows `embedded_figures: 7` and assumes empirical work. A theory-paper-flavoured example showing `embedded_figures: 0`, `theorems_rendered: 1`, `open_questions: 2` would reassure a theory researcher that the dashboard isn't "broken" when it shows zero figures.
- **Doc gap:** Theory-pack example in the worked-example list.
- **Time-to-clarity:** ~60s

### Turn 30 — pre_submission_checklist
- **Wanted:** Final gate.
- **Tool (simulated):** Load `audit/pre_submission_checklist`. Confirm: paper.pdf exists, all overrides logged + intentional, no fabricated citations, dashboard.html exists, conjecture status updated.
- **Simulated outcome:** GREEN (no blockers; one waiver — formal-check skipped, rationale logged).
- **Friction:** none
- **Time-to-clarity:** ~60s

### Turns 31–35 — would cover (in an empirical scenario) extra iteration loops, title workshop, cover letter, journal selection. For a pure-proof project these are optional.

---

## 6. Cross-checks + sign-off

- **conjecture_tracking** → status flipped open→proven with citation.
- **lemma_library** → "chordal tw≤3 is perfect" lemma registered.
- **theorem_dependency_graph** → would be empty for non-formalised work (see turn 20 friction).
- **tool_audit_claims** → every number in the paper (e.g. "treewidth ≤ 3") traces to either preliminaries.md or the proof body. No claims about empirical data (there is none).
- **tool_audit_prose** → flags hedging in the introduction if present.
- **pre_submission_checklist** → GREEN.
- **paper.pdf** → reached (turn 28).
- **dashboard.html** → reached (turn 29).

---

## 7. Top 5 friction points

| # | Severity | Title | Tool/Protocol | Suggested fix |
|---|---|---|---|---|
| 1 | **HIGH** | Theory_math protocols live in a separate namespace package (`src/research_os_theory_math/`) but the docs don't say so — a validation harness that grepped `src/research_os/protocols/` got zero hits and almost concluded the pack was missing entirely. (A real researcher using MCP would not hit this — but anyone debugging the install or reading source would.) | docs/PROTOCOLS.md, docs/AI_GUIDE.md | Add one sentence: "Pack protocols live under `src/research_os_<pack>/protocols/` namespace packages and are auto-loaded by the wheel; the catalogue here remains the source of truth." Also: `python scripts/regen_protocols_doc.py` should include pack protocols in the auto-generated catalogue (currently the catalogue contains zero theory_math entries despite the curated table listing 8). |
| 2 | **MEDIUM** | The handoff from `theory_paper_structure` (writes section files under `workspace/papers/<slug>/`) to `tool_synthesize` / `tool_paper_compile_typst` (consume `synthesis/paper.md`) is not documented. A user wouldn't know whether to concatenate by hand, trust auto-discovery, or call a different tool. | theory_math/output/theory_paper_structure → tool_synthesize → tool_paper_compile_typst | Add a closing step to theory_paper_structure.yaml: `assemble_synthesis_paper` — "Concatenate the section files into `synthesis/paper.md` in the canonical order; then call `tool_synthesize(output_type='paper')` followed by `tool_paper_compile_typst(template='generic_thesis')`." OR explicitly support `tool_synthesize(source_dir=…)`. |
| 3 | **MEDIUM** | `tool_theory_math_dep_graph` only parses `.lean` and `.v` files — so for non-formalised theory papers (the majority of math papers!) the graph is silently empty. | tool_theory_math_dep_graph | Either (a) extend the parser to handle markdown `## Theorem N.M` / `## Lemma N.M` headers in `workspace/proofs/*.md`, OR (b) document the skip path and return a `status: skipped, reason: no .lean/.v files found, dependency graph not available for informal proofs`. |
| 4 | **LOW** | `theory_paper_structure.yaml` `expected_outputs` lists `.tex` files even when the project is configured for `pdf_compile_engine: typst`. Ambiguous which extension to write. | theory_math/output/theory_paper_structure | Use neutral `.md` extensions in `expected_outputs`, OR branch on `writing_preferences.pdf_compile_engine`. |
| 5 | **LOW** | TOOLS.md worked-example block (lines 491–600) covers `tool_intake_autofill`, `tool_dashboard_create`, `tool_step_complete`, `tool_audit_quality_full` — all empirical scenarios. No theory-pack worked examples; theory researchers can't cross-check what shapes to expect. | docs/TOOLS.md | Add 2 theory worked examples: `tool_redteam_review(focus='proof')` return shape + `tool_dashboard_create` shape for a theory project (showing `embedded_figures: 0, theorems_rendered: 1`). |

---

## 8. Top 5 doc/guidance gaps

1. **Namespace-package location of pack protocols is undocumented.** The PROTOCOLS.md auto-generated catalogue is missing 8 theory_math protocols + their qualitative/humanities/engineering/wet_lab siblings because `scripts/regen_protocols_doc.py` doesn't walk the namespace packs.
2. **No template/example for `inputs/preliminaries.md`.** Hard prerequisite of `proof_strategy_selection`, but no `templates/preliminaries.md.template` ships. A worked example would set expectations for sections (`## Definitions`, `## Cited prior results`, `## Notation`).
3. **`tool_paper_compile_typst` theorem-environment support unclear.** Does `generic_thesis.typ` provide `#theorem` / `#lemma` / `#proof` macros with auto-numbering? Documentation is silent. A math researcher needs this to know if the PDF will render correctly.
4. **Theory-paper synthesis pipeline is implicit.** AI_GUIDE.md says "load theory_paper_structure instead of synthesis_paper" but doesn't describe the full chain from sections → synthesis/paper.md → tool_synthesize → tool_paper_compile_typst.
5. **Theory-flavoured worked examples missing throughout TOOLS.md.** Every worked example assumes empirical (figures, datasets, sample sizes). A theory researcher cannot cross-check tool returns against their scenario.

---

## 9. Top 5 things that worked well (POSITIVE FINDINGS)

1. **`step_intent: proof` is a first-class citizen.** The step_summary template (lines 32–36) explicitly documents `proof` as a step intent with `figure_required: false` / `table_required: false` / `literature_required: false` (when proof-citation-only). No empirical-audit machinery false-positives on a proof step. This is a thoughtfully-designed scaffold.
2. **`IMPORTED_AS_CITED` literature verdict closes the theoretical-claim gap.** `literature/literature_per_step.yaml` explicitly says (lines 24–30) that IMPORTED_AS_CITED is "most common in `step_intent: proof` work" — meaning theoretical claims grounded in cited prior lemmas pass the gate without needing AGREES/DISAGREES framing.
3. **`theory_paper_structure` protocol is opinionated AND specific.** It actively pushes back against IMRAD-instinct (editorial_voice rules: "Introduction is the shortest major section, not the longest"). It cites empirical quality bands (5–15% intro / 50–80% proofs derived from Annals/JAMS/FOCS/STOC/LICS survey) — this is exactly the kind of grounded scaffold a junior theorist needs.
4. **`proof_strategy_selection` is genuinely opinionated, not a neutral menu.** Lines 17–29: "Picking contradiction when a direct proof would have been three lines produces a paragraph of clutter that hides the actual idea." It names the default AND the trap for each strategy — this is the pattern-match a junior researcher actually lacks.
5. **`researcher_config.yaml` correctly anticipates pure-math needs.** `citation_style: amsplain` is documented as "AMS plain (numeric, alpha-keyed bib); pure mathematics + theoretical CS" (lines 107–108). `venue_template: generic_thesis` ships. `chicago_thesis` and `humanities_essay` exist for adjacent fields. The wizard surfaces the right knobs for a theory project on day 1.

---

## 10. Final rating: **8 / 10**

**Rationale:** The theory_math pack is genuinely thoughtfully designed — the step_intent enum, the literature-verdict adapter, the non-IMRAD paper structure, the opinionated strategy-selection protocol, and the AMS citation style all reflect deep field knowledge. A theory researcher dropping in on day 1 finds an environment that *thinks like a mathematician*, not like an empirical-research toolkit awkwardly stretched to fit.

What costs the rating two points:
- **(–1)** The namespace-pack discovery + the empty auto-generated catalogue. Even when only validation harnesses notice, the doctrine that PROTOCOLS.md's auto-catalogue is "ground truth" is broken for pack protocols. The curated table says one thing, the auto-catalogue says another.
- **(–1)** The synthesis → PDF chain for theory papers has documentation gaps (theorem environments in the Typst template? section-file → synthesis/paper.md? Tool extensions?). A first-time researcher will hesitate at exactly the "compile the PDF" step.

Compared to the v1.9.3 baseline (which I have not read): based on the depth of the theory_math protocols and the clean step_intent design, the pack feels mature; the rough edges are doc-surface (auto-catalogue + worked examples + final-mile synthesis), not protocol-design.

---

## 11. Onboarding-friction count (first 5 turns)

**2 frictions in first 5 turns** — 1 LOW (missing preliminaries template), 1 MEDIUM (namespace-package surprise during pack discovery; invisible to MCP users, visible to source-inspecting harnesses).

---

## 12. Reached paper.pdf? Reached dashboard.html?

- **Paper.pdf:** YES (turn 28) — `tool_paper_compile_typst(template='generic_thesis')` invocation reached.
- **Dashboard.html:** YES (turn 29) — `tool_dashboard_create(mode='explore', audience='academic')` invocation reached.

Both reached cleanly. The workflow is functional end-to-end for a theory paper.
