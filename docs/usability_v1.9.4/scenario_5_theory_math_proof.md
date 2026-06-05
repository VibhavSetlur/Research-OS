# Scenario 5 — Theory / Math — Small Proof Outline

Validation date: 2026-06-05
Research-OS version: 1.9.4 (per CHANGELOG; v1.9.3 is the most recent detailed CHANGELOG entry the docs ship with)
Validator profile: fresh AI agent, doc-surface-only

Hypothesis under test:
> For every connected graph G in class C (chordal graphs of treewidth <= 3),
> the chromatic number chi(G) equals the clique number omega(G).

Project type: pure-theory (no empirical data), single main theorem, ~3-5 supporting lemmas anticipated.
Expected deliverables: paper.pdf (generic_thesis venue), dashboard.html, proof sketch with LaTeX/Typst math.

---

## 1. Project setup (turns 1-5)

### Turn 1
- What I wanted to do: scaffold a new Research-OS project for a pure-theory problem.
- Tool I called: read `docs/START.md`, then plan to run `research-os init` in an empty dir.
- Simulated result: docs say "scaffold your first project (15s) — `mkdir my-project && cd my-project && research-os init`. Wizard collects location / name / domain / question / IDE."
- Format clear? yes — the install + scaffold cookbook in START.md is excellent.
- Knew what to do next? yes.
- Friction: none.
- Doc gap: none.
- Time-to-clarity: 30s.

### Turn 2
- What I wanted to do: confirm the wizard supports a "no data, theory-only" project.
- Tool I called: re-read START.md and `docs/USE_CASES.md` looking for "theory" / "theorem" / "proof".
- Simulated result: zero hits for any of those words across START, USE_CASES, RESEARCHER_GUIDE, FAQ, AI_GUIDE, PROTOCOLS.md. The closest match is the "no project yet, just thinking" researcher row which routes to `methodological_consultation` or `scope_clarification` — neither is a proof workflow.
- Format clear? no — the docs treat "no data" as "you haven't loaded data yet", not "this project will never have data".
- Knew what to do next? partially — I would have to guess that I should run `init` anyway and skip the data-drop step.
- Friction: **FRICTION/HIGH** — the entire user-facing doc set is silent on theory/math projects despite the bundled `research_os_theory_math` pack with 8 protocols + 3 tools. A theorist landing on START.md has no reason to believe Research-OS supports them.
- Doc gap: **`docs/USE_CASES.md` has no "theorist / pure-math" role row; `docs/START.md` has no theory example; `docs/PROTOCOLS.md` does not list the theory_math pack.**
- Time-to-clarity: 240s.

### Turn 3
- What I wanted to do: actually run `research-os init`.
- Tool I called: `research-os init` (simulated). The wizard asks 7 questions: location / name / domain / research question / IDEs / smoke check.
- Simulated result: scaffolds `inputs/{raw_data,literature,context}/`, `workspace/`, `synthesis/`, `docs/`, `.os_state/`, plus `AGENTS.md`, `CLAUDE.md`, MCP configs, `inputs/researcher_config.yaml`.
- Format clear? yes — but `inputs/raw_data/` and `inputs/literature/` are mandatory directories I will never populate. The wizard has no "this is a theory project, skip the data scaffolding" branch.
- Knew what to do next? yes.
- Friction: **FRICTION/LOW** — empty `inputs/raw_data/` is harmless but signals to the AI that intake is incomplete. Wizard should offer a `--project-kind theory` flag.
- Doc gap: wizard option for project_kind not documented.
- Time-to-clarity: 60s.

### Turn 4
- What I wanted to do: open `inputs/researcher_config.yaml` and set the writing preferences for a theory paper.
- Tool I called: read `templates/researcher_config.yaml`.
- Simulated result: `writing_preferences.venue_template` accepts `generic_thesis` (one of 10 templates). I would set `venue_template: "generic_thesis"`, `pdf_compile_engine: "typst"`, `citation_style: "apa"` (no math-specific style like `amsplain` or `siam`). `project_tier: "production"`.
- Format clear? mostly yes.
- Knew what to do next? yes.
- Friction: **FRICTION/MEDIUM** — `citation_style` enum is `apa | vancouver | acm | ieee | nature`. None of these are the conventional math style (`amsplain`, `alpha`, `siam`). A theorist writing for *Annals of Mathematics* has no in-band choice.
- Doc gap: `writing_preferences.citation_style` does not list math/CS-theory styles; no `theory_math_format` knob.
- Time-to-clarity: 90s.

### Turn 5
- What I wanted to do: drop "data" in inputs/. I have NONE.
- Tool I called: write `inputs/context/preliminaries.md` (the definitions of "chordal", "treewidth", chi, omega) and `inputs/context/known_results.md` (Dirac 1961, Hajnal-Suranyi 1958, etc.).
- Simulated result: the docs say `inputs/context/` is the right home for notes / drafts / past reports. The wizard does not pre-create a `preliminaries.md`.
- Format clear? yes.
- Knew what to do next? yes.
- Friction: **FRICTION/MEDIUM** — `inputs/preliminaries.md` is referenced as a hard prereq by `theory_math/method/proof_strategy_selection.yaml` ("The objects in the claim have definitions reachable from `inputs/preliminaries.md`"), but the wizard does not seed it and no doc tells the user it exists. Discovered only by reading the pack YAML.
- Doc gap: **`inputs/preliminaries.md` is undocumented in user-facing docs but is a hard prereq for the proof_strategy_selection protocol.**
- Time-to-clarity: 150s.

**Onboarding-friction count (first 5 turns): 4 (1 HIGH, 1 MEDIUM x2, 1 LOW)**

---

## 2. Hypothesis + planning (turns 6-10)

### Turn 6
- What I wanted to do: open the IDE, fire `sys_boot`, then `tool_route` on the prompt.
- Tool I called: `sys_boot` (per AI_GUIDE).
- Simulated result: returns state (empty), config (default + my venue_template override), no history, dep inventory (typst yes, lean no, coq no), no active plan, pause_classification null, recommended next protocol likely `guidance/project_startup` (default for empty state).
- Format clear? yes.
- Knew what to do next? yes.
- Friction: none.
- Time-to-clarity: 5s.

### Turn 7
- What I wanted to do: route my hypothesis.
- Tool I called: `tool_route(prompt="I have a conjecture: for every connected chordal graph of treewidth <= 3, chi(G) = omega(G). Help me prove it and write it up as a theory paper.")`.
- Simulated result: based on the L1->L2->L3 router and the trigger strings in `theory_math/proof/proof_verification_workflow.yaml` ("prove this", "I have a claim I need to prove", "proof verification"), the router SHOULD pick `theory_math/proof/proof_verification_workflow` or `theory_math/conjecture/conjecture_tracking`. Cannot verify without invoking — but I have to trust the detector.py + router_entries.py in the pack (which I am not allowed to read).
- Format clear? partial.
- Knew what to do next? partial — if the router did NOT pick a theory_math protocol, I have no doc-surface way to force it (e.g., "use the theory_math pack" is not a documented re-route phrase).
- Friction: **FRICTION/HIGH** — there is no user-facing doc that says "to invoke theory_math, say X". The trigger strings live only inside the YAML. A user who phrases their prompt as "I want to study chromatic numbers" without using the magic words "prove" or "proof" may get routed to `methodological_consultation` and never see the theory_math pack.
- Doc gap: **no doc lists trigger phrases per pack; no doc tells the user the theory_math pack even exists.**
- Time-to-clarity: 180s.

### Turn 8
- What I wanted to do: register the conjecture.
- Tool I called: load `theory_math/conjecture/conjecture_tracking` summary, then run its 5 steps (scan_register / state_conjecture / link_dependents / log_partial_progress / transition_status).
- Simulated result: writes `workspace/conjectures/_index.md` and `workspace/conjectures/chordal_chi_eq_omega_tw3.md` with `## Statement`, `## Attribution` (Dirac 1961 for the unconstrained chordal case), `## Why it matters`, `## Status: open` (or `partial_progress` since the unconstrained chordal case is already proven).
- Format clear? yes — conjecture_tracking.yaml is excellent.
- Knew what to do next? yes — the protocol's `next_protocol` is null but the workflow obviously continues to `proof_strategy_selection`.
- Friction: **FRICTION/LOW** — `next_protocol: null` on conjecture_tracking is plausible (it's a registry, not a phase), but a fresh user might not know to manually invoke the proof workflow next.
- Time-to-clarity: 60s.

### Turn 9
- What I wanted to do: pick a proof strategy.
- Tool I called: load `theory_math/method/proof_strategy_selection` summary, run its 6 steps (extract_claim_shape / small_case_probe / enumerate_candidate_strategies / name_the_choice / outline_default_scaffold / flag_canonical_mistakes).
- Simulated result: writes `workspace/proofs/chordal_chi_eq_omega_tw3.md` with `## Claim shape: universal over chordal connected graphs of treewidth <= 3`, `## Candidate strategies` (six one-liners), `## Strategy: induction on tree decomposition (well-founded)`, fallback: direct via perfect-elimination ordering. Probe file: `workspace/proofs/chordal_chi_eq_omega_tw3_probe.md` showing K_4 is the boundary case (treewidth 3 exactly).
- Format clear? yes — protocol is detailed and opinionated.
- Knew what to do next? yes.
- Friction: none.
- Time-to-clarity: 30s.

### Turn 10
- What I wanted to do: set up the global hypothesis register so the project tracks the main result.
- Tool I called: `mem_hypothesis_add(text=<conjecture>, status="active")` (per TOOLS.md).
- Simulated result: hypothesis goes into `state.active_hypotheses`.
- Format clear? yes.
- Knew what to do next? yes — but I notice the `mem_hypothesis_*` family is built around empirical hypothesis-testing (status: active / supported / refuted / pending). For a math conjecture, the conjecture_tracking lattice (open / partial_progress / proven / disproven / counter_example_found) is the correct one. Maintaining BOTH is silly.
- Friction: **FRICTION/MEDIUM** — duplication between `mem_hypothesis_*` (state-level, empirical-shaped) and `conjecture_tracking` (workspace-level, math-shaped) is undocumented. The fresh user does not know which to use.
- Doc gap: **no doc explains the relationship between `mem_hypothesis_*` and `theory_math/conjecture/conjecture_tracking`.**
- Time-to-clarity: 120s.

---

## 3. Per-step execution (turns 11-25)

For a theory project, the "step" abstraction maps to: state lemma -> pick strategy -> draft proof -> independent review -> formal check (optional) -> publish-into-paper. I model 4 supporting lemmas + 1 main theorem.

### Turn 11 — Lemma 1: Every chordal graph has a perfect elimination ordering (PEO).
- What I wanted to do: this is a CITED lemma (Dirac 1961, Fulkerson-Gross 1965), not a novel claim. Register it in the lemma library as a reference-only entry.
- Tool I called: load `theory_math/proof/lemma_library`, run scan_register -> state lemma -> proof = reference-only.
- Simulated result: writes `workspace/lemmas/peo_exists.md` with `## Statement`, `## Proof: see @fulkerson_gross_1965`, `## Dependents: lemma 2, theorem 1`.
- Format clear? yes.
- Friction: **FRICTION/MEDIUM** — the lemma_library editorial_voice says "A lemma earns library status only if it will be cited by at least two other results". For my proof outline I only have 4-5 internal results. The threshold is fine but the editorial_voice is not documented anywhere except the YAML.
- Time-to-clarity: 60s.

### Turn 12 — Lemma 1 literature gate.
- What I wanted to do: ground Lemma 1 in literature.
- Tool I called: `tool_audit_step_literature` against the lemma. Per TOOLS.md: "BLOCKs if `workspace/<step>/literature/findings_vs_literature.md` missing, any claim lacks a Verdict (AGREES | DISAGREES | EXTENDS | DEFERRED)".
- Simulated result: **GATE FAILS**. The audit looks under `workspace/<step>/literature/findings_vs_literature.md`. My lemma lives under `workspace/lemmas/peo_exists.md`, not `workspace/<step>/`. Even if I create the literature dir, the verdict vocabulary (AGREES / DISAGREES / EXTENDS / DEFERRED) is built for empirical findings. For a CITED prior lemma, the only natural verdict is "imported as cited prior result" — which is not in the enum.
- Format clear? no.
- Knew what to do next? no — three plausible workarounds: (a) tag the lemma as `literature_required: false` per literature_per_step.yaml's "do NOT use when ... pure data engineering" carve-out (but the carve-out is for data eng, not theory); (b) write a `findings_vs_literature.md` with verdict AGREES citing Fulkerson-Gross; (c) override the gate. None is signposted.
- Friction: **FRICTION/HIGH** — the per-step literature gate has no theory-mode. The AGREES / DISAGREES / EXTENDS verdict triad assumes a NEW empirical finding being compared to literature, not a CITED PRIOR RESULT being reused as a lemma. For theory projects half the "findings" are imported prior results.
- Doc gap: **no doc explains how literature_per_step.yaml's verdict enum applies (or doesn't) to theory work. The "Do NOT use when ... pure data engineering" exemption needs a "pure theory / cited prior result" extension.**
- Time-to-clarity: 360s.

### Turn 13 — Lemma 2: tree decomposition of width 3 yields a 4-colouring greedy on the elimination ordering.
- What I wanted to do: novel-ish lemma, needs real proof. Run `proof_verification_workflow` end-to-end.
- Tool I called: `theory_math/proof/proof_verification_workflow` summary; then state_claim / pick_strategy / draft_proof / independent_review / formal_check / publish.
- Simulated result: writes `workspace/proofs/greedy_4col_tw3.md`. Strategy: direct, by induction on bag elimination. Independent review: invokes `tool_redteam_review focus='proof'` (the workflow YAML mentions this — but the tool is NOT in TOOLS.md's listed tools table for theory_math; I have to assume it's a general adversarial-review tool).
- Format clear? partial.
- Knew what to do next? yes.
- Friction: **FRICTION/MEDIUM** — `tool_redteam_review` referenced inside `proof_verification_workflow.yaml` is not documented in TOOLS.md's index. Either it's a real tool buried in the unified `tool_verify` dispatcher or it's a phantom reference.
- Doc gap: **`tool_redteam_review` undocumented.**
- Time-to-clarity: 120s.

### Turn 14 — Lemma 2 literature gate (retry with workaround).
- What I wanted to do: per-step literature gate on the lemma.
- Tool I called: create `workspace/proofs/greedy_4col_tw3/literature/findings_vs_literature.md` with verdict EXTENDS (it extends Hajnal-Suranyi's chordal => perfect to the tw<=3 effective bound).
- Simulated result: gate PASSES because I shoehorned the verdict.
- Format clear? barely.
- Knew what to do next? yes — but only because I figured out the shoehorn.
- Friction: **FRICTION/MEDIUM** — the verdict EXTENDS works mechanically but the prose template "if EXTENDS, what is the leap + acknowledge limits" is empirical-flavoured. A theorist would write "this is a specialization of <cited>", not "extending beyond what's published".
- Time-to-clarity: 90s.

### Turn 15 — Lemma 3: K_4 is the unique forbidden subgraph at tw=3.
- What I wanted to do: standard graph-theory fact; reference-only via Robertson-Seymour minor theory.
- Tool I called: lemma_library register, reference-only proof, audit_step_literature with verdict AGREES.
- Simulated result: passes.
- Format clear? yes.
- Friction: none (now that I know the workaround).
- Time-to-clarity: 30s.

### Turn 16 — Lemma 4: chordal + 4-colouring + clique-cover-bound argument.
- What I wanted to do: glue lemma for the main theorem. Run proof_verification_workflow.
- Tool I called: workflow on `workspace/proofs/clique_chi_match.md`.
- Simulated result: strategy = direct, draft a 1-page proof, request independent review.
- Format clear? yes.
- Friction: none.
- Time-to-clarity: 60s.

### Turn 17 — Main Theorem assembly.
- What I wanted to do: state the main theorem and prove it via the 4 lemmas.
- Tool I called: proof_verification_workflow on `workspace/proofs/main_chordal_tw3_chi_eq_omega.md`.
- Simulated result: writes claim, strategy=direct(by lemmas), proof body cites lemmas 1-4. independent_review invokes `tool_redteam_review` (undoc — see Turn 13).
- Format clear? yes.
- Friction: none beyond Turn 13.
- Time-to-clarity: 60s.

### Turn 18 — Build theorem dependency graph.
- What I wanted to do: run the DAG protocol.
- Tool I called: `theory_math/proof/theorem_dependency_graph`. The mechanical edge extraction step uses `tool_theory_math_dep_graph` — but the YAML notes it parses `.lean` and `.v` files. I have NO formalised files. So the tool produces an empty graph.
- Simulated result: empty Mermaid + JSON. The protocol then says the AI "reconciles lexical edges with the proof body" — i.e. I have to hand-write the entire graph by parsing my own `workspace/proofs/*.md` files.
- Format clear? no.
- Knew what to do next? partial — the protocol does cover the manual fallback (`workspace/docs/dep_graph_manual.md`), but the experience is jarring: the headline tool produces nothing useful for informal proofs.
- Friction: **FRICTION/MEDIUM** — `tool_theory_math_dep_graph` does not handle informal markdown proofs. For a "small proof outline" scenario (no Lean / Coq), the user gets an empty graph and a manual-edit instruction.
- Doc gap: **TOOLS.md does not flag that `tool_theory_math_dep_graph` requires formal source files.**
- Time-to-clarity: 180s.

### Turn 19 — Formal-check decision.
- What I wanted to do: decide whether to run Lean/Coq.
- Tool I called: re-read `proof_verification_workflow.yaml` step `formal_check`. Triggers: foundational / contradicts a widely-believed conjecture / uses unusual axioms. My result is a special case of a 60-year-old theorem; none of the triggers apply.
- Simulated result: write `## Formal-check waiver` in the proof file explaining "result is a known corollary of Dirac 1961, no novel axiom use".
- Format clear? yes.
- Friction: none.
- Time-to-clarity: 30s.

### Turn 20 — Step-completeness audit for all 4 lemmas + theorem.
- What I wanted to do: run `tool_audit_step_completeness` per "step".
- Tool I called: `tool_audit_step_completeness` against each `workspace/proofs/<slug>/` and `workspace/lemmas/<slug>/`.
- Simulated result: **FAILS**. The tool's per-step gate per TOOLS.md requires "focal figure + caption + summary sidecars + non-stub conclusions + no mega-script". A theory step has NO figure, NO script, NO conclusions.md — only a proof.md.
- Format clear? no.
- Knew what to do next? no — there is no `--theory` mode for the audit. The override hatch exists (`override_completeness_gate=true` + rationale) but every single proof step would need an override entry.
- Friction: **FRICTION/HIGH** — `tool_audit_step_completeness` has no theory mode. A pure-theory project will trigger an override for every step, every audit, every release.
- Doc gap: **no doc tells the user that step-completeness gates expect figure + conclusions + script artefacts and how to satisfy them for theory work.**
- Time-to-clarity: 360s.

### Turn 21 — Step-completeness audit override.
- What I wanted to do: override the gate per proof.
- Tool I called: per AI_GUIDE: `tool_synthesize(override_completeness_gate=true, override_rationale="...")`. But the override docs are for `tool_synthesize` and `tool_dashboard_create` and `tool_plan_advance` — NOT for `tool_audit_step_completeness` itself.
- Simulated result: ambiguous — would the audit gate accept an override flag? Not clear from docs.
- Format clear? no.
- Friction: **FRICTION/HIGH** — overrides documented only at the synthesis-level. For a project where every step independently violates completeness, the user has no clean per-step path.
- Doc gap: **no doc shows how to override per-step audit gates; only the synthesis-level override is documented.**
- Time-to-clarity: 240s.

### Turn 22 — Step-literature gate, scope-clarified.
- What I wanted to do: do the literature ground for the main theorem.
- Tool I called: `tool_audit_step_literature` on the main theorem.
- Simulated result: I write `findings_vs_literature.md` with verdict AGREES (the main theorem is a corollary of Dirac 1961 restricted to tw<=3) and cite Dirac + Hajnal-Suranyi + Robertson-Seymour. Passes.
- Format clear? yes after Turn 14.
- Friction: none.
- Time-to-clarity: 60s.

### Turn 23 — Memory log + decision log.
- What I wanted to do: record the proof-strategy choice for posterity.
- Tool I called: `mem_log(kind="decision", text="Chose induction on tree decomposition because the inductive hypothesis = chi=omega on smaller bags propagates cleanly via PEO.")`.
- Simulated result: appended.
- Format clear? yes.
- Friction: none.
- Time-to-clarity: 30s.

### Turn 24 — Pre-synthesis quality check.
- What I wanted to do: run `tool_audit_quality_full`.
- Tool I called: per TOOLS.md, this is the gate before `tool_synthesize` runs.
- Simulated result: aggregates completeness, claims, code quality, prose, citations, preregister diff. For my project: completeness BLOCKS (no figures, no scripts), code quality N/A (no code), prose passes, citations passes (Crossref-verified), preregister N/A.
- Format clear? partial.
- Knew what to do next? no — the blocker on completeness will refuse synthesis unless I override.
- Friction: **FRICTION/HIGH** — `tool_audit_quality_full` aggregates a completeness blocker that is structurally impossible for theory projects to satisfy. The override is project-wide, which means every theory project requires a project-wide override pin in the override log.
- Time-to-clarity: 180s.

### Turn 25 — Decide on the synthesis path.
- What I wanted to do: pick a synthesis protocol for a theory paper.
- Tool I called: per USE_CASES.md, the canonical "draft the paper" routes to `synthesis/synthesis_paper`. But there's also `theory_math/output/theory_paper_structure`.
- Simulated result: I need both. `theory_paper_structure` is the non-IMRAD outline (Intro / Prelims / Main Results / Proofs / Examples / Open Questions); `synthesis_paper` is the synthesis pipeline that builds paper.md and feeds `tool_paper_compile_typst`.
- Format clear? no — the relationship between `theory_paper_structure` (pack) and `synthesis_paper` (core) is not documented. They likely chain (pack -> core) but no doc says so.
- Knew what to do next? partial.
- Friction: **FRICTION/HIGH** — two parallel synthesis paths (core `synthesis_paper` is IMRAD-shaped; pack `theory_paper_structure` is theory-shaped) with NO documented relationship. The user has no idea which to invoke or whether they should chain.
- Doc gap: **no doc explains how pack-specific output protocols (theory_paper_structure) integrate with core synthesis (synthesis_paper + tool_paper_compile_typst).**
- Time-to-clarity: 300s.

---

## 4. Per-step literature gate (interleaved above)

Summary of literature-gate behaviour:
- Lemma 1 (cited prior): no verdict in the AGREES/DISAGREES/EXTENDS/DEFERRED enum fits "imported as cited prior result". I shoehorned AGREES.
- Lemma 2 (novel-ish): verdict EXTENDS with empirical-flavoured prose template, awkward.
- Lemma 3 (cited prior): AGREES, same shoehorn as Lemma 1.
- Lemma 4 (glue): EXTENDS, awkward.
- Main theorem: AGREES (corollary of Dirac), works.

The literature gate "works" for theory but only via repeated shoehorning. The verdict enum needs a `IMPORTED_AS_CITED` or `SPECIALIZES` value for theory work.

---

## 5. Audit + synthesis (turns 26-35)

### Turn 26 — `tool_audit_quality_full` with overrides.
- What I wanted to do: re-run with the documented synthesis-level override.
- Tool I called: not the audit — instead jump to `tool_synthesize(override_completeness_gate=true, override_rationale="pure theory: no scripts/figures expected per theory_paper_structure")`.
- Simulated result: synthesis proceeds.
- Format clear? yes.
- Friction: see Turn 24.

### Turn 27 — `synthesis_paper` chain start.
- What I wanted to do: load synthesis_paper protocol summary.
- Tool I called: `sys_protocol_get name='synthesis/synthesis_paper' format='summary'`.
- Simulated result: synthesis_paper is IMRAD-shaped. It expects Introduction / Methods / Results / Discussion. Does NOT match the theory_paper_structure 6-section format.
- Format clear? no.
- Knew what to do next? no — should I run theory_paper_structure FIRST to draft each section into `workspace/papers/<slug>/*.tex`, then have synthesis_paper assemble the paper.md from those? The flow is undocumented.
- Friction: **FRICTION/HIGH** — synthesis_paper does not know about theory_paper_structure and vice versa. The integration is implicit.
- Doc gap: **no integration doc between core synthesis + theory_paper_structure.**

### Turn 28 — Run theory_paper_structure end-to-end.
- What I wanted to do: produce the 6 .tex section files per theory_paper_structure's expected_outputs.
- Tool I called: protocol's 6 steps (outline / preliminaries / main results / proofs / examples / intro+open).
- Simulated result: writes `workspace/papers/chordal_tw3/{outline.md, preliminaries.tex, main_results.tex, proofs.tex, examples.tex, introduction.tex, open_questions.tex}`.
- Format clear? yes — the protocol is excellent and explicit on per-section bounds (Intro 5-15%, Proofs 50-80%).
- Friction: none.
- Time-to-clarity: 60s.

### Turn 29 — Assemble paper.md.
- What I wanted to do: get a single paper.md that tool_paper_compile_typst can consume.
- Tool I called: `tool_synthesize_plan` then `tool_synthesize(output_type='paper')`.
- Simulated result: ambiguous. `tool_synthesize` per TOOLS.md "compiles workspace into paper / abstract / poster / dashboard / grant / report. Verified citations only." Does it know to assemble from `workspace/papers/<slug>/*.tex` or does it expect IMRAD-shaped step folders under `workspace/NN_step/`?
- Format clear? no.
- Knew what to do next? no.
- Friction: **FRICTION/HIGH** — `tool_synthesize`'s input schema is opaque from docs. For theory work that lives under `workspace/papers/` and `workspace/proofs/` (NOT `workspace/NN_step/`), it is unclear whether the assembler will find anything.
- Doc gap: **`tool_synthesize` input-discovery rules not documented; specifically how it handles non-step workspace layouts.**

### Turn 30 — `tool_paper_compile_typst`.
- What I wanted to do: produce paper.pdf via Typst.
- Tool I called: `tool_paper_compile_typst(template='generic_thesis')`.
- Simulated result: per TOOLS.md takes `synthesis/paper.md`, generates paper.typ via the `generic_thesis.typ` template, compiles to paper.pdf.
- Format clear? yes.
- Knew what to do next? yes — assuming Turn 29 produced a valid paper.md, this should work. LaTeX math inside the markdown will pass through to Typst's math syntax (which is similar but not identical — `\frac{a}{b}` becomes `a/b` in Typst; the protocol does not explain whether the markdown->typst converter handles math translation).
- Friction: **FRICTION/MEDIUM** — math notation translation md->typst not explicitly documented. A theorist's paper is 70% math; this is a critical gap.
- Doc gap: **no doc on how LaTeX math in paper.md is translated to Typst math.**
- Time-to-clarity: 240s.

### Turn 31 — Reached paper.pdf? YES (with caveats).
- The workflow reaches `tool_paper_compile_typst`. Whether the actual PDF is well-formed depends on the math translator (Turn 30 caveat).

### Turn 32 — `tool_dashboard_create` (v2).
- What I wanted to do: produce dashboard.html for the proof.
- Tool I called: `tool_dashboard_create(override_completeness_gate=true, override_rationale="theory project")`.
- Simulated result: per TOOLS.md produces single-file offline HTML. `tool_audit_dashboard_content` will check for "numeric grounding, figure-to-text proximity, per-section substantiveness, WCAG 2.2 AA, print stylesheet, color palette". For a theory dashboard, "numeric grounding" makes no sense — the dashboard's content is theorem statements + proof structure + dependency graph. The audit will likely fail.
- Format clear? no.
- Knew what to do next? no — same override hatch but the audit will fail differently per section.
- Friction: **FRICTION/HIGH** — dashboard audit (`tool_audit_dashboard_content`) has empirical assumptions (numeric grounding) that don't fit theory work. There is no `theory_dashboard` content schema.
- Doc gap: **no doc on theory-paper dashboards.**
- Time-to-clarity: 300s.

### Turn 33 — Reached dashboard.html? PARTIAL.
- Yes, the protocol path exists (`synthesis/synthesis_dashboard` -> `tool_dashboard_create`). But:
  1. Audit will block on numeric grounding without a project-wide override.
  2. There is no theory-flavoured layout (theorem cards, proof-tree viewer, lemma library).
  3. Dashboard will likely look like an IMRAD report skeleton with empty fields.

### Turn 34 — `pre_submission_checklist`.
- What I wanted to do: final GREEN / YELLOW / RED gate.
- Tool I called: `audit/pre_submission_checklist`.
- Simulated result: surfaces every override (3-5 of them: completeness, dashboard content, possibly literature on the cited-prior lemmas). Researcher confirms each. Verdict likely YELLOW (overrides required but justified).
- Format clear? yes.
- Friction: none beyond accumulated overrides.

### Turn 35 — Sign-off.
- What I wanted to do: lock the deliverable.
- Tool I called: pre_submission_checklist final.
- Simulated result: YELLOW. Acceptable for a theory project but a clear signal that v1.9.4 was not designed with theory in mind.

---

## 6. Cross-checks + sign-off

Cross-checks performed:
- `tool_audit_version_coherence`: N/A (no `.versions/` iterations done).
- `tool_citations_verify`: passes (all citations are well-known Crossref-resolvable papers).
- `tool_audit_cliches`: theory papers have a different cliché register ("It is well known that...", "Clearly..."). The cliché list is not documented, may or may not catch these.
- `tool_audit_prose`: causal-language flags will not fire (theory has no causal claims).

---

## 7. Top 5 friction points

| # | Title | Severity | Tool / protocol | Suggested fix |
|---|---|---|---|---|
| 1 | Per-step literature gate has no theory verdict | HIGH | `tool_audit_step_literature` / `literature_per_step.yaml` | Add `IMPORTED_AS_CITED` and `SPECIALIZES` verdicts. Document the "do NOT use when ... pure data engineering" exemption applies equally to "cited prior result imported as lemma". |
| 2 | `tool_audit_step_completeness` has no theory mode | HIGH | `tool_audit_step_completeness` | Detect `workspace/proofs/` and `workspace/lemmas/` layout and skip figure / script / conclusions gates; require `## Proof` heading + `## Strategy` + `## Mistakes to avoid` instead. |
| 3 | theory_math pack is undiscoverable from user docs | HIGH | `docs/PROTOCOLS.md`, `docs/USE_CASES.md`, `docs/START.md` | Add a "theorist / pure-math" role row to USE_CASES.md, a `## theory_math pack (8 protocols)` section to PROTOCOLS.md, and a theory-paper trigger example to START.md. |
| 4 | `synthesis_paper` and `theory_paper_structure` integration unspecified | HIGH | `synthesis/synthesis_paper.yaml`, `theory_math/output/theory_paper_structure.yaml` | Document the chain explicitly. Either make synthesis_paper detect a non-IMRAD project type and delegate, or document a "run theory_paper_structure first, then call tool_paper_compile_typst directly" path. |
| 5 | Dashboard tooling has no theory schema | HIGH | `tool_dashboard_create`, `tool_audit_dashboard_content` | Add a `theory_dashboard` content schema with theorem cards, proof tree, lemma library, dependency graph (the Mermaid output of `tool_theory_math_dep_graph`). |

---

## 8. Top 5 doc / guidance gaps

1. **`docs/USE_CASES.md` has no theorist / mathematician row.** A working mathematician has no entry point to Research-OS.
2. **`docs/PROTOCOLS.md` does not list the 8 theory_math pack protocols.** They exist only in source + audit lens docs.
3. **`inputs/preliminaries.md` is a hard prereq of `proof_strategy_selection` but is undocumented and not seeded by the wizard.**
4. **Override paths for per-step audits are not documented.** Only synthesis-level overrides (`tool_synthesize`, `tool_dashboard_create`, `tool_plan_advance`) are described.
5. **LaTeX-math-in-markdown -> Typst-math translation behaviour is undocumented.** Critical for any theory paper (70%+ of content is math).

Honourable mention: **`tool_redteam_review` is referenced in `proof_verification_workflow.yaml` but not in `docs/TOOLS.md`'s catalogue.**

---

## 9. Top 5 things that worked well

1. **The theory_math pack EXISTS and is well-designed.** 8 protocols cover claim -> strategy -> draft -> review -> formal-check -> publish, plus lemma library, dependency graph, and conjecture register. The editorial voice is sharp and opinionated in the right way ("the strategy follows the shape of the claim, not the researcher's comfort").
2. **`theory_paper_structure` non-IMRAD format is correct + opinionated.** The 6-section layout with per-section length bands (Intro 5-15%, Proofs 50-80%) reflects actual practice in *Annals of Mathematics* / JAMS / FOCS. Reviewers will recognise this paper format.
3. **`proof_strategy_selection` forces small-case probes before strategy commit.** This is a real research-quality lever; novices skip it. The protocol's editorial voice ("five minutes hunting a small case can save five hours") is exactly the senior-advisor tone the AI needs to imitate.
4. **`lemma_library` applies software-engineering versioning (semver) to lemmas.** Hypothesis-weakening / conclusion-strengthening = MINOR; statement change = MAJOR; proof rewrite = PATCH. This is genuinely novel as research infrastructure.
5. **`generic_thesis` Typst template exists** and is the right default for theory dissertations. The Typst stack is faster + cleaner than LaTeX for new theorists.

Bonus: **`conjecture_tracking` status lattice (open / partial_progress / proven / disproven / counter_example_found) is mathematically literate.** A real registry that working theorists would use.

---

## 10. Final rating

**Rating: 5 / 10.**

Rationale: the theory_math pack itself is 8/10 work — well-designed, opinionated, theorist-literate. But it is bolted onto a core that assumes empirical IMRAD workflows: the audit gates (completeness, literature-verdict enum, dashboard content), the synthesis chain (synthesis_paper vs theory_paper_structure integration), and the entire user-facing doc surface (USE_CASES, PROTOCOLS, START, FAQ) ignore theory work. A working mathematician would discover the pack only by reading source code (or this report). Of the workflow the pack does cover — claim -> proof -> theory_paper_structure -> tool_paper_compile_typst -> paper.pdf — the user gets to paper.pdf but only after fighting 3-4 audit gates that the docs do not explain how to override per-step. Dashboard is partial; the audit assumes numeric grounding.

To reach 8/10: (a) add theory verdicts to the literature gate enum, (b) add a theory mode to step-completeness audit, (c) surface the pack in user-facing docs, (d) document the synthesis chain integration, (e) add a theory dashboard schema.

---

## 11. Onboarding-friction count (first 5 turns)

**4 onboarding-friction events in turns 1-5.**
- Turn 2: HIGH — docs are silent on theory projects.
- Turn 3: LOW — wizard has no `--project-kind theory` flag.
- Turn 4: MEDIUM — citation_style enum lacks math styles.
- Turn 5: MEDIUM — `inputs/preliminaries.md` is undocumented prereq.

---

## 12. Reached paper.pdf step? Reached dashboard.html step?

- **paper.pdf: YES** (Turn 30-31) — the workflow reaches `tool_paper_compile_typst` with `generic_thesis` template. Quality of the produced PDF is uncertain because LaTeX-math -> Typst-math translation is undocumented.
- **dashboard.html: PARTIAL** (Turn 32-33) — `tool_dashboard_create` can be invoked with overrides, but `tool_audit_dashboard_content` will fail on numeric-grounding checks. The dashboard will render but will look like an empty IMRAD skeleton with theorem text dropped in; there is no theory-flavoured layout.
