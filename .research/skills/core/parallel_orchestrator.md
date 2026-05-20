# Parallel Orchestrator

## Purpose
Enables concurrent execution of independent research tasks (such as multiple research questions, sensitivity analysis variants, figure generation, or citation verification batches) to optimize speed and resource utilization while ensuring thread safety and data isolation.

## Protocol

### 1. Independence Assessment
Before executing tasks in parallel, verify that they are independent:
- **No Shared State:** They must not modify the same variables or shared state in memory.
- **No File Contention:** They must write to distinct, isolated file paths.
- **Resources:** Ensure there are sufficient system resources (CPU cores/memory) for the requested `max_workers`.

### 2. Isolated Workspace Allocation
Each parallel worker must operate in an isolated subdirectory to avoid conflicts:
- For research questions: `data/03_analytical/q{N}/` and `reports/analysis/q{N}/`.
- For figure generation: `reports/figures/q{N}/`.
- For table generation: `reports/tables/q{N}/`.

### 3. Execution Setup
Invoke the parallel runner script (`.research/scripts/utils/parallel_runner.py`):
```bash
python .research/scripts/utils/parallel_runner.py --tasks <tasks_json_file> --max-workers <num>
```
Tasks must be defined in a JSON file listing the script paths, arguments, and target output directories.

### 4. Concurrency Safety & State Locking
To prevent race conditions during parallel execution:
- **Ledger Writes:** Workers must never write directly to `state.json` or the research log concurrently. All ledger updates must be managed using a file lock mechanism (e.g., `portalocker` or a custom atomic rename-based lock).
- **Execution Log:** Log worker-specific tracebacks and outputs to temporary files inside their isolated workspace.
- **Error Handling:** If any single worker fails, capture its error traceback, log it to the dead ends registry under the worker's context, and mark the overall parallel run status as incomplete.

### 5. Transition to Synthesis
Once all parallel tasks finish execution:
1. Verify completion of all task outputs.
2. Read all worker results.
3. Pass control to the Synthesizer Skill (`synthesize_parallel_results.md`) to verify output integrity, check for contradictions, and merge outputs.
