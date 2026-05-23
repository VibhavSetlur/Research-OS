# Example Walkthrough: Analyzing Clinical Trial Data with Research OS

This document demonstrates how a researcher and an LLM agent interact using Research OS to analyze a dataset.

## Setup

1. **Researcher**: Opens a terminal in an empty directory `~/Projects/clinical_study`.
2. **Researcher**: Runs `python -m research_os.server`.
3. **Researcher**: Opens Cursor, Claude Code, or Antigravity and connects it to the MCP server.
4. **Researcher (in Chat)**: "Initialize the workspace for my new project: Efficacy of Drug X on Hypertension."

## Step 1: Scaffolding and Profiling

5. **Agent**: Calls `sys.workspace.scaffold` with project name "Efficacy of Drug X on Hypertension", then calls `sys.config.init` to create `inputs/researcher_config.yaml`.
   - *Behind the scenes*: Research OS creates the directory structure and initial documentation templates.
6. **Researcher**: Drops `trial_data.csv` (2GB) into `inputs/raw_data/`.
7. **Agent**: Calls `sys.workspace.scaffold` again (idempotent) or `sys.file.list` to discover the data.
8. **Agent**: Observes the `workspace/logs/data_inventory.json` file created by the profiling hook. It notes that the file is 2GB and estimated processing time is high.

## Step 2: Safe Exploration

9. **Agent**: Instead of writing a script to load the entire 2GB file, the agent calls `tool.data.sample`:
    - `filepath`: `inputs/raw_data/trial_data.csv`
    - `n_rows`: 1000
    - `strategy`: `random`
10. **Agent**: The tool returns a sampled dataset.
11. **Agent**: Calls `sys.path.create` to create the first experiment path (`01_baseline_eda`). Writes a Python script `workspace/01_baseline_eda/scripts/01_eda.py` to analyze the sampled data.
12. **Agent**: Calls `tool.python.exec` on the script.
13. **Agent**: Calls `mem.analysis.log` to append the initial EDA findings to `workspace/analysis.md`.

## Step 3: Immutability & Methodology

14. **Agent**: Decides to clean the data (handle missing values). It tries to write back to `inputs/raw_data/trial_data_cleaned.csv` using `sys.file.write`.
15. **Research OS**: Returns a `WriteProtectedError`.
16. **Agent**: Realizes its mistake, updates the script to save the cleaned data to `workspace/01_baseline_eda/data/cleaned_trial_data.csv`.
17. **Agent**: Calls `tool.log.decision`:
    - `context`: "Handling missing values in blood pressure readings."
    - `selected`: "Imputation via K-Nearest Neighbors."
    - `rationale`: "KNN imputation preserves the underlying distribution better than mean imputation for this dataset size."
18. **Agent**: Calls `mem.methods.append`: "Applied KNN imputation for missing blood pressure values."

## Step 4: Experiment Paths

19. **Researcher (in Chat)**: "Try running a Bayesian hierarchical model instead of the standard frequentist approach we discussed."
20. **Agent**: Recognizing this is a significant methodological shift, calls `sys.path.create`:
    - `name`: `bayesian_model`
21. This creates `workspace/03_bayesian_model/` (auto-numbered based on existing `0x_*` directories). The agent now works within this numbered experiment path.
22. **Agent**: Writes and executes `workspace/03_bayesian_model/scripts/bayesian_model.py`.
23. **Agent**: Calls `sys.checkpoint.create` after the model runs successfully.

## Step 5: Approval and Synthesis

24. **Agent**: Completes the analysis and calls `sys.checkpoint.pending`:
    - `description`: "Completed Bayesian hierarchical model."
    - `requires_approval`: true
25. **Researcher**: Reviews the generated figures and reports.
26. **Researcher (in Chat)**: "Looks good, proceed."
27. **Agent**: Calls `sys.checkpoint.approve`.
28. **Agent**: Generates a final report in `synthesis/paper.md` summarizing the methodology (pulled from `methods.md`), decisions (`decisions.log`), and findings (`analysis.md`).

This workflow ensures the researcher maintains control, the agent acts safely, and every step of the research process is rigorously documented.
