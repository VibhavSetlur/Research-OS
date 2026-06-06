# Scenario 3 — Qualitative Interview Thematic Analysis (n=8)

**Validator:** fresh-agent simulation (Claude Opus 4.7, 1M ctx)
**Date:** 2026-06-05
**Research-OS version under test:** v1.9.4 (codebase reflects v1.9.3 protocol versions)
**Scenario:** "Clinicians describe EHR friction along 3-5 themes (cognitive load, documentation burden, workflow disruption, communication breakdown, autonomy loss)."
**Data:** 8 synthetic 1000-word interview transcripts at `inputs/raw_data/transcripts/p01.txt .. p08.txt`
**Expected deliverables:** `synthesis/paper.pdf` (typst, generic_two_column), `synthesis/dashboard.html` (story mode)
**Mode:** simulated MCP execution. The agent reads documentation + protocol YAML + templates only; tool calls are inferred from `docs/TOOLS.md` + protocol `expected_outputs`.

---

## 1. Project setup (turns 1-5)

### Turn 1
- **What I wanted to do:** orient on Research-OS as a brand-new agent in an empty project directory. The researcher said "I have 8 clinician interview transcripts on EHR friction, can you walk this through Research-OS to a paper and dashboard?"
- **Tool I called (or attempted to call):** `sys_boot` (first MCP call of every session per `docs/AI_GUIDE.md` § "The session pattern").
- **Simulated result:** `sys_boot` returns: `state.has_os_state = false` (the project directory is empty, no `.os_state/` yet), `researcher_config = null`, `recommended_next_protocol = null`, `pause_classification = "fresh_project"`, `active_plan = null`. Implicit instruction: "run `research-os init` first".
- **Format clear?** yes — `sys_boot` is documented in three places (START.md, AI_GUIDE.md, TOOLS.md) and its return shape is described.
- **Did I know what to do next?** yes — the docs say to run `research-os init` if there's no `.os_state/`.
- **Friction:** none.
- **Doc gap:** none.
- **Time-to-clarity:** ~30s.

### Turn 2
- **What I wanted to do:** scaffold the project (CLI step, not an MCP call). The researcher needs to run this themselves.
- **Tool I called (or attempted to call):** I told the researcher to run `research-os init`. That drops `AGENTS.md`, `inputs/{raw_data,literature,context}/`, `workspace/`, `synthesis/`, `docs/`, `.os_state/`, `inputs/researcher_config.yaml`, and per-IDE MCP configs. Per START.md the wizard is 7 steps; I assumed defaults.
- **Simulated result:** clean scaffold. `inputs/researcher_config.yaml` is created from the template I read at `/scratch/vsetlur/Research-OS/templates/researcher_config.yaml`. Default `autonomy_level=supervised`, `model_profile=medium`, `project_tier=production`, `venue_template=generic_two_column`, `pdf_compile_engine=typst`.
- **Format clear?** yes — the scaffold output is exhaustively documented.
- **Did I know what to do next?** yes — drop transcripts into `inputs/raw_data/` and tell the AI "fill out the intake".
- **Friction:** FRICTION/LOW — `research-os init` is a CLI command the researcher must run, but a fresh agent might attempt to invoke it as an MCP tool. The docs are clear ("the only per-project command"), but a one-line callout in AI_GUIDE.md saying "the AI cannot bootstrap a project — instruct the human" would prevent a wasted turn.
- **Doc gap:** AI_GUIDE.md mentions `sys_active_project` returns `has_os_state=false` → "tell the researcher to run `research-os init`" but doesn't say it as a numbered cold-start step.
- **Time-to-clarity:** ~45s.

### Turn 3
- **What I wanted to do:** edit `researcher_config.yaml` to pre-fill what the researcher told me — name, institution, qualitative orientation, output_types.
- **Tool I called (or attempted to call):** `sys_config_set` (TOOLS.md line 234) — set fields via dot notation, OR direct file edit via `sys_file_write`.
- **Simulated result:** the config template I read has every field documented in-line. I'd set `research_goal.output_types = ["paper", "dashboard"]`, `target_venue = "journal"`, `writing_preferences.venue_template = "generic_two_column"`, `interaction.autonomy_level = "supervised"`.
- **Format clear?** yes — the template is the source-of-truth and is self-documenting.
- **Did I know what to do next?** yes — drop the transcripts and run intake.
- **Friction:** none. The config template is excellent: every field has a comment + an enum hint.
- **Doc gap:** none.
- **Time-to-clarity:** ~30s.

### Turn 4
- **What I wanted to do:** the researcher drops the 8 transcripts into `inputs/raw_data/`. I want to run intake so RO knows there are interview transcripts → routes to qualitative_research downstream.
- **Tool I called (or attempted to call):** `tool_intake_autofill` (TOOLS.md "Data" section: "Read inputs/, infer domain + question + hypotheses, write to `inputs/intake.md` + `docs/research_overview.md` + `.os_state/state.json`").
- **Simulated result:** based on file extensions (`.txt`) + filename pattern (`p01..p08`) + content sniffing, intake infers: domain = "qualitative health-systems research / clinical informatics"; data_kind = "interview transcripts"; population = 8 participants; research_question stub. Writes `inputs/intake.md`, `docs/research_overview.md`, updates `state.json`.
- **Format clear?** yes — TOOLS.md describes outputs explicitly.
- **Did I know what to do next?** yes — register the hypothesis next.
- **Friction:** FRICTION/LOW — `tool_intake_autofill` is documented as one line. It would help to know what it does on edge cases (e.g. does it actually parse transcript content, or just metadata? does it detect that they're interviews vs free-text essays vs survey responses?). The qualitative_research protocol trigger says it fires when "transcripts (.txt / .docx / .rtf) drop into inputs/raw_data/" — good signal — but the wiring from intake to that trigger isn't explicit in the docs.
- **Doc gap:** docs don't describe how `tool_intake_autofill` does its data-kind inference. If it gets it wrong (e.g. labels 8 txt files as "survey responses"), the downstream routing breaks silently.
- **Time-to-clarity:** ~60s.

### Turn 5
- **What I wanted to do:** register the hypothesis explicitly so the audit chain has something to trace claims back to.
- **Tool I called (or attempted to call):** `mem_hypothesis_add` (TOOLS.md mem section: "Register a new hypothesis (state.active_hypotheses + analysis.md)").
- **Simulated result:** writes H1 = "Clinicians describe EHR friction along 3-5 themes spanning cognitive load, documentation burden, workflow disruption, communication breakdown, and autonomy loss." Status=`testing`. Appends to `workspace/analysis.md` + `state.active_hypotheses`.
- **Format clear?** yes.
- **Did I know what to do next?** yes — call `tool_route` with the researcher's verbatim prompt to pick the right protocol.
- **Friction:** none.
- **Doc gap:** the hypothesis schema (id format, status enum, evidence field) isn't shown anywhere on the doc surface I'm allowed to read; I had to infer it from the `mem_hypothesis_update` example in the `analysis_plan` protocol. A two-line example in TOOLS.md would help.
- **Time-to-clarity:** ~45s.

---

## 2. Hypothesis + planning (turns 6-10)

### Turn 6
- **What I wanted to do:** route the researcher's full request ("walk 8 interview transcripts through to a paper + dashboard, theme structure already hypothesized") through `tool_route` per AI_GUIDE.md's mandatory turn-1 pattern.
- **Tool I called (or attempted to call):** `tool_route(prompt="I have 8 clinician interview transcripts on EHR friction…")`.
- **Simulated result:** `intent_class="methodology"`, `sub_intent="qualitative"`, `primary_protocol="methodology/qualitative_research"`, `complexity="high"` (because the researcher asked for end-to-end paper + dashboard), `active_plan` persisted to `.os_state/active_plan.json`, `ask_user=null`. The router index (_router_index.yaml lines 631-637) hits "interviews" + "thematic" triggers cleanly.
- **Format clear?** yes — the return shape is described in AI_GUIDE.md verbatim.
- **Did I know what to do next?** yes — because `complexity=high`, call `tool_plan_turn`.
- **Friction:** none.
- **Doc gap:** none.
- **Time-to-clarity:** ~20s.

### Turn 7
- **What I wanted to do:** get the per-turn batch sized to my `model_profile=medium`.
- **Tool I called (or attempted to call):** `tool_plan_turn`.
- **Simulated result:** returns `this_turn = [load qualitative_research summary, create_step, design_protocol]`, `next_turn = [ingest_transcripts, coding_pass_1, coding_pass_2]`, `chat_split_recommended = false`.
- **Format clear?** yes.
- **Did I know what to do next?** yes — execute the three entries.
- **Friction:** none.
- **Doc gap:** none.
- **Time-to-clarity:** ~15s.

### Turn 8
- **What I wanted to do:** load the qualitative_research protocol summary.
- **Tool I called (or attempted to call):** `sys_protocol_get format='summary' name='methodology/qualitative_research'`.
- **Simulated result:** ~300 tokens, lists step IDs (create_step, design_protocol, ingest_transcripts, coding_pass_1, coding_pass_2, theme_synthesis, trustworthiness, report) + quality_bar bullets + `expected_outputs` paths. The protocol is well-named — I can plan the rest of the session.
- **Format clear?** yes.
- **Did I know what to do next?** yes — but I notice the protocol's `next_protocol: guidance/analysis_plan`. That's a generic per-step loop, not a qualitative-specific synthesis hand-off. The chaining to `qualitative_quality_audit` only happens via `audit/audit_and_validation` (not explicitly in the qualitative_research `next_protocol` field). I had to find that by grepping `_router_index.yaml`.
- **Friction:** FRICTION/MEDIUM — `methodology/qualitative_research.next_protocol = guidance/analysis_plan` doesn't make sense for a transcript-only project (there are no "experiments" in the analysis_plan sense). I'd expect `next_protocol: methodology/qualitative_quality_audit`. Without my having read all 4 qualitative protocols, I would have run analysis_plan and hit a square-peg-round-hole problem.
- **Doc gap:** the qualitative-pack workflow (qualitative_research → coding_scheme_development → inter_rater_reliability → qualitative_quality_audit → synthesis) isn't documented as a chain anywhere I can read. The router index lists each individually with their own triggers, but the recommended END-TO-END sequence for "drop in transcripts, get a paper" is implicit.
- **Time-to-clarity:** ~3 min — I had to read 4 protocol YAMLs to figure out the chain.

### Turn 9
- **What I wanted to do:** create the numbered experiment folder for this qualitative work.
- **Tool I called (or attempted to call):** `sys_path_create name="qual_ehr_friction" hypothesis="H1: clinicians describe EHR friction along 3-5 themes…"` per the protocol's `create_step` step.
- **Simulated result:** creates `workspace/01_qual_ehr_friction/{scripts,literature,data/{input,output},outputs/{reports,figures,tables},environment}`; sets as current_path.
- **Format clear?** yes — the layout is documented in `docs/AI_GUIDE.md` and the analysis_plan protocol.
- **Did I know what to do next?** yes — design the interview protocol document next.
- **Friction:** FRICTION/LOW — `sys_path_create`'s hypothesis arg expects a string; the protocol says use `(qualitative — themes emerge from data)` as the placeholder. But the researcher DID supply a hypothesis (5 candidate themes). The protocol's voice suggests "themes always emerge" which is RIGHT for inductive thematic analysis but WRONG for the deductive/hybrid case the researcher gave me. The `methodology/coding_scheme_development` protocol explicitly handles inductive/deductive/hybrid — but qualitative_research doesn't reference that choice in its create_step.
- **Doc gap:** qualitative_research.yaml should reference coding_scheme_development.yaml in the create_step or design_protocol step. A reader has to know to look for it.
- **Time-to-clarity:** ~90s.

### Turn 10
- **What I wanted to do:** design the interview/observation protocol document per qualitative_research step `design_protocol`.
- **Tool I called (or attempted to call):** `sys_file_write` to drop `workspace/01_qual_ehr_friction/outputs/reports/interview_protocol.md` per the protocol's COREQ/SRQR scaffold (population + sampling + sample-size justification + setting + interviewer role + topic guide + recording + member-checking).
- **Simulated result:** file written. Justification for n=8 = "purposive sample; saturation expected by 6-8 per Guest, Bunce, Johnson 2006 (the canonical 'How many interviews are enough?' paper); will compute saturation curve in audit step." This is the right answer to the "n=8 must not be flagged underpowered" requirement — saturation evidence + the canonical citation justify it within COREQ/SRQR.
- **Format clear?** yes — the protocol literally lists the seven required sub-sections.
- **Did I know what to do next?** yes — ingest transcripts.
- **Friction:** FRICTION/LOW — the protocol says "cite the COREQ or SRQR item that each section addresses" but doesn't give me the COREQ/SRQR item numbers (1-32 for COREQ; 21 for SRQR). I'd have to look them up online. A `templates/qualitative/interview_protocol_template.md` with the canonical COREQ/SRQR item numbers pre-filled would close this gap.
- **Doc gap:** no qualitative-specific templates in `templates/` (only `AGENTS.md`, `CLAUDE.md`, `mcp_config.json`, `opencode.json`, `researcher_config.yaml`, `typst/`). Compare to the typst venue templates which are pre-built.
- **Time-to-clarity:** ~3 min.

---

## 3. Per-step execution (turns 11-25)

### Turn 11
- **What I wanted to do:** PII anonymization runs (per scenario requirement). The qualitative_research protocol's `ingest_transcripts` step says "symlink, do not move" but doesn't mention PII scrubbing as a pre-coding step.
- **Tool I called (or attempted to call):** I searched for any PII/de-identification tool. Grepping the docs I'm allowed to read, the only mention of "anonym" is in `qualitative_quality_audit.yaml::quote_anonymisation_audit` (runs LATER, on quotes embedded in the paper). There is no PRE-coding PII scrubber.
- **Simulated result:** I'd have to either (a) skip PII anonymization (risky), (b) write a custom Python script via `tool_python_exec` to redact names/employers/locations from each transcript before symlinking, or (c) interpret the scenario's "PII anonymization runs" as referring to the quote-level audit in step 5.
- **Format clear?** no — there's no PII tool in `tool_*` or `mem_*`.
- **Did I know what to do next?** no — I'd default to writing a custom script.
- **Friction:** FRICTION/HIGH — PII de-identification is a HARD requirement for any human-subjects qualitative work (HIPAA, IRB, GDPR). The scenario explicitly says "PII anonymization runs". Research-OS has NO pre-coding PII tool. The qualitative pack only has `tool_qualitative_codebook_diff` + `tool_qualitative_quote_provenance` (TOOLS.md lines 337-338). Quote-level audit at the END is too late — it doesn't help the AI coder, who has already seen the un-redacted text.
- **Doc gap:** HIGH — no protocol step for pre-coding PII redaction; no tool like `tool_qualitative_pii_redact`; no template; no policy guidance in `docs/`.
- **Suggested fix:** add `methodology/qualitative_pii_redaction.yaml` as a prerequisite for `qualitative_research` AND/OR a `tool_qualitative_pii_redact` in the qualitative pack that wraps presidio / spaCy NER / a regex pass.
- **Time-to-clarity:** ~4 min spent looking for the tool before giving up.

### Turn 12
- **What I wanted to do:** ingest transcripts into the step (qualitative_research step `ingest_transcripts`).
- **Tool I called (or attempted to call):** I'd write a shell or Python script that `ln -s ../../../../inputs/raw_data/transcripts/*.txt workspace/01_qual_ehr_friction/data/input/`. The protocol says "symlink, do not move".
- **Simulated result:** 8 symlinks created in `data/input/`. Provenance preserved (the source files in `inputs/raw_data/` are immutable + RO-blocked).
- **Format clear?** yes.
- **Did I know what to do next?** yes — start coding_pass_1 (open coding).
- **Friction:** FRICTION/LOW — the protocol doesn't give a tool for symlinking. The AI has to write its own `tool_python_exec` or `tool_bash_exec` to do it. A `sys_file_symlink` would be a low-cost addition. The closest existing tools (`sys_file_write`, `sys_file_read`) don't symlink.
- **Doc gap:** none — the step description is clear about WHAT, just not HOW.
- **Time-to-clarity:** ~30s.

### Turn 13
- **What I wanted to do:** decide the coding approach. Per the scenario, the researcher gave 5 candidate themes — that's hybrid (deductive seeds + inductive discovery) coding per `coding_scheme_development.yaml::pick_approach`.
- **Tool I called (or attempted to call):** load `methodology/coding_scheme_development` (`sys_protocol_get format='summary'`) + `sys_file_write` for `workspace/.qualitative/coding_approach.md` saying "HYBRID — five deductive seeds from the literature on EHR burden (Sinsky 2016, Shanafelt 2016, Babbott 2014, …); inductive codes welcome via open coding."
- **Simulated result:** file written. The protocol expects `workspace/.qualitative/` as a sibling of `workspace/`, not under the step folder. That's inconsistent with the rest of Research-OS (everything else goes under `workspace/<NN_slug>/`).
- **Format clear?** yes — the path is literal in the protocol.
- **Did I know what to do next?** yes — build first-pass codebook.
- **Friction:** FRICTION/MEDIUM — the `workspace/.qualitative/` directory pattern (used by `coding_scheme_development`) is NOT consistent with the rest of Research-OS (which scopes everything to `workspace/<NN_slug>/`). Two coexisting conventions force the AI to remember which protocol uses which.
- **Doc gap:** PROTOCOL_DOCTRINE.md should call out the `workspace/.qualitative/` convention if it's intentional, or coding_scheme_development should be patched to use `workspace/<NN_slug>/qualitative/`.
- **Time-to-clarity:** ~2 min.

### Turn 14
- **What I wanted to do:** build the v1 codebook with 5 deductive seeds + room for inductive codes (coding_scheme_development step `first_pass_codebook`).
- **Tool I called (or attempted to call):** `sys_file_write` for `workspace/.qualitative/codebook_v1.md` as a table (code | definition | inclusion | exclusion | example | parent).
- **Simulated result:** 5 seeded codes (C001-C005 = cognitive_load, documentation_burden, workflow_disruption, communication_breakdown, autonomy_loss), each with full schema entries. The protocol's editorial_voice rules — "a code is a label; a code DEFINITION is what makes it inter-subjective" — are excellent guidance.
- **Format clear?** yes.
- **Did I know what to do next?** in the IDEAL flow, calibrate with ≥2 coders. But this scenario has ONE AI coder — there is no second human to compare. The protocol assumes multi-coder. Single-coder workflow is mentioned in the `qualitative_quality_audit.yaml::intercoder_agreement_check` step ("Single-coder analysis. Intercoder agreement not computed. Limitation documented…") but `coding_scheme_development` doesn't have a single-coder branch.
- **Friction:** FRICTION/MEDIUM — `coding_scheme_development` is structurally multi-coder. A solo qualitative researcher (or solo AI coder) has to skip calibration_round_1 + revise_codebook (the iterative heart of the protocol). The protocol should branch on coder_count == 1 to a "self-calibration via constant-comparison" path.
- **Doc gap:** no single-coder branch in coding_scheme_development.yaml.
- **Time-to-clarity:** ~90s + a decision to proceed with one-coder caveat.

### Turn 15
- **What I wanted to do:** run open coding pass 1 (qualitative_research step `coding_pass_1`).
- **Tool I called (or attempted to call):** write a `tool_python_exec` script that reads each transcript, applies the v1 codebook, and produces `outputs/reports/open_codes.md` with rows of label + definition + source quote (transcript + line ref).
- **Simulated result:** script runs, ~120 codes emerge across 8 transcripts. Many map to the 5 seeds; ~30 are NEW inductive codes (e.g. "alert_fatigue", "copy_paste_propagation", "after_hours_documentation").
- **Format clear?** yes — protocol specifies row schema.
- **Did I know what to do next?** yes — axial coding to cluster.
- **Friction:** FRICTION/LOW — applying a codebook to 8 transcripts is what an LLM is GOOD at, but the protocol gives no scaffolding for HOW the AI should do it programmatically. `mem_methods_append` is mentioned for documenting "custom or assisted (LLM-aided) coding" but there's no `tool_qualitative_apply_codebook` that wraps the LLM call + writes the output in the expected schema. The AI has to roll its own.
- **Doc gap:** no helper tool for LLM-assisted coding (`tool_qualitative_code_transcript` or similar). The codebook + transcripts are the only inputs needed; the output schema is well-defined.
- **Time-to-clarity:** ~3 min building the script.

### Turn 16
- **What I wanted to do:** axial / focused coding to consolidate the 120 open codes into categories (qualitative_research step `coding_pass_2`).
- **Tool I called (or attempted to call):** another `tool_python_exec` (or just an LLM-aided rewrite) that produces `outputs/reports/codebook.md` with the consolidated categories.
- **Simulated result:** 5 seed themes + 12 sub-categories. The codebook now reflects what the data actually says.
- **Format clear?** yes.
- **Did I know what to do next?** yes — theme synthesis.
- **Friction:** none significant beyond the per-step grind.
- **Doc gap:** none.
- **Time-to-clarity:** ~3 min.

### Turn 17
- **What I wanted to do:** distill themes from categories (qualitative_research step `theme_synthesis`) → `outputs/reports/themes.md`.
- **Tool I called (or attempted to call):** `sys_file_write` after LLM-aided synthesis.
- **Simulated result:** 5 themes (matching the hypothesis) + 1 cross-cutting theme on "informal workarounds" that emerged inductively. Each theme has constituent codes, illustrative quotes (with `P0X` IDs), and one negative case where a clinician described AUTONOMY GAIN from the EHR (not loss).
- **Format clear?** yes.
- **Did I know what to do next?** yes — trustworthiness statement.
- **Friction:** none.
- **Doc gap:** none.
- **Time-to-clarity:** ~3 min.

### Turn 18
- **What I wanted to do:** write the trustworthiness report (qualitative_research step `trustworthiness`) + the per-step conclusions.
- **Tool I called (or attempted to call):** `sys_file_write` for `outputs/reports/trustworthiness.md` (credibility / transferability / dependability / confirmability / saturation) and `conclusions.md`.
- **Simulated result:** both files written. Conclusions.md follows the analysis_plan.yaml schema (## Plain-language summary / ## Findings / ## Hypothesis evidence / ## Methods / ## Methodological notes / ## Limitations / ## Decision / ## Next steps).
- **Format clear?** yes.
- **Did I know what to do next?** yes — but per `analysis_plan.yaml::ground_findings_in_literature`, every step MUST run the per-step literature loop before finalize.
- **Friction:** FRICTION/LOW — the qualitative_research protocol doesn't reference the per-step literature loop (`literature/literature_per_step`). I had to know from `analysis_plan.yaml` that the loop is pipeline-mandatory. A qualitative researcher reading ONLY qualitative_research.yaml wouldn't run the loop and would hit a blocker at synthesis time.
- **Doc gap:** qualitative_research.yaml's `report` step doesn't reference `literature/literature_per_step` as a mandatory next step.
- **Time-to-clarity:** ~2 min.

### Turn 19
- **What I wanted to do:** run the per-step literature loop (mandatory gate per `analysis_plan.yaml::ground_findings_in_literature`).
- **Tool I called (or attempted to call):** `sys_protocol_get format='full' name='literature/literature_per_step'`, then walk it: extract top-5 claims from `## Findings`, call `tool_search_semantic_scholar` + `tool_search_pubmed` per claim, download top-3 PDFs into `workspace/01_qual_ehr_friction/literature/`, write `findings_vs_literature.md`.
- **Simulated result:** 5 claims (one per theme) verdict-classified as AGREES (4 — well-established EHR burden literature) and EXTENDS (1 — the inductive "informal workarounds" theme adds nuance). All claims have evidence with `[@key]` references.
- **Format clear?** yes.
- **Did I know what to do next?** yes — gate via `tool_audit_step_literature`.
- **Friction:** none.
- **Doc gap:** none.
- **Time-to-clarity:** ~5 min.

### Turn 20
- **What I wanted to do:** run the per-step completeness audit + literature audit + lightweight in-step audit.
- **Tool I called (or attempted to call):** `tool_audit_step_completeness step_id="01_qual_ehr_friction"` AND `tool_audit_step_literature step_id="01_qual_ehr_friction"`.
- **Simulated result:** step_completeness flags a WARN: "no focal figure under outputs/figures/ — qualitative step, may justify exemption via step_summary.yaml::figure_required: false". But the qualitative_research protocol's `expected_outputs` doesn't include any figure — qualitative reports don't necessarily produce a figure. step_literature audit passes (verdicts present, AGREES dominant).
- **Format clear?** yes — both tools document their BLOCK/WARN behaviour.
- **Did I know what to do next?** I'd need to decide: produce a thematic-map figure (suggested by the qualitative_research::report step: "consider a thematic map figure") OR mark `figure_required: false`. The audit protocol says empty figures/ is a HARD FAIL.
- **Friction:** FRICTION/MEDIUM — `tool_audit_step_completeness` HARD-FAILS on empty figures/ (per analysis_plan.yaml line 358). But qualitative_research's `expected_outputs` lists no figure. These two protocols disagree. The escape valve `step_summary.yaml::figure_required: false` is mentioned in analysis_plan but not in qualitative_research. A naive AI runs the audit, gets a hard fail, and is stuck.
- **Doc gap:** qualitative_research.yaml needs an explicit `## Figure-exempt step` note (with the step_summary.yaml line to add). OR the completeness audit needs a qualitative-aware branch.
- **Time-to-clarity:** ~3 min to figure out the escape valve.

### Turn 21
- **What I wanted to do:** produce a thematic-map figure to be safe (per the qualitative_research suggestion) instead of using the figure_required exemption.
- **Tool I called (or attempted to call):** load `visualization/network_visualization` to draw a thematic map (5 themes as nodes; 12 sub-categories as child nodes; edges = shared codes). Then `tool_python_exec` with networkx + matplotlib.
- **Simulated result:** `outputs/figures/01_thematic_map.png` (300 DPI) + `.caption.md` + `.summary.md` + `.prov.json`.
- **Format clear?** yes — figure_guidelines.yaml + visualization/network_visualization.yaml are detailed.
- **Did I know what to do next?** yes — back to the audit, then qualitative_quality_audit.
- **Friction:** none.
- **Doc gap:** none.
- **Time-to-clarity:** ~5 min.

### Turn 22
- **What I wanted to do:** run the qualitative-specific quality audit (`methodology/qualitative_quality_audit`).
- **Tool I called (or attempted to call):** `sys_protocol_get format='summary' name='methodology/qualitative_quality_audit'` then walk it: saturation_evidence_check → reflexivity_statement_check → intercoder_agreement_check → member_checking_attempted → quote_anonymisation_audit → audit_trail_check → write_audit_summary → append_to_methods_and_conclusions → cross_check_with_audit.
- **Simulated result:** seven checks each producing a file in `outputs/reports/`.
  - saturation: I'd build the cumulative-unique-codes-vs-transcript curve. With only 8 transcripts, the curve likely flattens by transcript 6-7 (matching Guest et al. 2006). Verdict = SATURATED if no new codes in transcripts 7-8.
  - reflexivity: I write a STUB and tell the researcher to fill it in (researcher's first-person voice required).
  - intercoder agreement: SINGLE coder → write the limitation + recommended mitigation.
  - member checking: NONE → documented limitation (synthetic transcripts, no real participants to recontact).
  - quote anonymisation: scan all `.md` files with quotes; flag any participant identifier issues.
  - audit_trail: confirm codebook versions exist (`codebook_v1.md` + `codebook_v2.md` from the consolidation).
- **Format clear?** yes — `qualitative_quality_audit.yaml` is the most thorough protocol in this scenario.
- **Did I know what to do next?** yes — `audit/audit_and_validation` next (the protocol's `next_protocol`).
- **Friction:** FRICTION/LOW — the n=8 question. The protocol's saturation_evidence_check is the correct mechanism for justifying n=8 (saturation evidence, not a power calculation). Per the scenario requirement, n=8 must NOT be flagged as underpowered. The qualitative protocols do this CORRECTLY by routing sample-size justification through saturation, not power analysis. But a naive AI might still call `tool_audit_power` and get a misleading underpowered flag.
- **Doc gap:** `tool_audit_power` should refuse to run on qualitative steps (detect via step_summary.yaml::analysis_kind = "qualitative") OR the docs should say "do not call audit_power on qualitative steps".
- **Time-to-clarity:** ~6 min total to walk all 7 checks.

### Turn 23
- **What I wanted to do:** finalize the step (`tool_path_finalize`).
- **Tool I called (or attempted to call):** `tool_path_finalize` (TOOLS.md describes it — re-derives README + analysis.md + methods.md + citations.md from what was actually produced).
- **Simulated result:** all derived files refreshed.
- **Format clear?** yes.
- **Did I know what to do next?** yes — present_to_researcher (mandatory pause per analysis_plan.yaml line 567).
- **Friction:** none.
- **Doc gap:** none.
- **Time-to-clarity:** ~30s.

### Turn 24
- **What I wanted to do:** the mandatory pause (analysis_plan.yaml::present_to_researcher).
- **Tool I called (or attempted to call):** `tool_step_revision_options step_id="01_qual_ehr_friction"`, then present the summary + alternatives to the researcher.
- **Simulated result:** revision options surfaced: "consider adding negative-case analysis section to themes.md", "reflexivity statement is a stub — needs first-person fill-in by the researcher". Researcher (in this simulation) says: "looks good, proceed to synthesis".
- **Format clear?** yes.
- **Did I know what to do next?** yes — `tool_audit_quality_full` then synthesis.
- **Friction:** none.
- **Doc gap:** none.
- **Time-to-clarity:** ~1 min.

### Turn 25
- **What I wanted to do:** mark this step complete and proceed to the audit + synthesis phase.
- **Tool I called (or attempted to call):** `tool_step_complete` (mentioned by name in the workflow pattern; in TOOLS.md only the audit-level mention of "tool_step_complete to catch it" exists — no first-class entry in the catalog).
- **Simulated result:** I'd guess this maps to `tool_plan_advance` + a state update marking the step as complete. The lack of a clearly-named `tool_step_complete` tool with a TOOLS.md entry is confusing.
- **Format clear?** no — `tool_step_complete` is REFERENCED in TOOLS.md line 435 ("rely on `tool_step_complete` to catch it") but is not in any tool table. Is it the same as `tool_plan_advance`? Or `tool_path_finalize`? Or `sys_protocol_log status=completed`?
- **Did I know what to do next?** mostly — I'd default to `sys_protocol_log` + `tool_plan_advance` and assume the audit pipeline catches gaps.
- **Friction:** FRICTION/MEDIUM — `tool_step_complete` is referenced but not defined in the TOOLS.md table. Either it's an alias for one of the existing tools (in which case TOOLS.md should say so) or it's missing.
- **Doc gap:** clarify what `tool_step_complete` is — alias, separate tool, or doc typo for `tool_path_finalize`?
- **Time-to-clarity:** ~2 min.

---

## 4. Per-step literature gate (interleaved)

The literature gate is interleaved IN the step (turn 19 above). The architectural choice (per-step `findings_vs_literature.md` instead of a one-shot end-of-project lit review) is documented well in `literature/literature_per_step.yaml` and the gate is enforced by `tool_audit_step_literature`. This part worked well.

---

## 5. Audit + synthesis (turns 26-35)

### Turn 26
- **What I wanted to do:** run the master audit before synthesis.
- **Tool I called (or attempted to call):** `tool_audit_quality_full`.
- **Simulated result:** runs `tool_audit_step_completeness` + `tool_audit_code_quality` + `tool_audit_prose` + `tool_audit_claims` + `tool_preregister_diff` + `tool_ground`. With a single qualitative step + 1 thematic-map figure + all sidecars + quality_bar bullets met, expect a GREEN audit. Per-step literature gate is NOT bundled here (per TOOLS.md line 433) — I already ran it in turn 20.
- **Format clear?** yes.
- **Did I know what to do next?** yes — load synthesis_paper protocol.
- **Friction:** none.
- **Doc gap:** none.
- **Time-to-clarity:** ~30s.

### Turn 27
- **What I wanted to do:** load synthesis_paper protocol summary.
- **Tool I called (or attempted to call):** `sys_protocol_get format='summary' name='synthesis/synthesis_paper'`.
- **Simulated result:** the protocol enforces multi-turn drafting (line 14-31 of synthesis_paper.yaml): outline → methods → results → discussion → introduction → abstract → assemble → title → audit → end matter. ONE section per researcher prompt. This is intentional anti-one-shot — but it means the "produce paper.pdf" step is actually 10 turns minimum unless I'm on autopilot.
- **Format clear?** yes.
- **Did I know what to do next?** yes — outline first.
- **Friction:** FRICTION/MEDIUM — the multi-turn drafting requirement (10 turns to get to PDF) is great for paper quality but doesn't match the scenario's expectation that "paper.pdf" is one workflow step. For this validation I'll collapse turns 28-34 since autopilot mode allows automatic progression.
- **Doc gap:** none — multi-turn is well documented.
- **Time-to-clarity:** ~30s.

### Turn 28
- **What I wanted to do:** outline the paper, then walk sections 2-7 (methods → end matter) per synthesis_paper.
- **Tool I called (or attempted to call):** `tool_synthesize_plan` (proposes section order) then `tool_synthesize output_type='paper' section='outline'`, then per-section calls for methods/results/discussion/introduction/abstract/assemble.
- **Simulated result:** outline written to `synthesis/outline.md`; sections drafted into `synthesis/paper.md`. The qualitative-specific reporting standards (COREQ/SRQR per `qualitative_quality_audit::append_to_methods_and_conclusions`) get appended automatically because the gate logged the audit to `qualitative_quality_audit.md`.
- **Format clear?** yes.
- **Did I know what to do next?** yes — compile to PDF.
- **Friction:** none.
- **Doc gap:** none.
- **Time-to-clarity:** ~10 min real time per section if walked individually; ~2 min on autopilot.

### Turn 29
- **What I wanted to do:** compile `synthesis/paper.md` → `synthesis/paper.pdf` via typst + generic_two_column template.
- **Tool I called (or attempted to call):** `tool_paper_compile_typst venue_template="generic_two_column"`.
- **Simulated result:** invokes the typst engine with the template at `/scratch/vsetlur/Research-OS/templates/typst/generic_two_column.typ`. PDF written to `synthesis/paper.pdf`. **Workflow success: reached paper.pdf step.**
- **Format clear?** yes.
- **Did I know what to do next?** yes — dashboard.
- **Friction:** none. Typst-first is excellent (no LaTeX dependency hell).
- **Doc gap:** none.
- **Time-to-clarity:** ~30s.

### Turn 30
- **What I wanted to do:** build the story-mode dashboard source.
- **Tool I called (or attempted to call):** `tool_dashboard_story_generate` (per `synthesis_dashboard.yaml::build_story_mode_source` step at line 231).
- **Simulated result:** writes `synthesis/dashboard_story.md` — the story-mode source that the dashboard renders.
- **Format clear?** yes.
- **Did I know what to do next?** yes — quality bar then dashboard create.
- **Friction:** none.
- **Doc gap:** none.
- **Time-to-clarity:** ~30s.

### Turn 31
- **What I wanted to do:** quality-check the story source.
- **Tool I called (or attempted to call):** `tool_dashboard_story_quality_bar`.
- **Simulated result:** verdict OK (5-20 min read, figure in first 1000 words, ≥1 DISAGREES/EXTENDS callout from the per-step literature gate's EXTENDS verdict on "informal workarounds").
- **Format clear?** yes.
- **Did I know what to do next?** yes — dashboard_create.
- **Friction:** none.
- **Doc gap:** none.
- **Time-to-clarity:** ~30s.

### Turn 32
- **What I wanted to do:** create the dashboard.
- **Tool I called (or attempted to call):** `tool_dashboard_create`.
- **Simulated result:** single-file offline HTML at `synthesis/dashboard.html`. **Workflow success: reached dashboard.html step.**
- **Format clear?** yes.
- **Did I know what to do next?** yes — dashboard content audit.
- **Friction:** FRICTION/LOW — TOOLS.md describes `tool_dashboard_create` as "single-file offline HTML dashboard" but doesn't mention that story-mode requires the `dashboard_story.md` source to exist. A naive caller might call `tool_dashboard_create` first and get a non-story-mode output. The synthesis_dashboard.yaml protocol gets the ordering right, but if you skip the protocol and call the tool directly the dependency is implicit.
- **Doc gap:** TOOLS.md entry for `tool_dashboard_create` should mention the story-mode requirement.
- **Time-to-clarity:** ~30s.

### Turn 33
- **What I wanted to do:** audit dashboard content.
- **Tool I called (or attempted to call):** `tool_audit_dashboard_content`.
- **Simulated result:** numeric grounding pass; figure-to-text proximity pass; section substantiveness pass; WCAG 2.2 AA pass; 5-minute reviewer simulator pass.
- **Format clear?** yes.
- **Did I know what to do next?** yes — pre-submission checklist.
- **Friction:** none.
- **Doc gap:** none.
- **Time-to-clarity:** ~30s.

### Turn 34
- **What I wanted to do:** the final ready-to-submit gate (`audit/pre_submission_checklist`).
- **Tool I called (or attempted to call):** load + walk `audit/pre_submission_checklist`.
- **Simulated result:** GREEN / YELLOW / RED verdict. Likely YELLOW because reflexivity.md is still a stub (researcher must fill in first-person voice) and member-checking was justified-absent.
- **Format clear?** yes.
- **Did I know what to do next?** yes — hand to the researcher.
- **Friction:** none.
- **Doc gap:** none.
- **Time-to-clarity:** ~1 min.

### Turn 35
- **What I wanted to do:** wrap up + handoff.
- **Tool I called (or attempted to call):** `sys_checkpoint_create` + `sys_session_handoff`.
- **Simulated result:** workspace snapshot + handoff doc written.
- **Format clear?** yes.
- **Did I know what to do next?** session done.
- **Friction:** none.
- **Doc gap:** none.
- **Time-to-clarity:** ~30s.

---

## 6. Cross-checks + sign-off

- The workflow chain `qualitative_research → coding_scheme_development → qualitative_quality_audit → audit/audit_and_validation → synthesis/synthesis_paper → synthesis/synthesis_dashboard` is functionally correct but NOT documented as an end-to-end recipe on the doc surface.
- `n=8` is correctly handled via saturation evidence (not power analysis) — the qualitative_quality_audit protocol gets this right.
- PII anonymization is the largest gap — no tool, no pre-coding redaction step, only an after-the-fact quote-level audit.
- The qualitative pack has only 2 tools (`tool_qualitative_codebook_diff`, `tool_qualitative_quote_provenance`). Both are useful but neither helps with the bulk of qualitative work (codebook application, coding, theme extraction).
- The multi-coder assumption baked into `coding_scheme_development` is a poor fit for single-AI-coder use.
- The figure-required hard-fail vs qualitative's no-figure-needed expectation is a known friction.

---

## 7. Top 5 friction points

1. **No pre-coding PII anonymization tool or protocol.** [FRICTION/HIGH] — the scenario explicitly requires it; HIPAA/IRB/GDPR require it; Research-OS has nothing. Suggested fix: add `methodology/qualitative_pii_redaction.yaml` + `tool_qualitative_pii_redact` (presidio/spaCy NER + regex pass) as a prerequisite for `qualitative_research`.
2. **Qualitative workflow chain not documented end-to-end.** [FRICTION/MEDIUM] — `qualitative_research.next_protocol = guidance/analysis_plan` mis-routes the AI; the actual chain (qualitative_research → coding_scheme_development → qualitative_quality_audit → audit_and_validation → synthesis_paper → synthesis_dashboard) must be assembled by reading 4 separate YAMLs. Suggested fix: add a "qualitative end-to-end" recipe to `docs/USE_CASES.md` and fix the `next_protocol` chain.
3. **`coding_scheme_development` assumes ≥2 coders.** [FRICTION/MEDIUM] — single-coder (solo researcher OR solo AI coder) workflows have no branch. Suggested fix: add a `single_coder` branch in `coding_scheme_development.yaml::calibration_round_1` that does self-calibration via constant-comparison.
4. **Figure-required hard-fail conflicts with qualitative no-figure expectation.** [FRICTION/MEDIUM] — `tool_audit_step_completeness` HARD-FAILS on empty `outputs/figures/` but qualitative_research's `expected_outputs` doesn't include a figure. Escape valve (`step_summary.yaml::figure_required: false`) is documented in analysis_plan but not in qualitative_research. Suggested fix: qualitative_research.yaml should explicitly set figure_required: false OR recommend a thematic-map figure in its create_step.
5. **`tool_step_complete` referenced but not defined in TOOLS.md.** [FRICTION/MEDIUM] — TOOLS.md line 435 mentions "rely on `tool_step_complete` to catch it" but no first-class table entry. Suggested fix: either add the entry or clarify it's an alias for `tool_path_finalize`.

## 8. Top 5 doc/guidance gaps

1. **No PII anonymization documentation, protocol, or tool.** (HIGH) — see friction #1.
2. **No qualitative-end-to-end recipe in `docs/USE_CASES.md`.** The router index lists each protocol with triggers but never composes them. (MEDIUM)
3. **`workspace/.qualitative/` vs `workspace/<NN_slug>/` directory convention inconsistency.** Two coexisting conventions; `PROTOCOL_DOCTRINE.md` doesn't address. (MEDIUM)
4. **No qualitative-specific templates** in `templates/` (e.g. interview_protocol.md with pre-filled COREQ/SRQR item numbers, reflexivity.md stub, codebook.md table template). Typst venues are pre-built; qualitative scaffolds are not. (LOW)
5. **`tool_dashboard_create` story-mode dependency on `dashboard_story.md` is implicit.** TOOLS.md entry should call it out. (LOW)

## 9. Top 5 things that worked well

1. **`sys_boot` + `tool_route` two-call session boot.** The session-start pattern is documented identically in 3 places (START.md, AI_GUIDE.md, templates/CLAUDE.md). Zero ambiguity for a fresh agent. The router cleanly hit `methodology/qualitative_research` from the verbatim prompt.
2. **`qualitative_quality_audit.yaml` is the strongest protocol in the chain.** Seven checks, each with clear BLOCKER criteria, with explicit handling of single-coder + absent-member-checking + n=8-via-saturation cases. The editorial_voice rules ("saturation is evidence, not assertion") are exactly the right scaffolding.
3. **`literature/literature_per_step` + `tool_audit_step_literature`** is a great architectural choice. Per-step `findings_vs_literature.md` with AGREES/DISAGREES/EXTENDS/DEFERRED verdicts gives the synthesis_paper protocol something concrete to draft the discussion from.
4. **Typst-first PDF compilation.** No LaTeX dependency hell. Venue templates pre-built. `pdf_compile_engine` config knob is well-documented.
5. **`researcher_config.yaml` template is self-documenting.** Every field has an inline comment + an enum hint + an explanation of consequences. A fresh agent can edit it without reading any external docs.

## 10. Final rating

**7/10**

The qualitative path through Research-OS WORKS — a fresh agent can plausibly trace from empty project to paper.pdf + dashboard.html using only the documented surface. The protocols (especially `qualitative_quality_audit`) are excellent. The router cleanly picks the right protocol. The audit chain catches the right things.

But: **PII anonymization is missing** (HIPAA/IRB blocker for any real qualitative work), the end-to-end recipe is implicit (must read 4 YAMLs to compose), `coding_scheme_development` assumes ≥2 coders, and the figure-required hard-fail forces a workaround. These don't break the scenario but they meaningfully degrade the experience.

A 9/10 would close the PII gap and add an explicit qualitative-end-to-end recipe in USE_CASES.md.

## 11. Onboarding-friction count (first 5 turns)

Friction in turns 1-5:
- Turn 2: FRICTION/LOW (init is CLI, not MCP — 1 turn risk for fresh agent)
- Turn 4: FRICTION/LOW (intake inference behavior undocumented)

**Total: 2 LOW-severity onboarding friction items.** Setup itself is smooth.

## 12. Reached deliverables?

- **Reached paper.pdf step:** YES (turn 29 — `tool_paper_compile_typst venue_template="generic_two_column"`)
- **Reached dashboard.html step:** YES (turn 32 — `tool_dashboard_create` after story-mode source generation at turn 30)
