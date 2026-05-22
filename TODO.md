Now I have a thorough understanding of the codebase and the latest best practices. Below is a comprehensive, production‑grade TODO for the next building stage.

---

# TODO.md — Research OS: Pre‑Release Build Plan

*Generated: 2026-05-23 | Status: In‑Build (pre‑v1.0)*

---

## 🏗️ DIAGNOSIS: Current State Summary

The repository has been **successfully cleansed** of autonomous‑agent dead code. The `src/research_os/` directory now has a clean structure with 10 YAML guidance protocols, a working MCP server, and a state management layer. However, significant gaps remain before the system delivers on the "research‑grade AI guidance" vision.

### What's Working
- MCP stdio server with 28 tool definitions (`server.py`)
- 10 YAML guidance protocols in `protocols/`
- State ledger, checkpoint manager, branch operations (`state/`, `project_ops.py`)
- File I/O, python exec, LaTeX compile tools (`tool_impls.py`)
- Token budget tracker (`runtime/token_budget.py`)
- IDE integration docs (`IDE_INTEGRATION.md`)

### What's Broken / Missing
- **Protocols are thin** (~20‑25 lines each) — mostly prompt templates, not actionable decision graphs with library references, output schemas, and error recovery paths
- **No researcher configuration system** — no beginner/advanced/‑publication interaction levels, no HITL toggle, no API key onboarding
- **Many tool handlers are stubs** — `tool.search.web`, `tool.search.semantic_scholar`, `tool.search.pubmed`, `tool.search.crossref`, `tool.web.scrape` return placeholder messages
- **`memory/` has 7 files** but most are thin stubs or unused autonomous‑agent remnants
- **`runtime/` hooks and interceptors** still reference autonomous‑agent patterns (`pre_routing`, `pre_execution`, `emergency_synthesize`)
- **No `AGENTS.md` or `.cursor/rules/` templates** for researchers to give their IDE AI
- **No data size / task duration estimation** — AI cannot warn users about long‑running operations
- **Missing `research_design.yaml` and `writing_standards.yaml`** — referenced in docs but absent from `protocols/`
- **No researcher onboarding flow** — no API key collection for Firecrawl/Semantic Scholar/PubMed, no external MCP server detection
- **`prompts/` directory is empty** — ideal location for researcher config templates

### What Needs Full Redesign
- **Protocol depth** — current YAMLs are conversational prompts. They need to be structured decision trees with conditionals, output schemas, external library references, and checkpoints.
- **Researcher interaction model** — needs a configuration file where researchers set their preferred autonomy level, notification thresholds, and API keys.
- **Token‑efficient tool discovery** — 28 tools listed eagerly. Need 2‑tier lazy loading (summary → full schema on demand) per SEP‑1576 patterns.

---

## 🔴 PHASE 0: IMMEDIATE FIXES — Make the System Functional

### 0.1 Implement Stub Tool Handlers
- [ ] **`tool.search.web`** — Integrate Firecrawl API as primary backend. Read API key from researcher config. Log all queries to `workspace/logs/searches.log`. Return structured results (title, URL, snippet, timestamp).
- [ ] **`tool.search.semantic_scholar`** — Wire to Semantic Scholar Academic Graph API. Implement rate limiting (1 req/sec). Return structured paper objects with `paperId`, `title`, `authors`, `year`, `abstract`, `citationCount`, `url`.
- [ ] **`tool.search.pubmed`** — Wire to NCBI Entrez API. Implement MeSH term expansion. Respect rate limits (3 req/sec without API key, 10 req/sec with).
- [ ] **`tool.search.crossref`** — Wire to Crossref REST API for citation verification and metadata lookup.
- [ ] **`tool.web.scrape`** — Implement via Firecrawl scrape endpoint or BeautifulSoup fallback. Return cleaned markdown. Log scrape URL and timestamp.
- [ ] **`tool.literature.download`** — Implement PDF download with legal check (open access only unless user configures institutional access). Save to `inputs/literature/`. Update `inputs/literature_index.yaml`.
- [ ] **`sys.checkpoint.create`** / **`sys.checkpoint.rollback`** / **`sys.checkpoint.list`** — Wire to `checkpoint_manager.py` (currently return stub messages).
- [ ] **`sys.branch.switch`** / **`sys.branch.merge`** — Implement full branch switching and merging logic.
- [ ] **`tool.package.install`** — Wire to `pip install` with environment pinning.
- [ ] **`tool.env.freeze`** — Snapshot current environment to step's `environment/requirements.txt`.
- [ ] **`tool.env.restore`** — Restore from step's `environment/requirements.txt`.

### 0.2 Clean Up Dead Modules
- [ ] **Evaluate `memory/` files.** `artifact_memory.py` (8 lines — thin stub), `episodic_memory.py`, `procedural_memory.py`, `retrieval_policies.py`, `semantic_memory.py`, `memory_synthesizer.py`, `synthesis_watcher.py` — most are autonomous‑agent remnants. Either **consolidate into a single `workspace_logger.py`** or delete the unused ones.
- [ ] **Evaluate `runtime/` files.** `hooks.py` (105 lines) is a lifecycle hook engine designed for autonomous agents. `interceptors.py` likely follows the same pattern. `runtime_selector.py` — what does it select? If these are not wired into the MCP server, **delete or archive to `/legacy/`**.
- [ ] **Evaluate `core/__init__.py`** — imports `hook_engine` from runtime/hooks.py. If hooks are deleted, update this import.
- [ ] **Delete or repurpose `prompts/__init__.py`** — currently empty. This directory should hold researcher configuration templates (see Phase 1).

### 0.3 Create Missing Protocols
- [ ] **Create `research_design.yaml`** — Maps research question types (causal, predictive, exploratory, descriptive, evaluative) to formal designs (RCT, cohort, case‑control, cross‑sectional, quasi‑experimental, DiD, RDD, IV, systematic review, meta‑analysis). Include: conditions for each design, required data characteristics, common threats to validity, and external library references (DoWhy, EconML, statsmodels).
- [ ] **Create `writing_standards.yaml`** — Detailed guidance for each IMRAD section, APA/STROBE/CONSORT/PRISMA formatting, abstract structure, title conventions, keyword selection, and non‑causal language enforcement. Include citation format rules and cross‑reference to `audit_and_validation.yaml`.

---

## 🟡 PHASE 1: RESEARCHER CONFIGURATION & INTERACTION SYSTEM

### 1.1 Researcher Config File (`inputs/researcher_config.yaml`)

- [ ] **Create `sys.config.init` tool** — On first run (or when `inputs/researcher_config.yaml` is missing), prompt the AI to walk the researcher through setup. The AI asks questions via chat; the OS stores answers.

**Config Schema:**

```yaml
# Researcher Configuration v1.0
# Generated by sys.config.init

researcher:
  name: ""                    # How the AI addresses you
  expertise_level: "intermediate"  # beginner | intermediate | advanced | pi
  field: ""                   # Primary research domain
  institution: ""             # Optional
  orcid: ""                   # For publication metadata

interaction:
  autonomy_level: "supervised"     # supervised | semi_autonomous | autonomous
  # supervised:     AI proposes every action, researcher must approve
  # semi_autonomous: AI auto-executes standard steps, asks at key decision points
  # autonomous:     AI executes full pipeline, notifies at milestones only
  
  checkpoint_frequency: "after_each_step"  # after_each_step | after_branch | manual
  notification_preferences:
    on_step_complete: true
    on_error: true
    on_decision_required: true
    on_long_running_task: true    # Warn when task estimated > N seconds
    long_running_threshold_seconds: 300

api_keys:
  firecrawl: ""               # For web search and scraping
  semantic_scholar: ""        # Optional — higher rate limits
  pubmed_api_key: ""          # Optional — higher rate limits
  serpapi: ""                 # Alternative web search backend
  openai: ""                  # If AI model needs API access
  anthropic: ""               # If AI model needs API access

external_mcp_servers:
  # Other MCP servers the AI can discover and use
  - name: ""                  # e.g., "firecrawl-mcp"
    command: ""               # e.g., "npx"
    args: []                  # e.g., ["-y", "firecrawl-mcp"]

research_quality:
  target_venue: "journal"     # preprint | conference | journal | dissertation | report
  reporting_standard: "auto"  # auto | strobe | consort | prisma | apa | nature
  figure_dpi: 300
  reproducibility_level: "full"  # full | standard | minimal
  # full:     Pinned env, checksums, Dockerfile, full audit
  # standard: Pinned env, checksums, audit
  # minimal:  Basic versioning only
```

- [ ] **Implement `sys.config.get` / `sys.config.set` tools** — Read/write specific config values so the AI can reference researcher preferences during execution.
- [ ] **Implement `sys.config.validate`** — Verify API keys are functional, external MCP servers are reachable.

### 1.2 Interaction Level Behaviors

- [ ] **Supervised Mode:** Before every tool call that modifies data or begins a new experiment, the AI MUST call `sys.checkpoint.pending` which returns a summary of the proposed action and requires explicit researcher approval via `sys.checkpoint.approve`. The OS blocks execution until approved.
- [ ] **Semi‑Autonomous Mode:** Standard data profiling, literature search, and figure generation auto‑execute. The AI pauses and requests approval only at branch points (new experiment, methodology change, synthesis).
- [ ] **Autonomous Mode:** Full pipeline execution with milestone notifications. The AI still logs every decision to `mem.analysis.log` for post‑hoc review.
- [ ] **Implement `sys.notify` tool** — Writes a notification to `workspace/logs/notifications.log` and (if configured) triggers IDE notification for the researcher to review.

### 1.3 API Key & External MCP Integration

- [ ] **`tool.search.web` detects Firecrawl key** from config. If present, uses Firecrawl; falls back to SerpAPI; falls back to a notice that web search is unavailable.
- [ ] **`sys.external_mcp.discover`** — Scans researcher config for external MCP servers and attempts connection. Returns available external tools the AI can leverage.
- [ ] **Onboarding assistant in `prompts/onboarding_prompt.md`** — A template prompt the AI uses to walk the researcher through first‑time setup conversationally: "Welcome to Research OS! I'll help you configure your research environment. First, what's your primary research domain?"

---

## 🟡 PHASE 2: DEEPEN GUIDANCE PROTOCOLS

### 2.1 Protocol Format Upgrade

Current protocols are linear prompt lists. They need to become structured decision resources with:

**New Protocol Schema:**

```yaml
name: domain_analysis
version: "2.0"
description: "Full protocol description"

# When the AI should fetch this protocol
triggers:
  - "new project initialization"
  - "user provides new data or context files"
  - "research question changes"

# What the AI needs BEFORE running this protocol
prerequisites:
  required_inputs: ["inputs/raw_data/", "inputs/context/"]
  optional_inputs: ["inputs/intake.md", "inputs/literature/"]

# The decision tree
decision_tree:
  - node: analyze_inputs
    description: "Extract domain signals from all input files"
    action:
      tool: "sys.file.list"
      params: {directory: "inputs/"}
    then:
      - condition: "data_files > 0"
        goto: classify_domain
      - condition: "data_files == 0"
        output: "No data files found. Ask researcher to add data to inputs/raw_data/."

  - node: classify_domain
    description: "Map extracted keywords to domain profile"
    reasoning_prompt: |
      Based on the file names, extensions, column headers, and any context
      documents, classify the research domain. Consider:
      - File types: {file_types}
      - Column names: {column_sample}
      - Context keywords: {context_keywords}
      
      Map to ONE of: epidemiology | clinical_trials | economics | 
      machine_learning | natural_language_processing | bioinformatics |
      psychology | sociology | physics | chemistry | engineering | other
    output_schema:
      domain: string
      confidence: 0.0-1.0
      evidence: list[string]
      suggested_standards: list[string]

  - node: select_standards
    description: "Map domain to reporting standards"
    domain_standards_map:
      epidemiology: ["STROBE"]
      clinical_trials: ["CONSORT"]
      systematic_review: ["PRISMA"]
      economics: ["AEA Guidelines"]
      machine_learning: ["ML Reproducibility Checklist", "PapersWithCode"]
    then:
      - goto: identify_pitfalls

  - node: identify_pitfalls
    description: "Common domain-specific methodological pitfalls"
    pitfalls_by_domain:
      epidemiology: ["confounding by indication", "immortal time bias", "selection bias"]
      machine_learning: ["data leakage", "overfitting", "distribution shift"]
      economics: ["endogeneity", "simultaneity", "omitted variable bias"]
    output: "Checklist of pitfalls to monitor"

# What the AI produces after following this protocol
outputs:
  - file: "workspace/logs/domain_analysis.md"
    format: "markdown"
    template: |
      # Domain Analysis Report
      **Domain:** {domain}
      **Confidence:** {confidence}
      **Evidence:** {evidence}
      **Reporting Standards:** {suggested_standards}
      **Pitfalls to Monitor:** {pitfalls}
    destination: "workspace/logs/domain_analysis.md"

# Verification
checkpoints:
  - "Does the domain align with the data provided?"
  - "Are reporting standards appropriate for the domain?"
```

### 2.2 Rewrite All 10 Protocols to v2 Depth

- [ ] **Rewrite `domain_analysis.yaml`** — Full decision tree with domain‑standards mapping, pitfall database, output templates (as shown above).
- [ ] **Rewrite `research_design.yaml`** — Decision tree mapping 5 question types → 12 research designs with validity threats, required data structures, and library references.
- [ ] **Rewrite `methodology_selection.yaml`** — Multi‑branch decision tree: data type → distribution characteristics → dependency structure → recommended method. Include assumption lists and external library references (statsmodels, scipy, scikit‑learn, DoWhy, pymer4, lifelines, pymc).
- [ ] **Rewrite `literature_search.yaml`** — Add query building strategies by database, deduplication algorithm, snowballing depth configuration, PRISMA flow diagram generation, and quality assessment rubrics (AMSTAR, CASP, ROB‑2).
- [ ] **Rewrite `evidence_synthesis.yaml`** — Add claim extraction templates, evidence strength scoring rubric (sample size, effect magnitude, p‑value, study design weight), evidence matrix format, and contradiction flagging rules.
- [ ] **Rewrite `analysis_plan.yaml`** — Add experiment numbering conventions, README templates for each experiment step, branching criteria decision tree, and merge resolution strategy.
- [ ] **Rewrite `figure_guidelines.yaml`** — Add chart type selection matrix (data type × message type → chart type), color palette selection by data type and accessibility requirements, DPI/resolution requirements by target venue, and code generation templates for matplotlib/seaborn/plotly.
- [ ] **Rewrite `writing_standards.yaml`** — Add IMRAD section‑by‑section guidance with word budgets, tense conventions, citation placement rules, and non‑causal language enforcement rules with example rewrites.
- [ ] **Rewrite `reproducibility.yaml`** — Add environment pinning checklist, seed verification, path relativity check, checksum generation, and clean‑environment re‑run verification.
- [ ] **Rewrite `audit_and_validation.yaml`** — Add 3‑pass citation verification algorithm (existence → content → retraction), causal language scanner regex rules, statistical assumption re‑check against methods.md, and code quality linter configuration.

### 2.3 Add Protocol Versioning & Caching

- [ ] **Add `version` field to every protocol YAML.** Track in `workspace/.os_state/protocol_versions.json`.
- [ ] **`sys.guidance.get` checks cached version.** If the protocol has been updated, returns the new version and marks old cached context as stale.
- [ ] **Protocols are loaded lazily** — only when the AI calls `sys.guidance.get`. Descriptions (first 2 lines) are returned by `sys.guidance.list`.

---

## 🟡 PHASE 3: TOKEN‑EFFICIENT TOOL DISCOVERY

### 3.1 Two‑Tier Lazy Loading Pattern

Current: 28 tools × ~150 tokens/tool = ~4,200 tokens eagerly loaded.

Target pattern:

| Tier | Tool | Tokens | Description |
|------|------|--------|-------------|
| **Tier 1 (eager)** | `sys.guidance.list` | ~300 | Returns lightweight tool catalog: name + one‑line summary |
| **Tier 2 (lazy)** | `sys.tool.info` | ~500 | Returns full schema for a specific tool on demand |

- [ ] **Refactor `list_tools()` in `server.py`** — Instead of returning full `TOOL_DEFINITIONS`, return only Tier 1 summaries:
  ```python
  {
    "name": "tool.search.semantic_scholar",
    "summary": "Search academic papers via Semantic Scholar API",
    "category": "search",
    "cost": "low"
  }
  ```
- [ ] **Add `sys.tool.info` tool** — Accepts tool name, returns full `inputSchema` + `description`. The AI calls this only when it needs a specific tool.
- [ ] **Add `sys.tool.search` tool** — Accepts a semantic query ("I need to search for academic papers"), returns top‑3 matching tools with summaries. Uses simple keyword matching (no vector DB needed for 28 tools).
- [ ] **Token savings estimate:** 28 tools × 50 tokens (summary) = ~1,400 tokens vs 4,200 = **67% reduction**. After adding 10 more tools: 38 × 50 = ~1,900 tokens vs 5,700 = same ratio.

### 3.2 Tool Categories for Better Discovery

- [ ] **Tag every tool with a category** in `TOOL_DEFINITIONS`:
  - `guidance` — protocol loading tools
  - `workspace` — file/scaffold tools
  - `state` — state/branch/checkpoint tools
  - `memory` — logging tools
  - `search` — literature/web search tools
  - `execution` — code/package/env tools
  - `audit` — validation tools
- [ ] **`sys.guidance.list` returns tools grouped by category** for the AI to reason over.

---

## 🟢 PHASE 4: DATA AWARENESS & TASK DURATION ESTIMATION

### 4.1 Data Profiling on Ingestion

- [ ] **`sys.workspace.scaffold` auto‑runs `_profile_inputs()`** that scans `inputs/raw_data/` and produces `workspace/logs/data_inventory.json`:
  ```json
  {
    "files": [
      {
        "path": "inputs/raw_data/survey.csv",
        "size_mb": 45.2,
        "rows": 250000,
        "columns": 18,
        "column_names": ["age", "income", "education", ...],
        "dtypes": {"age": "int64", "income": "float64", ...},
        "missing_pct": {"income": 3.2, "education": 0.1},
        "sha256": "abc123..."
      }
    ],
    "total_size_mb": 45.2,
    "estimated_processing_time_seconds": 30
  }
  ```
- [ ] **Estimate processing time** using a simple heuristic: rows × columns × 0.0001 seconds for basic ops, 0.001 for statistical tests, 0.01 for ML models. Multiply by 3 for safety margin.

### 4.2 Long‑Running Task Warnings

- [ ] **Before `tool.python.exec`**, estimate script runtime based on data inventory. If estimated > `long_running_threshold_seconds` from config, return a warning:
  ```json
  {
    "status": "warning",
    "estimated_runtime_seconds": 600,
    "message": "This script may take ~10 minutes. Continue?",
    "requires_approval": true  // if in supervised mode
  }
  ```
- [ ] **`sys.task.monitor`** — If a script runs longer than estimated × 1.5, log a warning and notify the researcher (per their notification preferences).
- [ ] **`sys.task.kill`** — Allow the researcher or AI to terminate a long‑running script.

### 4.3 Data Chunking for Large Files

- [ ] **When data > 100MB**, `tool.python.exec` should suggest chunking strategies before execution. Add a `chunk_size` parameter.
- [ ] **`tool.data.sample`** — Extract a representative sample for exploratory work: stratified sampling, first N rows, or random sample with seed.

---

## 🟢 PHASE 5: RESEARCHER‑FACING DOCUMENTATION & AGENT RULES

### 5.1 AGENTS.md Template

- [ ] **Create `templates/AGENTS.md`** in the repository root. This is a copy‑paste file for researchers to drop into their project. Content:

```markdown
# AGENTS.md — Research OS Instructions for Your AI Agent

## System Identity
You are a rigorous research assistant powered by Research OS. You follow
structured guidance protocols, never hallucinate methods, and always ground
your work in the researcher's inputs and verified literature.

## Core Rules
1. **Never guess.** If you don't know the appropriate method, load the
   relevant guidance protocol via `sys.guidance.get`.
2. **Always ground.** Every claim must cite a source from the literature
   search or the researcher's context files.
3. **Always log.** Use `mem.analysis.log` after every significant step.
4. **Always verify.** Before final output, run `audit_and_validation`.
5. **Respect configuration.** Check `inputs/researcher_config.yaml` for
   autonomy level and notification preferences.

## Tool Usage Priority
1. Start with `sys.guidance.list` to see available protocols.
2. Load the relevant protocol with `sys.guidance.get`.
3. Use `sys.state.summary` to understand current progress.
4. Execute tools following the protocol's decision tree.
5. Log every decision with `tool.log.decision`.

## Writing Standards
- Use IMRAD structure for manuscripts.
- Never use causal language for associational findings.
- Report statistics in APA format: t(df) = X.XX, p = .XXX.
- Every figure must have labeled axes and error bars where applicable.

## Researcher Config
The researcher has set:
- Autonomy: {autonomy_level}
- Notification: {notification_preferences}
- Quality target: {target_venue}
```

- [ ] **Create `templates/.cursor/rules/research-os.mdc`** — Cursor‑specific rules file with the same content in MDC format.
- [ ] **Create `templates/.windsurf/rules/research-os.md`** — Windsurf‑specific rules.

### 5.2 Researcher Guide Rewrite

- [ ] **Rewrite `docs/RESEARCHER_GUIDE.md`** to cover:
  - First‑time setup: config interview flow
  - Interaction levels explained with concrete examples
  - How to add data, context, literature to `inputs/`
  - How to read `workspace/analysis.md` and workflow diagrams
  - How to interpret `workspace/logs/searches.log` for provenance
  - How to branch, rollback, and merge
  - How to trigger synthesis and what to review before publication
  - Common troubleshooting (API key issues, tool not found, etc.)

### 5.3 Example Walkthrough

- [ ] **Rewrite `docs/EXAMPLE_WALKTHROUGH.md`** as a complete session transcript:
  1. Researcher: "I have a CSV of patient outcomes. Analyze it."
  2. AI loads `domain_analysis` → identifies epidemiology → suggests STROBE
  3. AI loads `methodology_selection` → profiles data → recommends logistic regression
  4. AI creates `01_experiment_baseline/` via `sys.branch.create`
  5. AI writes analysis script, executes via `tool.python.exec`
  6. AI logs findings to `mem.analysis.log`, generates figures
  7. Researcher: "Branch and try a survival analysis instead."
  8. AI branches to `02_survival_analysis/`, runs Cox PH
  9. Researcher: "I'm satisfied. Write the paper."
  10. AI runs `writing_standards` and `audit_and_validation`, compiles PDF

### 5.4 AI Integration Docs

- [ ] **Add to `docs/AI_INTEGRATION.md`:** protocol decision tree format, config file reference, token‑efficient discovery pattern, error recovery strategies.
- [ ] **Add to `docs/GUIDANCE_SYSTEM.md`:** the v2 protocol format, how to read decision trees, how the AI should handle conditionals and branches.

---

## 🟢 PHASE 6: DIRECTORY STRUCTURE REFINEMENTS

### 6.1 Final Workspace Structure

Based on the existing `project_ops.py` and the researcher needs identified, the final structure should be:

```
<user-project>/
├── AGENTS.md                          # AI agent instructions (from template)
├── README.md                          # Auto-generated project overview
├── .cursor/rules/research-os.mdc      # Cursor-specific rules
├── .os_state/                         # INTERNAL — OS state
│   ├── state_ledger.yaml              # Source of truth
│   ├── state_ledger.json              # Legacy fallback
│   ├── manifest.json                  # Full file inventory with checksums
│   ├── checkpoints/                   # Workspace snapshots
│   ├── cache/                         # API response cache
│   └── protocol_versions.json         # Protocol version tracking
├── docs/                              # Human-written research docs
│   ├── research_question.md
│   ├── hypotheses.md
│   └── glossary.md
├── inputs/                            # IMMUTABLE — researcher provided
│   ├── researcher_config.yaml         # Researcher preferences & API keys
│   ├── raw_data/                      # Source data (or symlinks)
│   ├── literature/                    # PDFs
│   ├── context/                       # Notes, past results, text files
│   ├── intake.md                      # Auto-generated research brief
│   └── literature_index.yaml          # Filename → citation key mapping
├── workspace/                         # ACTIVE — iterative experiments
│   ├── methods.md                     # Append‑only method log
│   ├── analysis.md                    # Chronological log + Mermaid workflow
│   ├── citations.md                   # Running bibliography with verified flags
│   ├── logs/
│   │   ├── searches.log               # Every web search logged (JSON lines)
│   │   ├── state_changes.log          # Before/after state diffs
│   │   ├── notifications.log          # Researcher notifications
│   │   ├── data_inventory.json        # Auto‑profiled data inventory
│   │   └── <step>.log                 # Per‑step execution logs
│   ├── workflow.mermaid               # Auto‑updated workflow diagram
│   ├── workflow.png                   # Rendered diagram
│   ├── 01_experiment_baseline/
│   │   ├── README.md                  # Goal, hypotheses, outcomes
│   │   ├── conclusions.md             # Key findings, bugs, routing decisions
│   │   ├── methods_research.md        # AI's research into methods for this step
│   │   ├── data/                      # Derived data
│   │   ├── scripts/                   # Versioned (01_..._v1.py)
│   │   ├── outputs/
│   │   │   ├── reports/
│   │   │   ├── figures/
│   │   │   ├── tables/
│   │   │   └── dashboards/
│   │   └── environment/               # Pinned dependencies
│   ├── 02_...
│   └── .os_state/                     # Symlink to root .os_state/
├── synthesis/                         # FINAL — populated on completion
│   ├── abstract.md
│   ├── paper.tex / paper.pdf
│   ├── references.bib
│   ├── workflow_diagram.png
│   └── supplementary/
└── environment/                       # Global environment
    ├── requirements.txt
    └── Dockerfile
```

### 6.2 Update `project_ops.py`

- [ ] **Update `scaffold_minimal_workspace`** to create all directories above including `inputs/researcher_config.yaml` template, `templates/` copy, and `.cursor/rules/`.
- [ ] **Add `inputs/` immutability enforcement** — any tool that attempts to write to `inputs/raw_data/` or `inputs/literature/` raises `WriteProtectedError`. Only `inputs/intake.md`, `inputs/literature_index.yaml`, and `inputs/researcher_config.yaml` are writable.
- [ ] **Add `workspace/.os_state/` as symlink** to root `.os_state/` for tools that reference state from workspace context.

---

## 🔵 PHASE 7: TESTING, CI/CD & PACKAGING

### 7.1 Testing

- [ ] **Unit tests for every tool handler** — at minimum: `sys.file.read/write/list/delete`, `sys.state.get/summary`, `sys.branch.create`, `mem.analysis.log`, `mem.methods.append`, `tool.python.exec`, `tool.log.decision`.
- [ ] **Integration test** — full pipeline: `scaffold` → `domain_analysis` protocol → `branch.create` → write script → `python.exec` → `mem.analysis.log` → `synthesis`.
- [ ] **Mock API tests** for `tool.search.*` tools — mock Semantic Scholar, PubMed, Crossref, Firecrawl responses.
- [ ] **Snapshot tests** for protocol loading, state ledger serialization, manifest generation.

### 7.2 CI/CD

- [ ] **GitHub Actions workflow** — runs tests on Python 3.10, 3.11, 3.12.
- [ ] **Pre‑commit hooks:** ruff, mypy, and a custom hook that validates YAML protocol format.
- [ ] **Auto‑generate `docs/MCP_TOOLS_REFERENCE.md`** from `TOOL_DEFINITIONS` on every push.

### 7.3 Packaging

- [ ] **`pyproject.toml`** — add optional dependency groups: `[web]` for Firecrawl/SerpAPI, `[literature]` for scholarly/semanticscholar/metapub, `[viz]` for matplotlib/seaborn/plotly, `[all]`.
- [ ] **Publish to PyPI as `agentic-research-os`** when ready.

---

## 📋 PHASE 8: ROLLOUT SEQUENCE

| Priority | Phase | Tasks | Effort |
|----------|-------|-------|--------|
| 🔴 | **Phase 0: Immediate Fixes** | Stub handlers, dead module cleanup, missing protocols 
| 🟡 | **Phase 1: Researcher Config** | Config system, interaction levels, API key onboarding 
| 🟡 | **Phase 2: Protocol Depth** | Rewrite all 10 protocols to v2 decision tree format 
| 🟡 | **Phase 3: Token Efficiency** | 2‑tier lazy loading, tool categories, `sys.tool.info` 
| 🟢 | **Phase 4: Data Awareness** | Data profiling on ingestion, duration estimation, chunking 
| 🟢 | **Phase 5: Docs & Rules** | AGENTS.md, cursor rules, researcher guide, walkthrough 
| 🟢 | **Phase 6: Directory** | Finalize structure, update scaffold, immutability enforcement 
| 🔵 | **Phase 7: Testing & CI** | Tests, GitHub Actions, pre‑commit, packaging 

**Total estimated: ~6 weeks for a fully functional pre‑v1.0 system.**

---

## 🎯 CRITICAL PATH: What to Do First

1. **Implement stub handlers (Phase 0.1)** — the system is a hollow shell without working web search, literature retrieval, and checkpoint operations.
2. **Build researcher config system (Phase 1)** — all other features (interaction levels, API keys, notifications) depend on this.
3. **Rewrite protocols to v2 depth (Phase 2)** — thin protocols are the #1 gap between "a tool server" and "a research guidance engine."
4. **Implement lazy tool discovery (Phase 3)** — without this, adding more tools will bloat every chat session.

---

*End of TODO.md — Commit this file to the repository root. Track completion by checking boxes. The system is ready for first release when all Phase 0‑4 boxes are checked.*