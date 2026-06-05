# Scenario 2 — Humanities close reading (Henry James late-style) — RERUN against v1.9.4

**Scenario:** Hypothesis = *"Henry James's late-period vocabulary shifts
toward interiority and consciousness."* Corpus = Project Gutenberg subset
of James novels (early: *Roderick Hudson*, *The American*; late: *The
Ambassadors*, *The Wings of the Dove*). Humanities pack assumed active.
Expected deliverables: `paper.pdf` (humanities essay venue),
`dashboard.html` (story mode).

**Constraint:** the analytical claim is computational + interpretive
(distant + close reading hybrid) — must NOT be shoehorned into a
quantitative-statistics paper. Sections quote passages and cite line /
page / chapter anchors.

**Re-validator profile:** fresh agent, no prior context of v1.9.3
findings, doc-surface only (`docs/`, `templates/`,
`src/research_os/protocols/**/*.yaml`,
`src/research_os_humanities/protocols/**/*.yaml`).

---

## 1. Project setup (turns 1-5)

### Turn 1 — cold session start

- **What I wanted to do:** Boot the session. I'm a fresh agent attached
  to a freshly-`init`ed Research-OS workspace; the researcher's first
  message is *"I have 4 Henry James novels in `inputs/raw_data/` —
  early-period and late-period. Test whether his vocabulary shifts
  toward interiority + consciousness in the late novels."*
- **Tool I called:** `sys_boot` (per `templates/CLAUDE.md` and
  `docs/AI_GUIDE.md` § Session pattern — FIRST MCP call on every cold
  session).
- **Simulated result:** Returns workspace state (`has_os_state: true`,
  no prior protocol history), `recommended_next: guidance/project_startup`,
  `model_profile: medium` (template default), `pause_classification:
  fresh_project`, no active plan. Researcher config is the default
  template (`citation_style: apa`, `venue_template: generic_two_column`).
- **Was the result format clear?** Yes. The AI_GUIDE bullets enumerate
  the seven sub-payloads of `sys_boot`.
- **Did I know what to do next?** Yes — call `tool_route` with the
  verbatim prompt next.
- **Friction:** none.
- **Doc gap:** none.
- **Time-to-clarity:** ~10 s.

### Turn 2 — route the prompt

- **What I wanted to do:** Route the verbatim researcher message.
- **Tool I called:** `tool_route(prompt="I have 4 Henry James novels in
  inputs/raw_data/ — early-period and late-period. Test whether his
  vocabulary shifts toward interiority + consciousness in the late
  novels.")`
- **Simulated result:** Hybrid semantic + trigger picker. *"corpus of
  N texts" / "stylistic claim" / "vocabulary shift"* are humanities-pack
  triggers per the `USE_CASES.md` § Common first prompts row 3.
  Expected return: `intent_class=methodology`,
  `sub_intent=subfield_pipeline`, `primary_protocol=humanities/method/
  digital_humanities_workflow`, `complexity=high` (corpus + hypothesis
  warrants a multi-step active_plan), `ask_user=null`,
  `decomposition=[tool_intake_autofill, sys_protocol_get(humanities/
  method/digital_humanities_workflow), guidance/analysis_plan…]`.
- **Was the result format clear?** Yes.
- **Did I know what to do next?** Yes — `complexity=high` ⇒ router
  persisted an `active_plan`; I call `tool_plan_turn` next.
- **Friction:** FRICTION/LOW — there are TWO candidate humanities
  protocols (`textual/distant_reading`, `method/digital_humanities_
  workflow`) that overlap heavily on the same triggers. From the YAML
  reading, `digital_humanities_workflow` is the umbrella; `distant_
  reading` is the more constrained sub-protocol. `USE_CASES.md`
  resolves it ("auto-loads `digital_humanities_workflow`; see also
  `distant_reading` + `close_reading`"), but a fresh agent unfamiliar
  with the pack would have to peek at both to confirm.
- **Doc gap:** Single ranked routing line in
  `docs/PROTOCOLS.md` under the humanities pack section ("DH ⇒
  digital_humanities_workflow; corpus-only ⇒ distant_reading;
  passage-only ⇒ close_reading") would resolve it without protocol
  inspection. The 114-protocol catalogue index doesn't list the
  humanities pack at all (it's an external `research_os_humanities`
  package, not in the in-tree `protocols/` count).
- **Time-to-clarity:** ~40 s.

### Turn 3 — researcher_config check + intake autofill

- **What I wanted to do:** Verify the humanities venue template and
  citation style before kicking off intake; the default template ships
  `venue_template: generic_two_column` and `citation_style: apa`, both
  wrong for a humanities essay. Then run intake.
- **Tool I called:** Read `inputs/researcher_config.yaml` (via
  `sys_file_read` / direct read since the file is in `inputs/`).
  Prompt the researcher: *"I'll switch `venue_template` to
  `humanities_essay` and `citation_style` to `mla` (or
  `chicago_notes_bib` if you prefer footnotes) before drafting; OK?"*
- **Simulated result:** Researcher confirms `humanities_essay` +
  `chicago_notes_bib` (literary studies convention; the config comment
  in `templates/researcher_config.yaml` line 106 names it for "literary
  studies, theology, art history (footnotes)").
- **Was the result format clear?** Yes. The config comments are
  unusually well-written; every venue template option has a one-line
  audience description.
- **Did I know what to do next?** Yes — `sys_config_set` (or edit the
  yaml + commit via a `sys_file_write`).
- **Friction:** FRICTION/LOW — the wizard's interactive default
  doesn't detect "humanities pack triggered" and offer
  `humanities_essay` / `chicago_notes_bib` at scaffold time; the AI
  has to manually flip them. Not catastrophic, but every fresh
  humanities project will eat a turn on this.
- **Doc gap:** `docs/SETUP.md` / `docs/AI_GUIDE.md` § domain packs
  could note: *"When the humanities detector fires (or the prompt
  matches DH triggers), propose `venue_template: humanities_essay` +
  `citation_style: mla|chicago_notes_bib` on first turn."*
- **Time-to-clarity:** ~30 s.

### Turn 4 — tool_intake_autofill

- **What I wanted to do:** Read the four novel `.txt` files in
  `inputs/raw_data/` and propose project metadata
  (`docs/research_overview.md`, `inputs/intake.md`, state seed).
- **Tool I called:** `tool_intake_autofill` (shortcut tool for
  `discover/intake` per `_router_index.yaml`; described in TOOLS.md
  line 124). Per `docs/START.md` § "When your project needs extra
  `inputs/` subfolders", a humanities corpus belongs in
  `inputs/corpus/` (the autofill expects `inputs/corpus/corpus_
  manifest.csv` per `distant_reading.yaml` step `define_corpus_and_
  unit`). I would BEFORE-call advise: *"For humanities corpora, drop
  the texts in `inputs/corpus/` so the autofill builds
  `corpus_manifest.csv` automatically."* But the researcher already
  put them under `raw_data/`, so I need to either (a) move them or
  (b) treat `raw_data/` as the corpus root.
- **Simulated result:** Per AI_GUIDE § `inputs/` conventions, the
  autofill "populates corpus_manifest.csv when present" — so if
  files are in `raw_data/`, autofill will note them but won't build
  the manifest in the expected `corpus/` location. Likely returns
  `status=ok` with `domain_inferred=humanities`,
  `research_question="Does Henry James's late-period vocabulary
  shift toward interiority + consciousness?"`,
  `hypotheses=[{...}]`, and a WARN that the corpus is in `raw_data/`
  rather than `corpus/`. I'd then run `sys_file_move` to relocate
  (raw_data is immutable, so this is a problem — the server BLOCKS
  writes there per `docs/START.md` line 75).
- **Was the result format clear?** Yes for the typed envelope; no for
  the corpus-location decision. Once in `raw_data/`, the AI is stuck:
  immutability says "don't move", but the corpus protocol expects
  `corpus/`.
- **Did I know what to do next?** No — split path. I have to ask the
  researcher to manually move the files OR I accept `raw_data/<slug>/`
  as the corpus root and live with the manifest building under
  `workspace/dh/` rather than `inputs/corpus/`.
- **Friction:** FRICTION/MEDIUM — `inputs/raw_data/` is server-immutable
  but the humanities corpus protocols want `inputs/corpus/`. The
  first-turn AI guidance ("tell the researcher where to drop files
  BEFORE running autofill") doesn't help once they've already dropped
  in `raw_data/`. The "after-the-fact" recovery path isn't documented.
- **Doc gap:** `docs/START.md` table § "When your project needs extra
  inputs/ subfolders" should add a recovery row: *"Already dropped a
  text corpus in `raw_data/`? Symlink (`ln -s ../raw_data/<slug>
  inputs/corpus/<slug>`) — the server treats symlink targets under
  raw_data as read-only, but the manifest builds under `corpus/`."*
  Or document that the humanities protocols accept
  `inputs/raw_data/<slug>/` as a corpus root.
- **Time-to-clarity:** ~120 s (had to read three docs to confirm the
  immutability contract still allowed reading from raw_data into a
  workspace manifest — which it does, just not write-through).

### Turn 5 — researcher confirms intake + we lock the research overview

- **What I wanted to do:** Confirm the intake-inferred research
  question, hypothesis, and domain with the researcher before moving
  to planning.
- **Tool I called:** Surface `docs/research_overview.md` +
  `inputs/intake.md` for the researcher to read; if confirmed, write
  via `mem_log` that the project_startup phase is closed.
- **Simulated result:** Researcher confirms ("yes, that's the
  hypothesis; corpus is correct; bias profile of canonical
  Anglophone-male 19th-c novels noted").
- **Was the result format clear?** Yes — `research_overview.md` is
  the canonical artifact the rest of the pipeline reads.
- **Did I know what to do next?** Yes — `sys_protocol_next` would
  return `domain/domain_analysis` (or the humanities-pack equivalent),
  but the active_plan from turn 2 already has the right sequence
  queued — call `tool_plan_advance` and let it tell me.
- **Friction:** none.
- **Doc gap:** none.
- **Time-to-clarity:** ~20 s.

**Onboarding-friction count (turns 1-5):** 3 (1 LOW route ambiguity,
1 LOW venue-template default, 1 MEDIUM corpus-location-vs-immutability).

---

## 2. Hypothesis + planning (turns 6-10)

### Turn 6 — load digital_humanities_workflow protocol (summary)

- **What I wanted to do:** Load the umbrella DH protocol summary to see
  the step headings before executing.
- **Tool I called:** `sys_protocol_get(name="humanities/method/
  digital_humanities_workflow", format="summary")`.
- **Simulated result:** Returns 7 step headings: `corpus_audit`,
  `distant_pass`, `cluster_inspection`, `close_reading_sample`,
  `interpret_or_reject`, `visualize_with_caveats`,
  `write_methods_section`. Plus quality_bar headings (cluster_
  coverage, close_reading_minimum, reproducibility, bias_disclosure,
  visualization_honesty) and `next_protocol: humanities/output/
  scholarly_edition`.
- **Was the result format clear?** Yes — ~300 token summary as
  promised.
- **Did I know what to do next?** Yes — the protocol step list IS my
  plan. The protocol enforces the close-reading gate via
  `close_reading_sample` step (this is the load-bearing part for the
  scenario: the hypothesis WILL get tested by a distant pass, but
  every promoted cluster gets close-read before publication).
- **Friction:** none.
- **Doc gap:** none. The protocol is well-scoped and matches the
  scenario's "must not be shoehorned into statistics" constraint —
  the editorial_voice explicitly insists "Distant reading is
  hypothesis-generating, not hypothesis-confirming" and the
  close_reading_sample step requires 3+ texts per cluster.
- **Time-to-clarity:** ~30 s.

### Turn 7 — hypothesis tracking + glossary

- **What I wanted to do:** Register the hypothesis with the project
  memory so synthesis can carry it forward + populate the glossary
  with the operative terms (interiority, free indirect discourse,
  consciousness, late style, period vocabulary).
- **Tool I called:** `mem_hypothesis_log(claim="Henry James's late-
  period vocabulary shifts toward interiority and consciousness",
  scope="corpus = Roderick Hudson + The American (early) vs The
  Ambassadors + The Wings of the Dove (late)", status="open")`.
  Followed by `mem_glossary_add` for the five operative terms.
- **Simulated result:** Status `ok`; hypothesis stored in
  `.os_state/`; glossary written to `docs/glossary.md`.
- **Was the result format clear?** Yes.
- **Did I know what to do next?** Yes — proceed to `corpus_audit` step.
- **Friction:** none.
- **Doc gap:** `mem_glossary_add` doesn't appear in the TOOLS.md
  spotlight — I had to infer the API from `mem_*` namespace convention.
- **Time-to-clarity:** ~20 s.

### Turn 8 — analysis plan freeze

- **What I wanted to do:** Freeze the analytical plan before running
  computations. The hypothesis is well-formed enough to pre-register
  what counts as evidence: (a) MFW frequency drift between periods,
  (b) topic model deltas, (c) close-reading verification of N
  representative passages per promoted topic, (d) interpretive
  apparatus around at least 4 passages (one per novel).
- **Tool I called:** `tool_route("freeze the analysis plan")` →
  routes to `methodology/preregistration` OR `guidance/analysis_plan`.
  For a humanities project I lean `guidance/analysis_plan` (the
  preregistration protocol is empirical-hypothesis-shaped and would
  ask for power calcs that don't apply).
- **Simulated result:** Loads `guidance/analysis_plan` summary;
  per-step loop = `scope → ground → execute → document → snapshot`.
  Plan freeze writes `workspace/analysis_plan.md` listing the
  computational moves (MFW, LDA, frequency-drift table) AND the
  interpretive moves (4 close-reading passages, one per novel).
- **Was the result format clear?** Yes.
- **Did I know what to do next?** Yes — execute step 1 of DH
  workflow (`corpus_audit`).
- **Friction:** FRICTION/LOW — humanities-flavoured "freeze the
  analysis plan" doesn't trigger a humanities-aware preregistration
  variant; the empirical preregistration protocol would mismatch
  (power calc, multiple-testing correction etc.). Working through
  `analysis_plan` is fine but the field-appropriateness of the
  freeze artifact is on me.
- **Doc gap:** A humanities-flavoured analysis_plan example in
  `RESEARCHER_GUIDE.md` (or a sister protocol
  `humanities/method/interpretive_plan`) would resolve it.
- **Time-to-clarity:** ~40 s.

### Turn 9 — set step contract for the apparatus track

- **What I wanted to do:** Each step in this scenario will produce
  EITHER a computational artifact (numeric / figure) OR an
  interpretive apparatus (markdown close-reading). The
  `close_reading.yaml` protocol step `declare_step_contract` is
  explicit: write `workspace/<step>/step_summary.yaml` with
  `step_intent: apparatus`, `figure_required: false`,
  `table_required: false`, `literature_required: true`. This is
  what tells `tool_audit_step_completeness` not to BLOCK on missing
  figures for the close-reading steps.
- **Tool I called:** Pre-author `step_summary.yaml` per step using
  the template at `templates/step_summary.yaml.template`. The
  computational steps (corpus_audit, distant_pass) get
  `step_intent: analysis` + `figure_required: true`; the
  close-reading steps get `step_intent: apparatus`.
- **Simulated result:** OK. CHANGELOG v1.9.3 explicitly says
  `_is_humanities_project` was added so the completeness audit
  accepts `apparatus.md` / `transcriptions/` / `close_reading.md` /
  `citation_chains.md` as focal artifacts even without a figure —
  this is the v1.9.3 fix that unblocks the humanities flow.
- **Was the result format clear?** Yes.
- **Did I know what to do next?** Yes.
- **Friction:** none — this is the v1.9.3 fix at work.
- **Doc gap:** none.
- **Time-to-clarity:** ~30 s.

### Turn 10 — corpus_audit step kickoff

- **What I wanted to do:** Execute DH step 1 — `corpus_audit`. Build
  `workspace/dh/corpus_audit.md` with date distribution, author
  (single — James), genre (all novels), language (English), word
  count per novel, edition provenance (Project Gutenberg with their
  text-cleaning caveats), and the explicit absences register: NO
  non-fiction, NO short stories, NO posthumous fragments, NO
  notebooks — only 4 novels, 2 per period.
- **Tool I called:** `tool_step_pipeline_define(step_id="01_corpus_
  audit")` to create the step folder + pipeline.yaml; then
  `tool_python_exec` (or shell) for the manifest build.
- **Simulated result:** Folder + pipeline created; manifest builds
  with 4 rows.
- **Was the result format clear?** Yes.
- **Did I know what to do next?** Yes — run the audit, write the
  step's `.summary.md` + `conclusions.md`, then close via
  `tool_step_complete`.
- **Friction:** none.
- **Doc gap:** none.
- **Time-to-clarity:** ~30 s.

---

## 3 + 4. Per-step execution + per-step literature gate (turns 11-25)

The DH workflow has 7 steps; we interleave a literature-gate call after
each. To stay inside the turn budget I batch the lighter steps.

### Turn 11 — step 01 (corpus_audit) execution + step_complete

- **What I wanted to do:** Finish the corpus audit and gate-close it.
- **Tool I called:** `tool_step_complete(step_id="01_corpus_audit")`.
- **Simulated result:** Per TOOLS.md `tool_step_complete` schema,
  runs `tool_audit_step_completeness` + `tool_audit_step_literature`
  + per-step `tool_audit_quality_full` pieces in sequence, then
  `tool_path_finalize`. Expected:
  - completeness: PASS (manifest exists, summary written,
    step_intent=analysis matches a markdown report).
  - literature: likely BLOCK on missing `findings_vs_literature.md`
    — the corpus_audit step has NO empirical claim yet (it's
    descriptive), so I'd use the `override_literature_gate=true,
    override_rationale="step 01 is corpus enumeration; no
    interpretive claim, defer the literature loop to the distant_
    pass step where the actual finding emerges"` path.
- **Was the result format clear?** Yes (schema is exemplified at
  TOOLS.md line 538-554).
- **Did I know what to do next?** Yes — the override path is
  documented and logged to `workspace/logs/override_log.md`.
- **Friction:** FRICTION/MEDIUM — `tool_audit_step_literature` is
  by-design empirical-claim-centric ("any claim lacks a Verdict /
  AGREES|DISAGREES|EXTENDS|DEFERRED"). For descriptive corpus-build
  steps (or pure-prep steps), there's no NULL claim to verdict
  against — the only escape is the override. CHANGELOG v1.9.3 mentions
  `AUDIT-v1.9.2-022 — literature_per_step empirical-only (humanities
  blocker) | v1.9.4` as DEFERRED, so this is a known issue still open
  in v1.9.4.
- **Doc gap:** `tool_audit_step_literature` description in TOOLS.md
  should explicitly call out "for descriptive / corpus-build /
  pure-data-ingest steps with no interpretive claim, use the override
  path with rationale `descriptive_step`".
- **Time-to-clarity:** ~60 s.

### Turn 12 — step 02 (distant_pass) execution

- **What I wanted to do:** Run the distant-reading pass. Three
  computational moves: (a) MFW frequency drift between early-pair
  and late-pair, (b) topic model (LDA, k=10, 15, 20 — protocol
  requires param sweep per `distant_reading.yaml` quality_bar
  `parameter_sweep`), (c) target-vocabulary frequency tracking for
  interiority / consciousness / mind / felt / aware / thought /
  perception (and their inflections).
- **Tool I called:** `tool_step_pipeline_define(step_id="02_distant_
  pass")` with a pipeline.yaml of atomic nodes: `tokenize` →
  `build_dtm` → `mfw_drift` → `lda_sweep[10,15,20]` → `target_vocab_
  freq` → `report`. Then `tool_step_pipeline_run`.
- **Simulated result:** Five figures produced + `topic_freq_by_
  period.csv` + `target_vocab_freq.csv`. Pre-empt the target finding:
  the late novels DO show a marked uptick in {consciousness, aware,
  perception, mind, felt} relative to {action, object, place, deed} —
  consistent with the hypothesis, but the topic-model run also
  surfaces a "late-style syntactic complexity" cluster that's NOT
  about vocabulary but about clause length.
- **Was the result format clear?** Yes.
- **Did I know what to do next?** Yes — `cluster_inspection` (step
  3 of DH), then the close-reading gate.
- **Friction:** FRICTION/LOW — `pick_tool_stack` (R vs Python) for
  the LDA work isn't explicit in the DH protocol; the protocol says
  "gensim/scikit-learn LDA, BERTopic, or top2vec" but doesn't
  pre-route through `methodology/pick_tool_stack`. Minor — the
  protocol is open enough that I just pick Python with a
  citation-of-field-practice comment.
- **Doc gap:** none.
- **Time-to-clarity:** ~30 s.

### Turn 13 — step 02 literature gate

- **What I wanted to do:** Run the per-step literature gate against
  the distant_pass findings. The relevant prior literature:
  Underwood *Distant Horizons* (2019), Underwood & Sellers (2016)
  on novel reception, Hoover (2007) on stylometric drift in late
  James specifically, Krook (1962) on James's late style, Yeazell
  (2010) on Jamesian consciousness.
- **Tool I called:** `tool_route("literature search on late James
  style + computational stylometry")` →
  `literature/literature_per_step`. Run search,
  download (server can pull arXiv/Crossref where DOI exists; some
  literary-criticism cites won't have DOIs — Hoover 2007 will, Krook
  1962 won't). Build
  `workspace/02_distant_pass/literature/findings_vs_literature.md`
  with verdicts per claim.
- **Simulated result:** 4 verdicts:
  - Vocabulary shift toward consciousness → AGREES (Krook 1962;
    Yeazell 2010).
  - Late James complexity is syntactic not lexical → EXTENDS
    (Hoover 2007 — stylometric outlier signature exists; the
    interiority-vocab framing is novel).
  - Topic model sees genre stability across periods → AGREES
    (Underwood 2019, lower-level genre fingerprints are persistent).
  - Specific MFW ranking-shift artifact → DEFERRED (no comparable
    James-only MFW study located in v1 search).
- **Was the result format clear?** Yes — the AGREES / DISAGREES /
  EXTENDS / DEFERRED rubric is explicit in TOOLS.md
  `tool_audit_step_literature` row.
- **Did I know what to do next?** Yes — `tool_step_complete(step_id=
  "02_distant_pass")`. Should pass; one verdict is DEFERRED with no
  PDF, which is a v1.4.0 BLOCK trigger ("all-DEFERRED with no PDFs"
  — but I have non-DEFERRED verdicts, so this rule only fires when
  the WHOLE file is DEFERRED).
- **Friction:** FRICTION/LOW — DEFERRED needs a PDF if it's the
  ONLY verdict but not if there's a mix. The literature_per_step
  protocol doesn't enumerate worked examples; I had to infer the
  "mixed" allowance from the negation of the all-DEFERRED rule.
- **Doc gap:** Worked-example DEFERRED entry (with rationale text)
  in `literature_per_step.yaml` would prevent guess-and-check.
- **Time-to-clarity:** ~90 s (had to search Project Gutenberg-cite
  patterns + manually decide what to download).

### Turn 14 — step 03 (cluster_inspection) + close_reading_gate kickoff

- **What I wanted to do:** Per `digital_humanities_workflow.yaml`
  step 3, write pre-interpretive summaries for each LDA topic +
  the MFW drift outliers WITHOUT naming them. Then per step 4,
  sample 3 texts per cluster for close reading.
- **Tool I called:** `tool_step_pipeline_define(step_id="03_cluster_
  inspection")` then a manual markdown build per cluster
  (`workspace/dh/clusters/topic_<k>_<id>.md` with top-N words +
  top-N documents loaded + cluster size + coherence; no naming).
- **Simulated result:** 15 cluster files (LDA k=15 chosen as the
  reported run after sweep showed best coherence). 4 flagged
  "suspicious": one is a function-word residue, two are
  single-novel-dominated (one is *Wings of the Dove*-heavy, one is
  *Roderick Hudson*-heavy, both probably narrative-event clusters
  not thematic clusters), one is OCR-noise-shaped.
- **Was the result format clear?** Yes.
- **Did I know what to do next?** Yes — sample passages for each
  cluster I plan to keep, run close reading per
  `close_reading.yaml`.
- **Friction:** none.
- **Doc gap:** none.
- **Time-to-clarity:** ~30 s.

### Turn 15 — step 03 step_complete

- **What I wanted to do:** Close step 03.
- **Tool I called:** `tool_step_complete(step_id="03_cluster_
  inspection")`.
- **Simulated result:** PASS-with-warnings. Completeness OK
  (markdown summaries are the artifact, no figure needed since
  step_intent=analysis with `figure_required: false` set
  per-step). Literature gate: override with rationale "intermediate
  inspection step; cluster claims will be tested via close_reading
  in step 04 before any literature comparison".
- **Was the result format clear?** Yes.
- **Did I know what to do next?** Yes.
- **Friction:** see turn 11 (same lit-gate issue).
- **Doc gap:** same.
- **Time-to-clarity:** ~20 s.

### Turn 16 — step 04 (close_reading_sample) execution: load close_reading protocol

- **What I wanted to do:** For each cluster I plan to promote, run
  the close_reading protocol per text. Plan: keep 5 thematic
  clusters (drop the 4 suspicious ones), close-read 3 passages per
  cluster = 15 close readings — but I'll consolidate to 4 close
  readings (one per NOVEL) that each EXEMPLIFY the dominant
  interiority cluster, plus 2 counter-instances (one early-novel
  passage that already shows interiority; one late-novel passage
  that resists it).
- **Tool I called:** `sys_protocol_get(name="humanities/textual/
  close_reading", format="summary")`. The protocol has 7 steps:
  `declare_step_contract`, `scope_passage`, `declare_tradition`,
  `annotate_line_by_line`, `pattern_and_counter`, `situate`,
  `write_apparatus`.
- **Simulated result:** Loaded; step 1 (`declare_step_contract`)
  was already done at turn 9 — apparatus contract is in place.
- **Was the result format clear?** Yes.
- **Did I know what to do next?** Yes — pick the 6 passages, drop
  them in `inputs/textual/passages/<slug>.md` (per `start.md` table
  row, this subfolder is also not wizard-created), then run the
  protocol per passage.
- **Friction:** FRICTION/LOW — running the same 7-step protocol six
  times in a row is verbose. `tool_step_iterate` could parallelize,
  but the protocol is written for one-passage-at-a-time; running
  six close readings as six numbered steps inflates the workspace.
  Alternative: one step `04_close_reading` with a sub-folder per
  passage. The protocol's `expected_outputs` block (`inputs/textual/
  passages/<slug>.md` + `workspace/close_readings/<slug>.md` + …)
  is template-friendly to the sub-folder approach, but explicit
  guidance would help.
- **Doc gap:** `close_reading.yaml` could add a *"Running close
  reading on multiple passages within one step"* note pointing at
  the `<slug>` placeholders as the parallelization key.
- **Time-to-clarity:** ~60 s.

### Turn 17 — step 04 execution (6 passages)

- **What I wanted to do:** Run all 6 close readings. For each:
  scope + edition pin (Project Gutenberg with caveat that it's not
  a critical edition — for late James the New York Edition (1907-9)
  is canonical, Gutenberg uses earlier serial / first-edition
  texts, this is itself a finding the methods section must flag),
  declare tradition (formalist + historicist braid, per
  close_reading editorial_voice rule 2), annotate line-by-line,
  find pattern + counter, situate against Yeazell / Krook /
  Hoover, write apparatus.
- **Tool I called:** Manual markdown authoring; ran with `mem_log`
  per declaration as the protocol's `declare_tradition` step
  requires. Built 6 apparatus files under `workspace/close_readings/
  <slug>_apparatus.md`.
- **Simulated result:** 6 apparatus files. Three load-bearing
  findings emerge: (a) late James's interiority is enacted as much
  by syntactic suspension (delayed verbs, embedded clauses) as by
  vocabulary — this REFINES the original hypothesis from
  "vocabulary shifts" to "vocabulary + syntactic enactment shifts";
  (b) the early novels DO contain interiority passages but with a
  different register (interiority-as-emotion, not
  interiority-as-perception); (c) one late passage (*Wings* book V
  ch. 3) actively RESISTS interiority — Milly's exteriority is the
  point.
- **Was the result format clear?** Yes — the `<slug>_apparatus.md`
  artifact is the unit synthesis consumes.
- **Did I know what to do next?** Yes — close step 04 then run the
  citation_chains protocol (the `close_reading.yaml`'s
  `next_protocol: humanities/citation/citation_chains` points
  there).
- **Friction:** FRICTION/LOW — the "the New York Edition vs the
  Gutenberg edition" issue is real and recurring for Henry James
  digital projects; the close_reading protocol's `scope_passage`
  step does flag variant-edition pinning, but the apparatus has to
  flag the limitation in EVERY close reading. A pack-level convention
  ("if using Gutenberg, here's the standard caveat sentence") would
  reduce repetition.
- **Doc gap:** Humanities pack could ship a short
  `EDITION_CAVEATS.md` reference for the standard digital corpora
  (Gutenberg, HathiTrust, Wikisource, EEBO).
- **Time-to-clarity:** ~90 s.

### Turn 18 — step 04 literature gate (citation_chains)

- **What I wanted to do:** Per close_reading next_protocol pointer,
  load `humanities/citation/citation_chains` and verify every
  secondary-criticism citation invoked in the apparatus.
- **Tool I called:** `sys_protocol_get(name="humanities/citation/
  citation_chains", format="summary")` + `tool_citations_verify`.
- **Simulated result:** Loaded; verify pass — Krook 1962 (book,
  Cambridge UP — no DOI, but ISBN-verifiable via Crossref books
  endpoint); Yeazell 2010; Hoover 2007 (DOI verifies); Underwood
  2019 (Stanford UP). All resolve. The literature gate for step
  04 specifically would AGREES on the interiority-vocab finding,
  EXTENDS on the syntactic-enactment finding (Krook 1962 names
  the syntactic effect but not in MFW / distant-reading terms).
- **Was the result format clear?** Yes.
- **Did I know what to do next?** Yes.
- **Friction:** FRICTION/LOW — `tool_citations_verify` is built
  around DOI-resolution (Crossref / Semantic Scholar). For
  humanities monographs from the 1960s with no DOI, the verify
  path is shakier. The CHANGELOG v1.9.3 mentions
  `AUDIT-v1.9.2-074: Humanities pack chains dead-end at
  next_protocol: null` as DEFERRED — the chain
  close_reading→citation_chains→? may not have a forward path; I'd
  need to manually re-enter `tool_route` after.
- **Doc gap:** Citation-chains' `next_protocol` should not be null
  for the publication path; it should point at
  `humanities/method/digital_humanities_workflow` step 5
  (`interpret_or_reject`) or directly at synthesis. (This is a
  known DEFERRED finding; still open in v1.9.4.)
- **Time-to-clarity:** ~40 s.

### Turn 19 — step 04 step_complete

- **What I wanted to do:** Close step 04.
- **Tool I called:** `tool_step_complete(step_id="04_close_
  reading")`.
- **Simulated result:** PASS. Apparatus files are the focal
  artifacts; v1.9.3 fix means `_collect_humanities_artefacts`
  accepts them. Literature gate PASS (mixed verdicts, multiple
  PDFs / verified citations).
- **Was the result format clear?** Yes.
- **Did I know what to do next?** Yes — back to DH workflow step 5.
- **Friction:** none.
- **Doc gap:** none.
- **Time-to-clarity:** ~15 s.

### Turn 20 — step 05 (interpret_or_reject)

- **What I wanted to do:** Per DH step 5, decide each cluster's
  fate (PROMOTE / REJECT / REFINE) and log to
  `workspace/dh/cluster_decisions.md`.
- **Tool I called:** Manual markdown build.
- **Simulated result:** 5 PROMOTED clusters (interiority-vocab,
  perception-mind, free-indirect-discourse markers,
  syntactic-suspension markers, register-of-felt-thought),
  4 REJECTED (function-word residue, two single-novel narrative
  clusters, OCR-noise cluster), 1 REFINED (re-run LDA with k=12
  and a tighter stopword list to test stability of the
  interiority-vocab cluster).
- **Was the result format clear?** Yes.
- **Did I know what to do next?** Yes — close step 05 + run step 06
  (visualize_with_caveats).
- **Friction:** none.
- **Doc gap:** none.
- **Time-to-clarity:** ~30 s.

### Turn 21 — step 05 step_complete + step 06 (viz with caveats)

- **What I wanted to do:** Close step 05, then build the canonical
  figures: (F1) MFW drift heatmap early vs late; (F2)
  interiority-vocab frequency-over-novel line plot, with the 6
  close-reading passage anchors overlaid; (F3) LDA topic
  cluster-by-period stacked bar; (F4) a counter-instance plot
  showing the *Wings* book V passage's anomalous low-interiority
  score. Each figure ships with caveat.md + data.csv +
  regenerate.sh per protocol quality_bar `visualization_honesty`.
- **Tool I called:** `tool_step_complete(step_id="05_interpret")`
  then `tool_step_pipeline_define(step_id="06_visualize")` +
  `tool_step_pipeline_run`. Per-figure: `tool_audit_figure_full`
  to enforce DPI + palette + the 4 sidecars contract.
- **Simulated result:** PASS for step 05. Step 06: 4 figures pass
  the figure audit, all caveats written.
- **Was the result format clear?** Yes.
- **Did I know what to do next?** Yes — close step 06, then step 07
  (methods section draft).
- **Friction:** none.
- **Doc gap:** none.
- **Time-to-clarity:** ~30 s.

### Turn 22 — step 06 step_complete + literature gate

- **What I wanted to do:** Close step 06 and its lit gate. The
  figures are visualizations of step 02 + step 04 findings already
  vetted; this lit gate has no new claims.
- **Tool I called:** `tool_step_complete(step_id="06_visualize",
  override_literature_gate=true, override_rationale="figure-only
  step; all claims grounded in steps 02 + 04 literature gates")`.
- **Simulated result:** PASS-with-override (logged to
  `override_log.md`).
- **Was the result format clear?** Yes.
- **Did I know what to do next?** Yes.
- **Friction:** see turn 11 — same recurring "pure-viz / pure-prep
  step has no claim to verdict" issue.
- **Doc gap:** same.
- **Time-to-clarity:** ~15 s.

### Turn 23 — step 07 (methods section)

- **What I wanted to do:** Draft `synthesis/dh/methods_section.md`
  per DH step 7. Cover: corpus composition + bias (single author,
  4 novels, Gutenberg-edition caveat, all-male-canon noted);
  techniques + why (MFW for lexical drift, LDA for topic
  structure, target-vocab tracking for hypothesis-direct measure);
  cluster decisions; close-reading sampling frame (one passage
  per novel + 2 counter-instances); software versions + seeds.
- **Tool I called:** Manual markdown draft + `tool_audit_prose`
  pass.
- **Simulated result:** Draft written, audit_prose flags 1
  hedging instance ("seems to suggest"), fixed.
- **Was the result format clear?** Yes.
- **Did I know what to do next?** Yes — close step 07 then run
  master audit.
- **Friction:** none.
- **Doc gap:** none.
- **Time-to-clarity:** ~30 s.

### Turn 24 — step 07 step_complete

- **Tool I called:** `tool_step_complete(step_id="07_methods_
  section")`.
- **Simulated result:** PASS.
- **Friction:** none.
- **Time-to-clarity:** ~10 s.

### Turn 25 — pre-synthesis dependency check

- **What I wanted to do:** Confirm every step the synthesis will
  consume is finalized; confirm the apparatus track + computational
  track are both represented.
- **Tool I called:** `sys_dep_inventory` (would have been in the
  `sys_boot` payload, but since we're 24 turns in I'd want a fresh
  inventory) and `sys_protocol_history`.
- **Simulated result:** 7 steps finalized; no orphans; all step
  summaries written; close-reading apparatus + DH workflow outputs
  both present.
- **Was the result format clear?** Yes.
- **Did I know what to do next?** Yes — master audit.
- **Friction:** none.
- **Time-to-clarity:** ~15 s.

---

## 5. Audit + synthesis (turns 26-33)

### Turn 26 — tool_audit_quality_full

- **What I wanted to do:** Run the master audit before synthesis.
- **Tool I called:** `tool_audit_quality_full`.
- **Simulated result:** Per TOOLS.md sample (line 558+), runs 6
  gates: step_completeness, code_quality, prose, claims,
  preregister_diff, ground. Likely WARN, not BLOCK. Probably 2-3
  warnings: (a) one prose hedging instance in the apparatus that
  the apparatus tolerates but the master audit flags; (b)
  `preregister_diff` — I didn't formally preregister, so this is
  a no-op WARN; (c) one ground citation where the Krook 1962 page
  number was paraphrased without a verbatim quote — fix by adding
  the quote or marking as paraphrase.
- **Was the result format clear?** Yes — the schema example in
  TOOLS.md is exemplary.
- **Did I know what to do next?** Yes — address warnings then call
  `tool_synthesize`.
- **Friction:** none.
- **Doc gap:** none.
- **Time-to-clarity:** ~20 s.

### Turn 27 — fix warnings + re-audit

- **What I wanted to do:** Patch the 3 warnings.
- **Tool I called:** Edits to 3 apparatus files; re-run
  `tool_audit_quality_full`.
- **Simulated result:** PASS, 0 warnings.
- **Friction:** none.
- **Time-to-clarity:** ~30 s.

### Turn 28 — load synthesis_paper protocol

- **What I wanted to do:** Load the paper synthesis protocol.
  Default `synthesis/synthesis_paper.yaml` assumes IMRAD; per
  `AI_GUIDE.md` § Theory pack the IMRAD assumptions don't apply to
  theory — analogously, a humanities essay isn't IMRAD either. I
  need to check if synthesis_paper has a humanities variant or if
  I should output a different structure.
- **Tool I called:** `sys_protocol_get(name="synthesis/synthesis_
  paper", format="summary")`.
- **Simulated result:** Loaded. The protocol's
  `editorial_voice` + structure default to IMRAD; venue_template
  controls the typeset layout, not the section structure.
- **Was the result format clear?** Yes.
- **Did I know what to do next?** Partial — I need to decide how
  to coerce a humanities essay into the synthesis_paper protocol.
  Options: (a) call `synthesis_paper` with
  `venue_template=humanities_essay` and rely on its non-IMRAD
  conventions; (b) author the markdown manually around the
  protocol's `tool_synthesize` call.
- **Friction:** FRICTION/MEDIUM — `synthesis_paper` is IMRAD by
  default; the humanities essay's structure (Argument →
  Apparatus 1 → Apparatus 2 → … → Counter-readings → Coda) is
  fundamentally different. The `humanities_essay.typ` template
  exists but no `humanities_essay` PROTOCOL exists. Theory has
  `theory_math/output/theory_paper_structure`; humanities has no
  analogous `humanities/output/humanities_essay_structure`
  protocol (only `scholarly_edition`, which is for edition-of-
  text work, not essay writing).
- **Doc gap:** Humanities pack should ship
  `humanities/output/humanities_essay_structure` (paralleling
  `theory_paper_structure`) that names the canonical essay
  movement (claim → apparatus chain → counter → coda) and the
  load order for the apparatus files. Without it, the AI either
  forces the IMRAD frame (wrong for humanities) or invents an ad
  hoc structure.
- **Time-to-clarity:** ~90 s.

### Turn 29 — tool_synthesize

- **What I wanted to do:** Compile the workspace into
  `synthesis/paper.md` with venue=humanities_essay.
- **Tool I called:** `tool_synthesize(output_type="paper",
  venue_template="humanities_essay")`. Per the scenario's
  hard-line "must not be shoehorned into stats framing", I'd
  prepare `synthesis/synthesis_spec.md` manually first with the
  apparatus-first ordering, then call `tool_synthesize`.
- **Simulated result:** Per docstring (TOOLS.md line 149) the
  synthesis gate-calls `tool_audit_quality_full` first (already
  passed). Output: `synthesis/paper.md` with apparatus excerpts,
  block-quoted passages, line-anchored citations, references
  list. Citations all verified (Krook 1962, Yeazell 2010, Hoover
  2007, Underwood 2019, Moretti 2013, James 1907 NY Edition for
  comparison reference).
- **Was the result format clear?** Yes for the envelope; the
  body's structure is whatever the synthesis tool fills in.
- **Did I know what to do next?** Yes — `tool_paper_compile_typst`
  per CHANGELOG v1.9.3 fix `AUDIT-v1.9.2-029` (auto-appended to
  decomposition).
- **Friction:** see turn 28 (structural frame).
- **Doc gap:** see turn 28.
- **Time-to-clarity:** ~60 s.

### Turn 30 — tool_paper_compile_typst

- **What I wanted to do:** Compile `synthesis/paper.md` →
  `paper.typ` → `paper.pdf` via Typst with the humanities_essay
  template.
- **Tool I called:** `tool_paper_compile_typst(venue_template=
  "humanities_essay")`.
- **Simulated result:** Per `templates/typst/humanities_essay.typ`,
  the template is single-column, footnote-friendly, supports MLA
  / Chicago. PDF emits successfully. Hits `synthesis/paper.pdf`.
- **Was the result format clear?** Yes.
- **Did I know what to do next?** Yes — dashboard.
- **Friction:** none — this is the v1.9.3 fix (`AUDIT-v1.9.2-029`)
  at work. The compile step is reachable from `tool_plan_advance`.
- **Doc gap:** none.
- **Time-to-clarity:** ~20 s.

**Reached paper.pdf step:** YES.

### Turn 31 — synthesis_dashboard protocol load + dashboard_story_generate

- **What I wanted to do:** Build the dashboard in STORY mode (per
  scenario spec). The walk goes: load `synthesis_dashboard`
  protocol summary → confirm story mode → generate
  `synthesis/dashboard_story.md` → render.
- **Tool I called:** `sys_protocol_get(name="synthesis/synthesis_
  dashboard", format="summary")` then `tool_dashboard_story_
  generate`.
- **Simulated result:** synthesis_dashboard protocol loads; the
  step list per CHANGELOG references include
  `build_story_mode_source` (a step), and `tool_dashboard_story_
  generate` is a real tool per docs/AUDIT_v1.9.2/lens_04 hits.
  Story source is auto-built from `synthesis/abstract.md` + each
  step's `.summary.md` per ROADMAP.md line 367. I edit the
  generated `dashboard_story.md` to lead with the
  argument-then-apparatus structure (not the IMRAD-method-result
  frame the default story generator might assume).
- **Was the result format clear?** Partial — `tool_dashboard_
  story_generate`'s schema isn't in TOOLS.md spotlight examples,
  only mentioned by name in the audit appendix. I'd call
  `sys_tool_describe(tool_dashboard_story_generate)` to get the
  exact arguments.
- **Did I know what to do next?** Mostly — the protocol step list
  is the playbook, but the story-mode-specific tools (`tool_
  dashboard_story_generate`, `tool_dashboard_story_edit`, `tool_
  dashboard_story_quality_bar`) aren't enumerated in
  user-facing TOOLS.md.
- **Friction:** FRICTION/MEDIUM — the story-mode toolchain (3
  tools: generate, edit, quality_bar) is referenced internally
  but not surfaced in TOOLS.md. A fresh agent finds them via
  `sys_active_tools(synthesis_dashboard)` but not by reading the
  docs.
- **Doc gap:** TOOLS.md should add a *Dashboard story mode*
  sub-table listing `tool_dashboard_story_generate`,
  `tool_dashboard_story_edit`, `tool_dashboard_story_quality_bar`
  with their roles in the flow.
- **Time-to-clarity:** ~80 s.

### Turn 32 — tool_dashboard_create mode=story

- **What I wanted to do:** Render the dashboard.
- **Tool I called:** `tool_dashboard_create(mode="story",
  audience="academic", title="Henry James's late style:
  interiority + consciousness in vocabulary and syntax")`.
- **Simulated result:** Per TOOLS.md line 154, mode=story renders
  a linear top-to-bottom walk-through driven by `synthesis/
  dashboard_story.md`. Output: `synthesis/dashboard.html`,
  single-file offline, all figures embedded, all apparatus
  block-quotes inline with line anchors, citations linked.
- **Was the result format clear?** Yes — the envelope schema is
  exemplified at TOOLS.md line 521.
- **Did I know what to do next?** Yes — pre-submission checklist.
- **Friction:** none (the v1.9.4 mode-enum doc fix carried).
- **Doc gap:** none.
- **Time-to-clarity:** ~20 s.

**Reached dashboard.html step:** YES.

### Turn 33 — pre_submission_checklist

- **What I wanted to do:** Final GREEN / YELLOW / RED gate.
- **Tool I called:** `tool_route("is this ready to submit")` →
  `audit/pre_submission_checklist`.
- **Simulated result:** Likely YELLOW. The 2 overrides logged
  earlier (the literature-gate overrides for the descriptive +
  viz steps) get resurfaced; researcher confirms each was
  intentional. Edition caveat (Gutenberg vs NY Edition) gets
  surfaced as a limitations note. No fabricated citations, all
  resolved.
- **Was the result format clear?** Yes.
- **Did I know what to do next?** Yes — ship.
- **Friction:** none.
- **Doc gap:** none.
- **Time-to-clarity:** ~30 s.

---

## 6. Cross-checks + sign-off

### Turn 34 — version coherence audit

- **Tool I called:** `tool_audit_version_coherence`.
- **Simulated result:** PASS — no `.versions/` snapshots were made
  (no deliberate iteration), so every output traces to its v1
  script.
- **Friction:** none.

### Turn 35 — handoff

- **Tool I called:** `sys_session_handoff`.
- **Simulated result:** Handoff doc written with running tasks,
  hypotheses confirmed, dead-end lessons (the function-word LDA
  cluster + the *Roderick Hudson*-dominant cluster), resume
  prompt.
- **Friction:** none.

---

## 7. Top 5 friction points

| # | Severity | Title | Tool / Protocol | Suggested fix |
|---|---|---|---|---|
| 1 | MEDIUM | No `humanities/output/humanities_essay_structure` protocol; `synthesis_paper` is IMRAD-shaped by default | `synthesis/synthesis_paper.yaml` + humanities pack | Ship `humanities/output/humanities_essay_structure.yaml` paralleling `theory_math/output/theory_paper_structure.yaml`; route to it when `venue_template=humanities_essay` is set. Document the apparatus-first section order. |
| 2 | MEDIUM | `tool_audit_step_literature` is empirical-claim-centric; descriptive / prep / pure-viz steps have no claim to verdict, so the only escape is `override_literature_gate=true` (logged but recurring noise) | `tool_audit_step_literature` / `literature_per_step` | Add a `descriptive_step` / `prep_step` / `viz_only_step` step-intent that auto-waives the lit gate (paralleling how `step_intent: apparatus` waives the figure gate). CHANGELOG v1.9.3 references this as `AUDIT-v1.9.2-022` DEFERRED to v1.9.4 — still open. |
| 3 | MEDIUM | `inputs/raw_data/` is immutable but humanities corpus protocols expect `inputs/corpus/`; recovery path for already-misplaced corpora isn't documented | `tool_intake_autofill` / `START.md` | Add a "recovery" row to START.md's "extra inputs/ subfolders" table: how to symlink or how the protocols can be configured to accept a `raw_data/<slug>/` corpus root. |
| 4 | MEDIUM | Story-mode dashboard toolchain (`tool_dashboard_story_generate`, `tool_dashboard_story_edit`, `tool_dashboard_story_quality_bar`) not enumerated in user-facing TOOLS.md | `tool_dashboard_create` (story mode) | Add a *Dashboard story mode* sub-table to TOOLS.md listing the three tools + their flow position. The mode enum doc fix (carried from v1.9.4) helped, but the supporting tools are still hidden. |
| 5 | LOW | Router ambiguity between humanities pack protocols (`digital_humanities_workflow` vs `distant_reading` vs `close_reading`) — overlapping triggers | `tool_route` + humanities pack `router_entries.py` | Add a single ranked routing-resolution line to PROTOCOLS.md's humanities-pack section (DH umbrella ⇒ digital_humanities_workflow; corpus-only computational ⇒ distant_reading; passage-only interpretive ⇒ close_reading). |

## 8. Top 5 doc / guidance gaps

1. **No humanities-essay structure protocol.** Theory pack has
   `theory_paper_structure`; humanities pack does not. The
   `humanities_essay.typ` template exists but no protocol drives
   it. Without this, the AI defaults to IMRAD for humanities work.
2. **`tool_audit_step_literature` lacks worked examples for
   non-empirical steps.** A fresh agent does not know whether
   descriptive / prep / viz-only steps should override the lit
   gate or skip it via a step_intent flag. Recurring source of
   friction across every humanities pipeline.
3. **`inputs/corpus/` placement recovery is undocumented.**
   START.md tells the AI to advise the researcher BEFORE drops,
   but offers no recovery path for files already in `raw_data/`.
4. **Story-mode dashboard tools missing from TOOLS.md.** The mode
   enum is fixed; the supporting toolchain (story_generate,
   story_edit, story_quality_bar) isn't enumerated.
5. **No edition-caveat reference for digital humanities corpora.**
   Every humanities project using Gutenberg / HathiTrust /
   Wikisource / EEBO repeats the same caveats; a one-page
   reference in the humanities pack would cut prose noise.

## 9. Top 5 things that worked well (positive findings)

1. **The v1.9.3 humanities-completeness fix is solid.** The
   `_is_humanities_project` detector + `_collect_humanities_
   artefacts` lets `apparatus.md`, `close_readings/`,
   `transcriptions/`, `citation_chains.md` count as focal
   artifacts. The figure-mandatory wall is gone; the humanities
   flow runs.
2. **`close_reading.yaml` is a model protocol.** The
   `declare_step_contract` step is explicit, the
   `editorial_voice` rules are field-correct, the `quality_bar`
   (anchor_density, tradition_declared, counter_instance,
   edition_pinned, secondary_ledger) names exactly what
   reviewers in literary criticism actually check. Reading the
   YAML for the first time it was instantly obvious how to use
   it.
3. **`distant_reading.yaml` + `digital_humanities_workflow.yaml`
   nail the methodological doctrine.** The
   "computers don't read meaning" gate is enforced via the
   close_reading_sample step, the parameter_sweep quality bar
   blocks single-k LDA, negative_findings_documented is named —
   this is what differentiates a credible DH paper from a
   dressed-up topic model.
4. **`tool_paper_compile_typst` is reachable from
   `tool_plan_advance`** — the v1.9.3 fix (`AUDIT-v1.9.2-029`)
   that auto-appends the compile step to the synthesis_paper
   decomposition closed the previously-broken end-to-end PDF
   path. `humanities_essay.typ` exists and works.
5. **`tool_step_complete` is a great single-call gate.** Bundling
   completeness + literature + per-step quality audit into one
   call, with a clean BLOCKER + WARNING + next_steps envelope
   schema, makes the per-step loop fast and surfaces the override
   path explicitly.

## 10. Final rating: 7/10

**Rationale.** The humanities pipeline works end-to-end from
empty project to `paper.pdf` + `dashboard.html` in 35 turns. The
v1.9.3 humanities-completeness fix and the
`tool_paper_compile_typst` auto-routing fix together close the
two prior blockers I'd worry about on this scenario. The
protocols themselves (`close_reading`, `distant_reading`,
`digital_humanities_workflow`) are unusually high-quality —
they read as if written by someone who has actually published
in the field, not a generic AI-doctrine wrapper. The
`humanities_essay` Typst template exists and renders.

The two-point deduction comes from (1) the missing
`humanities_essay_structure` protocol, which forces the
synthesis paper into an IMRAD frame the scenario explicitly
warns against, and (2) the recurring literature-gate friction
on non-empirical steps that hasn't been resolved in v1.9.4
despite being flagged in v1.9.2 as `AUDIT-v1.9.2-022`. Add a
half-point for the four MEDIUM frictions clustering around the
humanities surface (essay-structure, lit-gate, corpus-location,
story-mode toolchain) — none individually catastrophic, but
together they signal the humanities pack is still less polished
than the empirical pipeline.

If the two MEDIUM items above were fixed, this would be a
solid 8.5 / 10 for humanities. The protocols are field-correct;
the wrapping needs another pass.

## 11. Onboarding-friction count (first 5 turns)

**3 frictions in turns 1-5:**
- Turn 2: LOW — router ambiguity (DH umbrella vs distant_reading
  vs close_reading)
- Turn 3: LOW — wizard default venue_template is wrong for
  humanities, AI has to flip it
- Turn 4: MEDIUM — corpus in raw_data/ vs immutability vs
  protocols expecting inputs/corpus/

## 12. End-state checks

- **Reached `paper.pdf`?** YES (turn 30, via
  `tool_paper_compile_typst` with `humanities_essay.typ`).
- **Reached `dashboard.html`?** YES (turn 32, via
  `tool_dashboard_create(mode="story")` after
  `tool_dashboard_story_generate`).
