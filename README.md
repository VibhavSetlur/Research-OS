<p align="center">
  <img src="assets/logo.svg" alt="Research OS — grounded · cited · auditable" width="520">
</p>

# Research OS

[![python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue.svg)](https://github.com/VibhavSetlur/Research-OS)
[![license](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![version](https://img.shields.io/badge/version-1.1.0-orange.svg)](CHANGELOG.md)

**Turn your AI IDE into a rigorous research collaborator.** Drop your
data, talk in plain English, get publication-grade outputs with
verified citations, full provenance, and audited quality gates — no
hallucinated numbers or references leaking into the paper.

You touch `inputs/`. The AI touches `workspace/` and `synthesis/`.
Research OS keeps it honest: every figure has a caption + summary +
provenance sidecar; every citation is verified online; every
deliverable passes a completeness gate; every gate bypass is logged
for your pre-submission audit.

Works with any MCP-speaking AI IDE: **Claude Code, Claude Desktop,
OpenCode, Antigravity, Cursor, VS Code (MCP), Windsurf, Continue,
Aider**. Research OS does NOT manage LLM provider keys — your IDE
owns model access.

---

## Install — one command

```bash
pip install "research-os[all] @ git+https://github.com/VibhavSetlur/Research-OS.git"
```

The `research-os` binary is global; install once and it serves every
project you scaffold. → [Per-IDE wiring & extras](docs/SETUP.md)

---

## Your first project — 60 seconds

```bash
mkdir my-project && cd my-project
research-os init                           # arrow-key wizard
# or: research-os init my-project --yes    # one-shot for CI/scripts
```

The wizard asks:
- where the project lives and what it's called,
- which AI IDEs you use (drops MCP configs in the right places),
- lets you paste a **Slack thread / email / PI message** → parsed and
  saved into `inputs/context/` with provenance frontmatter,
- lets you paste **arXiv IDs · DOIs · PDF URLs** → downloaded into
  `inputs/literature/` (Unpaywall for DOIs),
- offers to symlink existing data files into `inputs/raw_data/`.

Done in under a minute. → [Full walkthrough](docs/START.md)

---

## Day-to-day — drop files, talk

After the wizard, just open the project in your AI IDE. The MCP
server auto-launches. Drop data into `inputs/raw_data/`, PDFs into
`inputs/literature/`, notes into `inputs/context/`. Then in chat:

```
> fill out the intake
> what should I do next?
> run a baseline EDA
> compare logistic regression and gradient boosting
> draft the discussion section
> what's left before I can submit?
```

The AI picks the right workflow from **88 protocols**, runs it
through **143 MCP tools** that enforce real quality gates, and asks
you when it's uncertain — including `guidance/scope_clarification` for
open-ended or cross-disciplinary asks the router can't pick from.
→ [Common phrasings → outputs](docs/USE_CASES.md)

---

## Your project layout

```
my-project/
├── inputs/                  ← IMMUTABLE — you drop files here
│   ├── raw_data/                  CSV / parquet / FASTQ / ...
│   ├── literature/                PDFs of papers
│   ├── context/                   notes / drafts / PI messages
│   ├── intake.md                  short pointer; AI rewrites on autofill
│   └── researcher_config.yaml     AI behaviour (every field optional)
│
├── workspace/               ← ACTIVE — AI lives here
│   ├── methods.md · analysis.md · citations.md   (append-only memory)
│   ├── 01_baseline_eda/                          (numbered experiment)
│   │   ├── scripts/  (atomic, versioned _v1 → _v2)
│   │   ├── outputs/{figures,tables,reports}/
│   │   │       each figure ships .caption.md + .summary.md + .prov.json
│   │   ├── pipeline.yaml          (sub-task DAG, content-hash cached)
│   │   ├── conclusions.md
│   │   └── .versions/v<n>/        (snapshots from tool_step_iterate)
│   ├── logs/                      audit reports + override ledger
│   └── scratch/                   AI sandbox (gitignored)
│
├── synthesis/               ← FINAL — only when you ask for a deliverable
│   paper · abstract · poster + QR · dashboard · slides · handout · etc.
│
└── AGENTS.md · CLAUDE.md · .cursor/ · .claude/ · .windsurfrules · ...
                            per-IDE rules + MCP configs (auto-dropped)
```

Synthesis and the input subfolders are **lazy** — they materialise
on first write, so a fresh project surface stays uncluttered.

---

## What it does

Seven capability groups, 88 protocols, 143 MCP tools.

| | What you say · what you get |
|---|---|
| **Plan + design** | EDA + hypothesis generation · power analysis · evaluation design (split / CV / paired test) · hyperparameter sweep design · data ethics review (IRB / privacy / fairness) · preregistration |
| **Run analyses** | iterative experiments with provenance · head-to-head method comparison · data-quality audit · reproduction of published work · causal / Bayesian / time-series / ML / clinical / qualitative / mixed-methods pipelines · dead-end routing |
| **Build figures** | full viz workflow · multi-panel composition · figure narrative arc · colour-blind + WCAG accessibility audit · reviewer-style critique |
| **Write** | per-section drafting (methods · results · discussion · limitations · end-matter with CRediT) · title workshop · cover letter · pre-submission gate |
| **Synthesise** | IMRAD paper · abstract · poster + QR · talk slides (lab / conference / defense) · self-tested HTML dashboard · printable handout + QR · grant narrative · lay summary · PI progress update · null-findings companion |
| **Read + understand** | quick paper critique · multi-paper comparative review · methodological consultation (teach me X) · literature search with forward-citation walk · full PRISMA systematic review |
| **Audit + ship** | quality audit · reproducibility verification · code review · peer-review response · collaboration handoff (share-safe zip) · structured AI pushback when grounded evidence disagrees |

→ [docs/USE_CASES.md](docs/USE_CASES.md) — role × goal × output map
→ [docs/PROTOCOLS.md](docs/PROTOCOLS.md) — every protocol with
  trigger phrases and quality bars
→ [docs/TOOLS.md](docs/TOOLS.md) — every MCP tool with example calls

---

## Why use it — pain Research OS resolves

| Pain | How Research OS resolves it |
|---|---|
| AI hallucinates citations | Synthesis tools verify every cite online; drop the rest. Per-section caps (3 abstract / 12 dashboard / 40 paper). |
| AI hallucinates numbers | `tool_audit_claims` traces every number in `paper.md` back to a workspace artefact. BLOCKS synthesis if any are ungrounded. |
| AI guesses methodology | `tool_research_method` mandates literature grounding before any commit. |
| AI writes 400-line one-shot scripts | A step whose outputs span figures + tables + reports without a `pipeline.yaml` is BLOCKED. Forces atomic, content-hash-cached sub-tasks. |
| "Iterate Figure 2's look" → ad-hoc edits | `tool_step_iterate` snapshots scripts + outputs + captions + conclusion as a coordinated `.versions/v<n>/` BEFORE you edit; `tool_audit_version_coherence` flags any output whose `.prov.json` still points at an older script. |
| Pre-registered analyses drift | `tool_preregister_freeze` content-hashes the SAP; `_diff` surfaces every deviation. |
| Null findings → file drawer | `synthesis_null_findings` publishable companion for refuted / underpowered / abandoned. |
| Pre-submission anxiety | `audit/pre_submission_checklist` walks every check journals run — including reviewing every gate bypass logged in `workspace/logs/override_log.md`. |
| Researcher enters mid-pipeline | `guidance/mid_pipeline_entry` classifies into 7 archetypes; skips redundant intake. |
| 143 tools is too many to triage per turn | `tool_route` returns ~10-15 active tools per protocol; `sys_active_tools(protocol_name)` returns the same shortlist on demand. |
| Same project, different AI tomorrow | `sys_session_handoff` snapshots; `tool_session_resume` reconstructs intent in one call. |
| Long jobs on shared HPC | `tool_task_run` backgrounds them; `tool_slurm_submit` for clusters. |

→ [docs/RESEARCHER_GUIDE.md](docs/RESEARCHER_GUIDE.md) §
  Power-user patterns for the full list.

---

## Tune AI behaviour — `inputs/researcher_config.yaml`

Every field is optional. The two knobs that change how the AI
behaves on edge cases:

```yaml
interaction:
  # How quality-gate blockers are treated:
  #   enforce        → AI refuses bypass unless researcher explicitly
  #                    authorises AND supplies an override_rationale
  #                    (recorded to workspace/logs/override_log.md).
  #   allow_override → bypass on request; rationale logged if provided.
  #   warn_only      → blockers become warnings (sandbox use only).
  quality_gate_policy: enforce

  # What the AI does when your request is ambiguous:
  #   ask_when_uncertain → default; AI asks a one-line follow-up.
  #   take_best_default  → AI proceeds, surfaces the chosen default
  #                        for review.
  ambiguity_posture: ask_when_uncertain
```

Every bypass the AI takes is recorded — the pre-submission checklist
surfaces them so nothing ships without your sign-off.

---

## Documentation

| First time | Day-to-day | Reference |
|---|---|---|
| [START.md](docs/START.md) — install + first project + cheatsheet | [RESEARCHER_GUIDE.md](docs/RESEARCHER_GUIDE.md) — full workflow walkthrough | [PROTOCOLS.md](docs/PROTOCOLS.md) — every protocol |
| [SETUP.md](docs/SETUP.md) — install + per-IDE wiring | [USE_CASES.md](docs/USE_CASES.md) — role × goal × output map | [TOOLS.md](docs/TOOLS.md) — every MCP tool |
| [FAQ.md](docs/FAQ.md) — common questions | [SHARING.md](docs/SHARING.md) — share-safe zip + GitHub paths | [PROTOCOL_DOCTRINE.md](docs/PROTOCOL_DOCTRINE.md) — for protocol authors |
| | [AI_GUIDE.md](docs/AI_GUIDE.md) — for the AI itself | |

Doc index → [docs/README.md](docs/README.md).

---

## Verify your install

```bash
python scripts/preflight.py            # 13 wiring checks
pytest -q                              # 417 tests, ~9 s
ruff check src/ tests/ scripts/
```

---

## Contributing + License

See [CONTRIBUTING.md](CONTRIBUTING.md) — covers adding a tool, adding
or modifying a protocol (must follow the scaffold-not-script
doctrine), and the test conventions. Issues + PRs welcome at
<https://github.com/VibhavSetlur/Research-OS/issues>.

License: [MIT](LICENSE).
