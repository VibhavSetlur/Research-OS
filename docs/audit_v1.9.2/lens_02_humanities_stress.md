# Lens 02 — Humanities Pack Stress Test (v1.9.2 audit)

**Scenario.** A medievalist runs Research-OS on a literary-analysis project:
close reading of variant readings across 12 manuscript witnesses of a single
text (cf. the bundled `tests/fixtures/projects/humanities_ms_review` fixture).
The project produces transcriptions, an apparatus criticus, two citation
chains, and a critical-edition draft. There is no tabular data, no statistical
inference, no numeric finding, and no figure. The "result" is a markdown
apparatus the editor wants to publish as a critical edition + journal article.

**Pack under test.** `src/research_os_humanities/` (NOT under
`src/research_os/plugins/packs/` as the audit brief suggested — packs are
sibling top-level `research_os_<name>` packages discovered through `bundled`
entries in `server.py:6045`). Pack version `1.7.0`; protocol files versioned
`1.7.1`. Eight protocols + three tools.

## TRACE

### Pack registration

- `src/research_os/server.py:6045` lists `("humanities", "research_os_humanities:register")`
  in the `bundled` tuple passed to `discover_packs`. Loaded at server import.
- `src/research_os_humanities/__init__.py:25-39` defines
  `register() -> PackRegistration` returning name, version, protocols dir,
  decorated tools, router entries, and a domain detector.
- Preflight (`scripts/preflight.py`) confirms the pack loads:
  `Bundled packs discovered — 5 pack(s) discovered: humanities@1.7.0, ...`
  and `Pack protocols load — 36 pack protocol(s) load`.

### Detection

`detector.detect_humanities` scans `inputs/` for TEI/XML extension hits, a
hard-coded vocabulary of 33 humanities terms, and prose byte totals; subtracts
0.1 per tabular file. Returns a confidence in `[0,1]` with 0.5 = "probably",
0.7 = "strong".

### Protocols (8)

| Path | Adds | Routed via |
|---|---|---|
| `archival/archival_research` | locate → capture → transcribe → annotate → cite | trigger phrases ("archival research", "transcribe a manuscript") |
| `archival/source_provenance` | quotation chain-of-custody | "verify this quotation" |
| `textual/close_reading` | line-by-line annotation w/ tradition declaration | "close reading", "annotate this passage" |
| `textual/distant_reading` | corpus-as-data + interpretation GATE | "topic model", "stylometry" |
| `method/hermeneutic_method` | name your theory of interpretation | "what's my hermeneutic", "Gadamerian reading" |
| `method/digital_humanities_workflow` | hybrid distant + close | "DH project", "digital humanities" |
| `citation/citation_chains` | genealogy of an idea (Aristotle → us) | "trace this idea", "reception of Y" |
| `output/scholarly_edition` | stemma → base text → apparatus → translation | "prepare a critical edition" |

### Tools (3)

`tool_humanities_archive_lookup`, `tool_humanities_transcribe`,
`tool_humanities_citation_chain` — all scaffold-writers, no network/OCR deps.

### Where the pack joins the core flow

Triggers feed `tool_intake_autofill` and the hierarchical router via
`router_entries.HUMANITIES_ROUTER_ENTRIES`. Tools are visible to
`list_tools` after pack discovery. From there on the pack lives inside the
generic core protocol/synthesis/audit/dashboard machinery — and that is
where the breaks live.

## BUGS

### B1 (CRITICAL). Seven referenced tools do not exist; pack's primary
###       methodology protocol cannot be executed as written.

`digital_humanities_workflow.yaml` and `scholarly_edition.yaml` instruct the
AI to "call `tool_dh_topic_model`", "call `tool_dh_stylometry`",
"call `tool_dh_network`", "call `tool_humanities_close_reading`",
"call `tool_viz_dh`", "call `tool_humanities_collate`",
"call `tool_humanities_apparatus`", and
"`tool_humanities_apparatus_lint` flags lines where ...". Verified via
`research_os.server._resolve_tool_name`: every one returns `<<MISSING>>`.

```
src/research_os_humanities/protocols/method/digital_humanities_workflow.yaml:94-95   tool_dh_topic_model / tool_dh_stylometry / tool_dh_network
src/research_os_humanities/protocols/method/digital_humanities_workflow.yaml:127     tool_humanities_close_reading
src/research_os_humanities/protocols/method/digital_humanities_workflow.yaml:158     tool_viz_dh
src/research_os_humanities/protocols/output/scholarly_edition.yaml:75               tool_humanities_collate
src/research_os_humanities/protocols/output/scholarly_edition.yaml:114              tool_humanities_apparatus
src/research_os_humanities/protocols/output/scholarly_edition.yaml:131              tool_humanities_apparatus_lint
```

Preflight does NOT catch this: `scripts/preflight.py:394` scans only
`PROTOCOLS_DIR.rglob("*.yaml")` where `PROTOCOLS_DIR = .../research_os/protocols`
(line 28). Pack protocols are not scanned by the tool-ref resolver.

The fixture-driven stress test
(`tests/unit/test_v170_plugins_packs_stress.py:304`) does not invoke the tools
either — it canned-responses each protocol step and only verifies that the
named artefacts already exist on disk. So pack tests pass while the protocols
are effectively unrunnable.

This is the headline finding for the lens: a humanist following the
`digital_humanities_workflow` or `scholarly_edition` walk-through gets
told to call five-to-seven tools that the server has never heard of.

### B2 (CRITICAL). Server-side step_completeness gate blocks any humanities
###       project from reaching synthesis.

`tool_audit_step_completeness` (the gate `tool_synthesize` and
`tool_dashboard_create` call FIRST) requires per numbered step:

```
src/research_os/tools/actions/audit/audit.py:1349-1364
  if not figures:
      blockers.append(
          "No figure produced — every step MUST emit at least one focal "
          f"figure to outputs/figures/{step_num}_<descriptor>.png."
      )
```

PNG / SVG / JPG / JPEG only. Plus a sibling `.caption.md` AND `.summary.md`
per figure (lines 1372-1393).

A humanities literary project writes:
- `workspace/transcriptions/<image_stem>.md`
- `workspace/close_readings/<slug>_apparatus.md`
- `workspace/citations/chain_<slug>.md`
- `workspace/edition/apparatus.md`
- `workspace/hermeneutics/<text_slug>.md`

These are markdown, not figures, and they sit OUTSIDE numbered step folders
(every humanities protocol's `expected_outputs` block writes flat into
`workspace/<topic>/`, not `workspace/<NN_slug>/outputs/figures/`).

Result: any humanist who runs `tool_synthesize` to compile the apparatus +
discussion into a paper hits a BLOCKER from a gate that is structurally
inappropriate for the work. No override flag for "humanities mode" exists in
`audit_step_completeness`. The pack ships no compensating gate.

Compounding: `_step_completeness` step 4 (line 1408-1412) only warns on
missing `scripts/`, but its step 1421-1467 BLOCKER on a missing
`scratch/stack_plan.md` (from `methodology/pick_tool_stack`) fires only when
scripts are present — so the humanist is spared THAT one. They are not spared
the figure blocker.

### B3 (HIGH). synthesis_paper assumes statistical content; humanities
###       researcher writing close-reading/critical-edition paper is told
###       their work is sub-quality.

`synthesis/synthesis_paper.yaml`:
- `quality_bar.every_claim_grounded: true` — comment says
  "quantitative claim → workspace artifact OR cited paper" (line 75).
  Non-quantitative humanities claims (a reading of a passage; an editor's
  textual decision) have no path through the per-step claim auditor.
- `draft_results` step (line 173-177) demands "Every p-value formatted to
  3 decimals" and "Every effect estimate paired with 95% CI."
- `draft_abstract` step (line 210) explicitly requires
  "Includes one quantitative finding."

A scholarly edition + close reading produces neither. The protocol fails
these checks not because the work is sub-quality but because the AI
guidance is hard-coded for empirical / quantitative IMRAD papers. There is
no venue profile or section template for `humanities/critical_edition`,
`humanities/close_reading_essay`, or `humanities/article` — the
`venue_profile` block defaults to journals (Nature, Science, etc).

### B4 (HIGH). Literature gate is empirical-only; rejects primary-source
###       and critical-edition citations.

`literature/literature_per_step.yaml`:
- Extracts "the QUANTITATIVE anchor (log2FC, padj, HR, CI)" per claim
  (line 64).
- Builds queries against `tool_search_semantic_scholar`,
  `tool_search_pubmed`, `tool_search_crossref` (lines 87-89).
- Domain routing covers Biomedical / Clinical / Quantitative-Methods /
  Social-Behavioral / Geoscience / Hard-Sciences only (lines 91-96). No
  Humanities branch.
- Filter step (lines 103-108) ranks by "≥20 cumulative citations" and
  drops reviews — the wrong filter for primary sources and critical
  editions, which generally have low citation counts in commercial
  bibliometric databases (HathiTrust, BL catalogues, IIIF manifests
  don't even feed Crossref).

The verdict schema is `AGREES | DISAGREES | EXTENDS | DEFERRED` (line 134),
borrowed from a hypothesis-testing frame. The humanities equivalents —
"corroborates a reception-history reading", "departs from prior critical
edition", "introduces a new conjecture" — have no slot.

`tool_audit_step_literature` (the gate, lines 215-233) BLOCKS finalize when
`claims_grounded == 0` and `claims_deferred` is unjustified. A literary
critic legitimately citing only primary sources + 19th-c. apparatus criticus
will produce zero "claims_grounded" by this protocol's standard. They must
either fight the gate (override + rationale logged to the audit trail —
flagged at synthesis) or fake quantitative anchors.

### B5 (HIGH). Synthesis dashboard cannot render a qualitative codebook or
###       a critical-edition apparatus.

`synthesis/synthesis_dashboard.yaml` `quality_bar` (line 79-91) and
`dashboard_v2.py` sections (lines 794, 948, 981, 1039):

- Findings section reads `spec.get("findings")` and renders as
  `<ul><li>…</li></ul>` (line 948-963). No surface for a codebook (codes,
  inclusion / exclusion criteria, applied-quote counts, kappa per code).
- Verdicts section iterates `state.get("verdicts")` keyed by hypothesis_id
  (lines 981-996). Critical editions don't have hypotheses; they have
  textual decisions, editorial principles, and an apparatus.
- Methods section (line 1039) is a free-text block. Fine, but cannot pull
  the apparatus criticus's structured variants.
- `must_pair_figures_with_captions` + `must_pair_figures_with_plain_english`
  (lines 87-88) are figure-mandatory bars.

A humanist asking for a dashboard either gets a "no findings" placeholder
("_(none authored in synthesis_spec.yaml)_") or has to manually fill in
synthesis_spec.yaml under fields meant for an experimental study. The pack
does not ship a humanities-shaped synthesis_spec example.

### B6 (HIGH). Audit gate routes qualitative artefacts to
###       `methodology/qualitative_quality_audit` which assumes interview /
###       focus-group data — wrong for literary qualitative work.

`audit/audit_and_validation.yaml:70-71`:

```
  If the step is qualitative (themes.md / codebook.md exists):
    → also run protocol methodology/qualitative_quality_audit.
```

`methodology/qualitative_quality_audit.yaml` then enforces COREQ / SRQR
checklists, saturation curves, intercoder κ, member checking — every one of
which is appropriate for human-subjects qualitative research but
nonsensical for a literary close-reading codebook (you do not "member check"
a 9th-century manuscript witness; saturation is not a category for a
12-witness collation).

There is no separate route for "literary qualitative" vs "human-subjects
qualitative". The `audit_and_validation` decision rule keys on the existence
of `themes.md / codebook.md`, both of which a digital-humanities workflow
might legitimately produce.

This is the closest the system gets to the audit-gate-flagging-underpowered
concern in the brief: the audit doesn't grep for missing p-values
("underpowered" appears only twice in core, both in null-findings
contexts — `project_ops.py:2123` and `analysis_plan.yaml:406`), but it
DOES auto-route qualitative artefacts into a checklist that doesn't apply.

## FRICTION

### F1 (MEDIUM). Hermeneutic gate ends in a dead-end on_failure.

`method/hermeneutic_method.yaml:237-245`:

```yaml
on_failure: |
  If the researcher cannot name a framework, do NOT proceed to
  close_reading. Instead, call sys_path to surface the
  intellectual_history or critical_theory_survey protocol so the
  framework gets picked deliberately ...
```

Neither `intellectual_history` nor `critical_theory_survey` exists in the
repo (`grep -rn "intellectual_history\|critical_theory_survey" src/` returns
only this very on_failure block). The AI hits the failure branch and routes
to a nonexistent protocol.

### F2 (MEDIUM). Both `archival_research` and `citation_chains` ship
###       without any `quality_bar` block.

Other humanities protocols define a `quality_bar` dict. These two are silent,
so there is no automated way to tell when an archival or citation-chain step
is "done well enough". The protocol's own quality criteria live only in the
prose of `editorial_voice.rules`, which the audit machinery doesn't parse.

```
src/research_os_humanities/protocols/archival/archival_research.yaml      (no quality_bar)
src/research_os_humanities/protocols/citation/citation_chains.yaml        (no quality_bar)
```

### F3 (MEDIUM). Pack chains dead-end. After `output/scholarly_edition`
###       and `citation/citation_chains`, `next_protocol: null` —
###       researcher has no obvious return path into core synthesis.

Trace of humanities chain:
- archival_research → close_reading
- close_reading → citation_chains → **null**
- distant_reading → digital_humanities_workflow → scholarly_edition → **null**
- hermeneutic_method → close_reading → … → null
- source_provenance → scholarly_edition → **null**

Nothing routes back into `synthesis/manuscript_outline` or
`synthesis/synthesis_paper`. The researcher who follows the chain ends up
with workspace files and no published-form scaffold. The pack thinks of
"scholarly_edition" as the final deliverable, but the core flow's
publish-the-paper protocols are never invoked.

### F4 (LOW). Detector under-counts a real humanities project, over-penalises
###       a corpus manifest.

`detector.py:62-69`: prose-corpus heuristic only reads `.txt`, `.md`, `.tex`.
The comment on line 62 says ".pdf bodies" but the set literal does not
include `.pdf`. A medievalist whose `inputs/` contains the
Norton-edition PDF + the IIIF JSON sidecar + a corpus_manifest.csv gets:
- 0 humanities-term hits (no .pdf scan)
- 0.0 prose bonus (CSV present)
- -0.1 tabular penalty
- TEI/XML extension hits only if they shipped TEI

That can drop a clearly-humanities project below the 0.5 "probably" floor.
And `digital_humanities_workflow.yaml` prerequisites EXPLICITLY say
"call inputs/corpus/corpus_manifest.csv" — meaning the very file the DH
protocol mandates is the one the detector penalises by 0.1.

### F5 (LOW). hermeneutic_method `quality_bar` is a LIST. Every other
###       humanities + qualitative + core protocol uses a DICT.

`src/research_os_humanities/protocols/method/hermeneutic_method.yaml:212-228`
emits a YAML sequence:

```yaml
quality_bar:
  - The framework is named by author ...
  - "The 'priors' section answers at least three of these: ..."
```

vs. `close_reading.yaml:171-192`:

```yaml
quality_bar:
  anchor_density: |
    Every interpretive claim has at least one line / folio / page locator. ...
```

Any audit tool that reads `quality_bar` as `dict.items()` will TypeError on
hermeneutic_method. Verified via `yaml.safe_load`. Not currently parsed
machine-side, but a latent fragility once a `tool_audit_quality_bar` lands.

### F6 (LOW). Pack `__version__` (`1.7.0`) lags every protocol's `version`
###       field (`1.7.1`).

`src/research_os_humanities/__init__.py:20` says `__version__ = "1.7.0"`.
All eight humanities protocols carry `version: '1.7.1'`. Same lag in
`research_os_qualitative` (pack 1.7.0, protocols 1.7.1). Cosmetic but
violates the maintainer guide's hard invariant 3 ("Never bump pyproject
without also bumping __init__ and CITATION.cff" — same spirit:
single-source-of-truth versioning).

## DOC / CODE MISMATCHES

### D1. detector.py line 62 comment claims `.pdf` bodies are scanned;
###     line 63 includes only `.txt / .md / .tex`.

```
src/research_os_humanities/detector.py:62
        # Prose-corpus heuristic: .txt / .md / .pdf bodies
src/research_os_humanities/detector.py:63
        if suffix in {".txt", ".md", ".tex"}:
```

The comment is wrong (or the code is — but .pdf reading would need a parser
the pack does not import). Fix is to align the comment.

### D2. `archival_research.yaml:50` instructs the AI to call
###     `tool_humanities_archive_lookup` — the tool exists, but its
###     description (in `tools.py:56-64`) doesn't reference the
###     `holdings_register.md` output the protocol expects.

The protocol's first step writes to `inputs/archival/holdings_register.md`
(line 52). The tool writes to `inputs/archival/lookup_<slug>.md`. Two
different files; the protocol never tells the AI to bridge them. A
researcher follows the protocol literally and ends up with a `lookup_*.md`
that the next step (`capture`) does not look at.

### D3. `__init__.py` docstring (line 4) advertises "8 protocols + 3 tools".
###     That count is correct, but the docstring's enumeration omits
###     `hermeneutic_method` entirely:

```
src/research_os_humanities/__init__.py:3-9
    Adds 8 protocols + 3 tools for archival research, close reading,
    distant reading, hermeneutics, digital humanities, citation chains,
    and scholarly editions.
```

The list names 7 protocol topics but only 7 (the comma series omits
`source_provenance` as a topic — it's lumped under "archival research").
Cosmetic ambiguity; the 8th protocol is real
(`archival/source_provenance.yaml`).

## MISSING AI GUIDANCE

### G1. No "humanities mode" override for `audit_step_completeness`.

The most consequential missing affordance. A humanist literally cannot pass
the per-step completeness gate without faking a PNG. The pack needs either:

- a `pack_overrides` block on the audit gate ("if pack=humanities, skip
  PNG/SVG requirement; require apparatus.md / chain_*.md instead"), or
- a humanities-specific finalize tool that writes a placeholder figure
  (cover image of the manuscript), or
- a `domain: humanities` flag in `researcher_config.yaml` that the audit
  reads and adapts to.

None exists. Pack docs don't mention this gate at all.

### G2. No synthesis venue profile for "humanities article" or
###     "critical edition".

`synthesis_paper.yaml` `venue_profile` covers Nature, Science, NEJM, PLOS,
PNAS, JCO, IEEE, NeurIPS, ACL, generic-two-column, generic-thesis (lines
247-258). There is no entry for, say, *Modern Philology*, *PMLA*,
*Speculum*, *Renaissance Quarterly*, or a critical-edition slot (Loeb,
Oxford Classical Texts). The AI has no field-shaped template to fall back
on.

### G3. The pack ships zero examples of a humanities `synthesis_spec.yaml`
###     to feed the dashboard.

A humanist who runs `synthesis_dashboard` against their close-reading
project will produce a dashboard with an empty findings block (per
`dashboard_v2.py:951-955`). The Researcher Guide and the pack docs do not
show what a humanities spec file should look like. Without it, the
dashboard's "Headline findings" section literally renders
"_(none authored in synthesis_spec.yaml)_".

### G4. No guidance on the close_reading → citation_chains → ??? handoff.

`close_reading.yaml:199` sets `next_protocol: humanities/citation/citation_chains`.
`citation_chains.yaml:199` sets `next_protocol: null`. The AI is supposed
to know what to do after this. In a quantitative project, the implicit
next step is "audit + synthesize". In a humanities project, there's no
documented branch — and the audit gate will block them anyway (B2).

### G5. No surfacing of the "computers don't read meaning" gate as an
###     audit-time check.

`distant_reading.yaml:154-177` and `digital_humanities_workflow.yaml:118-136`
both enforce a "close-read N representative documents" gate as protocol
prose. But there is no `tool_audit_close_reading_gate` or equivalent that
machine-checks whether the close-reading files exist before the
computational pattern is allowed into a synthesis claim. The gate is
self-policed; nothing in `audit_and_validation` invokes it. A future
auto-pilot run could happily skip the close-reading sample and ship a
topic-model finding as a published claim.

## SUMMARY

The humanities pack ships eight thoughtful protocols and three useful
scaffold tools that pass preflight and the canned-response stress test.
But the moment you trace an actual close-reading + critical-edition workflow
from prerequisites through to a synthesis paper, you hit a wall of
silent assumptions inherited from the empirical-IMRAD core: step
completeness wants PNGs, claim grounding wants numbers, literature gate
wants Crossref / Semantic Scholar hits with ≥20 citations, dashboard
wants hypotheses + verdicts, and the qualitative-audit route assumes
interview data not manuscript variants. Two pack protocols reference
seven tools that don't exist, and the on_failure of `hermeneutic_method`
routes to two protocols that also don't exist. The pack's chains
dead-end at `null` without ever rejoining `synthesis/synthesis_paper`,
so a humanist who completes the apparatus has no documented next step.

None of these are tested — the stress runner canned-responds each step
and the preflight tool-ref check skips pack protocols entirely.

The pack is publishable as documentation. It is not yet executable as
infrastructure.
