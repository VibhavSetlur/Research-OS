# Scenario 3 (re-run) — Qualitative: thematic analysis of 8 interview transcripts (v1.9.4)

**Scenario inputs**
- Hypothesis: "Clinicians describe EHR friction along 3–5 themes (cognitive load, documentation burden, workflow disruption, communication breakdown, autonomy loss)."
- Data: 8 synthetic ~1000-word interview transcripts (assumed at `inputs/transcripts/p01.txt .. p08.txt`).
- Constraints: qualitative pack active; n=8 must NOT be flagged underpowered; PII anonymization must run.
- Expected deliverables: `synthesis/paper.pdf`, `synthesis/dashboard.html` (Story mode).

**Method**
Fresh-agent simulation: doc surface (`docs/*.md`, `templates/*`, `src/research_os/protocols/**/*.yaml`) is the only allowed source of truth. No `.py` reading. MCP tools are not actually executed; each tool call is logged with the doc-derived expected return and the friction encountered.

---

## 1. Project setup (turns 1–5)

### Turn 1
- What I wanted to do: Cold-start the session, orient.
- Tool: `sys_boot` (per `docs/AI_GUIDE.md` § "The session pattern" — mandatory first MCP call).
- Simulated result: Returns `{ state, researcher_config, protocol_history_tail, dep_inventory, recommended_next_protocol, pause_classification, active_plan }`. For a brand-new project, `state` is empty, `recommended_next_protocol` is likely `guidance/project_startup`.
- Result format clear? yes — `AI_GUIDE.md` lists the exact return fields.
- Knew what to do next? yes — call `tool_route` with the user prompt as the SECOND MCP call.
- Friction: none.
- Doc gap: none.
- Time-to-clarity: ~30s.

### Turn 2
- What I wanted to do: Route the researcher's verbatim message: *"qualitative project — assume thematic analysis unless transcripts suggest grounded theory. 8 interviews in inputs/transcripts/."*
- Tool: `tool_route(prompt=<verbatim>)`.
- Simulated result: Router resolves L1=`methodology`, L2=`qualitative`. Per `_router_index.yaml` triggers, `methodology/qualitative_research` and `methodology/qualitative_pii_redaction` both match. Doc surface (`AI_GUIDE.md` + qualitative_research prerequisites) says PII redaction MUST run first if `inputs/raw_data_redacted/` does not exist. The router *should* return `primary_protocol=methodology/qualitative_pii_redaction` (or an `ask_user` to confirm public vs private corpus). Likely `complexity=high` because of the multi-step pipeline ahead.
- Result format clear? yes — `tool_route` schema is documented in `TOOLS.md`.
- Knew what to do next? mostly — but I had to RECONCILE two doc surfaces. `START.md` says transcripts go to `inputs/raw_data/<slug>/`; the scenario premise says `inputs/transcripts/`. The `qualitative_pii_redaction` protocol reads from `inputs/raw_data/`. There is no documented `inputs/transcripts/` location.
- Friction: FRICTION/MEDIUM — the canonical transcript location is `inputs/raw_data/` (per `START.md` "Drop your files" table and per `qualitative_pii_redaction.detect_and_redact` step). A first-time user who lands on the scenario-style prompt would put transcripts in `inputs/transcripts/` and the redaction protocol would not find them.
- Doc gap: `START.md` mentions "Interview / survey instruments… → `inputs/context/`" but the line for raw interview TRANSCRIPTS lumps them with corpora as either `inputs/corpus/` (humanities) or `inputs/raw_data/<slug>/`. A dedicated `inputs/raw_data/transcripts/` example for the qualitative pack would close this.
- Time-to-clarity: ~120s.

### Turn 3
- What I wanted to do: Open `inputs/researcher_config.yaml`, set `model_profile`, declare `research_goal.output_types: [paper, dashboard]`, set `target_venue` and `writing_preferences.venue_template`.
- Tool: I'm editing a config file, not calling a tool. The wizard (`research-os init`) was assumed to have run already (this is "empty project + this data + this hypothesis"). Doc says wizard auto-creates `inputs/researcher_config.yaml`.
- Simulated result: File exists; I update `research_goal.output_types: [paper, dashboard]`, `target_venue: "journal"`, `model_profile: "large"` (we're Opus), `quality_gate_policy: "enforce"`, `gate_strictness: "normal"`.
- Result format clear? yes — `templates/researcher_config.yaml` is well-commented.
- Knew what to do next? yes — call `tool_intake_autofill` per `START.md` + `project_startup`.
- Friction: FRICTION/LOW — `researcher_config.yaml` does not have a domain-specific block ("qualitative pack — preferred coding tradition: thematic | grounded | framework | content"). The qualitative pack will simply default to thematic (per the trigger), but I would have liked a single line in the config to lock that in early.
- Doc gap: a "qualitative pack defaults" section in `researcher_config.yaml` comments.
- Time-to-clarity: ~60s.

### Turn 4
- What I wanted to do: Move transcripts from the wrong location (`inputs/transcripts/`) to the conventional `inputs/raw_data/`, then run intake.
- Tool: shell `mv inputs/transcripts/*.txt inputs/raw_data/`. (No MCP tool here — this is a researcher action.)
- Simulated result: 8 files relocated.
- Result format clear? n/a.
- Knew what to do next? yes.
- Friction: FRICTION/LOW — this is the second time the `inputs/transcripts/` vs `inputs/raw_data/` mismatch costs effort. The fix is either (a) accept `inputs/transcripts/` as a documented alias for the qualitative pack, or (b) detect transcripts at boot and prompt the researcher to relocate them.
- Doc gap: see Turn 2.
- Time-to-clarity: ~45s.

### Turn 5
- What I wanted to do: Auto-fill the intake from the dumped transcripts + the researcher's hypothesis statement.
- Tool: `tool_intake_autofill` (per `project_startup.autofill_intake`).
- Simulated result: Returns the inferred `{domain: qualitative/health-services, research_question: "What themes characterise clinicians' descriptions of EHR friction?", hypotheses: [{id: H1, text: "Clinicians describe EHR friction along 3–5 themes (cognitive load, documentation burden, workflow disruption, communication breakdown, autonomy loss)."}]}` and writes `inputs/intake.md` + populates `state.active_hypotheses`. The AI then presents the proposal in one short message and waits for approval.
- Result format clear? yes.
- Knew what to do next? yes — wait for researcher approval, then continue the `project_startup` walk.
- Friction: none.
- Doc gap: none.
- Time-to-clarity: ~30s.

**Onboarding-friction count (first 5 turns): 3** (one MEDIUM, two LOW — all clustered on the `inputs/transcripts/` vs `inputs/raw_data/` convention).

---

## 2. Hypothesis + planning (turns 6–10)

### Turn 6
- What I wanted to do: Register the hypothesis explicitly so per-step audits can attach evidence to it.
- Tool: `mem_hypothesis_update` (per `analysis_plan.scope_step`); `tool_research_overview` via `project_startup.present_startup_summary` may also touch `docs/research_overview.md`.
- Simulated result: `state.active_hypotheses` gains `H1` with status `proposed`.
- Result format clear? yes.
- Knew what to do next? yes — finish the `project_startup` walk: `ground_in_recent_literature`, `present_startup_summary`.
- Friction: none.
- Doc gap: none.
- Time-to-clarity: ~30s.

### Turn 7
- What I wanted to do: Initial literature ground (per `project_startup.ground_in_recent_literature`).
- Tool: parallel `tool_search_semantic_scholar(query="EHR friction clinicians qualitative thematic")` + `tool_search_pubmed(query="EHR usability burnout interview thematic")` + `tool_research_method(method="thematic analysis", domain="health services qualitative")`.
- Simulated result: Each returns hit list; top hits saved to `inputs/literature/` with `.meta.yaml` sidecars. Search log appended to `workspace/logs/search_log.md`.
- Result format clear? yes.
- Knew what to do next? yes — present the startup summary, then route to the qualitative PII redaction protocol (which `qualitative_research.prerequisites` mandates BEFORE coding).
- Friction: none.
- Doc gap: none.
- Time-to-clarity: ~30s.

### Turn 8
- What I wanted to do: Run the PII redaction protocol BEFORE any coding.
- Tool: `tool_route(prompt="redact transcripts before coding")` (or load directly via `sys_protocol_get format='full' name='methodology/qualitative_pii_redaction'`).
- Simulated result: Router returns `primary_protocol=methodology/qualitative_pii_redaction`. The protocol prereqs require `inputs/policy/pii_policy.md`. That file does NOT exist yet — the protocol expects me to draft it from `templates/qualitative/pii_policy.md` and ask the researcher to confirm.
- Result format clear? yes — protocol explicitly lists the 18 HIPAA Safe Harbor classes and the per-class choice (REMOVE/GENERALISE/PSEUDONYMISE/NOT_APPLICABLE).
- Knew what to do next? yes — but there's a quiet trap. The protocol says "draft one from the template at `templates/qualitative/pii_policy.md`". I confirmed this template exists. Good.
- Friction: FRICTION/LOW — the protocol references the template but does not show a copy-paste reference command (`sys_file_copy templates/qualitative/pii_policy.md inputs/policy/pii_policy.md` would be the obvious shortcut). A user-level researcher would not know whether they should fill it themselves or whether the AI should.
- Doc gap: none — the protocol's `load_or_draft_policy` step is detailed.
- Time-to-clarity: ~60s.

### Turn 9
- What I wanted to do: Create the redaction step folder, write the engineering-style `step_summary.yaml`, draft `inputs/policy/pii_policy.md`, draft `inputs/private/pseudonym_map.csv`, run `detect_and_redact` per transcript.
- Tool: `sys_path_create name="qual_pii_redact"`; `sys_file_write inputs/policy/pii_policy.md`; `tool_python_exec script="scripts/qual_pii_redact.py" args="--transcript ..."`.
- Simulated result: 8 redacted transcripts land in `inputs/raw_data_redacted/`; per-transcript ledger CSVs in `workspace/<NN>_qual_pii_redact/outputs/reports/redaction_ledger_<file>.csv`. Pseudonyms assigned deterministically. Any `requires_review=true` rows surface a `[REVIEW: <span>]` marker for the next step.
- Result format clear? yes.
- Knew what to do next? yes — `manual_review` step then `audit` step (held-out 5% NER recall ≥0.95).
- Friction: FRICTION/MEDIUM — the protocol says "a dedicated first-class MCP wrapper is planned but not yet shipped". So the fallback is the researcher hand-writing `scripts/qual_pii_redact.py` that calls Presidio + spaCy + regex. This is a non-trivial script and there is no canonical reference implementation in `scripts/` or `templates/` to start from. Doc-only researchers will not know how to bootstrap it.
- Doc gap: `templates/qualitative/qual_pii_redact.py.template` (a reference script) would close this.
- Time-to-clarity: ~120s.

### Turn 10
- What I wanted to do: Finalize the PII step, then route to `methodology/qualitative_research`.
- Tool: `tool_step_complete step_id=<NN_qual_pii_redact>` (per `TOOLS.md` — bundles `tool_audit_step_completeness` + `tool_audit_step_literature` + per-step audit pieces).
- Simulated result: Gates pass (engineering step — `figure_required: false`, `literature_required: false`, `table_required: false`). `tool_path_finalize` rewrites the step's READMEs.
- Result format clear? yes — `TOOLS.md` shows the exact JSON return.
- Knew what to do next? yes — `tool_route` again with "now run the thematic analysis" or load `methodology/qualitative_research` directly.
- Friction: none.
- Doc gap: none.
- Time-to-clarity: ~30s.

---

## 3. Per-step execution (turns 11–22)

The `qualitative_research` protocol has 8 internal steps. Each turn below maps one (or two when natural).

### Turn 11 — qualitative_research § create_step + design_protocol
- Tool: `sys_path_create name="qual_thematic_ehr_friction" hypothesis="(qualitative — themes emerge from data)"`; `sys_file_write workspace/<NN>/step_summary.yaml` with `step_intent: analyse`, `figure_required: false`, `table_required: false`, `literature_required: true`. Then write `outputs/reports/interview_protocol.md`.
- Simulated result: Step folder created. `step_summary.yaml` correctly sets `figure_required: false` so the completeness gate won't BLOCK on missing figures.
- Result format clear? yes — protocol gives the exact YAML contract block to write.
- Knew what to do next? yes.
- Friction: FRICTION/LOW — the protocol's note about flipping `figure_required: true` IF a thematic-map figure IS produced is buried mid-step; easy to miss when iterating.
- Doc gap: a tiny callout box in `qualitative_research.create_step` saying "Decision: thematic map figure? yes → set figure_required=true and the focal figure name; no → leave false."
- Time-to-clarity: ~60s.

### Turn 12 — ingest_transcripts
- Tool: Symlink each redacted transcript from `inputs/raw_data_redacted/` into `workspace/<NN>/data/input/`.
- Simulated result: 8 symlinks; `data/input/p01.txt..p08.txt`.
- Friction: none.
- Doc gap: none.
- Time-to-clarity: ~15s.

### Turn 13 — coding_pass_1 (open coding) + literature ground for coding tradition
- Tool: First, `ground_methods` per analysis_plan: `tool_research_method(query="reflexive thematic analysis vs grounded theory transcripts n=8")`. Save canonical Braun & Clarke (2006/2019) + Glaser&Strauss to `literature/`. Then `tool_python_exec` on a coding script producing `outputs/reports/open_codes.md` (one row per code: label, definition, source quote with transcript + line ref).
- Simulated result: Open codes file with ~40–80 codes across 8 transcripts; `mem_methods_append` records "thematic analysis (Braun & Clarke 2019) — LLM-assisted open coding, human verification expected".
- Friction: FRICTION/LOW — `coding_pass_1` says "Custom or assisted (LLM-aided) coding is allowed; `mem_methods_append` MUST document which" but does NOT name a default LLM-coding tool / library / Python helper. The AI will end up hand-rolling a coding script. That's OK in principle (scaffold-not-script doctrine), but a reference Python snippet would help.
- Doc gap: a `templates/qualitative/open_coding.py.template` reference.
- Time-to-clarity: ~120s.

### Turn 14 — coding_pass_2 (axial / focused)
- Tool: `tool_python_exec` to cluster open codes; write `outputs/reports/codebook.md` with code/definition/inclusion/exclusion/exemplar.
- Simulated result: ~12–18 categories. Hypothesis H1 named 5 themes, so the categories should converge near those 5 once theme synthesis runs.
- Friction: none.
- Doc gap: none.
- Time-to-clarity: ~60s.

### Turn 15 — theme_synthesis
- Tool: `tool_python_exec` (or just markdown synthesis) producing `outputs/reports/themes.md` with 3–7 themes. The hypothesis hints at 5; the data may produce 4 or 6. The protocol explicitly says "The right number is whatever the data supports — three themes can be sufficient".
- Simulated result: 5 themes emerge matching H1's named candidates (cognitive load, documentation burden, workflow disruption, communication breakdown, autonomy loss). At least 2 quotes per theme from ≥2 participants (per the quality_bar).
- Result format clear? yes — the protocol prescribes the per-theme section schema.
- Friction: none.
- Doc gap: none.
- Time-to-clarity: ~60s.

### Turn 16 — trustworthiness + report (conclusions.md)
- Tool: Write `outputs/reports/trustworthiness.md` (credibility / transferability / dependability / confirmability / saturation evidence) and `conclusions.md` (## Plain-language summary / ## Findings / ## Hypothesis evidence / ## Methods / ## Methodological notes / ## Limitations / ## Decision / ## Next steps).
- Simulated result: conclusions with 5 themes + cross-theme map + H1 status `supported`.
- Friction: none.
- Doc gap: none.
- Time-to-clarity: ~60s.

### Turn 17 — analysis_plan § ground_findings_in_literature (per-step literature gate)
- Tool: Load `literature/literature_per_step`. Extract top-5 claims from `conclusions.md ## Findings`, search Semantic Scholar / PubMed / Crossref per claim, download top-3 PDFs into `workspace/<NN>/literature/`, write `findings_vs_literature.md` with AGREES/DISAGREES/EXTENDS/DEFERRED verdicts.
- Simulated result: All 5 themes have known parallels in the EHR/burnout literature (Sinsky 2016 documentation burden, Friedberg 2014 RAND EHR survey, etc.). Most verdicts AGREE; "autonomy loss" likely EXTENDS the dominant focus on time burden.
- Friction: none.
- Doc gap: none.
- Time-to-clarity: ~60s.

### Turn 18 — tool_audit_step_literature gate
- Tool: `tool_audit_step_literature step_id=<NN>`.
- Simulated result: PASS — `findings_vs_literature.md` exists, every claim has a verdict, DISAGREES verdicts have a discussion implication block.
- Friction: none.
- Doc gap: none.
- Time-to-clarity: ~15s.

### Turn 19 — present_to_researcher (mandatory pause) + tool_step_complete
- Tool: `tool_step_revision_options step_id=<NN>` → present verbatim to researcher. Then `tool_step_complete`.
- Simulated result: would_benefit_from_revision likely false; one suggested revision: "consider producing a thematic-map figure to make the inter-theme relationships visible; flip figure_required to true if you do." `tool_step_complete` runs `tool_audit_step_completeness` + `tool_audit_step_literature` + code-quality + finalize. PASSES because the step contract waived `figure_required`.
- Result format clear? yes.
- Friction: none.
- Doc gap: none.
- Time-to-clarity: ~30s.

### Turn 20 — qualitative_quality_audit § saturation_evidence_check
- Tool: Load `methodology/qualitative_quality_audit`. `tool_python_exec` to build the cumulative-unique-codes saturation curve → `outputs/figures/saturation_curve.png` + sidecars + `outputs/reports/saturation_check.md`.
- Simulated result: With n=8 synthetic transcripts, the curve plateau may NOT be reached (saturation typically requires 12–20 in real qualitative work). Verdict likely **INCONCLUSIVE** or **NOT SATURATED**. The protocol says route back to `qualitative_research` to collect more data OR document explicitly in the limitations. Since the scenario constrains n=8, we document in limitations.
- Result format clear? yes — protocol prescribes the verdict-writing format and the off-ramp.
- Friction: FRICTION/MEDIUM — the scenario constraint says "n=8 must NOT be flagged underpowered". The qualitative pack handles this correctly (saturation, not power, is the relevant gate, and saturation has an explicit "document in limitations" off-ramp). HOWEVER, an inexperienced researcher reading `saturation_check.md` with "NOT SATURATED" verdict may misinterpret it as a blocker. The protocol does not visually distinguish "BLOCKER" from "documented limitation" with a single status pill.
- Doc gap: a single `verdict_status: PASS_WITH_LIMITATION | BLOCKER | PASS` line at the top of `saturation_check.md` would help.
- Time-to-clarity: ~90s.

### Turn 21 — qualitative_quality_audit § reflexivity + intercoder_agreement + member_checking
- Tool: Write `reflexivity.md` (researcher characteristics, theoretical orientation, relationship to participants, prior assumptions, how positions shaped recruitment/rapport/coding/theme selection). Write `intercoder_agreement.md` (single-coder analysis since this is a synthetic walkthrough — documented as limitation). Write `member_checking.md` (NONE — synthetic transcripts, no participants to check with — documented as limitation).
- Simulated result: All three files written. Reflexivity >200 words (protocol blocks otherwise). Single-coder limitation logged. Member-checking absence justified (synthetic corpus).
- Friction: FRICTION/MEDIUM — for a real n=8 study, having no member checking + single coder + n=8 stacking limitations + INCONCLUSIVE saturation = the pre-submission audit may turn RED. The protocol allows justified absence but the AI driving the pipeline does not yet have a doc-surface way to know "how many stacked limitations does the publication audit tolerate before it blocks?". This is policy that lives in `audit/pre_submission_checklist`'s thresholds (unread).
- Doc gap: a one-line summary in `qualitative_quality_audit` of "how many stacked limitations triggers a YELLOW vs RED pre-submission verdict".
- Time-to-clarity: ~120s.

### Turn 22 — qualitative_quality_audit § quote_anonymisation_audit + audit_trail + write_audit_summary
- Tool: scan `themes.md` for any verbatim quote lacking a participant token (P01..P08) or carrying residual identifying detail; emit `quote_anonymisation_audit.md`. Check codebook versioning / coding memos. Write `qualitative_quality_audit.md`.
- Simulated result: anonymisation audit is clean (PII redaction did the heavy lifting upstream); codebook versioning fine (single pass). Aggregate audit summary written.
- Friction: none.
- Doc gap: none.
- Time-to-clarity: ~30s.

---

## 4. Per-step literature gate (interleaved)
Already covered at Turn 17 + Turn 18. The `literature_per_step` loop is what the protocol calls into for the per-step findings_vs_literature.md; the `tool_audit_step_literature` gate runs as part of `tool_step_complete`. Both came back PASS.

---

## 5. Audit + synthesis (turns 23–32)

### Turn 23 — tool_audit_quality_full
- Tool: `tool_audit_quality_full` (per `audit/audit_and_validation` and `TOOLS.md` § "audit").
- Simulated result: Bundles `tool_audit_step_completeness` + `tool_audit_code_quality` + `tool_audit_prose` + `tool_audit_claims` + `tool_preregister_diff` + `tool_ground`. For this step, completeness PASSES (the YAML contract waived figure), code-quality PASSES (the redaction + coding scripts are short), prose PASSES (no causal language), claims PASSES (every quantitative claim, e.g. "5 themes across 8 participants", traces to a workspace artefact), preregister diff WARN (no preregistration filed). Note: per `TOOLS.md`, `tool_audit_quality_full` does NOT run the per-step literature gate — but `tool_step_complete` already ran it at Turn 19. Good.
- Result format clear? yes — `TOOLS.md` shows the full JSON return.
- Friction: FRICTION/LOW — the doc explicitly warns `tool_audit_quality_full` doesn't cover per-step literature. The AI has to remember it called `tool_step_complete` per step (or risk a blocker later at `tool_audit_synthesis`). One unified `tool_audit_quality_full_with_per_step_literature` would reduce cognitive load.
- Doc gap: none — the warning IS in `TOOLS.md` and `AI_GUIDE.md`.
- Time-to-clarity: ~30s.

### Turn 24 — synthesis_paper § select_venue_profile + plan_sections
- Tool: Load `synthesis/synthesis_paper`. Read `research_goal.target_venue: "journal"`. Call `tool_synthesize_plan`.
- Simulated result: Returns ordered sources + recommended section ordering (methods → results → discussion → introduction → abstract per the journal venue profile).
- Friction: none.
- Doc gap: none.
- Time-to-clarity: ~30s.

### Turn 25 — draft_methods (separate turn per protocol)
- Tool: `tool_synthesize section="methods" output_type="paper"`.
- Simulated result: synthesis/methods.md drafted from `workspace/methods.md` + verified citations.
- Friction: none — the multi-turn enforcement is well-documented in `synthesis_paper`'s `description` block.
- Doc gap: none.
- Time-to-clarity: ~30s.

### Turn 26 — draft_results
- Tool: `tool_synthesize section="results" output_type="paper"`.
- Simulated result: synthesis/results.md aggregating `workspace/*/conclusions.md` Findings.
- Friction: FRICTION/LOW — the quality check says "every p-value formatted to 3 decimals; every effect estimate paired with 95% CI; every figure cited and present in synthesis/figures/." None of that applies to a qualitative paper. The protocol's `quality_bar` (esp. `figures_minimum: 1`) is quantitative-leaning. For qualitative work the focal-figure equivalent is a thematic map or a quote table. The protocol does not branch its quality bar by domain.
- Doc gap: a `venue_profile: qualitative_journal` or a `domain_profile: qualitative` override that swaps `figures_minimum: 1` for `themes_table_minimum: 1` (or accepts the codebook + themes.md as the "figure"-equivalent artefact).
- Time-to-clarity: ~90s.

### Turn 27 — draft_discussion
- Tool: `tool_synthesize section="discussion" output_type="paper"`.
- Simulated result: synthesis/discussion.md.
- Friction: none.
- Doc gap: none.
- Time-to-clarity: ~30s.

### Turn 28 — draft_introduction + draft_abstract
- Tool: two separate `tool_synthesize` calls (introduction first, then abstract).
- Simulated result: synthesis/introduction.md (~600 words, ≥3 framing citations); synthesis/abstract.md (~250 words, structured per the journal venue).
- Friction: none.
- Doc gap: none.
- Time-to-clarity: ~30s.

### Turn 29 — final_assembly + tool_citations_verify
- Tool: `tool_synthesize` (no section) `output_type="paper"`; then `tool_citations_verify`.
- Simulated result: synthesis/paper.md + synthesis/references.bib assembled; every citation verified against Crossref/Semantic Scholar/PubMed; any `pending verification` would block assembly.
- Friction: none.
- Doc gap: none.
- Time-to-clarity: ~30s.

### Turn 30 — tool_paper_compile_typst
- Tool: `tool_paper_compile_typst(venue="generic_two_column")` (no qualitative-specific journal template — fallback is generic).
- Simulated result: synthesis/paper.md → synthesis/paper.typ → synthesis/paper.pdf via the bundled Typst pipeline + Hayagriva biblio.yml synthesised from `workspace/citations.md`.
- Result format clear? yes.
- Knew what to do next? yes — **REACHED THE PAPER.PDF STEP.**
- Friction: FRICTION/LOW — none of the bundled venue templates explicitly targets a qualitative health-services journal (e.g. *Qualitative Health Research*, *BMJ Open*). The generic fallback works, but for a real submission the researcher would need to drop a journal-specific class file.
- Doc gap: a `templates/typst/qualitative_journal.typ` (or even a documentation note "the bundled `generic_two_column` venue passes IMRAD + reflexivity checks for most qualitative health journals; full QHR/BMJ Open templates are not yet bundled").
- Time-to-clarity: ~30s.

### Turn 31 — synthesis_dashboard § select_audience + confirm_sources + run_completeness_audit + finalize_all_steps + curate_figures + author synthesis_spec + build_story_mode_source
- Tool: Load `synthesis/synthesis_dashboard`. Ask researcher: "audience? academic/executive/technical/teaching" — defaults to academic. Run `tool_synthesis_curate_figures` — likely returns `missing_figures: [<NN_qual_thematic_ehr_friction>]` because the qualitative step waived the focal figure. The dashboard handles this gracefully (the per-step appendix surfaces the themes.md + plain summary instead of a figure). Then `tool_dashboard_story_generate` to build `synthesis/dashboard_story.md` for Story mode.
- Simulated result: dashboard_story.md assembled from spec abstract + per-step plain summaries + adversarial verdicts from findings_vs_literature.md.
- Friction: FRICTION/MEDIUM — `tool_synthesis_curate_figures` flags missing focal figures for steps that legitimately have no figure (per the qualitative `step_summary.yaml` contract). It would be cleaner if the curator read `step_summary.yaml.figure_required` and silently skipped steps that explicitly waived figures — instead of returning a `missing_figures: [...]` audit-flag that the AI then has to suppress.
- Doc gap: a one-line clarification in `synthesis_dashboard.curate_figures` description: "Steps with `step_summary.yaml.figure_required: false` are silently skipped, not flagged as missing."
- Time-to-clarity: ~60s.

### Turn 32 — build_dashboard with mode=story + verify_quality + share
- Tool: `tool_dashboard_create title="<headline>" audience="academic" dashboard_default_mode="story"` (Story mode per scenario expectation).
- Simulated result: `synthesis/dashboard.html` single-file written. Verify: title present, abstract section non-empty, verdicts grid has H1 row, traceability table has H1 → step → themes link, themes.md prose surfaces in the per-hypothesis findings section (with the saturation_curve.png as the focal figure embedded base64, since the qualitative_quality_audit step DID emit a figure).
- Result format clear? yes.
- Knew what to do next? yes — **REACHED THE DASHBOARD.HTML STEP.**
- Friction: none.
- Doc gap: none.
- Time-to-clarity: ~30s.

---

## 6. Cross-checks + sign-off (turns 33–35)

### Turn 33 — pre_submission_checklist
- Tool: Load `audit/pre_submission_checklist`. Returns GREEN/YELLOW/RED.
- Simulated result: Likely YELLOW — saturation INCONCLUSIVE + single-coder + no member checking + no preregistration are documented limitations. None individually a BLOCKER. The synthesis-level audit (`tool_audit_synthesis`) confirms no fabricated citations, no causal language on observational design, every claim traces.
- Friction: FRICTION/LOW — the YELLOW/RED threshold for "how many stacked qualitative limitations is too many" is policy and is not surfaced in user-facing docs.
- Doc gap: see Turn 21.
- Time-to-clarity: ~30s.

### Turn 34 — workshop the title + cover letter + end matter
- Tool: `synthesis_title_workshop` → `synthesis/title.md`; `writing/writing_data_availability` → end matter appended to paper.md; `synthesis_cover_letter`.
- Simulated result: title, cover letter, data availability statement all drafted.
- Friction: none.
- Doc gap: none.
- Time-to-clarity: ~30s.

### Turn 35 — final report to researcher
- Tool: report_to_researcher (per `synthesis_paper.report_to_researcher`).
- Simulated result: section word counts, citation count + verified ratio, figure count (1 — saturation curve), output files (paper.md, paper.tex/typ, paper.pdf, references.bib, dashboard.html), end-matter status, cover-letter status, pre-submission YELLOW verdict + punch list.
- Friction: none.
- Doc gap: none.
- Time-to-clarity: ~30s.

---

## 7. Top 5 friction points

| # | Severity | Title | Tool/Protocol | Suggested fix |
|---|---|---|---|---|
| 1 | MEDIUM | `inputs/transcripts/` vs `inputs/raw_data/` convention mismatch | `qualitative_pii_redaction`, `qualitative_research`, `START.md` | Either (a) document `inputs/raw_data/transcripts/` as the canonical location for qualitative pack OR (b) detect transcripts in `inputs/transcripts/` at boot and offer to relocate. |
| 2 | MEDIUM | No reference Presidio + spaCy + regex script for PII redaction | `qualitative_pii_redaction.detect_and_redact` | Ship `templates/qualitative/qual_pii_redact.py.template` as a copy-paste starting point. |
| 3 | MEDIUM | Saturation INCONCLUSIVE for n=8 has no single-line verdict pill | `qualitative_quality_audit.saturation_evidence_check` | Add `verdict_status: PASS_WITH_LIMITATION \| BLOCKER \| PASS` at the top of `saturation_check.md` so the next AI / human reader does not misinterpret as a blocker. |
| 4 | MEDIUM | `synthesis_dashboard.curate_figures` flags figure-waived steps as missing | `tool_synthesis_curate_figures`, `synthesis_dashboard` | Read `step_summary.yaml.figure_required` and silently skip waived steps; do not surface as `missing_figures` audit-flag. |
| 5 | LOW | `synthesis_paper.quality_bar` is quantitative-leaning (figures_minimum: 1, p-values, 95% CIs) | `synthesis_paper` | Add a `domain_profile: qualitative` override that swaps figure requirement for themes-table requirement and removes the quant-only Results checks. |

## 8. Top 5 doc/guidance gaps

1. **No `templates/qualitative/qual_pii_redact.py.template`** — first-class MCP wrapper is planned (ROADMAP) but no fallback example ships.
2. **No `templates/qualitative/open_coding.py.template`** — the protocol allows LLM-assisted coding but does not show a reference invocation.
3. **`researcher_config.yaml` has no qualitative-pack defaults block** — coding tradition (thematic | grounded | framework | content) cannot be locked at config time.
4. **No qualitative-journal Typst template** — `tool_paper_compile_typst` falls back to `generic_two_column` for Qualitative Health Research / BMJ Open submissions.
5. **No documented threshold of "stacked limitations → YELLOW/RED"** in `audit/pre_submission_checklist` — the policy is opaque to the doc-only reader.

## 9. Top 5 things that worked well

1. **PII redaction is a HARD GATE upstream of coding** (per `qualitative_research.ingest_transcripts` and `qualitative_pii_redaction`) — exactly the right architectural choice. HIPAA Safe Harbor's 18 classes are listed explicitly in the protocol. Far better than the common pattern of "anonymise at output time".
2. **`step_summary.yaml` figure_required contract uniformly waives the figure gate** for qualitative `analyse` steps. The audit tools honour the contract without per-protocol carve-outs, which is exactly the abstraction `analysis_plan.classify_step_intent` promised.
3. **Saturation curve is the right gate for n=8** (not statistical power). The qualitative pack correctly treats sample-size adequacy as an evidence-not-assertion question, with a documented off-ramp (document in limitations) when the data is what it is.
4. **`tool_step_complete` is a great one-call gate** that bundles completeness + per-step literature + code quality + finalize. Reduces the AI's mental load substantially (and `TOOLS.md` shows the exact JSON return shape).
5. **The synthesis_paper multi-turn enforcement** (one section per researcher prompt) is the right anti-context-fill pattern. The protocol explicitly calls out why ("AI agents tend to complete long plans as fast as possible") and provides a clean 10-turn cadence.

## 10. Final rating 1–10 + rationale

**Rating: 8 / 10.**

Rationale: The qualitative pack is a coherent, doctrinally-aligned pipeline. The PII gate is rigorously upstream; the saturation gate correctly replaces the power gate; the figure-waiver contract works as advertised. The biggest friction points are doc-surface gaps (canonical transcript location, missing reference scripts for PII + open coding, no qualitative journal venue template) rather than protocol-design defects. None of them block reaching paper.pdf or dashboard.html — they slow first-time setup. A v1.9.5 with template scripts + a doc-surface clarification on transcript location would lift this to 9.

## 11. Onboarding-friction count (first 5 turns)

**3** (one MEDIUM at Turn 2, two LOW at Turns 3–4, all clustered on the `inputs/transcripts/` vs `inputs/raw_data/` convention).

## 12. Reached paper.pdf step? Reached dashboard.html step?

- **paper.pdf: YES** (Turn 30 — `tool_paper_compile_typst(venue="generic_two_column")`).
- **dashboard.html: YES** (Turn 32 — `tool_dashboard_create dashboard_default_mode="story"`).

---

## Summary (vs v1.9.3 baseline — opinion only, baseline not re-read)

The v1.9.4 qualitative pack as documented is a clean, end-to-end pipeline that handles the scenario constraints (n=8 not flagged underpowered; PII anonymisation runs; paper + Story-mode dashboard both reachable) without significant friction. The principal remaining gaps are doc-surface artefacts (canonical transcript location, missing template scripts, no qualitative-journal Typst template) and a few minor protocol polish items (single-line verdict pill on `saturation_check.md`, silently-skip figure-waived steps in the dashboard figure curator, domain-profile override for `synthesis_paper.quality_bar`). Reaching paper.pdf + dashboard.html cost ~35 turns total (vs the 6–10 the pipeline's headline cadence implies), but every additional turn was deliberate — the multi-turn pacing of `synthesis_paper` is a feature, not friction.
