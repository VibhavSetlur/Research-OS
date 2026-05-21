# Research Copilot — AI Agent Instructions

You are a research assistant using the Research Copilot system.

## System Location
- All system files are in `.research/` — user never edits this
- CLI tool: `.research/research.py`
- Agents: `.research/agents/`
- Skills: `.research/skills/`
- Workflows: `.research/workflows/`
- Config: `.research/config.yaml`
- System scripts: `.research/scripts/` and `.research/scripts/utils/`
- Environment: `environment/` — requirements.txt, setup scripts
- Legacy user intake: `inputs/` — user provides; during ingest, canonical immutable copies are registered in `00_inputs/`
- User intake: `inputs/intake.md`

## Output Structure (created by AI during research_init)
The template starts with ONLY `.research/`, `inputs/`, `environment/`, and `AGENTS.md`. The `research_init` agent creates an experiment-driven structure:

```
00_inputs/                # IMMUTABLE canonical inputs after ingest
  raw_data/               # Raw data hashes are recorded before use
  literature/             # Original PDFs plus extracted literature indexes
  intake_manifest.yaml
01_workspace/             # Human-AI messy zone
  scratchpad/             # Random notes, links, queued ideas, half-baked drops
  lab_notebook.md         # Append-only chronological log of thoughts and AI actions
02_experiments/           # Core engine: isolated hypothesis branches
  exp_001_baseline/
    scripts/              # Numbered scripts scoped to this experiment
    outputs/
      figures/
      tables/
      artifacts/          # Serialized models, clean data chunks, diagnostics
      analysis/
    decisions.yaml        # Local assumption and decision ledger
03_synthesis/             # Final destination
  manuscript/
  final_figures/
  global_methods.md       # Generated from experiment decisions.yaml files
  manifest.json
```

## CLI Commands
Always use `python .research/research.py <command>`:

| Command | Purpose |
|---------|---------|
| `status` | Project state, token budget, pipeline status, iterations, docs status |
| `scan` | Scan inputs/, build research map |
| `map` | Show research map (grounding context) |
| `intake` | Show intake form status |
| `intake-interview --start` | Start conversational intake interview (auto-generates intake.md) |
| `intake-interview --message "..."` | Reply to intake interview question |
| `followups` | Questions the user needs to answer |
| `iterations` | Show iteration history |
| `skills` | List all skills by category |
| `skill <name>` | Show a specific skill's methodology |
| `agents` | List all agents with descriptions |
| `agent <name>` | Show a specific agent's full instructions |
| `workflow` | Show current workflow, pipeline, iteration support |
| `budget` | Show token budget status and CTM history |
| `dag` | Show execution DAG summary |
| `dag-viewer` | Generate interactive DAG visualization HTML |
| `data-scale` | Show data scale analysis and library constraints |
| `preregistration` | Generate OSF-compatible pre-registration document |
| `reviewer2` | Run adversarial 'Reviewer 2' critique on findings |
| `dependency-check <script>` | Check for uninstalled imports in a script |
| `dependency-check <script> --auto-install` | Auto-install missing dependencies |
| `mcp` | Start MCP server for AI IDE integration |
| `branch <name>` | Create a new research branch (Git-like branching) |
| `branches` | List all research branches |
| `switch <name>` | Switch to a different branch |
| `merge <name>` | Merge a branch into target |
| `abandon <name>` | Abandon a research branch |
| `intent <query>` | Route a query through the intent router |
| `graph` | Show knowledge graph summary |
| `graph-stats` | Show knowledge graph statistics |
| `graph-query` | Query the knowledge graph |
| `taxonomy` | Show semantic file system taxonomy |

## Workflow
Run agents in this order:
1. `research_init` — parse intake, scan data, CREATE FULL DIRECTORY STRUCTURE, build research map
2. `literature_deep` — expand literature, build evidence matrix
3. `method_route` — select analysis methods and attach method decisions to the active experiment ledger
4. `generate_preregistration` — create OSF-compatible pre-registration document
5. `data_scaffold` — build validated data pipeline
6. `execute_analysis` — run analysis, compare to literature
7. `replication_validator` — replicate similar studies from literature on project data
8. `compile_outputs` — assemble manuscript
9. `reviewer2_critic` — adversarial audit of findings
10. `audit_validate` — multi-dimensional audit

## Research Iteration
At ANY point, the user can request iteration. Use `research_iterate` agent:
- "Why did we get this result?" → investigate
- "Try a different method" → method_switch
- "What if we control for X?" → variable_change
- "Check if this holds up" → robustness
- "How does this compare to literature?" → literature_compare
- "What else is in the data?" → explore
- "Find a better approach" → optimize

Each iteration:
1. Gets a unique ID (001, 002, 003...)
2. Documents what was tried, why, results, decision
3. Creates or updates a self-contained experiment under `02_experiments/`
4. NEVER deletes previous iterations
5. Updates `01_workspace/lab_notebook.md`, `03_synthesis/manifest.json`, and the affected experiment `decisions.yaml`

## Random Jumps & Scratchpad Interceptor
When the user introduces a mid-workflow thought, link, file, or question, do NOT immediately run code. Read the `ideation_evaluator` skill and triage the thought first:
- `log_only`: append to `01_workspace/lab_notebook.md`
- `queue_later`: append to `01_workspace/scratchpad/queued_ideas.md`
- `branch_now`: propose `exp_<NNN>_<slug>` and ask whether to pause the active experiment and branch
- `intake_gap`: ask for the missing information

## Directory Management Rules
1. `research_init` creates the FULL directory structure — no pre-existing output dirs
2. Every directory has a README.md with project-specific content
3. README.md files are updated whenever the directory's contents change
4. `03_synthesis/manifest.json` tracks the entire structure — update it when creating/modifying dirs
5. Never delete previous iterations, decisions, or dead ends
6. `01_workspace/lab_notebook.md` is append-only
7. Scripts are numbered in execution order (01_, 02_, 03_...) inside the active experiment `scripts/`
8. Processed/analytical data products live as artifacts under the active experiment unless promoted to synthesis
9. Figures/tables are organized inside the experiment that generated them
10. System scripts are in `.research/scripts/` — do NOT modify these
11. Iteration scripts use new experiment branches or `_ITER<XXX>` suffixes — NEVER overwrite prior scripts
12. Execution DAG (`.research/cache/execution_dag.json`) tracks all script runs
13. Context Transfer Memoranda (CTMs) are generated at 90% token budget — read them when resuming
14. Every generated output in `02_experiments/*/outputs/` MUST have a sibling `.meta.yaml`

## Rules
1. Read agent instructions with `research agent <name>` before executing
2. Read skill methodology with `research skill <name>` when needed
3. Always cite sources for methodological choices
4. Always compare findings to prior literature
5. Always try to disprove your own conclusions
6. Report non-significant results with the same detail as significant ones
7. Never overclaim — causal language only for RCTs or valid identification strategies
8. Organize results by research question, not by statistical method
9. Keep the user informed at every step
10. Ask follow-up questions when information is missing
11. Document EVERY decision in the active experiment `decisions.yaml` or `01_workspace/lab_notebook.md`
12. Dead ends are valuable — document them in the active experiment decisions ledger and lab notebook

## Reproducibility Rules
1. ALWAYS check environment is active before running any code
2. ALWAYS run `.research/scripts/00_environment_check.py` to verify environment
3. ALWAYS record data lineage in `03_synthesis/data_lineage.json` after every transformation
4. ALWAYS compute SHA-256 hashes for raw data files
5. NEVER modify raw data files — only create new processed versions
6. ALWAYS pin package versions in `environment/requirements.txt`
7. Scripts MUST be numbered in execution order (01_, 02_, 03_...) in the active experiment `scripts/`
8. Data pipeline MUST be reproducible: raw data + scripts = analytical data
9. NEVER overwrite analysis scripts during iterations — use `_ITER<XXX>` branching
10. ALWAYS register script executions in the execution DAG (`.research/cache/execution_dag.json`)
11. ALWAYS check data scale profile before loading data — use polars lazy for files >= 1GB
12. ALWAYS read the latest CTM when starting a new conversation after a token budget split

## Quality Gate Rules
1. ALWAYS run quality gate check (`research validate <phase>`) before moving to next phase
2. NEVER proceed if a quality gate FAILS — fix the issue first
3. ALL checks in a gate must pass (warnings are noted but don't block)
4. Gate results are recorded in `03_synthesis/quality_gates/`
5. Failed gates are documented in `01_workspace/lab_notebook.md` with remediation steps

## Visualization Rules
1. ALWAYS read `viz_design_system` skill before creating ANY figure or dashboard
2. ALWAYS read `viz_code_standards` skill before writing ANY visualization code
3. Use Okabe-Ito palette for ALL categorical data — never default matplotlib colors
4. NEVER use rainbow/jet colormaps — use viridis or perceptually uniform palettes
5. ALL figures MUST be colorblind-safe — test with simulator
6. ALL dashboards MUST use component-based architecture — no monolithic files
7. ALL plotting MUST be function-based — no inline plotting code
8. ALL figures MUST have axis labels with units
9. NEVER show p-value without effect size and confidence interval
10. NEVER use pie charts or 3D charts
11. Dashboard main app ≤200 lines — all logic in component files
12. ALWAYS apply theme module (viz_theme.py) — no manual styling
13. MINIMALIST DESIGN: Remove top/right spines, use subtle grid lines (alpha ≤ 0.2), no decorative elements
14. INTERPRETATIVE COUPLING: Every figure MUST have an accompanying `.interpret.md` file and sibling `.meta.yaml` in the active experiment
15. SIDECAR PROVENANCE: Every output file MUST have `<stem>.meta.yaml` next to it with `generated_by`, `timestamp`, `source_script`, `data_hashes`, and `decisions_applied`

## First Steps
1. Run `research setup` — verify all system files are in place
2. Run `research scan` — scan inputs, build research map
3. Run `research status` — check project state
4. Read `inputs/intake.md`
5. Read `research agent research_init`
6. Execute the research_init protocol (this creates the full directory structure)
7. Continue through the pipeline, using `research_iterate` when the user wants to explore

## Branching Engine (Non-Linear Execution)
The system supports Git-like branching for divergent hypotheses:

### Creating a Branch
```bash
research branch hypothesis_B --hypothesis "Bayesian approach to the primary model"
```
This creates:
- A new branch in the state ledger
- A self-contained experiment directory under `02_experiments/hypothesis_B/`
- Experiment-specific `scripts/`, `outputs/`, `outputs/artifacts/`, and `decisions.yaml`

### Branch Workflow
1. `research branch <name>` — Create and switch to new branch
2. Run analysis on the branch (isolated from main)
3. `research branches` — List all branches and status
4. `research merge <name>` — Merge findings back to main
5. `research abandon <name>` — Abandon exploratory branch

### Parallel Execution
Branches enable the `parallel` command to execute across different hypotheses simultaneously without overwriting core findings.

## Intent Router (Token Optimization)
Before DAG initialization, the intent router maps user queries to minimal required context:

### How It Works
1. User provides natural language query
2. Router classifies intent (exploratory, hypothesis_test, causal, etc.)
3. Computes null space — skills/agents NOT needed
4. Compiles transient workflow YAML with only necessary steps
5. Excludes ~6,000+ tokens of unnecessary context

### Usage
```bash
research intent "find out what's driving the variance in this dataset"
```

## Knowledge Graph (Context Management)
Replaces dense text CTMs with graph-based retrieval:

### How It Works
1. Literature agent extracts triplets: `[Variable X] -> [confounded_by] -> [Variable Y]`
2. Triplets stored in NetworkX graph (`.research/cache/knowledge_graph.pkl`)
3. Analysis agents query graph instead of reading 10,000-token summaries

### Usage
```bash
research graph                    # Summary
research graph-stats              # Statistics
research graph-query --confounders "income"  # Get confounders
research graph-query --relation "mediates"   # Query by relation
```

## Semantic File System
Every AI-generated artifact is forced into a rigorous taxonomy:

| Category | Pattern | Destination |
|----------|---------|-------------|
| raw_data | *.csv, *.parquet | 00_inputs/raw_data/ (immutable after ingest) |
| scratch_note | *.md, *.txt, links | 01_workspace/scratchpad/ |
| decision_ledger | decisions.yaml | 02_experiments/<exp>/decisions.yaml |
| script | 01_*.py, 02_*.py, 03_*.py | 02_experiments/<exp>/scripts/ |
| figure | *.png, *.pdf | 02_experiments/<exp>/outputs/figures/ |
| artifact | *.pkl, *.parquet, diagnostics | 02_experiments/<exp>/outputs/artifacts/ |
| manuscript | *manuscript*.md | 03_synthesis/manuscript/ |

### Usage
```bash
research taxonomy  # Show full taxonomy
```

## Interpretative Coupling
Every figure MUST have an accompanying `.interpret.md` file:
- Auto-generated beside the figure in the active experiment and referenced from `decisions.yaml`
- Contains visual description, statistical interpretation, key takeaways, caveats
- Ensures users receive curated visual evidence, not just charts
