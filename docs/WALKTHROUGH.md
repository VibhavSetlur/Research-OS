# Research OS: End-to-End Walkthrough

This walkthrough demonstrates how to use Research OS for a realistic research project from start to finish. We will be analyzing a dataset on air pollution and its effects on respiratory health.

## 1. Setup Your Environment

First, install Research OS with all features, create a project, and start the server:

```bash
# Install Research OS with all optional features
pip install "research-os[all] @ git+https://github.com/VibhavSetlur/Research-OS.git"

# Create a project directory
mkdir air-pollution-research
cd air-pollution-research

# Initialize the workspace
research-os init --name "Air Pollution and Respiratory Health"

# Start the MCP Server
research-os start --workspace .
```

Connect your AI IDE (like Cursor or Claude Desktop) to the running MCP server.

## 2. Ingest Data and Context

1. Drop your dataset (e.g. `air_quality_health_impacts.csv`) into `inputs/raw_data/`.
2. Add any background literature or PDFs into `inputs/literature/`.

## 3. Guide Your AI IDE

Once your IDE is connected, open a new chat and simply copy-paste these prompts in order:

### Prompt 1: Initial Discovery
> "Explore my data. Please load the `air_quality_health_impacts.csv` dataset from `inputs/raw_data/` and provide a high-level summary of the columns, missing values, and potential hypotheses we can explore."

*Research OS will invoke `sys.workspace.scaffold` (if not done) or `tool.python.exec` to run exploratory data analysis (EDA).*

### Prompt 2: Methodological Planning
> "Based on the EDA, let's create a formal analysis plan. Use `sys.guidance.get` to load the `data_analysis` protocol and apply it to our research questions. What statistical tests are appropriate for determining the effect of PM2.5 levels on respiratory health metrics?"

### Prompt 3: Execute Baseline Experiment
> "Use `sys.path.create` to create our first experiment folder (e.g., `01_baseline_analysis`). Write a Python script to clean the data and perform a baseline regression analysis. Save the script in the `scripts/` folder of this new path and save the regression results in the `outputs/reports/` folder."

### Prompt 4: Log Decisions
> "Let's log our decision to use linear regression. Please use `log-decision` (or `tool.log.decision`) to record why we chose this method and why we handled missing values the way we did."

### Prompt 5: Literature & Context
> "Search PubMed for recent papers (from the last 3 years) on PM2.5 and respiratory hospital admissions. Download the top 2 relevant papers to `inputs/literature/` and summarize their findings."

### Prompt 6: Synthesis and Reporting
> "We are ready to synthesize our findings. Use `tool.synthesize` to generate a markdown report of our methodology, results, and literature context into the `synthesis/` directory."

By following this chronological path, all of your methods, decisions, code, and data transformations will be rigorously documented, making your research entirely reproducible.
