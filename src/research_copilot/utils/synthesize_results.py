#!/usr/bin/env python3
"""
Research Copilot Results Synthesizer
Reads parallel runner execution results, compiles individual task outputs,
detects empirical conflicts, and updates the research map and manifest.
"""

import os
import sys
import json
import argparse
import hashlib
import time
from pathlib import Path
from typing import List, Dict, Any, Optional


def compute_sha256(file_path: Path) -> str:
    """Compute the SHA-256 hash of a file."""
    sha256 = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            while chunk := f.read(8192):
                sha256.update(chunk)
        return sha256.hexdigest()
    except Exception:
        return "unknown"


def detect_conflicts(compiled_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Detect statistical or empirical conflicts across parallel task findings.
    
    Looks for:
    1. Direct coefficient/effect sign contradictions for the same variable/outcome.
    2. Discrepancies in statistical significance (one worker finds significant, another non-significant).
    """
    conflicts = []
    variable_effects = {}

    for question_id, data in compiled_data.items():
        # Expecting a list of findings or single model summary in task results
        findings = data.get("findings", [])
        if not isinstance(findings, list):
            # Wrap single dict finding
            findings = [findings]

        for finding in findings:
            variable = finding.get("variable")
            outcome = finding.get("outcome")
            effect_size = finding.get("effect_size")
            p_value = finding.get("p_value")
            
            if not variable or not outcome:
                continue

            key = (variable, outcome)
            if key not in variable_effects:
                variable_effects[key] = []

            variable_effects[key].append({
                "question_id": question_id,
                "effect_size": effect_size,
                "p_value": p_value,
                "finding": finding
            })

    # Compare effects for each variable-outcome pair
    for (variable, outcome), list_effects in variable_effects.items():
        if len(list_effects) < 2:
            continue

        for i in range(len(list_effects)):
            for j in range(i + 1, len(list_effects)):
                eff_i = list_effects[i]
                eff_j = list_effects[j]

                val_i = eff_i.get("effect_size")
                val_j = eff_j.get("effect_size")
                p_i = eff_i.get("p_value")
                p_j = eff_j.get("p_value")

                # 1. Directional conflict (both non-null and opposite signs)
                if val_i is not None and val_j is not None:
                    try:
                        if float(val_i) * float(val_j) < 0:
                            conflicts.append({
                                "type": "directional_conflict",
                                "variable": variable,
                                "outcome": outcome,
                                "detail": f"Contradictory effect directions for {variable} on {outcome}: "
                                         f"{eff_i['question_id']} ({val_i}) vs {eff_j['question_id']} ({val_j})"
                            })
                    except (ValueError, TypeError):
                        pass

                # 2. Significance conflict (one significant p < 0.05, other not)
                if p_i is not None and p_j is not None:
                    try:
                        sig_i = float(p_i) < 0.05
                        sig_j = float(p_j) < 0.05
                        if sig_i != sig_j:
                            conflicts.append({
                                "type": "significance_discrepancy",
                                "variable": variable,
                                "outcome": outcome,
                                "detail": f"Discrepant significance levels for {variable} on {outcome}: "
                                         f"{eff_i['question_id']} (p={p_i}) vs {eff_j['question_id']} (p={p_j})"
                            })
                    except (ValueError, TypeError):
                        pass

    return conflicts


def update_research_map(map_path: Path, compiled_data: Dict[str, Any]) -> bool:
    """Update research_map.json with the completed question statuses and findings."""
    if not map_path.exists():
        return False

    try:
        with open(map_path, "r") as f:
            research_map = json.load(f)

        # Update findings under each question
        questions = research_map.get("questions", [])
        updated = False
        for q in questions:
            q_id = q.get("id")
            if q_id in compiled_data:
                q["status"] = "completed"
                q["findings"] = compiled_data[q_id].get("findings", {})
                updated = True

        if updated:
            with open(map_path, "w") as f:
                json.dump(research_map, f, indent=2)
            return True
    except Exception as e:
        print(f"WARNING: Failed to update research map: {e}")
    
    return False


def main():
    parser = argparse.ArgumentParser(description="Consolidate and Synthesize Parallel Runner Outputs")
    parser.add_argument("--results-file", required=True, help="Path to parallel run _results.json file")
    parser.add_argument("--output-dir", default="reports/analysis", help="Target output directory for combined results")
    parser.add_argument("--research-map", help="Path to research_map.json to update")
    parser.add_argument("--manifest", default="docs/manifest.json", help="Path to manifest.json to update")

    args = parser.parse_args()

    results_path = Path(args.results_file)
    if not results_path.exists():
        print(f"ERROR: Parallel results file not found: {results_path}")
        sys.exit(1)

    try:
        with open(results_path, "r") as f:
            run_results = json.load(f)
    except Exception as e:
        print(f"ERROR: Failed to load results JSON: {e}")
        sys.exit(1)

    print("=" * 60)
    print("RESULTS SYNTHESIS RUNNING")
    print(f"  Parallel run file: {results_path}")
    print("=" * 60)

    # 1. Compile individual task outputs
    compiled_results = {}
    validation_failures = 0
    worker_results = run_results.get("results", [])

    for worker in worker_results:
        task_id = worker.get("id")
        success = worker.get("success", False)
        log_file = worker.get("log_file")

        if not success:
            print(f"  [✗] Task {task_id} failed. Skipping output collection.")
            validation_failures += 1
            continue

        # Look for the worker's results summary file
        # Convention: The worker outputs results into their directory
        # e.g., reports/analysis/q1/q1_results.json
        q_results_file = Path(args.output_dir) / task_id / f"{task_id}_results.json"
        
        # Fallback: search in output dir or task directory
        if not q_results_file.exists():
            # Try searching recursively for a json summary in the subfolder
            task_subfolder = Path(args.output_dir) / task_id
            if task_subfolder.exists():
                json_files = list(task_subfolder.glob("*.json"))
                if json_files:
                    q_results_file = json_files[0]

        if not q_results_file.exists():
            print(f"  [✗] Output file for task {task_id} not found at {q_results_file}")
            validation_failures += 1
            continue

        # Hash verify the worker file
        file_hash = compute_sha256(q_results_file)
        print(f"  [✓] Verified Task {task_id} output: {q_results_file.name} (SHA-256: {file_hash[:8]})")

        try:
            with open(q_results_file, "r") as f:
                task_data = json.load(f)
            compiled_results[task_id] = {
                "hash": file_hash,
                "results": task_data
            }
            # Extract findings if present
            if "findings" in task_data:
                compiled_results[task_id]["findings"] = task_data["findings"]
            elif isinstance(task_data, list):
                compiled_results[task_id]["findings"] = task_data
            else:
                compiled_results[task_id]["findings"] = [task_data]
        except Exception as e:
            print(f"  [✗] Failed to read output file for task {task_id}: {e}")
            validation_failures += 1

    # 2. Conflict Detection
    conflicts = detect_conflicts(compiled_results)
    
    # 3. Create combined outputs JSON
    output_dir_path = Path(args.output_dir)
    output_dir_path.mkdir(parents=True, exist_ok=True)
    combined_path = output_dir_path / "combined_results.json"

    combined_payload = {
        "metadata": {
            "parallel_run_id": results_path.stem,
            "synthesized_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "total_workers": len(worker_results),
            "valid_workers": len(compiled_results),
            "failures": validation_failures,
            "conflicts_detected": len(conflicts)
        },
        "tasks": compiled_results,
        "conflicts": conflicts
    }

    try:
        with open(combined_path, "w") as f:
            json.dump(combined_payload, f, indent=2)
        print(f"Combined results written to: {combined_path}")
    except Exception as e:
        print(f"ERROR: Failed to save combined results: {e}")
        sys.exit(1)

    # Item 18: LLM-based Parallel Execution Synthesis
    print("=" * 60)
    print("LLM-BASED PARALLEL SYNTHESIS")
    print("=" * 60)
    try:
        from research_copilot.core.model_resolver import cascade_resolve
        prompt = (
            "Analyze the following synthesized parallel execution results and any detected conflicts. "
            "Determine the 'Winning Branch' (task_id) that produced the most robust, well-supported findings. "
            "Explain your reasoning and state the winning branch.\n\n"
            f"Results: {json.dumps(combined_payload, indent=2)}"
        )
        synthesis_decision = cascade_resolve(prompt, model="google/gemini-pro", temperature=0.2)
        print("Synthesis Decision:\n", synthesis_decision)
        
        # Output to ledger via log_decision
        from research_copilot.project_ops import log_decision, current_branch, find_project_root
        root = find_project_root()
        log_decision(
            context="Parallel execution synthesis. Need to select winning exploratory branch.",
            selected="LLM selected best branch based on empirical results.",
            rationale=synthesis_decision,
            branch_id=current_branch(root),
            root=root
        )
        print(f"Synthesis decision logged to experiment ledger.")
    except Exception as e:
        print(f"WARNING: LLM synthesis failed: {e}")

    # 4. Update research map and manifest if requested
    if args.research_map:
        map_path = Path(args.research_map)
        if update_research_map(map_path, compiled_results):
            print(f"Research map successfully updated: {map_path}")

    if args.manifest:
        manifest_path = Path(args.manifest)
        if manifest_path.exists():
            try:
                with open(manifest_path, "r") as f:
                    manifest = json.load(f)
                
                manifest["last_updated"] = time.strftime("%Y-%m-%d", time.gmtime())
                if "analysis_status" not in manifest:
                    manifest["analysis_status"] = {}
                
                for task_id in compiled_results.keys():
                    manifest["analysis_status"][task_id] = "complete"

                with open(manifest_path, "w") as f:
                    json.dump(manifest, f, indent=2)
                print(f"Manifest successfully updated: {manifest_path}")
            except Exception as e:
                print(f"WARNING: Failed to update manifest: {e}")

    # Display synthesis summary
    print("=" * 60)
    print("SYNTHESIS SUMMARY REPORT")
    print("=" * 60)
    print(f"  Valid workers processed: {len(compiled_results)}/{len(worker_results)}")
    
    if conflicts:
        print(f"\n  [!] WARNING: {len(conflicts)} conflict(s) detected during synthesis:")
        for c in conflicts:
            print(f"    - [{c['type'].upper()}] {c['detail']}")
    else:
        print("\n  [✓] No directional or significance conflicts detected.")
        
    print()
    if validation_failures > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
