#!/usr/bin/env python3
"""Global Research Ledger — atomic state management for the research pipeline.

Single source of truth for every pipeline run. Replaces fragmented
manifest/registry/log files with one authoritative object.

Location: .os_state/state_ledger.json (primary). Human-readable
project status lives at STATE.md at the project root, NOT at
.os_state/state_ledger.yaml (removed in v1.3.0 — was a duplicate).
"""

import json
import logging
import os
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

try:
    import fcntl  # type: ignore[import-untyped]  # POSIX only
except ImportError:  # pragma: no cover — Windows fallback
    fcntl = None  # type: ignore[assignment]

try:
    import yaml  # type: ignore[import-untyped]
except ImportError:
    yaml = None

logger = logging.getLogger("research.state_ledger")

from research_os.utils.common import find_project_root


class ResearchLedger:
    """Thread-safe, atomic research state ledger."""

    def __init__(self, state_path: Optional[Path] = None):
        if state_path is None:
            root = find_project_root()
            state_path = root / ".os_state" / "state_ledger.json"
        self._path = Path(state_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> dict:
        if self._path.exists():
            with open(self._path) as f:
                raw = json.load(f)
            return self._migrate(raw)
        return self._default_state()

    def _save(self, data: dict) -> None:
        """Atomic write: write to temp file, then rename to avoid corruption.

        Wrapped in an advisory file lock (POSIX ``fcntl.flock``) so two
        concurrent writers serialise instead of clobbering each other.
        Windows has no fcntl — there we fall through unlocked (single-user
        dev environment, the atomic ``os.replace`` is best-effort)."""
        self._path.parent.mkdir(parents=True, exist_ok=True)

        lock_path = self._path.with_suffix(".lock")
        lock_fd: Optional[int] = None
        if fcntl is not None:
            lock_fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT, 0o600)
            fcntl.flock(lock_fd, fcntl.LOCK_EX)

        try:
            fd, tmp_path = tempfile.mkstemp(dir=str(self._path.parent), suffix=".tmp")
            try:
                with os.fdopen(fd, "w") as f:
                    json.dump(data, f, indent=2, default=str, sort_keys=True)
                os.replace(tmp_path, str(self._path))
            except Exception:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                raise

            # v1.3.0: stopped writing the .yaml mirror. STATE.md at the
            # project root + state_ledger.json are sufficient. The yaml
            # was duplicate, hard to keep in sync, and contributed to the
            # .os_state "too many files" friction the user surfaced.
            # Clean up any stale yaml from a previous Research-OS version.
            stale_yaml = self._path.with_suffix(".yaml")
            if stale_yaml.exists():
                try:
                    stale_yaml.unlink()
                except OSError:
                    pass
        finally:
            if lock_fd is not None and fcntl is not None:
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
                finally:
                    os.close(lock_fd)

    @staticmethod
    def _default_state() -> dict:
        """Canonical default state — ONE schema, no legacy aliases.

        Fields removed (kept only as compatibility shims via _migrate):
          * ``run_id``                — duplicated ``project_id``; dropped.
          * ``phase``                 — legacy alias of ``pipeline_stage``.
          * ``project``               — legacy alias of ``project_name``.
          * ``token_budget``          — vestigial 200K-static placeholder.
          * ``knowledge_graph_path``  — never read by any tool.
          * ``data_scale_profile``    — placeholder, never populated.
          * ``execution_dag_path``    — DAG file lives at a fixed
            ``.os_state/execution_dag.json`` path; no need to record.

        Fields externalised to disk-only logs (NOT inlined in state):
          * ``context_transfer_memos`` — kept in
            ``.os_state/context_transfer_memos/<ctm_id>.json``; the in-state
            list now stores only ``{ctm_id, generated_at, phase}`` stubs
            so the JSON doesn't bloat across long sessions.
          * ``checkpoint_history`` / ``rollback_history`` — pulled from
            ``.os_state/checkpoints/*.meta.json`` on demand.
        """
        now = datetime.now(timezone.utc).isoformat()
        return {
            "schema_version": "4.0",
            "project_id": str(uuid.uuid4()),
            "project_name": "Research Project",
            "created_at": now,
            "updated_at": now,
            "pipeline_stage": "init",
            "step": 0,
            "current_path": "main",
            "checkpoints": {},
            "active_hypotheses": [],
            "dead_ends": [],
            "loaded_data": [],
            "errors": [],
            "resumable_from": None,
            "last_checkpoint": now,
            "context_transfer_memo_stubs": [],
            "linked_external_data": [],
            "paths": {
                "main": {
                    "path_id": "main",
                    "created_at": now,
                    "status": "active",
                    "experiment_dir": "workspace",
                }
            },
        }

    @staticmethod
    def _migrate(state: dict) -> dict:
        """Translate legacy fields into the canonical schema in-place.

        Kept for one release cycle so existing projects continue to boot
        without manual intervention. Logs at INFO when migration runs.
        """
        changed = False
        # phase → pipeline_stage
        if "phase" in state and "pipeline_stage" not in state:
            state["pipeline_stage"] = state.pop("phase")
            changed = True
        elif "phase" in state and "pipeline_stage" in state:
            state.pop("phase", None)
            changed = True
        # project → project_name
        if "project" in state and not state.get("project_name"):
            state["project_name"] = state.pop("project") or "Research Project"
            changed = True
        elif "project" in state:
            state.pop("project", None)
            changed = True
        # run_id → project_id
        if "run_id" in state and not state.get("project_id"):
            state["project_id"] = state.pop("run_id")
            changed = True
        elif "run_id" in state:
            state.pop("run_id", None)
            changed = True
        # Drop vestigial fields outright. checkpoint_history /
        # rollback_history were always written but never read — their
        # canonical home is .os_state/checkpoints/*.meta.json. Older
        # state files still carry them; pop on migration.
        for vestigial in (
            "token_budget", "knowledge_graph_path", "data_scale_profile",
            "execution_dag_path", "checkpoint_history", "rollback_history",
        ):
            if vestigial in state:
                state.pop(vestigial)
                changed = True
        # Externalise full CTM blobs. We keep only stubs in-state.
        if state.get("context_transfer_memos"):
            stubs = []
            for ctm in state["context_transfer_memos"]:
                if isinstance(ctm, dict):
                    stubs.append({
                        "ctm_id": ctm.get("ctm_id"),
                        "generated_at": ctm.get("generated_at"),
                        "phase": ctm.get("phase"),
                    })
            state["context_transfer_memo_stubs"] = stubs
            del state["context_transfer_memos"]
            changed = True
        state.setdefault("context_transfer_memo_stubs", [])
        # Per-path: drop the bulky input_data_hashes / data_hashes mirrors;
        # `compute_input_hashes` returns the live view on demand.
        for p in state.get("paths", {}).values():
            for legacy_key in ("input_data_hashes", "data_hashes"):
                if legacy_key in p:
                    p.pop(legacy_key)
                    changed = True
        if changed:
            state["schema_version"] = "4.0"
            logger.info("ResearchLedger migrated legacy state → schema 4.0")
        return state



    def get(self) -> dict:
        return self._load()

    def get_current_path(self) -> str:
        """Return the currently active experiment path id."""
        state = self._load()
        return state.get("current_path", "main")

    def update(self, **kwargs) -> dict:
        state = self._load()
        state.update(kwargs)
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._save(state)
        return state

    def set_phase(self, phase: str, step: int = 0) -> dict:
        """Backward-compatible name; updates ``pipeline_stage``."""
        state = self._load()
        state["pipeline_stage"] = phase
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
        self._save(state)
        return state

    def add_hypothesis(
        self,
        hypothesis_id: str,
        status: str = "testing",
        effect: Optional[float] = None,
    ) -> dict:
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
        state.setdefault("errors", []).append(
            {
                "message": error,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._save(state)
        return state

    def track_tokens(self, used: int, limit: Optional[int] = None) -> dict:
        """Deprecated — token_budget removed from state schema in v4.0.

        The runtime token accounting was never reliable (numbers were a
        static 200k placeholder unrelated to the actual model). The IDE's
        own context manager is the authoritative source; this no-op stub
        is kept only so existing callers don't break.
        """
        state = self._load()
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
        """Save a Context Transfer Memorandum.

        Architecture: full CTM blob is written to disk at
        ``.os_state/context_transfer_memos/<ctm_id>.json``. The state
        ledger keeps only a 3-field STUB (``ctm_id``, ``generated_at``,
        ``phase``) so multi-day sessions don't accumulate megabytes of
        CTM text inside the state ledger.

        CTMs are typically generated at 90% token budget to preserve
        context that doesn't survive structured-state transfer alone.
        """
        state = self._load()
        now = datetime.now(timezone.utc)

        ctm = {
            "ctm_id": f"ctm_{now.strftime('%Y%m%d_%H%M%S')}",
            "phase": ctm_data.get(
                "phase", state.get("pipeline_stage", "unknown"),
            ),
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

        # Disk-side: full blob.
        ctm_dir = self._path.parent / "context_transfer_memos"
        ctm_dir.mkdir(parents=True, exist_ok=True)
        ctm_path = ctm_dir / f"{ctm['ctm_id']}.json"
        self._save_to_path(ctm_path, ctm)

        # State-side: stub only.
        state.setdefault("context_transfer_memo_stubs", []).append({
            "ctm_id": ctm["ctm_id"],
            "generated_at": ctm["generated_at"],
            "phase": ctm["phase"],
        })
        state["updated_at"] = now.isoformat()
        self._save(state)

        return state

    def get_latest_ctm(self) -> Optional[dict]:
        """Load the most recent Context Transfer Memorandum from disk."""
        state = self._load()
        stubs = state.get("context_transfer_memo_stubs", [])
        if not stubs:
            return None
        latest = stubs[-1]
        ctm_path = (
            self._path.parent
            / "context_transfer_memos"
            / f"{latest['ctm_id']}.json"
        )
        if not ctm_path.exists():
            return latest  # stub-only fallback
        try:
            return json.loads(ctm_path.read_text())
        except Exception:
            return latest

    def get_all_ctms(self) -> list:
        """Load every Context Transfer Memorandum from disk (or stubs if missing)."""
        state = self._load()
        stubs = state.get("context_transfer_memo_stubs", [])
        out: list = []
        ctm_dir = self._path.parent / "context_transfer_memos"
        for stub in stubs:
            p = ctm_dir / f"{stub['ctm_id']}.json"
            if p.exists():
                try:
                    out.append(json.loads(p.read_text()))
                    continue
                except Exception:
                    pass
            out.append(stub)
        return out

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
                json.dump(data, f, indent=2, default=str, sort_keys=True)
            os.replace(tmp_path, str(path))
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    def add_dag_node(
        self,
        node_id: str,
        script_path: str,
        input_files: list,
        output_files: list,
        depends_on: list = None,
        iteration_id: str = None,
        status: str = "complete",
    ) -> dict:
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
        current_path = state.get("current_path", "main")

        input_hashes = {}
        for fp in input_files:
            p = Path(fp)
            if p.exists():
                input_hashes[fp] = self._compute_file_hash(p)

        node = {
            "node_id": node_id,
            "script_path": script_path,
            "iteration_id": iteration_id,
            "path_id": current_path,
            "depends_on": depends_on or [],
            "input_files": input_files,
            "output_files": output_files,
            "status": status,
            "timestamp": now,
            "data_hash_in": input_hashes,
            "data_hash_out": {},
        }

        dag["nodes"][node_id] = node

        for dep in depends_on or []:
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
        """Human-readable status snapshot. Slimmer than the dump form:
        no token-budget panel, no per-error trace tail."""
        state = self._load()
        lines = [
            "=" * 60,
            "RESEARCH LEDGER",
            "=" * 60,
            "",
            f"  Project:        {state.get('project_name', 'unnamed')}",
            f"  Pipeline:       {state.get('pipeline_stage', 'init')} (step {state.get('step', 0)})",
            f"  Current path:   {state.get('current_path', 'main')}",
            f"  Updated:        {state.get('updated_at', 'N/A')}",
            "",
            "  Checkpoints:",
        ]
        for phase, status in (state.get("checkpoints", {}) or {}).items():
            marker = "✓" if status == "complete" else "○"
            lines.append(f"    {marker} {phase}: {status}")
        if not state.get("checkpoints"):
            lines.append("    (none yet)")

        hyps = state.get("active_hypotheses", []) or []
        lines.append("")
        lines.append(f"  Hypotheses ({len(hyps)}):")
        for h in hyps[:8]:
            eff = f", effect={h['effect']}" if h.get("effect") is not None else ""
            lines.append(f"    - {h['id']}: {h['status']}{eff}")
        if len(hyps) > 8:
            lines.append(f"    … and {len(hyps) - 8} more")

        dead = state.get("dead_ends", []) or []
        lines.append("")
        lines.append(f"  Dead ends: {len(dead)}")
        for d in dead[-3:]:
            lines.append(f"    - {d}")

        errors = state.get("errors", []) or []
        lines.append("")
        lines.append(f"  Errors: {len(errors)} (latest only)")
        if errors:
            e = errors[-1]
            lines.append(f"    - [{e.get('timestamp', '')}] {e.get('message', '')[:120]}")

        paths = state.get("paths", {}) or {}
        active = state.get("current_path", "main")
        lines.append("")
        lines.append(f"  Paths: {len(paths)}")
        for pid, p in paths.items():
            marker = "▶" if pid == active else " "
            status_icon = {
                "active": "○", "completed": "✓",
                "dead_end": "✗", "abandoned": "✗",
            }.get(p.get("status", "active"), "○")
            lines.append(f"    {marker} {status_icon} {pid}")

        ctm_count = len(state.get("context_transfer_memo_stubs", []))
        if ctm_count:
            lines.extend(["", f"  Context transfers archived: {ctm_count}"])

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
            f"Project: {state.get('project_name', 'unnamed')}",
            f"Phase: {state.get('pipeline_stage', 'unknown')} (step {state.get('step', 0)})",
            f"Path: {state.get('current_path', 'main')}",
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
        pipeline = [
            "domain_analysis", "research_design", "methodology_selection",
            "literature_search", "evidence_synthesis", "analysis_plan",
            "figure_guidelines", "writing_core", "writing_synthesis",
            "audit_and_validation",
        ]
        completed = {p for p, s in checkpoints.items() if s == "complete"}
        next_action = next(
            (p for p in pipeline if p not in completed), "research_iterate"
        )
        lines.append(f"Next action: {next_action}")

        summary = "\n".join(lines)
        # Truncate at sentence boundary if over limit
        words = summary.split()
        if len(words) > max_tokens:
            truncated = " ".join(words[:max_tokens])
            for sep in (". ", "\n"):
                idx = truncated.rfind(sep)
                if idx > 0:
                    return truncated[: idx + 1]
            return truncated + "..."
        return summary

    def snapshot_workspace(self, checkpoint_id: str, root: Path | None = None) -> dict:
        """Snapshot workspace/ into .os_state/checkpoints/<checkpoint_id>/."""
        if root is None:
            try:
                root = find_project_root()
            except Exception:
                root = self._path.parent.parent
        ckpt_dir = root / ".os_state" / "checkpoints" / checkpoint_id
        ckpt_dir.mkdir(parents=True, exist_ok=True)

        manifest: list[dict] = []
        workspace = root / "workspace"
        if workspace.exists():
            for f in sorted(workspace.rglob("*")):
                if not f.is_file():
                    continue
                # Skip large binary / data artifacts
                ext = f.suffix.lower()
                if ext in (
                    ".csv",
                    ".parquet",
                    ".feather",
                    ".pkl",
                    ".joblib",
                    ".h5",
                    ".hdf5",
                ):
                    manifest.append(
                        {
                            "path": str(f.relative_to(root)),
                            "size": f.stat().st_size,
                            "sha256": "ref_only",
                            "skipped": True,
                        }
                    )
                    continue
                rel = f.relative_to(root)
                dest = ckpt_dir / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dest)
                manifest.append(
                    {
                        "path": str(rel),
                        "size": f.stat().st_size,
                        "sha256": "copied",
                    }
                )

        (ckpt_dir / "checkpoint_manifest.json").write_text(
            json.dumps(manifest, indent=2, default=str) + "\n"
        )
        return {
            "checkpoint_id": checkpoint_id,
            "path": str(ckpt_dir.absolute()),
            "files_snapshotted": len([m for m in manifest if not m.get("skipped")]),
            "files_ref_only": len([m for m in manifest if m.get("skipped")]),
        }

    def rollback(self, checkpoint_id: str, root: Path | None = None) -> dict:
        """Restore workspace from a checkpoint snapshot.

        Reads checkpoint_manifest.json from .os_state/checkpoints/<checkpoint_id>/
        and restores every file to its original location under workspace/.
        The current workspace state is backed up first.
        """
        if root is None:
            try:
                root = find_project_root()
            except Exception:
                root = self._path.parent.parent
        ckpt_dir = root / ".os_state" / "checkpoints" / checkpoint_id
        manifest_path_ckpt = ckpt_dir / "checkpoint_manifest.json"

        if not manifest_path_ckpt.exists():
            raise FileNotFoundError(
                f"Checkpoint '{checkpoint_id}' not found at {ckpt_dir}. "
                f"Available: {[d.name for d in (root / '.os_state' / 'checkpoints').iterdir()] if (root / '.os_state' / 'checkpoints').exists() else 'none'}"
            )

        # Backup current workspace
        backup_id = f"pre_rollback_{checkpoint_id}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        backup_dir = root / ".os_state" / "checkpoints" / backup_id
        backup_dir.mkdir(parents=True, exist_ok=True)

        workspace = root / "workspace"
        if workspace.exists():
            for f in sorted(workspace.rglob("*")):
                if not f.is_file():
                    continue
                rel = f.relative_to(root)
                dest = backup_dir / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dest)

        # Restore from checkpoint
        manifest: list[dict] = json.loads(manifest_path_ckpt.read_text())
        restored = 0
        for entry in manifest:
            if entry.get("skipped"):
                continue
            dest_path = root / entry["path"]
            src_path = ckpt_dir / entry["path"]
            if src_path.exists():
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_path, dest_path)
                restored += 1

        # Touch updated_at so consumers of state ordering see the
        # rollback event. The rollback-history list previously persisted
        # here was never read by any code path (the .meta.json sidecars
        # in .os_state/checkpoints/ are the authoritative log) — dropped
        # to keep state.json lean.
        state = self._load()
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._save(state)

        logger.info(
            "Rollback to '%s' complete — %d files restored (backup: %s)",
            checkpoint_id,
            restored,
            backup_id,
        )
        return {
            "checkpoint_id": checkpoint_id,
            "backup_id": backup_id,
            "files_restored": restored,
        }

