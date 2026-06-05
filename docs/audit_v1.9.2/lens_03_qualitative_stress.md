# LENS 03 — Qualitative-stress audit

**Scenario:** 12-participant qualitative interview study (e.g. thematic analysis
of clinician interviews about EHR friction). Stress-test the qualitative pack +
REDCap adapter for participant tracking + anonymization + intercoder reliability
+ saturation handling + theoretical/snowball sampling.

**Repo state at audit:** core `__version__ = 1.9.2` (note: task brief said
v1.9.1 — codebase already bumped). 114 protocols (118 if you count the 4
qualitative-pack YAMLs and 1 dead `humanities`); 872 tests pass under
`research-os` conda env; ruff clean across `src/research_os_qualitative` and
`src/research_os_adapter_redcap`.

---

## Asset map

### Core qualitative protocols (5 in `src/research_os/protocols/methodology/`)
- `qualitative_research.yaml` (v1.7.1) — COREQ/SRQR-anchored TA / GT / IPA scaffold.
- `qualitative_quality_audit.yaml` (v1.7.1) — COREQ/SRQR enforcement audit.
- `coding_scheme_development.yaml` (v1.7.1) — first-pass codebook design.
- `interview_guide_design.yaml` (v1.7.1) — pre-collection guide drafting.
- `inter_rater_reliability.yaml` (v1.7.1) — κ / α / ICC / weighted-κ chooser.

### Qualitative pack (`src/research_os_qualitative/`, pack v1.7.0)
- 5 protocols: `coding/coding_scheme_iteration`,
  `validity/member_checking`, `method/grounded_theory_iteration`,
  `method/thematic_analysis_braun_clarke`, `output/qualitative_report_format`.
- 2 tools: `tool_qualitative_codebook_diff`,
  `tool_qualitative_quote_provenance`.
- 1 detector: `detect_qualitative` (speaker-turn regex, qual-tool filename
  hints, IRB-phrase scan, small-N demographic CSV sniff).
- Router-index contributions: 5 entries (validated by namespace prefix
  `qualitative/`).

### REDCap adapter (`src/research_os_adapter_redcap/`, v1.8.0)
- `detect()`, `extract()`, `describe()`, `register()`.
- 1 tool: `tool_redcap_schema_describe`.
- Fixture: `tests/fixtures/projects/redcap_longitudinal/`.

---

## Stress-test runs (live, on conda env `research-os`)

### Run 1 — Pack registers, tools wire
```
Pack: qualitative 1.7.0
Tools: ['tool_qualitative_codebook_diff', 'tool_qualitative_quote_provenance']
Router entries: 5
Domain detector: detect_qualitative
```
PASS — pack loads via `bundled` list in `server._discover_packs_once`.

### Run 2 — REDCap adapter on shipped longitudinal fixture
```
detect: True
data_dictionary_file: inputs/raw_data/study_DataDictionary.csv
export_file: inputs/raw_data/study_DATA.csv
longitudinal: True, events: 3, instruments: 3, sample_n: 4,
phi_warnings: [{field: ssn, label: SSN, warning: ...DUA/IRB...}]
```
PASS — fixture is detected; PHI warning fires on `Identifier? = y`.

### Run 3 — REDCap adapter on a realistic qualitative
**participant-tracking CSV** (12 interviewees, no `redcap_event_name`)
```
detect: False
extract: {data_dictionary_file: null, export_file: null, ..., _notes:
         ["No REDCap-shaped CSV found at extract() time."]}
```
**FAIL.** A perfectly normal REDCap export — single instrument, no
longitudinal events, no repeating instruments — is silently invisible to
the adapter. The qualitative researcher who built a "Participant Tracking"
instrument in REDCap and exported the CSV gets *zero* PHI warnings,
*zero* schema description, *zero* provenance entry, because the detector
hard-requires one of `redcap_event_name | redcap_repeat_instrument |
redcap_repeat_instance` in the export header. `describe()` claims
`shapes_supported: ["data_dictionary_csv", "longitudinal_export_csv",
"cross_sectional_export_csv"]` — but the third shape is **not actually
detected by `_classify_csv`**. The dictionary-only path triggers detection,
but an export without one of the three stamping columns does not. This
is the central capability gap exposed by Lens 3.

See finding #1.

### Run 4 — Qualitative detector on 12 interview transcripts (.txt format)
```
DETECTOR signals:
{
  "pack": "qualitative",
  "confidence": 0.1,
  "signals": ["IRB / informed-consent references in 1 file(s)"]
}
```
**Surprisingly weak.** 12 `.txt` transcripts with speaker turns
("Interviewer:" / "P01:") yielded **confidence 0.1**. Two reasons:
1. `.txt` is NOT in `_INTERVIEW_HINT_EXTS = {".vtt", ".otr", ".docx",
   ".rtf"}`. The most common transcript shape — plain text — does not
   contribute to the file-extension score.
2. The speaker-turn regex requires `≥ 5` turn-matches per file. Realistic
   short pilot transcripts (4 turns) fall below the threshold even though
   they are clearly interview data. Confidence 0.1 is below any
   plausible auto-load threshold. See finding #2.

### Run 5 — `tool_qualitative_codebook_diff` and `tool_qualitative_quote_provenance`
Both ran to success on a 3-code → 3-code codebook with applied-coding
JSON files; per-code κ computed (one κ=0.0 case verified mathematically
correct — one rater always assigned the code, the other never did
post-revision). Tools register, namespace-validate as `tool_qualitative_*`,
and write to `workspace/codebooks/diff_v1_to_v2.md` +
`workspace/quotes/registry.jsonl`.

### Run 6 — `tool_data_profile` on a 12-row participant tracking CSV
```
"suggestions": [
  "Sample size n=12 is small — consider whether this is enough for the
   planned statistical test.",
  "Next step: create an experiment (sys_path_create) for baseline EDA."
]
```
**Friction.** For a qualitative interview study where n=12 may be the
*right* sample size for saturation, the data-profile suggestion is
misleading and surface-noisy. The audit gates do NOT block (the
underpowered detector in `tools/actions/audit/null_findings.py:26` only
flags if a `power_report.md` exists with power<0.8), so this is friction
in the prose output of `data_profile`, not a hard block. See finding #6.

### Run 7 — Audit gate doesn't auto-flag n=12 as underpowered
Confirmed: `_collect_underpowered()` only fires when a step has actually
run `tool_audit_power` and the `Computed power: <0.8`. No row-count or
participant-count heuristic auto-flags qualitative work as underpowered
at the audit gate level. **PASS** for the question "does the audit gate
handle n=12 = right-n-for-saturation without flagging it as underpowered."

---

## Findings (ordered by severity)

### HIGH-1 — REDCap adapter cannot detect cross-sectional exports it claims to support
**File:** `src/research_os_adapter_redcap/__init__.py`
- Line 39-43: `_EXPORT_SIGNAL_COLUMNS = {redcap_event_name,
  redcap_repeat_instrument, redcap_repeat_instance}` — at least one of
  these must be in the export header for detection.
- Line 100-106: `_classify_csv` returns `"export"` only if `record_id`
  **AND** at least one of the three signal columns is present.
- Line 442-443: `describe()` advertises `shapes_supported:
  [..., "cross_sectional_export_csv"]` — **the detector does not match
  this shape**.
- A REDCap project that exports a single-instrument, cross-sectional CSV
  (the natural shape for a participant-tracking sheet in a 12-person
  qualitative study) is silently dropped: `detect → False`, `extract →
  notes "No REDCap-shaped CSV found"`. PHI warnings under-report by
  100 % of the dataset.
- **Suggested fix (NOT applied — production-code change):** loosen
  detection to also classify as `"export"` when `record_id` is present
  AND the file has a sibling REDCap dictionary CSV in the same
  directory, OR when the column names look like the dictionary's field
  list. Alternatively, accept any CSV with `record_id` as a candidate
  export and let `extract` mark it `longitudinal: false`. At minimum,
  remove `cross_sectional_export_csv` from `describe()` until detection
  catches up — the lie is worse than the gap.
- **Suggested target:** v1.9.3 (HIGH severity, docs lie).

### HIGH-2 — Qualitative detector mis-scores plain-text transcripts (the most common shape)
**File:** `src/research_os_qualitative/detector.py`
- Line 12: `_INTERVIEW_HINT_EXTS = {".vtt", ".otr", ".docx", ".rtf"}` —
  `.txt` is excluded.
- Line 58: speaker-turn pattern requires `≥ 5` matches per file.
- A realistic pilot run with 12 short `.txt` transcripts (4 speaker turns
  each — Interviewer / P / Interviewer / P) returns confidence **0.1**.
  Even with longer transcripts, the `.txt` extension contributes
  nothing to `min(0.3, interview_files * 0.1)`.
- The IRB-phrase regex hits, but only contributes 0.1 max. Without
  `.txt` enrichment, a project that ships only `.txt` transcripts will
  never auto-fire the qualitative pack — the researcher has to invoke
  it by trigger phrase.
- **Suggested fix (NOT applied — production logic):** add `.txt` and
  `.md` to `_INTERVIEW_HINT_EXTS` and weight speaker-turn matches at
  ≥3 instead of ≥5. Two-line touch.
- **Suggested target:** v1.9.3.

### HIGH-3 — Member-checking protocol references two unimplemented helpers
**File:** `src/research_os_qualitative/protocols/validity/member_checking.yaml`
- Line 46: `If not, run consent_amendment first.` — **no protocol named
  `consent_amendment` exists anywhere in core or any pack.**
- Line 110: ``Use `tool_redact` if any third-party names appear in the
  quotes`` — **no tool named `tool_redact` is registered**. A grep across
  all of `src/` returns only the private helper `_redact` inside
  `tools/actions/state/reliability.py`. There is no qualitative-namespace
  redactor either (`tool_qualitative_redact` would be the namespace-correct
  name; it does not exist).
- The protocol writes a confident path through anonymization that
  evaporates when the AI tries to follow it. Mid-flow, the AI either
  hallucinates a redactor or stalls. Both bad.
- **Suggested target:** v1.9.3. Either ship `tool_qualitative_redact`
  (regex + named-entity sweep) and a `consent_amendment` mini-protocol,
  or rewrite the two lines as "manually redact third-party names" /
  "amend the IRB protocol via your institutional process."

### HIGH-4 — Three qualitative-pack protocols misuse `sys_path` as a file-finder
- `src/research_os_qualitative/protocols/method/thematic_analysis_braun_clarke.yaml:210`
  — ``sys_path` to find the relevant checklist scaffold`
- `src/research_os_qualitative/protocols/output/qualitative_report_format.yaml:79`
  — `Call sys_path to confirm the standard's checklist YAML exists`
- `src/research_os_qualitative/protocols/validity/member_checking.yaml:193`
  — `Use \`sys_path\` to confirm the next protocol artifacts exist`
- `sys_path` is the path-lifecycle dispatcher with operations
  `create | abandon | list` (per `server.py:2367-2386`). It has no
  filesystem-read role. The intended tool is `sys_file_read` /
  `sys_file_list` (or `tool_search` for content search).
- **Suggested fix (DOC-only):** rewrite the three lines to call the
  correct tool. Doc-only string change, NOT applied here because the
  task brief restricts trivial fixes to typos and stale counts — these
  are user-facing prose corrections in a protocol description, which
  cross the "don't modify production text" line for a discovery-sprint
  audit. Logged for the next protocol-docs pass.
- **Suggested target:** v1.9.3.

### HIGH-5 — COREQ / SRQR checklist scaffold YAMLs are never shipped
**File:** `src/research_os_qualitative/protocols/output/qualitative_report_format.yaml`
- The `coverage_gate` / `walk_checklist` steps depend on a checklist
  YAML at `workspace/checklists/<standard>_coverage_v<N>.yaml`. The
  `select_standard` step says "Call sys_path to confirm the standard's
  checklist YAML exists under workspace/checklists/." There is **no
  checklist YAML shipped anywhere in the repo** (`find . -name
  "*coreq*" -o -name "*srqr*"` returns nothing under `src/` or
  `templates/`).
- The AI is therefore forced to hallucinate the 32 COREQ items or the
  21 SRQR items from training. This is exactly the failure mode the
  grounded-AI design is supposed to prevent.
- **Suggested fix (NOT applied — would add new files, against task
  rules):** ship `templates/checklists/coreq_32items.yaml` and
  `templates/checklists/srqr_21items.yaml` with the verbatim item text
  (both standards are CC-licensed); have `select_standard` copy the
  appropriate one into `workspace/checklists/`.
- **Suggested target:** v1.10.0 (MINOR — new bundled assets).

### MEDIUM-1 — κ threshold drift across three intercoder protocols
- `qualitative/coding/coding_scheme_iteration.yaml:42`
  — `per_code_kappa_minimum: 0.60   # Landis & Koch 'moderate'`
- `methodology/qualitative_quality_audit.yaml:152`
  — `A verdict < 0.70 without a reconciliation plan is a BLOCKER.`
- `methodology/inter_rater_reliability.yaml:144-149`
  — verdict table: `0.61-0.80 (substantial), 0.41-0.60 (moderate)`
- `methodology/qualitative_quality_audit.yaml:144-148`
  — verdict table: `0.60 ≤ κ < 0.80 = substantial, 0.40 ≤ κ < 0.60 = moderate`
- Three problems: (a) pack vs core disagree on the floor (0.60 vs 0.70);
  (b) the two verdict tables disagree on the boundary (`0.61` vs `0.60`,
  `0.41` vs `0.40`) — Landis & Koch 1977 actually uses `0.61–0.80` for
  substantial; (c) the pack's `Landis & Koch 'moderate'` label is wrong
  in shorthand — moderate is `0.41–0.60`, not `0.60`. A user running both
  protocols on the same corpus gets contradictory blockers.
- **Suggested target:** v1.9.3 (HIGH-ish friction; pick one canonical
  table, cite it once, reference from all three protocols).

### MEDIUM-2 — `data_profile` emits "n=12 is small" against any small DataFrame
**File:** `src/research_os/tools/actions/data/data.py:164-168`
- Hard-coded threshold `n_rows < 30` triggers the suggestion
  `"Sample size n={n_rows} is small — consider whether this is enough
  for the planned statistical test."` This is correct framing for
  exploratory quantitative work; it is misleading for qualitative
  studies where n=12 is canonical for saturation work.
- The audit gate proper (`null_findings._collect_underpowered`) does
  NOT escalate this into a blocker, so this is friction not failure —
  but it pollutes the per-step profile report when the same CSV is a
  participant-tracking sheet, not a statistical sample.
- **Suggested fix (NOT applied — touches production logic):** when the
  step is qualitative (themes.md / codebook.md exists under
  `workspace/<step>/`), suppress the small-n suggestion or rephrase to
  "for a qualitative study, n=12 is in the typical saturation range
  (Guest, Bunce & Johnson 2006)." Two-line guard.
- **Suggested target:** v1.9.4.

### MEDIUM-3 — Pack version drift from core (1.7.0 / 1.7.1 vs core 1.9.2)
- `research_os_qualitative.__version__ = 1.7.0`
- `research_os_humanities.__version__ = 1.7.0`
- All five qualitative-pack protocols carry `version: '1.7.1'`.
- Per `CLAUDE.md` "When working on protocols → Bump the protocol's
  `version:` field to match the next package release." All five pack
  protocols and the five core qualitative-themed protocols (`qualitative_research`,
  `qualitative_quality_audit`, `coding_scheme_development`,
  `interview_guide_design`, `inter_rater_reliability`) are all at
  `1.7.1` while core is `1.9.2`. `sys_packs_installed` will surface
  `qualitative 1.7.0` next to `core 1.9.2`, which reads as "this pack
  is unmaintained."
- **Suggested target:** v1.9.3 (sweep-bump unchanged protocol files to
  '1.9.2' OR carve out the qualitative pack into its own PyPI package
  per the comment in `pyproject.toml:71-76`).

### LOW-1 — Detector teases NVivo/Atlas.ti/MAXQDA/Dedoose without integration
**File:** `src/research_os_qualitative/detector.py:13-16`
- Detector raises the qualitative-pack confidence on filenames matching
  `nvivo / atlas.ti / atlas_ti / maxqda / dedoose / transana / quirkos /
  taguette`, but no adapter or tool actually consumes any of these.
  Confidence-only signal with no follow-through.
- **Suggested target:** v1.10.0 (write a `tool_qualitative_nvivo_import`
  that reads the `.nvp` / `.qda` exchange format and surfaces codebook
  + applied codes into `tool_qualitative_codebook_diff` — real win for
  the existing-NVivo-shop persona). Until then, the detector should
  add a `_notes` entry saying "qualitative-tool artefacts detected;
  no native import — manual conversion required."

### LOW-2 — `tool_qualitative_codebook_diff` always writes to `diff_v1_to_v2.md`
**File:** `src/research_os_qualitative/tools.py:137`
- Tool description (line 90-92) says: "Writes `workspace/codebooks/
  diff_v{N}_to_v{M}.md`." Actual implementation writes literally
  `diff_v1_to_v2.md` regardless of which versions the user passes —
  N and M from the path inputs aren't extracted. Subsequent diff calls
  overwrite the previous file silently.
- **Suggested fix (NOT applied — production-logic change):** parse N/M
  from `arguments["codebook_v1"]` / `["codebook_v2"]` (regex `v(\d+)`
  on the basename) and slot into the output filename.
- **Suggested target:** v1.9.4.

### LOW-3 — `qualitative_quality_audit` SQL → "the audit IS the trail" parenthetical
**File:** `src/research_os/protocols/methodology/qualitative_research.yaml:83`
- `- Dependability: audit trail (this protocol IS the audit trail)`
  reads weird. The protocol is a *scaffold* the AI follows; the audit
  trail is the artefacts the AI produces (`codebook_v<N>.md`, memos).
  Low-stakes prose nit.
- **Suggested target:** v1.9.4 (or wait for the next protocol-prose pass).

---

## Coverage gaps (not findings per se, but worth surfacing)

1. **No saturation-curve tool.** `qualitative_quality_audit.yaml:69-94`
   tells the AI to "Write a tool_python_exec script" that parses
   open-codes, computes cumulative unique codes, plots the curve, and
   judges whether the slope at the last transcript is > 0. This is
   reasonable per the "scaffolds not scripts" doctrine, but every
   project re-derives the same logic from scratch. A
   `tool_qualitative_saturation_curve` that consumes an
   `applied_codes.jsonl` per-transcript and emits the figure + verdict
   would save 50-100 lines of generated Python per project and make the
   curve comparable across studies. Not a bug; an opportunity.

2. **No anonymization / PHI-scrubbing tool of any kind.** `data_ethics_review`,
   `qualitative_quality_audit`, and `member_checking` all describe
   anonymization audits in prose, but the AI has no programmatic helper
   for the most common scrub patterns (employer names, exact dates,
   rare diagnoses, geographic precision). The `redcap` adapter's PHI
   warning surfaces the `Identifier? = y` flag — that is good, but it
   stops there. For transcript anonymization the project is on its own.

3. **No native NVivo / Atlas.ti / MAXQDA / Dedoose import.** Detector
   knows the filenames; no tool reads them.

4. **`tool_data_profile` is not qualitative-aware.** It treats every
   small DataFrame as a statistical sample. See MEDIUM-2.

5. **REDCap adapter cross-sectional path.** See HIGH-1.

---

## What works well

- `tool_qualitative_codebook_diff` correctly computes per-code Cohen's κ
  from applied-codes JSON and flags codes with κ<0.60. The κ math
  matches the textbook formula and a manual recomputation.
- `tool_qualitative_quote_provenance` writes a JSONL registry that the
  `qualitative_report_format` protocol's quotation audit can consume.
  Provenance is round-trip-able.
- `qualitative_research.yaml` correctly surfaces purposive / snowball /
  theoretical as sampling-strategy options; the grounded-theory pack
  protocol (`method/grounded_theory_iteration.yaml`) explicitly scaffolds
  theoretical sampling with a sampling memo per case and a saturation
  curve. Snowball is named but not scaffolded — it would slot into
  `interview_guide_design.yaml` step `clarify_paradigm` if it wanted
  more depth.
- The audit gate proper does NOT flag n=12 as underpowered — power
  detection is gated on a `power_report.md` artefact, not row count.
- REDCap adapter PHI flagging is real: `Identifier? = y` correctly
  surfaces in `phi_warnings` and the optional `tool_redcap_schema_describe`
  renders a Markdown PHI table.

---

## Trivial fixes considered

None applied. The findings above would require:
- Protocol-prose edits (HIGH-4, LOW-3) — declined because the task
  brief restricts trivial fixes to typos / stale counts / dead imports;
  protocol prose is user-facing text.
- Production-code changes (HIGH-1, HIGH-2, MEDIUM-2, LOW-1, LOW-2) —
  explicitly forbidden by the task brief ("DO NOT modify production code
  logic").
- New file authoring (HIGH-3 helper tools, HIGH-5 checklist YAMLs) —
  forbidden ("DO NOT add new tools, protocols, deps, tests").

Ruff was already clean across `src/research_os_qualitative` and
`src/research_os_adapter_redcap`; no auto-fixes available.

---

## Summary

The qualitative pack + REDCap adapter handle the canonical happy path
(longitudinal REDCap study; ≥6-transcript interview corpus with `.docx`
or `.vtt` files) and the κ / saturation / member-checking gates fire
correctly. The audit chain does NOT mis-classify n=12 as underpowered;
that fear is unfounded. **But the cross-sectional REDCap export path
the adapter advertises is non-functional**, the qualitative detector
is blind to plain-text transcripts, the member-checking protocol
references two helpers (`tool_redact`, `consent_amendment`) that do
not exist, three qualitative-pack protocols misroute the user to
`sys_path` for file-finding (it's the path-lifecycle dispatcher, not
a filesystem reader), the COREQ/SRQR checklist scaffolds the report
protocol depends on are not shipped, κ thresholds drift across three
intercoder protocols, and `tool_data_profile` emits a misleading
"n=12 is small" suggestion for qualitative participant sheets. None
of these are CRITICAL — release isn't blocked, data isn't corrupted —
but five of them surface to users as the system "lying" or stalling
mid-flow.
