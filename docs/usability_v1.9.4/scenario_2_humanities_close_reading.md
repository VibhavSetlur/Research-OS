# Scenario 2 — Humanities close-reading textual analysis

**Hypothesis:** "Henry James's late-period vocabulary shifts toward interiority and consciousness."

**Corpus:** Project Gutenberg subset of Henry James's novels — early: *Roderick Hudson*, *The American*; late: *The Ambassadors*, *The Wings of the Dove*. Plain text, one file per chapter.

**Pack:** humanities (auto-detected from corpus + metadata).

**Expected outputs:** `synthesis/paper.pdf` (humanities-flavoured IMRAD with block quotes + page anchors), `synthesis/dashboard.html` (story mode, hypothesis-led).

**Fresh-agent rule:** I am pretending to be an MCP-driven AI on cold start with no prior memory of Research-OS. I have only read `docs/*.md`, `templates/*`, and the user-facing protocol YAMLs under `src/research_os/protocols/` and `src/research_os_humanities/protocols/`. I have NOT read any `.py` under `src/research_os/`. Tool calls are simulated; their return shapes are inferred from `TOOLS.md` + the protocol's `expected_outputs`.

---

## 1. Project setup (turns 1-5)

### Turn 1 — cold-start session boot

- **What I wanted to do:** Open the fresh project folder in my IDE; the IDE auto-launched the `research-os` MCP server. I need to orient.
- **Tool called:** `sys_boot`
- **Simulated result:** Returns `{state: {has_os_state: false}, ...}`. Empty project — `inputs/`, `workspace/`, `synthesis/`, `.os_state/` do not exist.
- **Format clear?** Yes — `AI_GUIDE.md` and `templates/CLAUDE.md` both told me `sys_boot` is mandatory call #1 of every session.
- **Did I know what to do next?** Yes — when `has_os_state` is false, `AI_GUIDE.md` says tell the researcher to run `research-os init`. But the researcher's intent is already "do this James project" — so I tell them to scaffold first.
- **Friction:** none
- **Doc gap:** none
- **Time-to-clarity:** 5 s

### Turn 2 — scaffold

- **What I wanted to do:** Have the researcher scaffold the project.
- **Tool called:** (shell — not MCP) `mkdir james-late-style && cd james-late-style && research-os init`
- **Simulated result:** 7-step wizard runs. The wizard asks: project name, optional domain, optional question, IDEs to wire, optional smoke check. I prefill domain=`humanities` and question=`Does James's late-period vocabulary shift toward interiority and consciousness?`. Wizard drops `AGENTS.md`, `inputs/{raw_data,literature,context}/`, `workspace/`, `synthesis/`, `docs/`, `.os_state/`, `inputs/researcher_config.yaml`.
- **Format clear?** Yes — `START.md` lines 39-60 walk through this.
- **Did I know what to do next?** Yes — `START.md` says "drop your files".
- **Friction:** FRICTION/LOW — `inputs/` only has `raw_data/`, `literature/`, `context/` as canonical subfolders. The humanities `distant_reading` protocol expects `inputs/corpus/` and `inputs/textual/passages/` (see `distant_reading.yaml` step `define_corpus_and_unit`, output path `inputs/corpus/corpus_definition.md`). The wizard does not create these humanities-specific subfolders, and `START.md` doesn't mention they're protocol-created on demand. A first-time user would wonder whether to drop the texts under `inputs/raw_data/` or invent `inputs/corpus/`.
- **Doc gap:** `docs/SETUP.md` and `START.md` do not document that some protocols expect subfolders outside the canonical three (`raw_data`/`literature`/`context`). Recommend: add a one-liner in `START.md` "Some packs (humanities, qualitative) expect additional subfolders — the protocol will tell you when to create them" OR have the humanities pack detector pre-create `inputs/corpus/` + `inputs/textual/`.
- **Time-to-clarity:** 90 s (I had to grep `distant_reading.yaml` to find the expected `inputs/corpus/` path).

### Turn 3 — drop texts + configure

- **What I wanted to do:** Stage the corpus (4 novels, ~80 chapters total as plain-text from Project Gutenberg) and edit `researcher_config.yaml`.
- **Tool called:** (shell) `mv ~/jameseca/* inputs/raw_data/james/`, then edit `inputs/researcher_config.yaml` to set `research_goal.output_types: [paper, dashboard]`, `writing_preferences.citation_style: mla` ... wait.
- **Simulated result:** `researcher_config.yaml` only lists `apa | vancouver | acm | ieee | nature` as supported `citation_style` values. **MLA is not in the menu** — and MLA is the dominant citation style in literary studies. I either pick `apa` (off-genre for a literature paper) or leave it set to a value the venue won't accept.
- **Format clear?** Yes — template is well commented.
- **Did I know what to do next?** Partially — I default to `apa` and `venue_template: generic_two_column`, but a humanities paper would actually want `generic_thesis` or a Chicago-style template, and the venue list is sciences-only (nature / science / nejm / cell / ieee_conf / neurips / acl / plos / generic_two_column / generic_thesis).
- **Friction:** FRICTION/HIGH — humanities project, no humanities citation style (MLA / Chicago notes-bibliography / Chicago author-date are absent), no humanities-friendly Typst venue template. The pack ships protocols but `writing_preferences.venue_template` and `citation_style` were never extended to cover what the pack's deliverables would need.
- **Doc gap:** `researcher_config.yaml` `citation_style` enum is hardcoded to STEM styles; humanities pack does not document a workaround. `docs/VENUE_TEMPLATES.md` (skimmed earlier) lists 9 Typst templates, none labelled "humanities" / "literary" / "thesis-humanities" / "Chicago".
- **Suggested fix:** add `mla` + `chicago_author_date` + `chicago_notes_bib` to `citation_style`; ship a `humanities_essay.typ` template (single column, footnote-heavy, generous margins, block-quote macro). Surface the missing menu items as a humanities-pack install task.
- **Time-to-clarity:** 180 s

### Turn 4 — intake

- **What I wanted to do:** Have RO read `inputs/raw_data/james/` + `inputs/context/notes.md` + (eventually) any literature PDFs and write `inputs/intake.md` + `docs/research_overview.md` + register the hypothesis.
- **Tool called:** `tool_intake_autofill` (per TOOLS.md description).
- **Simulated result:** Reads `inputs/`, infers domain = humanities (the humanities detector keys on word counts > certain thresholds, .txt corpus files, etc. — inferred from the existence of `research_os_humanities/detector.py`, which I cannot read). Writes `inputs/intake.md` with the 4 novels + chapter counts, `docs/research_overview.md` with my hypothesis, and registers the hypothesis in `.os_state/state.json`.
- **Format clear?** Mostly — `TOOLS.md` describes the outputs.
- **Did I know what to do next?** Yes — `tool_research_overview` / `mem_hypothesis_add` if the autofill didn't catch the hypothesis verbatim.
- **Friction:** FRICTION/MEDIUM — `tool_intake_autofill`'s description does not say what it does for plain-text corpora vs structured data. For tabular data its job is clear (profile columns, guess units). For 4 novels of prose it's not obvious whether it reads the texts, counts chapters, builds a manifest, or just notes "4 .txt files present, language=en". A user dropping a corpus expects the intake to produce `inputs/corpus/corpus_manifest.csv` (per `digital_humanities_workflow.yaml` prerequisites) — but nothing in `TOOLS.md` promises that.
- **Doc gap:** no example of intake-on-text-corpus in `docs/`. Add a worked example to `RESEARCHER_GUIDE.md`.
- **Time-to-clarity:** 120 s

### Turn 5 — register hypothesis explicitly

- **What I wanted to do:** Make sure the hypothesis is logged structurally so the synthesis step can iterate per-hypothesis.
- **Tool called:** `mem_hypothesis_add(name="late_period_interiority", statement="Henry James's late novels show a higher rate of interiority / consciousness vocabulary than his early novels.", status="active")`
- **Simulated result:** Appends to `.os_state/state.json` `active_hypotheses` + `workspace/analysis.md`.
- **Format clear?** Yes.
- **Did I know what to do next?** Yes — route the hypothesis to a protocol via `tool_route`.
- **Friction:** none
- **Doc gap:** none
- **Time-to-clarity:** 10 s

**Onboarding friction in first 5 turns:** 3 (1 HIGH, 1 MEDIUM, 1 LOW).

---

## 2. Hypothesis + planning (turns 6-10)

### Turn 6 — route the hypothesis

- **What I wanted to do:** Have the router pick the right humanities protocol(s).
- **Tool called:** `tool_route(prompt="Test the hypothesis that Henry James's late novels show a vocabulary shift toward interiority and consciousness, using close reading + corpus stats on the early vs late texts.")`
- **Simulated result:** Based on `router_entries.py` (which I read because the router index in `_router_index.yaml` is silent on humanities — the pack contributes its own entries at import time):
  - intent_class=`methodology`, sub_intent=`method_pick`
  - primary_protocol=`humanities/textual/distant_reading` (matched "corpus analysis", "text mining"). 
  - decomposition likely also surfaces `humanities/method/digital_humanities_workflow` (the hybrid distant+close protocol — explicitly designed for exactly this question).
  - complexity=`high` (multi-step pipeline that spans 6+ protocol steps).
  - active_plan persisted to `.os_state/active_plan.json`.
- **Format clear?** Yes.
- **Did I know what to do next?** Yes — `tool_plan_turn`.
- **Friction:** FRICTION/MEDIUM — `tool_route`'s decomposition vs primary_protocol disambiguation isn't obvious for a fresh agent. Both `close_reading`, `distant_reading`, and `digital_humanities_workflow` triggers overlap heavily ("corpus analysis", "distant reading" → distant_reading; "I have a corpus of N texts" → digital_humanities_workflow). The hierarchy is L1 → L2 → L3 but two L3 protocols compete here. Without reading the router source (forbidden), I can't tell whether the router picks one and ignores the other, or stacks them.
- **Doc gap:** `AI_GUIDE.md` § "Protocol categories" mentions 114 protocols but doesn't show how the router resolves competing L3 matches inside the same sub_intent.
- **Time-to-clarity:** 90 s

### Turn 7 — plan turn

- **What I wanted to do:** Get the batch of steps for this turn.
- **Tool called:** `tool_plan_turn`
- **Simulated result:** Returns `this_turn: [{protocol: digital_humanities_workflow, step: corpus_audit}, ...]` sized to `model_profile=medium` → 3 steps. `chat_split_recommended: false` (still early).
- **Format clear?** Yes.
- **Did I know what to do next?** Yes.
- **Friction:** none
- **Doc gap:** none
- **Time-to-clarity:** 10 s

### Turn 8 — load the primary protocol summary

- **What I wanted to do:** Get the step headings + quality bar for `digital_humanities_workflow` without burning 1.8k tokens on the full YAML.
- **Tool called:** `sys_protocol_get(name="humanities/method/digital_humanities_workflow", format="summary")`
- **Simulated result:** ~300 tokens of step ids + names + quality_bar names.
- **Format clear?** Yes — `TOOLS.md` documents the format options.
- **Did I know what to do next?** Yes.
- **Friction:** none
- **Doc gap:** none
- **Time-to-clarity:** 15 s

### Turn 9 — check active project + active tools

- **What I wanted to do:** Confirm the humanities pack is active and see which tools the protocol expects.
- **Tool called:** `sys_active_tools(protocol="humanities/method/digital_humanities_workflow")`
- **Simulated result:** Returns shortlist incl. `tool_python_exec`, `tool_search`, `tool_humanities_archive_lookup`, `tool_humanities_citation_chain`, `mem_log`, `tool_step_pipeline_define`, etc.
- **Format clear?** Yes.
- **Did I know what to do next?** Yes — `digital_humanities_workflow` step 1 says "audit the corpus before any computation".
- **Friction:** FRICTION/LOW — the humanities pack only ships 2 dedicated tools (`tool_humanities_archive_lookup`, `tool_humanities_citation_chain`) but the protocols reference `tool_python_exec` for all the actual NLP work. That's the **right design** — protocols are scaffolds, not scripts — but a fresh agent expects more dedicated tooling (e.g. a `tool_humanities_topic_model` wrapper, a `tool_humanities_stylometry`). The protocol does say it explicitly ("distant-reading techniques are not yet wired as first-class tools — run them by writing a short script") which is good, but it could be louder up front.
- **Doc gap:** the explicit "v1.9.3 has no first-class topic-model tool, write a script" note is in `digital_humanities_workflow.yaml` step `distant_pass` but NOT in `TOOLS.md` § Humanities pack. A user reading `TOOLS.md` first will think the pack is anemic.
- **Time-to-clarity:** 45 s

### Turn 10 — define the analysis plan

- **What I wanted to do:** Per the scaffold-not-script doctrine, I draft the analysis steps. For this hypothesis on this corpus they are:
  1. Corpus audit (date, chapter count, word count, OCR? — Project Gutenberg is clean).
  2. Define "interiority vocabulary" — build a seed lexicon from the literature (Banfield, Cohn *Transparent Minds*, Palmer *Fictional Minds*) using `tool_search` + `mem_log`.
  3. Per-novel word-frequency analysis on the seed lexicon (early vs late).
  4. Per-novel topic model (LDA, k=12-20 swept) to inspect what other clusters emerge.
  5. Close-reading sample: 3 passages per novel from high-loading chapters (the gate).
  6. Comparative close reading: same scene type (a character's reflective moment) early vs late.
  7. Triangulation against Cohn / Banfield / Stowell / Tintner.
  8. Negative-findings audit + methods write-up.
- **Tool called:** `tool_step_pipeline_define(step_id="01_corpus_audit", nodes=[ingest, profile, manifest, report])` — and similar pipeline defs for the heavier steps. I also call `mem_decision_log` to record the 8-step plan.
- **Simulated result:** `pipeline.yaml` files written under `workspace/01_corpus_audit/`, `workspace/02_lexicon/`, etc.
- **Format clear?** Yes.
- **Did I know what to do next?** Yes — execute step 1.
- **Friction:** FRICTION/LOW — `step_pipeline_define` is meant for multi-script steps (the per-step audit blocks >2 scripts without one). For a single-script step like "lexicon = read seed-paper PDFs and extract a word list", forcing a pipeline.yaml feels heavy. The protocol doesn't say whether close-reading steps (mostly markdown notes, no code) need a pipeline at all.
- **Doc gap:** `step_pipeline_define` is described as "declare a multi-node `pipeline.yaml`" but the threshold "use it when you have >2 scripts" lives only in `tool_audit_step_completeness`'s blocker message. Humanities steps are often 100% prose; doc should call out the prose-only-step exemption.
- **Time-to-clarity:** 60 s

---

## 3. Per-step execution (turns 11-22)

For each analysis step I run: `tool_step_pipeline_run` → `tool_audit_step_completeness` → `tool_audit_step_literature` → `tool_step_complete`. I will compress turns 11-22 by step (each step = ~1-2 turns in the real session, but I log one turn per step).

### Turn 11 — Step 01: corpus audit

- **What I wanted to do:** Build `workspace/dh/corpus_audit.md` per `digital_humanities_workflow` step `corpus_audit`.
- **Tool called:** `tool_python_exec` to run a 30-line script: walks `inputs/raw_data/james/`, counts words per novel, builds `inputs/corpus/corpus_manifest.csv` (title, year, words, chapters, period: early|late), writes `workspace/01_corpus_audit/corpus_audit.md` with the bias register ("4 novels — Henry James only, anglophone, late-19th-c. canon; no comparison authors; chapter sampling NOT random"). `mem_log` the audit.
- **Simulated result:** corpus_manifest.csv has 4 rows; corpus_audit.md is ~600 words.
- **Format clear?** Yes.
- **Did I know what to do next?** Yes — focal figure (the audit step's quality bar wants a figure).
- **Friction:** FRICTION/MEDIUM — `tool_audit_step_completeness` requires a focal figure per active step. For a "corpus audit" step there's no obvious figure — maybe a bar chart of word counts per novel? Forcing a figure on a prose-only methods step is the kind of false-positive blocker `quality_gate_policy: enforce` will produce here.
- **Doc gap:** the "focal figure required per step" rule doesn't carve out humanities/qualitative steps. `AI_GUIDE.md` says protocols are scaffolds, but the per-step completeness gate is prescriptive.
- **Time-to-clarity:** 120 s — I end up generating a single bar chart `01_corpus_words_per_novel.png` to satisfy the gate.

### Turn 12 — Step 01 audit + complete

- **What I wanted to do:** Pass the step gate.
- **Tool called:** `tool_audit_step_completeness(step="01_corpus_audit")` → `tool_audit_step_literature(step="01_corpus_audit")` → `tool_step_complete`.
- **Simulated result:** Completeness passes (focal figure exists). Literature gate is the interesting one — it BLOCKS unless `workspace/01_corpus_audit/literature/findings_vs_literature.md` exists with verdicts. For a corpus-audit step there's nothing to compare to literature yet — the "finding" is "the corpus is 4 novels, all by James, biased toward late canon". The literature gate forces me to invent a `findings_vs_literature.md` with a stub verdict (`DEFERRED — bias profile, no scholarship to compare`) just to clear the gate.
- **Format clear?** Yes — `tool_audit_step_literature`'s description is clear.
- **Did I know what to do next?** Yes — but only by reading the YAML; the doc surface gave the rule but not how to satisfy it on a not-yet-comparative step.
- **Friction:** FRICTION/MEDIUM — the literature gate is per-step (good for results), but applying it to a corpus-audit step is premature. The DEFERRED escape hatch works but is awkward.
- **Doc gap:** `tool_audit_step_literature` should document when DEFERRED is the intended answer (early pipeline steps with no comparative claim).
- **Time-to-clarity:** 90 s

### Turn 13 — Step 02: build interiority lexicon

- **What I wanted to do:** Build a seed lexicon by reading Cohn (1978), Banfield (1982), Palmer (2004), Stowell (1980). I need to pull at least the abstracts via `tool_search` and ideally page-anchored quotes.
- **Tool called:** `tool_search(query="Henry James late style interiority free indirect discourse vocabulary", databases=["semantic_scholar", "crossref"])`, then `tool_research_assistant` for the deeper read, `mem_log` for each lexical commitment ("words for inward attention: consciousness, awareness, sense, perceive, feel, impression, conscious, aware, perceive...").
- **Simulated result:** ~15 papers surfaced. I select 4-5. Build `workspace/02_lexicon/seed_lexicon.md` with 80 words grouped into 4 semantic fields (perception, cognition, affect, qualia). Verify the lexicon does NOT include high-frequency function words.
- **Format clear?** Yes — `tool_search` is well documented.
- **Did I know what to do next?** Yes.
- **Friction:** FRICTION/LOW — `tool_search` writes structured search-result records but doesn't fetch PDFs automatically. For literary scholarship a lot of the canonical books (Cohn, Banfield) are in *Princeton/Cornell UP* monographs, NOT in Semantic Scholar's full-text index. I had to fall back to whatever's in `inputs/literature/`.
- **Doc gap:** `tool_search` doesn't document humanities-specific database coverage (MLA International Bibliography, JSTOR, Project MUSE are likely not covered — humanities pack should at minimum say so explicitly).
- **Time-to-clarity:** 30 s

### Turn 14 — Step 02 audit + complete

- Same pattern as turn 12. Completeness passes (lexicon doc + a figure showing lexicon size per semantic field). Literature gate: I now have real comparative claims, so I write `findings_vs_literature.md`: "Seed lexicon AGREES with Cohn (1978) Transparent Minds pp. 99-140 (free-indirect discourse vocabulary)", "EXTENDS Palmer's 'aspectuality' frame", etc.
- **Friction:** none here.

### Turn 15 — Step 03: per-novel frequency analysis

- **What I wanted to do:** Compute per-novel word-frequency for each lexicon item; aggregate to per-period; bootstrap CIs.
- **Tool called:** `tool_python_exec` (script: tokenise, lowercase, lemmatise (spaCy), count lexicon hits per 10k tokens, bootstrap 1000 resamples per chapter).
- **Simulated result:** `workspace/03_freq/freq_results.csv`, `workspace/03_freq/freq_by_period.svg` (boxplots with CIs), `.prov.json` sidecars.
- **Format clear?** Yes.
- **Did I know what to do next?** Yes — but this is the place where the scenario instruction "MUST NOT be shoehorned into statistical framing" gets pressure-tested. The boxplot + bootstrap CI is essentially the only thing the gate-set will accept ("every quantitative claim needs a CI"). For literary criticism the more honest finding is "in *Ambassadors* Strether's reflective passages dilate into 200-word sentences full of *aware / sense / feel*; in *The American* Newman's similar moments are 30-word sentences without those words". That's a close-reading claim, not a frequency claim — and Research-OS has no audit gate for it.
- **Friction:** FRICTION/MEDIUM — the audit toolkit (`tool_audit_assumptions`, `tool_audit_power`, `tool_audit_evalue`) is statistics-flavoured; there's no `tool_audit_close_reading_apparatus` that checks "every interpretive claim is anchored to a line/page". The `close_reading.yaml` quality bar lists `anchor_density`, `counter_instance`, `tradition_declared`, `edition_pinned`, `secondary_ledger` — these are the right checks, but no MCP tool enforces them. The protocol's quality_bar is text in a YAML; without a tool, the AI is on its honour.
- **Doc gap:** there should be a `tool_humanities_apparatus_audit` or similar. Otherwise the humanities pack's protocols are recommendations the AI may quietly skip when stats gates are louder.
- **Time-to-clarity:** 60 s

### Turn 16 — Step 03 audit + complete

- Same loop. Literature gate writes verdicts AGREES with Hoover (2007) on Burrows-style word-frequency drift, EXTENDS Underwood (2019) ch. 4 on novelistic perspective.

### Turn 17 — Step 04: topic model (LDA sweep)

- **What I wanted to do:** Per `distant_reading` step `run_computational_pass` — sweep k ∈ {8,12,16,20}; capture coherence + top-N words + top-N chapters per topic. Set seed=42.
- **Tool called:** `tool_python_exec` (gensim LDA, multiple k, deterministic seed).
- **Simulated result:** `workspace/04_topics/models/lda_k{8,12,16,20}/`, `workspace/04_topics/patterns/lda_inspection.md` with top-words/top-chapters per topic per k, unlabelled.
- **Format clear?** Yes.
- **Did I know what to do next?** Yes — the gate ("close-read top 5 docs per topic").
- **Friction:** none beyond the prior point.
- **Time-to-clarity:** 30 s.

### Turn 18 — Step 05: close-reading gate (this is the load-bearing humanities step)

- **What I wanted to do:** For each topic I plan to cite (probably 3-4 from k=12 model), close-read the top 5 chapters per `distant_reading` step `close_reading_gate`. Also pick 4 passages (one per novel) to close-read line-by-line per `close_reading.yaml`.
- **Tool called:** I write `inputs/textual/passages/ambassadors_book5_strether.md` with the block quote + edition pin (Penguin Classics, ed. Adrian Poole, 2008, pp. 132-136), and run `close_reading.yaml`'s 6 steps for each of the 4 passages. `mem_log` the tradition declaration ("New Critical / narratological / Cohn-Banfield"). `tool_humanities_citation_chain` to verify the citation chain back to Cohn's discussion of the same passage.
- **Simulated result:** 4 × `workspace/close_readings/<slug>_apparatus.md` files, each with the block quote at top, numbered claims with line anchors, counter-instances, secondary-criticism ledger.
- **Format clear?** Yes — `close_reading.yaml` is explicit and excellent.
- **Did I know what to do next?** Yes.
- **Friction:** FRICTION/LOW — `close_reading.yaml` is a thoughtful, well-grounded protocol. Two annoyances: (a) passages live under `inputs/textual/passages/` which is created on demand (see Turn 2 friction); (b) the protocol's `next_protocol` points at `citation_chains`, but for this scenario I want to loop back to the apparatus build, not chain another genealogy.
- **Doc gap:** none beyond the inputs/ subfolder gap already logged.
- **Time-to-clarity:** 30 s.

### Turn 19 — Step 05 audit + complete

- Completeness gate accepts the apparatus.md files as the focal "figure" (the block-quoted passage is the artefact). Literature gate verdicts: AGREES with Cohn (1978) pp. 121-129 on the *Ambassadors* dilations; EXTENDS Hale (1998) on FID consolidation in James's late prose.
- **Friction:** FRICTION/LOW — accepting a markdown apparatus as a focal "figure" relies on the audit being lenient. If the gate strictly requires a `.png` / `.svg`, I'd have to also produce a "figure" that's really just a typeset block quote, which is silly.
- **Doc gap:** `tool_audit_step_completeness` should document whether markdown apparatuses count as focal artefacts.

### Turn 20 — Step 06: comparative close reading (same scene type, early vs late)

- **What I wanted to do:** Pair scenes: Roderick Hudson's reflective moment in ch. IV vs Strether's in *Ambassadors* Book 5; Newman in *The American* vs Densher in *Wings of the Dove*. Show the dilation + lexical shift in matched scenes.
- **Tool called:** same close_reading apparatus pattern, plus `tool_humanities_citation_chain` to verify both passages have been close-read in prior scholarship.
- **Simulated result:** 2 × `workspace/comparative/<pair>_apparatus.md`. Counter-pattern (per protocol) documented: Hyacinth Robinson's reflective moments in *Princess Casamassima* (1886, transitional) are AS interior as the late novels, which complicates the early-vs-late dichotomy. Good — this is the kind of counter-finding the protocol explicitly demands.
- **Format clear?** Yes.
- **Did I know what to do next?** Yes.
- **Friction:** none
- **Time-to-clarity:** 20 s

### Turn 21 — Step 07: triangulate

- Per `distant_reading` step `triangulate_against_external_knowledge`. Write `workspace/distant/triangulation.md`: my finding (lexical + close-reading + counter-pattern with Princess) AGREES with the long Cohn / Hale / Stowell consensus, EXTENDS Underwood's quantitative-corroborates-qualitative methodological argument. Cite Tintner on James's revisions to the New York Edition as a confounder (he re-wrote early novels in late style).
- **Friction:** FRICTION/MEDIUM — the New York Edition (1907-1909) is a methodological CONFOUNDER for this whole study: James revised *Roderick Hudson* in 1907 toward his late style. My corpus must specify which edition of each text. If I used the Gutenberg files without checking, the early novels might actually be the NYE revisions, and my finding collapses. `tool_humanities_archive_lookup` could check this but the protocol doesn't FORCE me to.
- **Doc gap:** `distant_reading.yaml` step `define_corpus_and_unit` should call out "for authors with revised editions, pin which edition is in the corpus".
- **Time-to-clarity:** 60 s

### Turn 22 — Step 08: methods + negative findings write-up

- Per `distant_reading` step `write_methods_section_with_negative_findings`. Write `synthesis/distant/methods_section.md`: corpus + bias + preprocessing + LDA sweep + close-reading sampling frame + the *Princess Casamassima* counter-pattern as a negative finding + the NYE-revision confounder.
- **Friction:** none.

---

## 4. Per-step literature gate (interleaved — already shown above)

Every step ran `tool_audit_step_literature`. Notable patterns:
- Steps 01 and 04 (corpus audit, raw LDA output) wrote DEFERRED verdicts. The gate accepts DEFERRED only if there are PDFs in `inputs/literature/`; if not, it BLOCKS. For corpus-audit steps this is the wrong default — the audit has no comparative claim to make.
- Steps 02, 03, 05, 06, 07 had real AGREES / EXTENDS / DISAGREES verdicts and produced healthy `findings_vs_literature.md` files.

---

## 5. Audit + synthesis (turns 23-30)

### Turn 23 — `tool_audit_quality_full`

- **What I wanted to do:** Run the master quality gate before synthesis.
- **Tool called:** `tool_audit_quality_full`
- **Simulated result:** Bundles `tool_audit_step_completeness` + `tool_audit_code_quality` + `tool_audit_prose` + `tool_audit_claims` + `tool_preregister_diff` + `tool_ground`. Returns blockers + warnings. Likely blockers:
  - `tool_audit_prose` — humanities writing uses hedging routinely ("might", "perhaps", "the passage suggests"), which the prose-audit flags as vague quantifiers. False positives.
  - `tool_audit_claims` — every number must trace to an artefact. My frequency claims do; my close-reading claims have page anchors. Should pass.
- **Format clear?** Yes — `TOOLS.md` describes the bundle.
- **Did I know what to do next?** Yes.
- **Friction:** FRICTION/MEDIUM — `tool_audit_prose` is calibrated for scientific reporting voice. A literary-critical paper genuinely IS hedged and exploratory; the audit's vague-quantifier flagger will produce a lot of noise the user has to ignore.
- **Doc gap:** `tool_audit_prose` doesn't document a humanities/qualitative profile. Should auto-relax based on `pack=humanities`.
- **Time-to-clarity:** 60 s.

### Turn 24 — outline the paper

- **What I wanted to do:** Per `synthesis_paper`'s multi-turn enforcement, turn-1 is "outline".
- **Tool called:** `tool_synthesize_plan(output_type="paper")` → returns proposed section order. I then load `synthesis/manuscript_outline` protocol (it's pointed at by synthesis_paper) and write `workspace/.outline/paper_outline.md`.
- **Simulated result:** Outline with: Title (workshop deferred), Abstract, Introduction (problem + James scholarship gap + my contribution), Methods (corpus + lexicon + LDA + close-reading sampling), Results (per hypothesis, with block quotes), Discussion (situate within Cohn/Banfield/Underwood), Limitations (NYE revisions, 4-novel corpus), Conclusion, References.
- **Format clear?** Yes.
- **Did I know what to do next?** Yes — draft methods next turn.
- **Friction:** none
- **Time-to-clarity:** 30 s

### Turn 25 — draft methods

- **Tool called:** `tool_synthesize(output_type="paper", section="methods")` invokes `writing/writing_methods`.
- **Simulated result:** `synthesis/paper.md` methods section written. Section has: corpus + bias (with the NYE confounder), lexicon construction (cited from Cohn/Banfield/Palmer), LDA hyperparameters + seed, close-reading sampling frame, audit gates, software versions.
- **Friction:** none.

### Turn 26 — draft results

- **Tool called:** `tool_synthesize(output_type="paper", section="results")` → `writing/writing_results`.
- **Simulated result:** Results section. Each hypothesis sub-section quotes a block-quote passage with page number, then names the close-reading verdict, then surfaces the supporting frequency stat. **This is where the scenario instruction "sections quote passages + cite page numbers" gets validated.** The `writing_results` protocol does not (as I read it) explicitly call out "block-quote evidence first, stat second" for humanities; it just says "report numbers, defer interpretation". A humanities-flavoured `writing_results_humanities` would make this enforced.
- **Friction:** FRICTION/MEDIUM — generic `writing_results` works but I had to interpret it humanities-style without protocol guidance. A small `writing_results_humanities` variant would lock in block-quote-first reporting.
- **Doc gap:** humanities pack does not ship a `writing_results_humanities` (or `writing_humanities_apparatus`).
- **Time-to-clarity:** 60 s

### Turn 27 — draft discussion + limitations + intro + abstract (separate turns in real life)

- 4 separate turns per `synthesis_paper`'s multi-turn enforcement. Each calls the relevant writing protocol. Limitations section is rich here (NYE confounder, 4-novel corpus, single-author study, no comparison author, lexicon was curated not learned).
- **Friction:** none beyond Turn 26.

### Turn 28 — assemble + compile PDF

- **What I wanted to do:** Produce `synthesis/paper.pdf`.
- **Tool called:** `tool_synthesize(output_type="paper", phase="final_assembly")` → `tool_paper_compile_typst(venue_template="generic_thesis")`.
- **Simulated result:** `tool_citations_verify` runs as final-assembly gate; verifies every reference against Crossref/Semantic Scholar. Cohn (1978) *Transparent Minds* is a Princeton UP monograph — may or may not have a Crossref DOI. If verification fails, the assembly blocks. Either I drop the un-verifiable cite (bad — Cohn is the foundational citation) or I find a Crossref-indexed review/companion to use as proxy.
- **Friction:** FRICTION/HIGH — Crossref + Semantic Scholar coverage of humanities monographs (literary criticism, philosophy, theology) is sparse compared to STEM journals. A strict citation-verify gate will block paper assembly for foundational humanities citations that genuinely exist but aren't in the verifier's databases. The override path (`override_completeness_gate=true`) exists but `tool_citations_verify` is a HARD gate — `synthesis_paper`'s prerequisites say "any citation still in pending verification state blocks the assembly". For a humanities project this could be the whole reference list.
- **Doc gap:** `tool_citations_verify` doesn't document humanities-monograph fallback (ISBN lookup via WorldCat / OpenLibrary / LOC).
- **Suggested fix:** add WorldCat + LOC + OpenLibrary as fallback verifiers for ISBN'd books; or surface a per-pack relaxed gate.
- **Time-to-clarity:** 240 s

### Turn 29 — dashboard (story mode)

- **What I wanted to do:** Build `synthesis/dashboard.html` as the paper-as-interactive-walkthrough per `synthesis_dashboard.yaml` audience=academic. Per the scenario, "story mode" = the v2 dashboard with `tool_dashboard_story_generate`.
- **Tool called:** `tool_dashboard_story_generate` → produces `synthesis/dashboard_story.md`. Then `tool_dashboard_create(audience="academic", story=true)`.
- **Simulated result:** Single-file `synthesis/dashboard.html`. Sections per hypothesis, each with the block-quote (rendered inline), the close-reading apparatus collapsed under a "Show apparatus" toggle, the frequency boxplot hoverable, the *Princess Casamassima* counter-pattern callout.
- **Format clear?** Yes — `synthesis_dashboard.yaml` is very explicit about audience profiles.
- **Did I know what to do next?** Yes — pre-submission checklist.
- **Friction:** FRICTION/LOW — `tool_dashboard_story_quality_bar` requires "≥1 DISAGREES / EXTENDS callout". I have an EXTENDS verdict (extending Underwood) — passes. But the "5-20 min read" constraint for story mode is calibrated for a tight scientific narrative; a humanities walk-through with block quotes and apparatuses naturally runs 25-40 min.
- **Doc gap:** `tool_dashboard_story_quality_bar` reading-time bounds are hardcoded.
- **Time-to-clarity:** 30 s.

### Turn 30 — pre-submission checklist

- **Tool called:** `audit/pre_submission_checklist` protocol via `tool_route("is this ready to submit?")`.
- **Simulated result:** Final GREEN/YELLOW/RED gate. Resurfaces every gate override from `workspace/logs/override_log.md`.
- **Friction:** none.

---

## 6. Cross-checks + sign-off

- Hypothesis verdict registered via `mem_hypothesis_update(name="late_period_interiority", status="supported_with_caveats", evidence_refs=[...])`.
- `tool_audit_version_coherence` confirms no scripts drifted past their figures.
- `sys_checkpoint_create` snapshots the project.
- `sys_session_handoff` writes the handoff doc.

---

## 7. Top 5 friction points

1. **HIGH — Citation verification gate is STEM-biased.** `tool_citations_verify` runs against Crossref / Semantic Scholar / PubMed / arXiv. Humanities scholarship lives heavily in monographs (Princeton UP, Cornell UP, Oxford UP) that may not have Crossref DOIs. The HARD gate inside `tool_paper_compile_typst` blocks assembly for foundational citations that genuinely exist. **Fix:** add WorldCat / OpenLibrary / LOC ISBN-based verifiers; allow per-pack relaxed gate; surface "verified via ISBN" status.
2. **HIGH — Researcher_config has no humanities citation styles or venue templates.** `citation_style` enum lacks `mla` / `chicago_author_date` / `chicago_notes_bib`; `venue_template` lacks `humanities_essay` / `chicago_thesis` / `mla_essay`. A user fills in something off-genre by default. **Fix:** extend the enum + ship a `humanities_essay.typ` template that handles footnotes + block quotes + generous margins.
3. **MEDIUM — No `tool_humanities_apparatus_audit`.** `close_reading.yaml`'s quality_bar (anchor_density, counter_instance, tradition_declared, edition_pinned, secondary_ledger) lives only in YAML. There's no MCP tool that machine-checks an apparatus.md file against those bars. The AI is on its honour to follow them; meanwhile the statistics-flavoured audit gates fire loudly. **Fix:** ship `tool_humanities_apparatus_audit(apparatus_path)` that scans for line/page anchors per claim, tradition-declared header, counter-instance section.
4. **MEDIUM — `tool_audit_prose` doesn't recognise the humanities register.** Flags hedging + vague quantifiers + interpretive language ("the passage suggests", "might be read as") as defects. In literary criticism this IS the register. **Fix:** pack-aware prose profile (humanities = tolerant of hedging, demands page anchors instead).
5. **MEDIUM — Per-step literature gate forces DEFERRED on early pipeline steps.** Corpus audit and raw model output have no comparative claim yet, but `tool_audit_step_literature` BLOCKS unless `findings_vs_literature.md` exists with a verdict. DEFERRED works but is awkward, and the protocol doesn't document when DEFERRED is the correct verdict. **Fix:** auto-allow DEFERRED for any step with no `## Findings` claims yet; document this carve-out.

---

## 8. Top 5 doc / guidance gaps

1. **`inputs/` subfolder convention is canonical-only.** Humanities pack uses `inputs/corpus/` and `inputs/textual/passages/`; `START.md` / `SETUP.md` only document `raw_data/literature/context/`. First-time user doesn't know whether to colonise `inputs/raw_data/` or invent the new subfolder.
2. **`tool_intake_autofill` on a text corpus is undocumented.** Description focuses on tabular data inference. Add a worked example.
3. **`tool_search` humanities-database coverage is opaque.** No mention of MLA International Bibliography / JSTOR / Project MUSE in TOOLS.md. Humanities-pack tools should at minimum say "Crossref + Semantic Scholar coverage is sparse for literary monographs; manual `inputs/literature/` PDF drops recommended".
4. **Distant-reading "no first-class topic-model tool" warning is buried.** Lives in `distant_reading.yaml` step body. Should appear in `TOOLS.md` § Humanities pack as a quick "this pack is scaffolding-first, write your own scripts via `tool_python_exec`".
5. **Multi-protocol decomposition resolution is undocumented.** When `tool_route` matches both `close_reading` AND `distant_reading` AND `digital_humanities_workflow` (all overlapping triggers), how does it pick? `AI_GUIDE.md` doesn't say.

---

## 9. Top 5 things that worked well

1. **Humanities pack protocols are EXCELLENT prose.** `close_reading.yaml`, `distant_reading.yaml`, `digital_humanities_workflow.yaml`, `citation_chains.yaml` read like they were written by working humanists, not by a STEM engineer guessing what humanists want. Tradition declarations, counter-pattern requirement, "computers do not detect meaning" doctrine, anchor-density quality bar — these are field-true. This is the single biggest positive finding of the validation.
2. **The hybrid distant-reading-with-close-reading-gate protocol IS the right answer for this hypothesis.** `digital_humanities_workflow.yaml` enforces exactly the loop a peer reviewer would demand: distant pass → cluster → close-read 3+ representative texts before naming the cluster → cluster_decisions.md as the methodological appendix. No fudging.
3. **`sys_boot` + `tool_route` two-call session start is clean.** As a fresh agent with only `AI_GUIDE.md` + `templates/CLAUDE.md` I was unblocked in 5 seconds. The pattern is repeated identically in every IDE rules file.
4. **Scaffold-not-script doctrine is genuinely respected in the protocols.** Even `digital_humanities_workflow` step `distant_pass` names the method classes (LDA, BERTopic, Burrows's Delta, NetworkX) but does NOT hardcode hyperparameters / library calls — the AI fills the specifics per project. The PROTOCOL_DOCTRINE doc and the protocol implementations agree.
5. **The dashboard v2 story-mode design is well thought out.** `synthesis_dashboard.yaml` treats the dashboard as the paper-as-interactive, with per-hypothesis grouping, hoverable figures, "Why?" expanders revealing methods detail, and an audit-summary surface. For a humanities project this maps cleanly onto block-quote + apparatus + close-reading verdict per hypothesis.

---

## 10. Final rating

**7 / 10** for this scenario.

Rationale: the humanities pack is far better thought through than I expected from a "general research OS". The protocols are field-true and the doctrine is honored. The deductions all come from the **last-mile assembly** stage: citation-verify is STEM-biased and blocks humanities monographs, citation-style enum doesn't include MLA/Chicago, no Typst template suits a humanities essay, no apparatus-audit tool exists, and `tool_audit_prose` mis-flags the humanities register. None of these are fatal — the override paths exist — but they create the impression that Research-OS lets humanities scholars **plan** rigorously and then **trips them at the gate** when it's time to ship. Fix those 5 last-mile items and this scenario goes to 9/10.

---

## 11. Onboarding-friction count (first 5 turns)

**3 friction points in first 5 turns** (1 HIGH, 1 MEDIUM, 1 LOW). Logged at turns 2 (LOW), 3 (HIGH), 4 (MEDIUM).

---

## 12. Endpoint status

- **Reached paper.pdf step?** YES — Turn 28 invokes `tool_paper_compile_typst`. Whether the PDF actually compiles depends on `tool_citations_verify` accepting the humanities references (Friction #1).
- **Reached dashboard.html step?** YES — Turn 29 invokes `tool_dashboard_story_generate` + `tool_dashboard_create(story=true)`. Expected to succeed (no humanities-specific blocker beyond the reading-time bound on story-mode).

---

## Appendix — total turn count and severity tally

- **Total turns logged:** 30
- **Friction by severity:** HIGH=2, MEDIUM=6, LOW=5 (and roughly that many "none" turns)
- **Doc gaps:** 5 substantive ones logged in §8; another ~5 minor ones embedded in turn entries.
