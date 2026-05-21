#!/usr/bin/env python3
"""Auto-Debugging Sandbox — captures, diagnoses, and retries failing scripts.

When any Python script fails:
1. Capture full traceback + last 20 lines of stdout
2. Identify the failing function
3. Bundle error context into a debug JSON
4. LLM rewrites only the failing function
5. Retry (max 3 attempts)
6. Log all attempts in docs/dead_ends/

Usage:
    python .research/scripts/utils/auto_debug.py --script scripts/02_analysis.py
    python .research/scripts/utils/auto_debug.py --script scripts/02_analysis.py --max-attempts 3
    python .research/scripts/utils/auto_debug.py --script scripts/02_analysis.py --apply-fix <fixed_code_file>
"""

import argparse
import json
import os
import re
import subprocess
import sys
import traceback as tb_module
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


from research_copilot.utils.common import find_project_root


def get_python_version() -> str:
    return f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"


def get_package_versions(packages: list[str]) -> dict[str, str]:
    """Get versions of specific packages."""
    versions = {}
    for pkg in packages:
        try:
            mod = __import__(pkg)
            versions[pkg] = getattr(mod, "__version__", "unknown")
        except ImportError:
            versions[pkg] = "not_installed"
    return versions


def get_input_files(script_path: Path) -> list[str]:
    """Extract file paths referenced in the script."""
    try:
        content = script_path.read_text()
    except Exception:
        return []

    patterns = [
        r'open\(["\']([^"\']+)["\']',
        r'pd\.read_csv\(["\']([^"\']+)["\']',
        r'pd\.read_excel\(["\']([^"\']+)["\']',
        r'Path\(["\']([^"\']+)["\']',
        r'json\.load\(open\(["\']([^"\']+)["\']',
    ]

    files = set()
    for pattern in patterns:
        files.update(re.findall(pattern, content))
    return sorted(files)


def extract_failing_function(traceback_text: str, script_path: str) -> tuple[Optional[str], Optional[int]]:
    """Extract the failing function name and line number from traceback."""
    script_name = Path(script_path).name
    lines = traceback_text.split("\n")

    # Search in reverse to find the deepest frame in our target script
    for line in reversed(lines):
        if script_name in line and "File" in line:
            match = re.search(r'File ".*?", line (\d+)(?:, in (\w+))?', line)
            if match:
                line_num = int(match.group(1))
                func_name = match.group(2)
                return func_name, line_num

    return None, None


def extract_function_source(script_path: Path, func_name: str, line_num: Optional[int] = None) -> Optional[str]:
    """Extract a specific function's source code from a script."""
    try:
        content = script_path.read_text()
    except Exception:
        return None

    lines = content.split("\n")
    func_start = None
    func_indent = None

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("def ") and func_name in stripped:
            func_start = i
            func_indent = len(line) - len(line.lstrip())
            break

    if func_start is None:
        return None

    func_lines = [lines[func_start]]
    for i in range(func_start + 1, len(lines)):
        line = lines[i]
        if line.strip() == "":
            func_lines.append(line)
            continue
        current_indent = len(line) - len(line.lstrip())
        if current_indent <= func_indent and line.strip():
            break
        func_lines.append(line)

    return "\n".join(func_lines)


def run_script(script_path: Path, timeout: int = 300) -> tuple[int, str, str]:
    """Run a script and capture return code, stdout, stderr."""
    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(find_project_root()),
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"Script timed out after {timeout} seconds"
    except Exception as e:
        return -1, "", str(e)


def build_debug_bundle(
    script_path: Path,
    returncode: int,
    stdout: str,
    stderr: str,
    attempt: int,
    max_attempts: int,
) -> dict:
    """Build a structured debug bundle for the LLM."""
    func_name, line_num = extract_failing_function(stderr, str(script_path))
    func_source = None
    if func_name:
        func_source = extract_function_source(script_path, func_name, line_num)

    important_packages = ["pandas", "numpy", "scipy", "matplotlib", "sklearn", "statsmodels"]

    bundle = {
        "script": str(script_path),
        "attempt": attempt,
        "max_attempts": max_attempts,
        "error_type": _classify_error(stderr),
        "traceback": stderr,
        "stdout_tail": "\n".join(stdout.strip().split("\n")[-20:]),
        "failing_function": func_name,
        "failing_line": line_num,
        "function_source": func_source,
        "environment": {
            "python_version": get_python_version(),
            "cwd": str(find_project_root()),
            "packages": get_package_versions(important_packages),
        },
        "input_files": get_input_files(script_path),
    }

    return bundle


def _classify_error(stderr: str) -> str:
    """Classify the error type from stderr."""
    error_patterns = [
        ("ImportError", r"ImportError|ModuleNotFoundError"),
        ("FileNotFoundError", r"FileNotFoundError|No such file"),
        ("KeyError", r"KeyError"),
        ("IndexError", r"IndexError"),
        ("ValueError", r"ValueError"),
        ("TypeError", r"TypeError"),
        ("SyntaxError", r"SyntaxError"),
        ("AttributeError", r"AttributeError"),
        ("RuntimeError", r"RuntimeError"),
        ("MemoryError", r"MemoryError"),
        ("ConvergenceWarning", r"ConvergenceWarning|Did not converge"),
    ]

    for error_type, pattern in error_patterns:
        if re.search(pattern, stderr):
            return error_type
    return "Unknown"


def apply_fix(script_path: Path, func_name: str, new_code: str) -> bool:
    """Replace a function in the script with new code."""
    try:
        content = script_path.read_text()
    except Exception:
        return False

    lines = content.split("\n")
    func_start = None
    func_indent = None

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("def ") and func_name in stripped:
            func_start = i
            func_indent = len(line) - len(line.lstrip())
            break

    if func_start is None:
        return False

    func_end = func_start + 1
    for i in range(func_start + 1, len(lines)):
        line = lines[i]
        if line.strip() == "":
            func_end = i + 1
            continue
        current_indent = len(line) - len(line.lstrip())
        if current_indent <= func_indent and line.strip():
            func_end = i
            break
    else:
        func_end = len(lines)

    new_lines = new_code.split("\n")
    updated_lines = lines[:func_start] + new_lines + lines[func_end:]

    try:
        with open(script_path, "w") as f:
            f.write("\n".join(updated_lines))
        return True
    except Exception:
        return False


def log_debug_attempt(
    script_path: Path,
    bundle: dict,
    fix_applied: Optional[str],
    success: bool,
    output_dir: Optional[Path] = None,
) -> Path:
    """Log a debug attempt to docs/dead_ends/."""
    root = find_project_root()
    if output_dir is None:
        output_dir = root / "docs" / "dead_ends"
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    script_name = script_path.stem
    log_path = output_dir / f"debug_{script_name}_{timestamp}.md"

    with open(log_path, "w") as f:
        f.write(f"# Debug Log: {script_path.name}\n\n")
        f.write(f"- **Script**: {script_path}\n")
        f.write(f"- **Attempt**: {bundle['attempt']}/{bundle['max_attempts']}\n")
        f.write(f"- **Error Type**: {bundle['error_type']}\n")
        f.write(f"- **Failing Function**: {bundle['failing_function']}\n")
        f.write(f"- **Failing Line**: {bundle['failing_line']}\n")
        f.write(f"- **Timestamp**: {datetime.now(timezone.utc).isoformat()}\n")
        f.write(f"- **Result**: {'SUCCESS' if success else 'FAILED'}\n\n")

        f.write("## Traceback\n```\n")
        f.write(bundle["traceback"][-2000:])
        f.write("\n```\n\n")

        f.write("## Last 20 Lines of stdout\n```\n")
        f.write(bundle["stdout_tail"])
        f.write("\n```\n\n")

        if fix_applied:
            f.write("## Fix Applied\n```\n")
            f.write(fix_applied)
            f.write("\n```\n\n")

        f.write("## Environment\n")
        f.write(f"- Python: {bundle['environment']['python_version']}\n")
        f.write(f"- CWD: {bundle['environment']['cwd']}\n")
        f.write(f"- Packages: {json.dumps(bundle['environment']['packages'], indent=2)}\n\n")

        if bundle["input_files"]:
            f.write("## Input Files\n")
            for fp in bundle["input_files"]:
                f.write(f"- {fp}\n")

    return log_path


def run_auto_debug(
    script_path: Path,
    max_attempts: int = 3,
    fix_code: Optional[str] = None,
    fix_func: Optional[str] = None,
) -> dict:
    """Run the auto-debugging loop."""
    root = find_project_root()
    results = []

    for attempt in range(1, max_attempts + 1):
        print(f"\n{'=' * 60}")
        print(f"DEBUG ATTEMPT {attempt}/{max_attempts}")
        print(f"Script: {script_path}")
        print(f"{'=' * 60}")

        if fix_code and fix_func and attempt == 1:
            success = apply_fix(script_path, fix_func, fix_code)
            if success:
                print(f"  Applied fix to function: {fix_func}")
            else:
                print(f"  WARNING: Could not apply fix to {fix_func}")

        returncode, stdout, stderr = run_script(script_path)

        if returncode == 0:
            print(f"  SUCCESS: Script completed without errors")
            result = {
                "attempt": attempt,
                "success": True,
                "returncode": returncode,
            }
            results.append(result)

            bundle = build_debug_bundle(script_path, returncode, stdout, stderr, attempt, max_attempts)
            log_path = log_debug_attempt(script_path, bundle, fix_code if fix_code else None, True)
            print(f"  Debug log: {log_path}")
            return {"success": True, "attempts": attempt, "results": results}

        print(f"  FAILED: {stderr[:200]}...")

        bundle = build_debug_bundle(script_path, returncode, stdout, stderr, attempt, max_attempts)
        results.append({
            "attempt": attempt,
            "success": False,
            "error_type": bundle["error_type"],
            "failing_function": bundle["failing_function"],
            "failing_line": bundle["failing_line"],
            "traceback": stderr[-500:],
        })

        log_path = log_debug_attempt(script_path, bundle, None, False)
        print(f"  Debug log: {log_path}")
        print(f"  Debug bundle saved for LLM processing")

        if attempt < max_attempts:
            print(f"  Waiting for LLM to provide fix for: {bundle['failing_function']}")
            print(f"  Debug bundle: {json.dumps({k: v for k, v in bundle.items() if k != 'traceback'}, indent=2)}")
            return {"success": False, "needs_fix": True, "bundle": bundle, "attempts": attempt, "results": results}

    print(f"\n  FAILED after {max_attempts} attempts")
    print(f"  Creating dead end entry")
    return {"success": False, "needs_fix": False, "attempts": max_attempts, "results": results}


def main():
    parser = argparse.ArgumentParser(description="Auto-Debugging Sandbox")
    parser.add_argument("--script", type=str, required=True, help="Path to the failing script")
    parser.add_argument("--max-attempts", type=int, default=3, help="Maximum debug attempts (default: 3)")
    parser.add_argument("--apply-fix", type=str, help="Path to file containing fixed function code")
    parser.add_argument("--fix-func", type=str, help="Name of the function to replace")
    args = parser.parse_args()

    root = find_project_root()
    script_path = Path(args.script) if Path(args.script).is_absolute() else root / args.script

    if not script_path.exists():
        print(f"ERROR: Script not found: {script_path}")
        sys.exit(1)

    fix_code = None
    if args.apply_fix:
        fix_path = Path(args.apply_fix) if Path(args.apply_fix).is_absolute() else root / args.apply_fix
        fix_code = fix_path.read_text()

    result = run_auto_debug(script_path, max_attempts=args.max_attempts, fix_code=fix_code, fix_func=args.fix_func)

    print(f"\n{'=' * 60}")
    print("AUTO-DEBUG SUMMARY")
    print(f"{'=' * 60}")
    print(f"  Script: {script_path}")
    print(f"  Attempts: {result['attempts']}")
    print(f"  Success: {result['success']}")

    if not result["success"] and result.get("needs_fix"):
        bundle = result["bundle"]
        print(f"\n  LLM ACTION REQUIRED:")
        print(f"  Fix the function: {bundle['failing_function']}")
        print(f"  Error type: {bundle['error_type']}")
        if bundle.get("function_source"):
            print(f"\n  Current function source:")
            print(f"  {bundle['function_source'][:500]}")
        print(f"\n  Then run: python .research/scripts/utils/auto_debug.py --script {script_path} --apply-fix <fixed_file> --fix-func {bundle['failing_function']}")

    sys.exit(0 if result["success"] else 1)

def trace_node(node_id: str, root: Path) -> None:
    ledger_path = root / "03_synthesis" / "state_ledger.json"
    if not ledger_path.exists():
        print("Ledger not found")
        return
    with open(ledger_path) as f:
        ledger = json.load(f)
    
    node_entries = [e for e in ledger.get("history", []) if e.get("node_id") == node_id]
    if not node_entries:
        print(f"No execution history found for node: {node_id}")
        return

    print("=" * 60)
    print(f"TRACE FOR NODE: {node_id}")
    print("=" * 60)
    for idx, entry in enumerate(node_entries):
        print(f"\n--- EXECUTION ATTEMPT {idx+1} ---")
        print(f"Status: {entry.get('status')}")
        if entry.get("prompt"):
            print("\n[PROMPT]")
            p = entry.get("prompt")
            print(p[:500] + "..." if len(p) > 500 else p)
        if entry.get("raw_json"):
            print("\n[RAW JSON OUTPUT]")
            print(entry.get("raw_json"))
        if entry.get("stderr"):
            print("\n[STDERR]")
            print(entry.get("stderr"))
        if entry.get("error_context"):
            print("\n[ERROR CONTEXT]")
            print(entry.get("error_context"))


if __name__ == "__main__":
    main()
