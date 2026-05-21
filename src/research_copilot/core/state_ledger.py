#!/usr/bin/env python3
"""Global Research Ledger — atomic state management for the research pipeline.

Single source of truth for every pipeline run. Replaces fragmented
manifest/registry/log files with one authoritative object.

Location: .research/cache/state.json
"""

import json
import logging
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("research.state_ledger")

from research_copilot.utils.common import find_project_root


class ResearchLedger:
    """Thread-safe, atomic research state ledger."""

    def __init__(self, state_path: Optional[Path] = None):
        if state_path is None:
            root = find_project_root()
            state_path = root / "03_synthesis" / "state_ledger.json"
        self._path = Path(state_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> dict:
        if self._path.exists():
            with open(self._path) as f:
                return json.load(f)
        return self._default_state()

    def _save(self, data: dict) -> None:
        """Atomic write: write to temp file, then rename to avoid corruption."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            dir=str(self._path.parent), suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, indent=2, default=str)
            os.replace(tmp_path, str(self._path))
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    @staticmethod
    def _default_state() -> dict:
        return {
            "run_id": str(uuid.uuid4()),
            "project": "",
            "phase": "research_init",
            "step": 0,
            "checkpoints": {},
            "active_hypotheses": [],
            "dead_ends": [],
            "loaded_data": [],
            "token_budget": {"used": 0, "remaining": 200000, "limit": 200000},
            "last_checkpoint": datetime.now(timezone.utc).isoformat(),
            "errors": [],
            "resumable_from": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "context_transfer_memos": [],
            "execution_dag_path": None,
            "data_scale_profile": None,
            "active_branch": "main",
            "current_branch": "main",
            "branches": {
                "main": {
                    "branch_id": "main",
                    "parent_branch": "",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "status": "active",
                    "hypothesis": "Primary research workflow",
                    "merge_commit": None,
                    "merged_at": None,
                    "evaluation": None,
                    "workspace_prefix": "",
                    "experiment_dir": "02_experiments/exp_001_baseline",
                    "data_hashes": {},
                }
            },
            "knowledge_graph_path": None,
        }

    def _run_pre_commit_hooks(self, state: dict, action: str, **kwargs) -> dict:
        """Run pre_ledger_commit hooks synchronously via trigger_sync().

        No nest_asyncio needed — hooks.py handles async/sync normalization.
        """
        try:
            from research_copilot.core.hooks import hook_engine
            import research_copilot.core.interceptors  # noqa: F401 — registers interceptors
            import research_copilot.utils.state_compressor  # noqa: F401
        except ImportError:
            try:
                from .hooks import hook_engine
                from . import interceptors  # noqa: F401
                from ..utils import state_compressor  # noqa: F401
            except ImportError:
                return state

        return hook_engine.trigger_sync(
            "pre_ledger_commit", state, action=action, **kwargs
        )

    def get(self) -> dict:
        return self._load()

    def update(self, **kwargs) -> dict:
        state = self._load()
        state.update(kwargs)
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        state = self._run_pre_commit_hooks(state, "update", **kwargs)
        self._save(state)
        return state

    def set_phase(self, phase: str, step: int = 0) -> dict:
        state = self._load()
        state["phase"] = phase
        state["step"] = step
        state["checkpoints"][phase] = "in_progress"
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._save(state)
        return state

    def complete_phase(self, phase: str) -> dict:
        state = self._load()
        state["checkpoints"][phase] = "complete"
        state["resumable_from"] = phase
        state["last_checkpoint"] = datetime.now(timezone.utc).isoformat()
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        state = self._run_pre_commit_hooks(state, "complete_phase", phase=phase)
        self._save(state)
        return state

    def add_hypothesis(self, hypothesis_id: str, status: str = "testing", effect: Optional[float] = None) -> dict:
        state = self._load()
        hypotheses = state.get("active_hypotheses", [])
        for h in hypotheses:
            if h["id"] == hypothesis_id:
                h["status"] = status
                if effect is not None:
                    h["effect"] = effect
                state["updated_at"] = datetime.now(timezone.utc).isoformat()
                self._save(state)
                return state
        hypotheses.append({"id": hypothesis_id, "status": status, "effect": effect})
        state["active_hypotheses"] = hypotheses
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._save(state)
        return state

    def add_dead_end(self, approach: str) -> dict:
        state = self._load()
        if approach not in state.get("dead_ends", []):
            state.setdefault("dead_ends", []).append(approach)
            state["updated_at"] = datetime.now(timezone.utc).isoformat()
            self._save(state)
        return state

    def add_error(self, error: str) -> dict:
        state = self._load()
        state.setdefault("errors", []).append({
            "message": error,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._save(state)
        return state

    def track_tokens(self, used: int, limit: Optional[int] = None) -> dict:
        state = self._load()
        budget = state.get("token_budget", {"used": 0, "remaining": 200000, "limit": 200000})
        if limit is not None:
            budget["limit"] = limit
        budget["used"] = used
        budget["remaining"] = max(0, budget["limit"] - used)
        state["token_budget"] = budget
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._save(state)
        return state

    def add_loaded_data(self, data_path: str) -> dict:
        state = self._load()
        if data_path not in state.get("loaded_data", []):
            state.setdefault("loaded_data", []).append(data_path)
            state["updated_at"] = datetime.now(timezone.utc).isoformat()
            self._save(state)
        return state

    def save_ctm(self, ctm_data: dict) -> dict:
        """Save a Context Transfer Memorandum to state and write to disk.

        CTMs are generated at 90% token budget to preserve latent context
        that cannot be transferred via structured state alone.

        Args:
            ctm_data: Dict with keys: phase, token_usage_pct, abandoned_paths,
                      micro_decisions, immediate_goals, partial_results,
                      open_questions, state_file_refs, handoff_notes

        Returns:
            Updated state dict
        """
        state = self._load()
        now = datetime.now(timezone.utc)

        ctm = {
            "ctm_id": f"ctm_{now.strftime('%Y%m%d_%H%M%S')}",
            "phase": ctm_data.get("phase", state.get("phase", "unknown")),
            "token_usage_pct": ctm_data.get("token_usage_pct", 0.9),
            "generated_at": now.isoformat(),
            "abandoned_paths": ctm_data.get("abandoned_paths", []),
            "micro_decisions": ctm_data.get("micro_decisions", []),
            "immediate_goals": ctm_data.get("immediate_goals", []),
            "partial_results": ctm_data.get("partial_results", []),
            "open_questions": ctm_data.get("open_questions", []),
            "state_file_refs": ctm_data.get("state_file_refs", []),
            "handoff_notes": ctm_data.get("handoff_notes", ""),
        }

        state.setdefault("context_transfer_memos", []).append(ctm)
        state["updated_at"] = now.isoformat()
        self._save(state)

        ctm_dir = self._path.parent / "context_transfer_memos"
        ctm_dir.mkdir(parents=True, exist_ok=True)
        ctm_path = ctm_dir / f"{ctm['ctm_id']}.json"
        self._save_to_path(ctm_path, ctm)

        return state

    def get_latest_ctm(self) -> Optional[dict]:
        """Retrieve the most recent Context Transfer Memorandum."""
        state = self._load()
        memos = state.get("context_transfer_memos", [])
        if memos:
            return memos[-1]
        return None

    def get_all_ctms(self) -> list:
        """Retrieve all Context Transfer Memoranda."""
        state = self._load()
        return state.get("context_transfer_memos", [])

    def get_dag_path(self) -> Path:
        """Get or create the execution DAG file path."""
        state = self._load()
        dag_path_str = state.get("execution_dag_path")
        if dag_path_str:
            return Path(dag_path_str)

        dag_path = self._path.parent / "execution_dag.json"
        state["execution_dag_path"] = str(dag_path)
        self._save(state)

        if not dag_path.exists():
            self._init_dag(dag_path)

        return dag_path

    def _init_dag(self, dag_path: Path) -> None:
        """Initialize a new execution DAG file."""
        state = self._load()
        dag = {
            "schema_version": "7.0.0",
            "project": state.get("project", ""),
            "nodes": {},
            "edges": [],
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }
        self._save_to_path(dag_path, dag)

    def _save_to_path(self, path: Path, data: dict) -> None:
        """Save data to a specific path atomically."""
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, indent=2, default=str)
            os.replace(tmp_path, str(path))
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    def add_dag_node(self, node_id: str, script_path: str, input_files: list,
                     output_files: list, depends_on: list = None,
                     iteration_id: str = None, status: str = "complete") -> dict:
        """Add a node to the execution DAG.

        Args:
            node_id: Unique node ID (format: <script_name>_<iteration_id>_<run_index>)
            script_path: Path to the executed script
            input_files: List of input data files consumed
            output_files: List of output files produced
            depends_on: List of node_ids this execution depends on
            iteration_id: Iteration ID if part of an iteration
            status: Execution status (pending, running, complete, failed)

        Returns:
            Updated state dict
        """
        dag_path = self.get_dag_path()

        if not dag_path.exists():
            self._init_dag(dag_path)

        with open(dag_path) as f:
            dag = json.load(f)

        now = datetime.now(timezone.utc).isoformat()
        state = self._load()
        current_branch = state.get("current_branch", state.get("active_branch", "main"))

        input_hashes = {}
        for fp in input_files:
            p = Path(fp)
            if p.exists():
                input_hashes[fp] = self._compute_file_hash(p)

        node = {
            "node_id": node_id,
            "script_path": script_path,
            "iteration_id": iteration_id,
            "branch_id": current_branch,
            "depends_on": depends_on or [],
            "input_files": input_files,
            "output_files": output_files,
            "status": status,
            "timestamp": now,
            "data_hash_in": input_hashes,
            "data_hash_out": {},
        }

        dag["nodes"][node_id] = node

        for dep in (depends_on or []):
            if dep in dag["nodes"]:
                dag["edges"].append({"from": dep, "to": node_id})

        dag["last_updated"] = now
        self._save_to_path(dag_path, dag)

        state["execution_dag_path"] = str(dag_path)
        state["updated_at"] = now
        self._save(state)

        return state

    def update_dag_node_output_hashes(self, node_id: str) -> dict:
        """Compute and store SHA-256 hashes for a node's output files."""
        dag_path = self.get_dag_path()
        if not dag_path.exists():
            return self._load()

        with open(dag_path) as f:
            dag = json.load(f)

        if node_id not in dag["nodes"]:
            return self._load()

        node = dag["nodes"][node_id]
        output_hashes = {}
        for fp in node.get("output_files", []):
            p = Path(fp)
            if p.exists():
                output_hashes[fp] = self._compute_file_hash(p)

        node["data_hash_out"] = output_hashes
        dag["last_updated"] = datetime.now(timezone.utc).isoformat()
        self._save_to_path(dag_path, dag)

        return self._load()

    def get_dag(self) -> dict:
        """Load and return the full execution DAG."""
        dag_path = self.get_dag_path()
        if not dag_path.exists():
            self._init_dag(dag_path)
        with open(dag_path) as f:
            return json.load(f)

    @staticmethod
    def _compute_file_hash(file_path: Path) -> str:
        """Compute SHA-256 hash of a file."""
        import hashlib
        sha256 = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    sha256.update(chunk)
            return sha256.hexdigest()
        except (FileNotFoundError, PermissionError):
            return "error"

    def summary(self) -> str:
        state = self._load()
        lines = [
            "=" * 60,
            "GLOBAL RESEARCH LEDGER",
            "=" * 60,
            "",
            f"  Run ID:      {state.get('run_id', 'N/A')}",
            f"  Project:     {state.get('project', 'N/A')}",
            f"  Phase:       {state.get('phase', 'N/A')} (step {state.get('step', 0)})",
            f"  Created:     {state.get('created_at', 'N/A')}",
            f"  Updated:     {state.get('updated_at', 'N/A')}",
            "",
            "  Checkpoints:",
        ]
        for phase, status in state.get("checkpoints", {}).items():
            marker = "✓" if status == "complete" else "○"
            lines.append(f"    {marker} {phase}: {status}")
        if not state.get("checkpoints"):
            lines.append("    (none yet)")

        lines.append("")
        lines.append(f"  Hypotheses: {len(state.get('active_hypotheses', []))}")
        for h in state.get("active_hypotheses", []):
            eff = f", effect={h['effect']}" if h.get("effect") is not None else ""
            lines.append(f"    - {h['id']}: {h['status']}{eff}")

        lines.append("")
        lines.append(f"  Dead ends: {len(state.get('dead_ends', []))}")
        for d in state.get("dead_ends", []):
            lines.append(f"    - {d}")

        lines.append("")
        lines.append(f"  Loaded data: {len(state.get('loaded_data', []))} file(s)")
        for d in state.get("loaded_data", []):
            lines.append(f"    - {d}")

        budget = state.get("token_budget", {})
        lines.append("")
        lines.append("  Token Budget:")
        lines.append(f"    Used:      {budget.get('used', 0):,}")
        lines.append(f"    Remaining: {budget.get('remaining', 0):,}")
        lines.append(f"    Limit:     {budget.get('limit', 0):,}")

        errors = state.get("errors", [])
        lines.append("")
        lines.append(f"  Errors: {len(errors)}")
        for e in errors[-5:]:
            lines.append(f"    - [{e.get('timestamp', '')}] {e.get('message', '')}")
        if len(errors) > 5:
            lines.append(f"    ... and {len(errors) - 5} more")

        lines.append("")
        lines.append(f"  Resumable from: {state.get('resumable_from', 'none')}")

        branches = state.get("branches", {})
        lines.append("")
        lines.append(f"  Branches: {len(branches)}")
        active = state.get("current_branch", state.get("active_branch", "main"))
        for bid, b in branches.items():
            marker = "▶" if bid == active else " "
            status_icon = "✓" if b.get("status") == "merged" else ("✗" if b.get("status") == "abandoned" else "○")
            parent = f" (from: {b.get('parent_branch', 'main')})" if b.get("parent_branch") and b.get("parent_branch") != "main" else ""
            lines.append(f"    {marker} {status_icon} {bid}{parent}")
            if b.get("hypothesis"):
                lines.append(f"      Hypothesis: {b['hypothesis']}")

        lines.append("")
        return "\n".join(lines)

    def get_project_summary(self, max_tokens: int = 500) -> str:
        """Return a compact project summary for new conversation injection.

        Covers: project title, current phase, last 3 decisions, active hypotheses,
        dead ends, next action. Target: under 500 tokens.

        Args:
            max_tokens: Approximate token limit for the output

        Returns:
            Compact summary string
        """
        state = self._load()
        lines = [
            f"Project: {state.get('project', 'unnamed')}",
            f"Phase: {state.get('phase', 'unknown')} (step {state.get('step', 0)})",
            f"Branch: {state.get('current_branch', state.get('active_branch', 'main'))}",
        ]

        # Last 3 decisions
        decisions = state.get("decisions", [])
        if decisions:
            last = decisions[-3:]
            lines.append("Recent decisions:")
            for i, d in enumerate(last, 1):
                desc = d.get("decision", d.get("description", str(d)))[:80]
                lines.append(f"  {i}. {desc}")

        # Active hypotheses
        hypotheses = state.get("active_hypotheses", [])
        if hypotheses:
            lines.append(f"Hypotheses ({len(hypotheses)}):")
            for h in hypotheses[:3]:
                eff = f" (effect={h['effect']})" if h.get("effect") is not None else ""
                lines.append(f"  - {h['id']}: {h['status']}{eff}")

        # Dead ends
        dead_ends = state.get("dead_ends", [])
        if dead_ends:
            lines.append(f"Dead ends to avoid ({len(dead_ends)}):")
            for d in dead_ends[-3:]:
                lines.append(f"  - {d[:80]}")

        # Next action
        checkpoints = state.get("checkpoints", {})
        pipeline = ["research_init", "literature_deep", "method_route", "data_scaffold",
                    "execute_analysis", "compile_outputs", "audit_validate"]
        completed = {p for p, s in checkpoints.items() if s == "complete"}
        next_action = next((p for p in pipeline if p not in completed), "research_iterate")
        lines.append(f"Next action: {next_action}")

        summary = "\n".join(lines)
        # Truncate at sentence boundary if over limit
        words = summary.split()
        if len(words) > max_tokens:
            truncated = " ".join(words[:max_tokens])
            for sep in (". ", "\n"):
                idx = truncated.rfind(sep)
                if idx > 0:
                    return truncated[:idx + 1]
            return truncated + "..."
        return summary

    def branch_state(
        self,
        branch_id: str,
        hypothesis: str = "",
        parent: str = None,
        experiment_dir: str = None,
        data_hashes: dict = None,
    ) -> dict:
        """Create a new research branch (Git-like branching model).

        Args:
            branch_id: Unique branch identifier (e.g., 'hypothesis_B', 'bayesian_approach')
            hypothesis: Research hypothesis or exploration goal for this branch
            parent: Parent branch to fork from (default: current active branch)

        Returns:
            Updated state dict with new branch

        Raises:
            ValueError: If branch_id already exists
        """
        state = self._load()
        branches = state.get("branches", {})

        # Initialize main branch if it doesn't exist
        if "main" not in branches:
            branches["main"] = {
                "branch_id": "main",
                "parent_branch": "",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "status": "active",
                "hypothesis": "Primary research workflow",
                "merge_commit": None,
                "merged_at": None,
                "evaluation": None,
                "workspace_prefix": "",
                "experiment_dir": "02_experiments/exp_001_baseline",
                "data_hashes": {},
            }
            state["branches"] = branches
            state["active_branch"] = "main"
            state["current_branch"] = "main"

        if branch_id in branches:
            raise ValueError(f"Branch '{branch_id}' already exists. Use a unique name.")

        parent_branch = parent or state.get("current_branch", state.get("active_branch", "main"))
        if parent_branch not in branches:
            raise ValueError(f"Parent branch '{parent_branch}' does not exist.")

        now = datetime.now(timezone.utc).isoformat()
        experiment_dir = experiment_dir or f"02_experiments/{branch_id}"
        workspace_prefix = f"{branch_id}/"

        branches[branch_id] = {
            "branch_id": branch_id,
            "parent_branch": parent_branch,
            "created_at": now,
            "status": "active",
            "hypothesis": hypothesis,
            "merge_commit": None,
            "merged_at": None,
            "evaluation": None,
            "workspace_prefix": workspace_prefix,
            "experiment_dir": experiment_dir,
            "data_hashes": data_hashes or {},
        }

        state["branches"] = branches
        state["active_branch"] = branch_id
        state["current_branch"] = branch_id
        state["updated_at"] = now
        self._save(state)

        logger.info("Created branch '%s' from '%s'", branch_id, parent_branch)
        return state

    def switch_branch(self, branch_id: str) -> dict:
        """Switch the active branch.

        Args:
            branch_id: Branch to switch to

        Returns:
            Updated state dict

        Raises:
            ValueError: If branch doesn't exist
        """
        state = self._load()
        branches = state.get("branches", {})

        if branch_id not in branches:
            raise ValueError(f"Branch '{branch_id}' does not exist. Available: {list(branches.keys())}")

        if branches[branch_id].get("status") == "abandoned":
            raise ValueError(f"Branch '{branch_id}' has been abandoned.")

        old_branch = state.get("active_branch", "main")
        state["active_branch"] = branch_id
        state["current_branch"] = branch_id
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._save(state)

        logger.info("Switched branch from '%s' to '%s'", old_branch, branch_id)
        return state

    def merge_branch(self, branch_id: str, target: str = "main", commit_msg: str = "") -> dict:
        """Merge a branch into the target branch.

        Args:
            branch_id: Branch to merge
            target: Target branch (default: 'main')
            commit_msg: Description of what is being merged

        Returns:
            Updated state dict

        Raises:
            ValueError: If branch doesn't exist or is already merged
        """
        state = self._load()
        branches = state.get("branches", {})

        if branch_id not in branches:
            raise ValueError(f"Branch '{branch_id}' does not exist.")

        if target not in branches:
            raise ValueError(f"Target branch '{target}' does not exist.")

        branch = branches[branch_id]
        if branch.get("status") == "merged":
            raise ValueError(f"Branch '{branch_id}' is already merged.")

        now = datetime.now(timezone.utc).isoformat()
        commit_id = f"merge_{branch_id}_{now.replace(':', '').replace('-', '')[:15]}"

        branches[branch_id]["status"] = "merged"
        branches[branch_id]["merge_commit"] = commit_id
        branches[branch_id]["merged_at"] = now
        branches[branch_id]["evaluation"] = {
            "decision": "merge",
            "rationale": commit_msg or f"Merged into {target}",
        }

        state["branches"] = branches
        state["active_branch"] = target
        state["current_branch"] = target
        state["updated_at"] = now
        self._save(state)

        logger.info("Merged branch '%s' into '%s': %s", branch_id, target, commit_msg)
        return state

    def abandon_branch(self, branch_id: str, reason: str = "") -> dict:
        """Abandon a research branch.

        Args:
            branch_id: Branch to abandon
            reason: Reason for abandonment

        Returns:
            Updated state dict
        """
        state = self._load()
        branches = state.get("branches", {})

        if branch_id not in branches:
            raise ValueError(f"Branch '{branch_id}' does not exist.")

        if branch_id == "main":
            raise ValueError("Cannot abandon the main branch.")

        now = datetime.now(timezone.utc).isoformat()
        branches[branch_id]["status"] = "abandoned"
        branches[branch_id]["evaluation"] = {
            "decision": "abandon",
            "rationale": reason or "Branch abandoned",
        }

        state["branches"] = branches
        if state.get("active_branch") == branch_id:
            state["active_branch"] = "main"
        if state.get("current_branch") == branch_id:
            state["current_branch"] = "main"
        state["updated_at"] = now
        self._save(state)

        logger.info("Abandoned branch '%s': %s", branch_id, reason)
        return state

    def list_branches(self) -> list:
        """List all branches with their status.

        Returns:
            List of branch info dicts
        """
        state = self._load()
        branches = state.get("branches", {})
        active = state.get("current_branch", state.get("active_branch", "main"))

        result = []
        for bid, b in branches.items():
            result.append({
                "branch_id": bid,
                "parent": b.get("parent_branch", "main"),
                "status": b.get("status", "unknown"),
                "hypothesis": b.get("hypothesis", ""),
                "active": bid == active,
                "created_at": b.get("created_at", ""),
                "workspace_prefix": b.get("workspace_prefix", ""),
                "experiment_dir": b.get("experiment_dir", ""),
                "data_hashes": b.get("data_hashes", {}),
            })
        return result

    def get_branch_workspace(self, branch_id: str = None) -> dict:
        """Get the workspace prefix for a branch.

        Returns dict with branch-specific directory paths:
        {
            "figures": "reports/figures/<branch>/",
            "scripts": "scripts/models/<branch>/",
            "analysis": "reports/analysis/<branch>/",
            ...
        }
        """
        state = self._load()
        bid = branch_id or state.get("current_branch", state.get("active_branch", "main"))
        branches = state.get("branches", {})

        if bid not in branches:
            raise ValueError(f"Branch '{bid}' does not exist.")

        prefix = branches[bid].get("workspace_prefix", "")
        if bid == "main":
            prefix = ""

        return {
            "branch_id": bid,
            "prefix": prefix,
            "figures": f"reports/figures/{prefix}" if prefix else "reports/figures/",
            "scripts": f"scripts/models/{prefix}" if prefix else "scripts/",
            "analysis": f"reports/analysis/{prefix}" if prefix else "reports/analysis/",
            "tables": f"reports/tables/{prefix}" if prefix else "reports/tables/",
            "manuscript": f"reports/manuscript/{prefix}" if prefix else "reports/manuscript/",
        }

    def compress_ledger(self, model: str = "ollama/llama3", dry_run: bool = False) -> dict:
        """Compress completed DAG node outputs using a local model.

        Feeds each completed checkpoint's output to the local model one-by-one
        to generate a 1-sentence abstract, then rewrites the ledger in place.
        This frees up ~80% of the context window at zero API cost.

        Args:
            model:   Model identifier in format ``provider/name`` (e.g.
                     ``ollama/llama3``, ``ollama/mistral``).
            dry_run: If True, print the compressed outputs without saving.

        Returns:
            Dict with keys ``compressed_nodes`` (count), ``original_chars``,
            ``compressed_chars``, and ``savings_pct``.
        """
        import subprocess
        import shutil

        state = self._load()

        provider, _, model_name = model.partition("/")
        if not model_name:
            model_name = provider
            provider = "ollama"

        if provider != "ollama":
            raise ValueError(
                f"Unsupported provider '{provider}'. Only 'ollama' is currently supported.\n"
                "Example: rcp compress --model=ollama/llama3"
            )

        if not shutil.which("ollama"):
            raise RuntimeError(
                "ollama is not installed or not on PATH.\n"
                "Install it from https://ollama.com and pull a model: ollama pull llama3"
            )

        db_path = self._path.parent.parent / ".research" / "cache" / "state_cache.sqlite"
        node_outputs: dict[str, str] = {}

        # Load raw outputs from SQLite cache if available.
        if db_path.exists():
            import sqlite3
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            try:
                cursor.execute("SELECT node_id, raw_output FROM outputs")
                for row in cursor.fetchall():
                    node_outputs[row[0]] = row[1] or ""
            except Exception:
                pass
            finally:
                conn.close()

        # Fall back to checkpoints stored in the ledger itself.
        for phase, status in state.get("checkpoints", {}).items():
            if phase not in node_outputs:
                node_outputs[phase] = str(status)

        if not node_outputs:
            return {"compressed_nodes": 0, "original_chars": 0, "compressed_chars": 0, "savings_pct": 0.0}

        total_original = sum(len(v) for v in node_outputs.values())
        compressed: dict[str, str] = {}

        print(f"Compressing {len(node_outputs)} node(s) with {model} ...")

        for node_id, raw_output in node_outputs.items():
            if not raw_output.strip():
                compressed[node_id] = ""
                continue

            prompt = (
                f"Summarize the following research pipeline node output in exactly ONE sentence, "
                f"preserving the most important metric, result, or error:\n\n{raw_output[:3000]}"
            )
            try:
                result = subprocess.run(
                    ["ollama", "run", model_name, prompt],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                summary = result.stdout.strip() or raw_output[:200]
            except subprocess.TimeoutExpired:
                logger.warning("Timeout compressing node %s — keeping original.", node_id)
                summary = raw_output[:200]
            except Exception as exc:
                logger.warning("Error compressing node %s: %s", node_id, exc)
                summary = raw_output[:200]

            compressed[node_id] = summary
            print(f"  [{node_id}] → {summary[:80]}{'…' if len(summary) > 80 else ''}")

        total_compressed = sum(len(v) for v in compressed.values())
        savings_pct = (
            round((1.0 - total_compressed / total_original) * 100, 1)
            if total_original > 0 else 0.0
        )

        if not dry_run:
            # Rewrite SQLite cache with compressed outputs.
            if db_path.exists():
                import sqlite3
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                for node_id, summary in compressed.items():
                    cursor.execute(
                        "INSERT OR REPLACE INTO outputs (node_id, raw_output) VALUES (?, ?)",
                        (node_id, summary),
                    )
                conn.commit()
                conn.close()

            # Record compression event in ledger.
            state.setdefault("compression_history", []).append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "model": model,
                "nodes_compressed": len(compressed),
                "original_chars": total_original,
                "compressed_chars": total_compressed,
                "savings_pct": savings_pct,
            })
            state["updated_at"] = datetime.now(timezone.utc).isoformat()
            self._save(state)
            print(f"\nCompression complete. Context savings: ~{savings_pct}%")

        return {
            "compressed_nodes": len(compressed),
            "original_chars": total_original,
            "compressed_chars": total_compressed,
            "savings_pct": savings_pct,
        }

