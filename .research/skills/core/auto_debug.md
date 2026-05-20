# Auto-Debugging Sandbox

## Purpose
When any Python script fails, automatically capture the error, diagnose the issue, rewrite only the failing function, and retry. Max 3 iterations before creating a dead end entry.

## Invocation
Triggered automatically when a script executed by any agent exits with a non-zero status code.

## Protocol

### Step 1: Capture Failure Context
When a script fails, collect:
1. **Full traceback** — complete Python traceback from stderr
2. **Last 20 lines of stdout** — what was printed before the crash
3. **Script content** — full source of the failing script
4. **Environment info** — Python version, installed packages, working directory
5. **Input files** — list of files the script was reading (from the script's open() calls)

### Step 2: Diagnose the Error
Classify the error type:
- `ImportError` — missing package or wrong module name
- `FileNotFoundError` — wrong file path or missing input
- `KeyError/IndexError` — wrong column name or array index
- `ValueError` — invalid data type or shape mismatch
- `TypeError` — wrong argument type
- `SyntaxError` — code syntax issue
- `RuntimeError` — convergence failure, memory error, etc.

### Step 3: Build Debug Prompt
Bundle the context into a structured debug prompt:
```
DEBUG REQUEST
=============
Script: {script_path}
Error Type: {error_type}
Traceback:
{full_traceback}

Last 20 lines of stdout:
{stdout_tail}

Script content:
{full_script}

Environment:
- Python: {python_version}
- Working directory: {cwd}
- Key packages: {package_versions}

TASK: Fix ONLY the failing function. Do NOT rewrite the entire script.
Return the corrected function code only.
```

### Step 4: LLM Rewrites the Failing Function
- Extract the failing function name from the traceback
- Read only that function's source code
- Generate a corrected version
- Replace ONLY that function in the script (not the entire file)

### Step 5: Retry Execution
- Run the script again with the fix applied
- Capture result (success or new error)
- If success: log the fix, continue pipeline
- If new error: go back to Step 1 (max 3 iterations)

### Step 6: Max Iterations Reached
If still failing after 3 attempts:
1. Create dead end entry: `docs/dead_ends/debug_{script_name}_{timestamp}.md`
2. Document: what was tried, what errors persisted, what manual intervention is needed
3. Alert user with the full debug log
4. Do NOT continue pipeline with broken script

### Step 7: Log All Debug Attempts
Every debug attempt is logged in `docs/dead_ends/debug_{script_name}_{timestamp}.md`:
```
---
Script: {script_path}
Attempt: 1/3
Error Type: {error_type}
Original Error: {traceback_snippet}
Fix Applied: {description of change}
Result: {success|new_error}
New Error (if any): {new_traceback}
---
```

## Implementation

### Python Helper: `.research/scripts/utils/auto_debug.py`
```bash
python .research/scripts/utils/auto_debug.py --script <path> --max-attempts 3
```

The script:
1. Executes the target script and captures output
2. On failure: parses traceback, identifies failing function
3. Outputs a structured JSON debug bundle for the LLM to process
4. Applies the LLM's fix and retries
5. Logs all attempts

### Debug Bundle JSON Format
```json
{
  "script": "scripts/02_analysis.py",
  "attempt": 1,
  "max_attempts": 3,
  "error_type": "ValueError",
  "traceback": "full traceback text",
  "stdout_tail": "last 20 lines",
  "failing_function": "compute_correlation",
  "failing_line": 47,
  "environment": {
    "python_version": "3.11.5",
    "cwd": "/project/root",
    "packages": {"pandas": "2.2.0", "scipy": "1.12.0"}
  },
  "input_files": ["data/03_analytical/analysis_q1.csv"]
}
```

## Integration

- Called automatically by agents when a script fails
- Also available as a CLI tool: `research debug <script_path>`
- All debug logs are append-only — never overwrite previous attempts
- Successful fixes are recorded in the state ledger
