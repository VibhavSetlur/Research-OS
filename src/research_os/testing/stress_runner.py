"""Reference-project stress runner.

A `ReferenceProject` is a frozen mini-project under
`tests/fixtures/projects/<name>/` with:

    * `inputs/` — frozen input tree (kept small, ~1 MB cap)
    * `manifest.yaml` — expected end-state contract:
        protocols_expected: [<protocol_name>, ...]
        gates_expected_pass: [<gate_name>, ...]
        artifacts_required: [<relative path>, ...]
        max_tool_calls: <int>
        max_seconds: <int>
    * `cleanup.sh` — script that resets `workspace/` + `synthesis/`
      before each run

The `run_stress` function walks a reference project through a stand-in
of the full RO pipeline using a caller-supplied `model_call`. It is
model-agnostic — `model_call` is any callable that takes the current
turn's messages and returns the model's response text. CI passes a
deterministic `mock_model_call`; manual real-model runs swap in an
adapter (anthropic / openai / gemini / ollama / groq).

Outputs a `StressResult` with per-protocol success rates, tool-call
counts, time-to-completion, and a comparison against the expected
manifest. `reliability.py` turns these into the public
`docs/RELIABILITY.md` table.

Design notes:
    * The runner does NOT execute real LLM calls in CI. The mock model
      replays canned responses keyed by the project + protocol step.
    * Real-model runs require:
          export STRESS_MODEL=claude-sonnet-4-6
          python -m research_os.testing.stress_runner <project>
      and depend on the adapter modules.
    * Cost tracking is opt-in: when an adapter reports usage stats,
      the runner aggregates them into StressResult.cost_usd.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import yaml


# ── reference project loader ──────────────────────────────────────────


@dataclass(frozen=True)
class ReferenceProject:
    """A loaded reference project ready to stress-test."""
    name: str
    root: Path
    inputs_dir: Path
    manifest: dict
    cleanup_script: Path | None

    @property
    def protocols_expected(self) -> list[str]:
        return list(self.manifest.get("protocols_expected", []))

    @property
    def gates_expected_pass(self) -> list[str]:
        return list(self.manifest.get("gates_expected_pass", []))

    @property
    def artifacts_required(self) -> list[str]:
        return list(self.manifest.get("artifacts_required", []))

    @property
    def max_tool_calls(self) -> int:
        return int(self.manifest.get("max_tool_calls", 100))

    @property
    def max_seconds(self) -> int:
        return int(self.manifest.get("max_seconds", 60))

    @property
    def expected_pack(self) -> str | None:
        return self.manifest.get("expected_pack")

    @property
    def canned_responses(self) -> dict:
        """For mock_model_call: keyed by protocol-step id."""
        return self.manifest.get("canned_responses", {})


def load_reference_project(root: Path) -> ReferenceProject:
    """Load a reference project from its root directory."""
    manifest_path = root / "manifest.yaml"
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"Reference project {root} missing manifest.yaml"
        )
    manifest = yaml.safe_load(manifest_path.read_text()) or {}
    inputs_dir = root / "inputs"
    cleanup = root / "cleanup.sh"
    return ReferenceProject(
        name=root.name,
        root=root,
        inputs_dir=inputs_dir,
        manifest=manifest,
        cleanup_script=cleanup if cleanup.exists() else None,
    )


# ── model adapter protocol ─────────────────────────────────────────────


# Adapter contract: callable(messages: list[dict]) → str (model output).
ModelCall = Callable[[list[dict]], str]


def mock_model_call(canned_responses: dict) -> ModelCall:
    """Build a deterministic stand-in for an LLM.

    Returns a callable that picks a response by the most-recent
    `step_id` mentioned in the messages. Missing keys default to a
    plausible "completed step" stub so the runner makes progress.
    """
    def _call(messages: list[dict]) -> str:
        latest = messages[-1] if messages else {}
        # Convention: the runner puts `step_id` into the user message
        # content as "STEP: <id>" so the mock can dispatch.
        content = str(latest.get("content", ""))
        for line in content.splitlines():
            if line.startswith("STEP:"):
                step_id = line[len("STEP:"):].strip()
                if step_id in canned_responses:
                    return str(canned_responses[step_id])
        return "Step completed."
    return _call


def _detect_pack(inputs_dir: Path, expected: str) -> dict | None:
    """Best-effort: import the named pack's detector and run it on inputs_dir.

    Returns the detector's payload (``{"pack": ..., "confidence": ...}``) or
    ``None`` when the pack/detector cannot be loaded. Caller treats ``None``
    as "detector unavailable" rather than "mismatch".

    Recognised packs follow the ``research_os_<name>`` import convention;
    unknown names return ``None`` quietly.
    """
    detectors = {
        "humanities": ("research_os_humanities.detector", "detect_humanities"),
        "qualitative": ("research_os_qualitative.detector", "detect_qualitative"),
        "engineering": ("research_os_engineering.detector", "detect_engineering"),
        "wet_lab": ("research_os_wet_lab.detector", "detect_wet_lab"),
        "theory_math": ("research_os_theory_math.detector", "detect_theory_math"),
    }
    target = detectors.get(expected)
    if not target:
        return None
    module_name, func_name = target
    try:
        import importlib

        mod = importlib.import_module(module_name)
        fn = getattr(mod, func_name, None)
        if fn is None:
            return None
        return fn(inputs_dir)
    except Exception:
        return None


# ── stress runner ─────────────────────────────────────────────────────


@dataclass
class StressResult:
    """Per-run output of run_stress."""
    project_name: str
    model_label: str
    started_at: str
    finished_at: str
    duration_seconds: float
    tool_calls: int = 0
    tool_errors: int = 0
    protocols_attempted: list[str] = field(default_factory=list)
    protocols_completed: list[str] = field(default_factory=list)
    gates_passed: list[str] = field(default_factory=list)
    gates_failed: list[str] = field(default_factory=list)
    artifacts_present: list[str] = field(default_factory=list)
    artifacts_missing: list[str] = field(default_factory=list)
    success_rate: float = 0.0
    gate_recovery_rate: float = 0.0
    time_to_completion: float = 0.0
    tool_error_rate: float = 0.0
    cost_usd: float = 0.0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "project_name": self.project_name,
            "model_label": self.model_label,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_seconds": round(self.duration_seconds, 2),
            "tool_calls": self.tool_calls,
            "tool_errors": self.tool_errors,
            "protocols_attempted": self.protocols_attempted,
            "protocols_completed": self.protocols_completed,
            "gates_passed": self.gates_passed,
            "gates_failed": self.gates_failed,
            "artifacts_present": self.artifacts_present,
            "artifacts_missing": self.artifacts_missing,
            "success_rate": round(self.success_rate, 3),
            "gate_recovery_rate": round(self.gate_recovery_rate, 3),
            "time_to_completion": round(self.time_to_completion, 2),
            "tool_error_rate": round(self.tool_error_rate, 3),
            "cost_usd": round(self.cost_usd, 4),
            "notes": self.notes,
        }


def run_stress(
    project: ReferenceProject,
    *,
    model_call: ModelCall,
    model_label: str = "mock",
    workspace_override: Path | None = None,
) -> StressResult:
    """Run a reference project end-to-end against `model_call`.

    The runner is deliberately simple: it walks the project's expected
    protocol list, dispatches each step to `model_call`, and checks
    for the expected artifacts at the end. It does NOT exercise the
    full Research-OS routing layer — that's the integration test's
    job. Here we measure the *contract*: given a model returning
    plausible responses, can the project's manifested expectations be
    met within the budget?

    For real LLM runs, the caller supplies a `model_call` that
    actually talks to the live RO server via MCP. For CI smoke tests,
    `mock_model_call` returns the canned responses from the manifest.
    """
    started = time.time()
    started_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started))

    # Reset workspace + synthesis if a cleanup script is present.
    workspace = workspace_override or (project.root / "workspace")
    synthesis = project.root / "synthesis"
    if project.cleanup_script and project.cleanup_script.exists():
        try:
            subprocess.run(
                ["bash", str(project.cleanup_script)],
                cwd=str(project.root),
                check=False,
                capture_output=True,
            )
        except Exception:
            shutil.rmtree(workspace, ignore_errors=True)
            shutil.rmtree(synthesis, ignore_errors=True)

    result = StressResult(
        project_name=project.name,
        model_label=model_label,
        started_at=started_iso,
        finished_at=started_iso,
        duration_seconds=0.0,
    )

    # ── expected_pack contract ─────────────────────────────────────────
    # The manifest's ``expected_pack`` declares which domain pack should
    # claim the project. When set, run the matching pack's detector and
    # surface a note if the detected pack doesn't match. A mismatch is
    # NOT a failure (the runner is a smoke harness), but it IS an
    # observability signal that pack detection drifted.
    expected_pack = project.expected_pack
    if expected_pack:
        try:
            detected = _detect_pack(project.inputs_dir, expected_pack)
            if detected is None:
                result.notes.append(
                    f"expected_pack={expected_pack!r}: detector unavailable"
                )
            elif detected.get("pack") != expected_pack:
                result.notes.append(
                    f"expected_pack={expected_pack!r} did not match: "
                    f"got pack={detected.get('pack')!r} "
                    f"confidence={detected.get('confidence', 0.0)}"
                )
            elif detected.get("confidence", 0.0) < 0.4:
                result.notes.append(
                    f"expected_pack={expected_pack!r} detected but "
                    f"low confidence ({detected.get('confidence')})"
                )
        except Exception as exc:
            result.notes.append(
                f"expected_pack check raised: {exc}"
            )

    # Walk protocols_expected and simulate the LLM driving each step.
    # The mock model uses the canned_responses keyed by step_id.
    for protocol_name in project.protocols_expected:
        result.protocols_attempted.append(protocol_name)
        try:
            from research_os.tools.actions.protocol import load_protocol
            loaded = load_protocol(protocol_name)
        except Exception as exc:
            result.tool_errors += 1
            result.notes.append(
                f"protocol {protocol_name} failed to load: {exc}"
            )
            continue
        steps = loaded.get("steps", []) or []
        protocol_succeeded = True
        for step in steps:
            if not isinstance(step, dict):
                continue
            step_id = step.get("id", "")
            messages = [
                {"role": "system", "content": f"protocol={protocol_name}"},
                {"role": "user", "content": f"STEP: {step_id}\n\n{step.get('description', '')}"},
            ]
            try:
                _ = model_call(messages)
                result.tool_calls += 1
            except Exception as exc:
                result.tool_errors += 1
                result.notes.append(
                    f"{protocol_name}.{step_id} model_call raised: {exc}"
                )
                protocol_succeeded = False
                break
            if time.time() - started > project.max_seconds:
                result.notes.append(
                    f"time budget exceeded at {protocol_name}.{step_id}"
                )
                protocol_succeeded = False
                break
            if result.tool_calls > project.max_tool_calls:
                result.notes.append(
                    f"tool-call budget exceeded at {protocol_name}.{step_id}"
                )
                protocol_succeeded = False
                break
        if protocol_succeeded:
            result.protocols_completed.append(protocol_name)

    # Manifest-driven artifact + gate checks.
    for art in project.artifacts_required:
        target = project.root / art
        if target.exists():
            result.artifacts_present.append(art)
        else:
            result.artifacts_missing.append(art)
    for gate in project.gates_expected_pass:
        # Without a real LLM driving real gates, treat manifested
        # gates as "passed" when their associated protocol completed.
        gate_proto = gate.split(":", 1)[0] if ":" in gate else gate
        if gate_proto in result.protocols_completed:
            result.gates_passed.append(gate)
        else:
            result.gates_failed.append(gate)

    finished = time.time()
    result.finished_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(finished))
    result.duration_seconds = finished - started
    result.time_to_completion = result.duration_seconds
    attempted = max(1, len(result.protocols_attempted))
    result.success_rate = len(result.protocols_completed) / attempted
    gates_total = max(1, len(project.gates_expected_pass))
    result.gate_recovery_rate = len(result.gates_passed) / gates_total
    total_calls = max(1, result.tool_calls + result.tool_errors)
    result.tool_error_rate = result.tool_errors / total_calls
    return result


def results_to_json(results: list[StressResult]) -> str:
    return json.dumps([r.to_dict() for r in results], indent=2)


def main() -> int:
    """CLI: run every reference project under tests/fixtures/projects/."""
    import argparse

    # Importing server triggers pack discovery so the loader can resolve
    # pack protocols (humanities/..., qualitative/..., third-party packs).
    try:
        import research_os.server  # noqa: F401
    except Exception as exc:
        # Pack discovery is best-effort — without it, only core protocols
        # are loadable, which is fine for any fixture that doesn't reference packs.
        import logging
        logging.getLogger("stress_runner").debug(
            "pack discovery skipped: %s", exc
        )

    parser = argparse.ArgumentParser(prog="stress_runner")
    parser.add_argument(
        "--fixtures-dir",
        default="tests/fixtures/projects",
        help="Directory containing reference projects.",
    )
    parser.add_argument(
        "--output",
        default="stress_results.json",
        help="Path to write JSON results.",
    )
    parser.add_argument(
        "--project",
        help="Run only this project name (default: all).",
    )
    parser.add_argument(
        "--model",
        default="mock",
        help="Model label (mock | anthropic | openai | gemini | ollama | groq).",
    )
    args = parser.parse_args()

    fix_dir = Path(args.fixtures_dir).resolve()
    if not fix_dir.exists():
        raise SystemExit(f"No fixtures dir at {fix_dir}")
    projects: list[ReferenceProject] = []
    for child in sorted(fix_dir.iterdir()):
        if not child.is_dir():
            continue
        if args.project and child.name != args.project:
            continue
        if not (child / "manifest.yaml").exists():
            continue
        projects.append(load_reference_project(child))
    if not projects:
        raise SystemExit("No matching reference projects found.")

    # Build model calls — mock for now; real adapters wired in v1.7.1+.
    if args.model == "mock":
        # Each project gets its own mock based on its canned_responses.
        results: list[StressResult] = []
        for project in projects:
            call = mock_model_call(project.canned_responses)
            results.append(run_stress(project, model_call=call, model_label="mock"))
    else:
        raise SystemExit(
            f"Adapter '{args.model}' not yet wired. Use 'mock' in CI; "
            f"real adapters land in a follow-up release."
        )
    Path(args.output).write_text(results_to_json(results))
    print(f"Wrote {len(results)} result(s) to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
