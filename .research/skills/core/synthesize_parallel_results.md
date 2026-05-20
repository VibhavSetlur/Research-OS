# Synthesize Parallel Results

## Purpose
Merges outputs from parallel analysis runs, verifies results integrity, detects potential logical or empirical conflicts, and updates the central research map and state ledger.

## Protocol

### 1. Integrity Verification
Before merging, confirm that all parallel tasks executed successfully:
- Read the parallel execution results JSON (`*_results.json`).
- Verify that every worker task has a `success: true` flag.
- Compute SHA-256 hashes of generated task outputs and cross-check against recorded values (if available in lineage logs).

### 2. Conflict Detection
Analyze the findings from the independent question directories (`reports/analysis/q{N}/`):
- **Contradictory Effects:** Check if Q{N} and Q{M} analyze the same outcome variable and predictors but yield contradictory coefficient signs or directional claims.
- **Varying Significance:** Detect cases where the same effect is highly significant in one subset/specification but non-significant in another, and log this difference.
- **Robustness Discrepancies:** Detect if a model passes sensitivity tests in one worker but fails in another.
- **Reporting:** If conflicts are detected, flag them clearly in the combined output report as critical warnings.

### 3. Consolidation & Merging
- Merge individual question result JSON files into a single, unified `reports/analysis/combined_results.json`.
- Structure the consolidated payload by research question ID.
- Include metadata about the parallel run (execution date, total elapsed time, success rate).

### 4. Research Map Update
Update `reports/baseline/research_map.json` or `docs/manifest.json`:
- Mark status of analyzed questions as `completed`.
- Populate outcome findings, effect sizes, p-values, and confidence intervals under each question.

### CLI Reference
```bash
python .research/scripts/utils/synthesize_results.py --results-file <results_json_path>
```
