# Research Copilot — AI Agent Instructions

You are assisting a researcher using the Research Copilot system. This is an AI-driven research engine that transforms raw data into publication-ready manuscripts through a reproducible, verified pipeline.

---

## System Overview

Research Copilot is installed as a Python package. All agents, skills, workflows, and domains are bundled in the package. The project directory contains:

| Path | Purpose |
|------|---------|
| `.research/config.yaml` | Project configuration (workflow, routing, thresholds) |
| `.research/cache/` | Runtime cache (auto-created) |
| `00_inputs/` | Immutable raw data and literature |
| `01_workspace/` | Human-AI working notes |
| `02_experiments/` | Isolated hypothesis branches |
| `03_synthesis/` | Manuscript and final outputs |
| `environment/` | Python dependencies |

---

## CLI Commands

Always use `rcp <command>`:

| Command | Purpose |
|---------|---------|
| `rcp status` | Project state, pipeline progress, next step |
| `rcp scan` | Scan inputs, build research map |
| `rcp intake` | Show intake form status |
| `rcp agents` | List all available agents |
| `rcp agent <name>` | Show an agent's full instructions |
| `rcp skills` | List all skills by category |
| `rcp skill <name>` | Show a skill's methodology |
| `rcp workflow` | Show current workflow |
| `rcp intent <query>` | Route a query through intent router |
| `rcp branch <name>` | Create a research branch |
| `rcp branches` | List all branches |
| `rcp mcp` | Start MCP server for IDE integration |
| `rcp preregistration` | Generate OSF pre-registration |
| `rcp reviewer2` | Run adversarial Reviewer 2 critique |
| `rcp budget` | Show token budget status |
| `rcp dag` | Show execution DAG |
| `rcp data-scale` | Show data scale analysis |
| `rcp dependency-check <script>` | Check for missing imports |

---

## Workflow

Run agents in this order:

1. `research_init` — Parse intake, scan data, create directory structure, build research map
2. `literature_deep` — Expand literature, build evidence matrix
3. `method_route` — Select analysis methods
4. `generate_preregistration` — Create OSF pre-registration
5. `data_scaffold` — Build validated data pipeline
6. `execute_analysis` — Run analysis, compare to literature
7. `replication_validator` — Replicate similar studies
8. `compile_outputs` — Assemble manuscript
9. `reviewer2_critic` — Adversarial audit of findings
10. `audit_validate` — Multi-dimensional audit

---

## Research Iteration

At any point, the researcher can request iteration:

| Researcher Says | Iteration Type |
|----------------|----------------|
| "Why did we get this result?" | investigate |
| "Try a different method" | method_switch |
| "What if we control for X?" | variable_change |
| "Check if this holds up" | robustness |
| "How does this compare to literature?" | literature_compare |
| "What else is in the data?" | explore |
| "Find a better approach" | optimize |

Each iteration:
1. Gets a unique ID (001, 002, 003...)
2. Creates a self-contained experiment under `02_experiments/`
3. NEVER deletes previous iterations
4. Updates `01_workspace/lab_notebook.md` and the experiment's `decisions.yaml`

---

## Rules

### Research Integrity
1. Never invent a citation. If you cannot find a real DOI, write `[CITATION NEEDED]`.
2. Never invent a p-value, effect size, or sample size. Compute or mark `[COMPUTED NEEDED]`.
3. Never assume a file exists without checking via `Path.exists()`.
4. Never assume a variable name exists in data without checking the profile.
5. If unsure about a library API, check documentation before writing code.
6. If a number in your output cannot be traced to a file, flag it.
7. When uncertain: understate, not overstate. Use "may" not "demonstrates".
8. Causal language only for RCTs or valid identification strategies.
9. Report non-significant results with the same detail as significant ones.
10. Organize results by research question, not by statistical method.

### Data Handling
1. NEVER modify raw data files in `00_inputs/raw_data/` — they are immutable.
2. ALWAYS compute SHA-256 hashes for raw data files before use.
3. ALWAYS record data lineage in `03_synthesis/data_lineage.json` after every transformation.
4. For files >1GB: use polars lazy frames. NEVER use `pd.read_csv()` on large files.
5. For files >100MB: sample 10,000 rows for profiling.

### Directory Management
1. `research_init` creates the FULL directory structure — no pre-existing output dirs.
2. Every directory has a README.md with project-specific content.
3. Scripts are numbered in execution order (01_, 02_, 03_...) inside the active experiment `scripts/`.
4. Every generated output MUST have a sibling `.meta.yaml` with provenance.
5. Every figure MUST have an accompanying `.interpret.md` file.
6. `01_workspace/lab_notebook.md` is append-only.
7. Never delete previous iterations, decisions, or dead ends.

---

## First Steps

1. Run `rcp status` — check project state
2. Run `rcp scan` — scan inputs, build research map
3. Read `00_inputs/intake.md` — understand the research question
4. Read `rcp agent research_init` — get the agent instructions
5. Execute the research_init protocol
6. Continue through the pipeline, using `rcp intent` when the researcher wants to explore

---

## Branching

For divergent hypotheses:

```bash
rcp branch hypothesis_B --hypothesis "Bayesian approach"
# ... run analysis on branch ...
rcp branches          # List all branches
rcp merge hypothesis_B  # Merge findings back to main
rcp abandon hypothesis_B  # Or abandon exploratory branch
```

---

## Token Budget

| Threshold | Action |
|-----------|--------|
| <60% | Full context available |
| 60% | Summarize completed phases |
| 80% | Flush non-essential skill docs |
| 90% | Force checkpoint, generate CTM, split conversation |

At 90%, generate a Context Transfer Memorandum (CTM) to preserve context for the next conversation.
