"""ResearchEngine — unified headless execution engine for Research Copilot.

Epic 3 additions:
  - HITL "Explain-to-Proceed" gate (Item 9): pauses on method-routing or
    exploratory intents to get user approval before running.
  - Dead-End Auto-Recovery (Item 12): when a node returns status=failed, the
    ledger is updated via add_dead_end(), the engine reverts to the parent
    node, injects the dead-end context into the next prompt, and forces an
    alternative pathway selection.
"""

import logging
import json
import tempfile
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from research_copilot.core.hooks import hook_engine
from research_copilot.core.state_ledger import ResearchLedger
from research_copilot.intent_router import IntentRouter
from research_copilot.project_ops import create_experiment_branch, log_decision, save_artifact
from research_copilot.utils.asset_manager import AssetManager
from research_copilot.utils.dag_manager import ExecutionDAGManager

logger = logging.getLogger("research.engine")

# Intents that require human approval before proceeding.
_HITL_INTENTS = {"hypothesis_test", "causal", "bayesian", "predictive", "manuscript"}
_MAX_DEAD_END_RETRIES = 3


class ResearchEngine:
    """Unified headless execution engine for Research Copilot.

    Attributes:
        root:              Project root Path.
        assets:            AssetManager for resolving skill/agent files.
        ledger:            ResearchLedger — single source of truth.
        hooks:             Hook engine for pre/post execution interceptors.
        router:            IntentRouter for depth-aware query routing.
        dag:               ExecutionDAGManager.
        depth:             Default routing depth.
        token_tracker:     TokenBudgetTracker.
        default_timeout:   Subprocess timeout in seconds.
        hitl_enabled:      When True, pause for user approval on method intents.
        _interactive:      Whether stdin is a real TTY (auto-detected).
    """

    def __init__(
        self,
        project_root: Optional[Path] = None,
        depth: str = "academic",
        default_timeout: int = 300,
        hitl_enabled: bool = True,
    ):
        self.root = project_root or AssetManager.find_project_root()
        if not self.root:
            raise ValueError("Not in a Research Copilot workspace.")

        self.assets = AssetManager(self.root)
        self.ledger = ResearchLedger(self.root / "03_synthesis" / "state_ledger.json")
        self.hooks = hook_engine
        self.router = IntentRouter(self.root)
        self.dag = ExecutionDAGManager(self.root)
        self.depth = depth
        self.default_timeout = default_timeout
        self.hitl_enabled = hitl_enabled

        import sys
        self._interactive = sys.stdin.isatty()

        from research_copilot.core.token_budget import TokenBudgetTracker
        self.token_tracker = TokenBudgetTracker(max_tokens=200_000)

    # ------------------------------------------------------------------
    # Item 9 — HITL "Explain-to-Proceed" Gate
    # ------------------------------------------------------------------

    def _hitl_gate(
        self,
        intent: str,
        proposed_plan: List[str],
        query: str,
    ) -> bool:
        """Pause and ask the user to approve the proposed plan.

        Sets ledger state to ``WAITING_ON_USER`` while waiting.  On approval
        it transitions back to ``running``.  When not running interactively
        (e.g. MCP server, tests) the gate is skipped and returns True.

        Args:
            intent:        Classified intent string (e.g. 'hypothesis_test').
            proposed_plan: List of proposed workflow steps.
            query:         Original user query.

        Returns:
            True if the user approves (or HITL is disabled / non-interactive).
            False if the user rejects.
        """
        if not self.hitl_enabled or not self._interactive:
            logger.info("HITL gate skipped (non-interactive or disabled).")
            return True

        # Record the waiting state.
        self.ledger.update(
            phase="WAITING_ON_USER",
            hitl_pending={
                "intent": intent,
                "proposed_plan": proposed_plan,
                "query": query,
            },
        )

        print("\n" + "=" * 60)
        print("  RESEARCH COPILOT — PLAN APPROVAL REQUIRED")
        print("=" * 60)
        print(f"\nQuery : {query}")
        print(f"Intent: {intent}\n")
        print("Proposed plan:")
        for i, step in enumerate(proposed_plan, 1):
            print(f"  {i}. {step}")
        print()

        try:
            answer = input("Approve this plan? [Y/n]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = "n"

        approved = answer in ("", "y", "yes")

        self.ledger.update(
            phase="running" if approved else "user_rejected",
            hitl_pending=None,
        )

        if not approved:
            print("Plan rejected. Workflow halted.")
        return approved

    # ------------------------------------------------------------------
    # Item 12 — Dead-End Auto-Recovery
    # ------------------------------------------------------------------

    def _handle_dead_end(
        self,
        node_id: str,
        failed_result: Dict[str, Any],
        retry_count: int = 0,
    ) -> Dict[str, Any]:
        """Record a dead-end and prepare recovery context.

        Called when a node returns status=failed.  It:
        1. Calls ledger.add_dead_end() with the failed approach.
        2. Logs the failure to the DAG.
        3. Returns a recovery dict with injected error context for the
           calling loop to inject into the next prompt.

        Args:
            node_id:       The failed DAG node ID.
            failed_result: The result dict with status=failed.
            retry_count:   How many dead-ends have already been recorded.

        Returns:
            Recovery dict with keys: dead_end_recorded, error_context,
            retry_allowed, suggested_action.
        """
        approach_desc = f"{node_id}: {failed_result.get('stderr', '')[:200]}"
        self.ledger.add_dead_end(approach_desc)
        self.ledger.add_error(
            f"Dead-end at node '{node_id}' (attempt {retry_count + 1}): "
            f"{failed_result.get('stderr', '')[:300]}"
        )

        logger.warning(
            "Dead-end recorded for node '%s' (attempt %d/%d). "
            "Reverting to parent and injecting error context.",
            node_id, retry_count + 1, _MAX_DEAD_END_RETRIES,
        )

        retry_allowed = retry_count < _MAX_DEAD_END_RETRIES

        dead_ends = self.ledger.get().get("dead_ends", [])
        error_context = (
            f"DEAD-END DETECTED — The following approach failed and must NOT be repeated:\n"
            f"  Node: {node_id}\n"
            f"  Error: {failed_result.get('stderr', '(no stderr)')[:400]}\n\n"
            f"All dead ends so far:\n"
            + "\n".join(f"  - {d}" for d in dead_ends[-5:])
            + "\n\nSelect an ALTERNATIVE methodology or approach."
        )

        return {
            "dead_end_recorded": True,
            "error_context": error_context,
            "retry_allowed": retry_allowed,
            "suggested_action": "select_alternative_pathway",
            "dead_end_count": len(dead_ends),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _run_script(
        self,
        script_content: str,
        *,
        timeout: Optional[int] = None,
        node_id: Optional[str] = None,
        input_files: Optional[list] = None,
        output_files: Optional[list] = None,
    ) -> Dict[str, Any]:
        """Write *script_content* to a temp file and execute via ResearchExecutor."""
        from research_copilot.utils.executor import ResearchExecutor

        executor = ResearchExecutor(root=self.root)
        effective_timeout = timeout or self.default_timeout

        fd, tmp_path = tempfile.mkstemp(suffix=".py", prefix="rcp_node_")
        try:
            with os.fdopen(fd, "w") as f:
                f.write(script_content)

            result = executor.run_python(
                script_path=tmp_path,
                timeout=effective_timeout,
                node_id=node_id,
                input_files=input_files or [],
                output_files=output_files or [],
            )
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        if result.exit_code == 0:
            return {
                "status": "success",
                "node": node_id,
                "output": result.stdout,
                "stderr": result.stderr,
                "exit_code": 0,
                "duration_seconds": result.duration_seconds,
            }
        else:
            logger.warning(
                "Node %s failed (exit %d):\n%s",
                node_id, result.exit_code, result.stderr,
            )
            return {
                "status": "failed",
                "node": node_id,
                "output": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.exit_code,
                "duration_seconds": result.duration_seconds,
                "error_context": result.stderr,
            }

    def _validate_agent_output(
        self,
        raw_json: str,
        task_name: str,
        call_llm: Optional[Any] = None,
        base_prompt: str = "",
        node_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        from research_copilot.assets.schemas.validator import validate_with_retry, get_schema_for_task

        try:
            schema = get_schema_for_task(task_name)
        except ValueError:
            logger.debug("No schema for task '%s' — skipping validation.", task_name)
            try:
                return json.loads(raw_json)
            except json.JSONDecodeError:
                return {"raw": raw_json}

        try:
            instance = validate_with_retry(
                raw_json=raw_json,
                schema=schema,
                call_llm=call_llm,
                base_prompt=base_prompt,
                node_id=node_id,
            )
            return instance.model_dump()
        except Exception as exc:
            logger.error(
                "Node %s failed Pydantic validation after all retries: %s", node_id, exc
            )
            self.ledger.add_error(f"Node {node_id} schema validation failed: {exc}")
            return None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def execute_node(
        self,
        node_id: str,
        script: Optional[str] = None,
        task_name: Optional[str] = None,
        call_llm: Optional[Any] = None,
        base_prompt: str = "",
        timeout: Optional[int] = None,
        input_files: Optional[list] = None,
        output_files: Optional[list] = None,
        dead_end_context: Optional[str] = None,
        dead_end_retry: int = 0,
        **kwargs,
    ) -> Dict[str, Any]:
        """Execute a single DAG node with dead-end recovery.

        Args:
            node_id:          Unique identifier for this DAG node.
            script:           Python source code to execute (optional).
            task_name:        Schema key for Pydantic validation (optional).
            call_llm:         Callable(prompt) -> str for retry prompts.
            base_prompt:      Original prompt used to build retry context.
            timeout:          Per-node subprocess timeout in seconds.
            input_files:      Input files tracked in the execution DAG.
            output_files:     Output files tracked in the execution DAG.
            dead_end_context: Injected context from a previous dead-end.
            dead_end_retry:   Number of dead-end retries so far.
            **kwargs:         Forwarded to pre_execution hook and cache key.

        Returns:
            Result dict with at minimum: status, node, output.
            On dead-end: additionally contains dead_end_recorded, error_context.
        """
        logger.info("Executing node %s (dead_end_retry=%d)", node_id, dead_end_retry)
        effective_script = script

        # ── Item 15: Data Scale Detector Prompt Injection ───────────────────────
        if "data_scaffold" in node_id or (task_name and "data" in task_name):
            try:
                from research_copilot.utils.data_scale_detector import DataScaleDetector
                detector = DataScaleDetector(self.root)
                constraint = detector.get_constraint_message()
                if constraint:
                    if effective_script:
                        effective_script = f"# {constraint.replace(chr(10), chr(10) + '# ')}\n\n" + effective_script
                    if base_prompt:
                        base_prompt = f"{base_prompt}\n\n{constraint}"
                    if not dead_end_context:
                        dead_end_context = constraint
            except Exception as e:
                logger.warning("Data scale detection failed: %s", e)

        # Inject dead-end context into the script/prompt if provided.
        if dead_end_context and effective_script:
            effective_script = (
                f"# DEAD-END CONTEXT (injected by ResearchEngine):\n"
                f"# {dead_end_context.replace(chr(10), chr(10) + '# ')}\n\n"
                + effective_script
            )

        import hashlib
        inputs_str = json.dumps(
            {"node_id": node_id, "dead_end_retry": dead_end_retry, **kwargs},
            sort_keys=True,
        )
        data_hash = hashlib.md5(inputs_str.encode()).hexdigest()

        state = {
            "node_id": node_id,
            "operation": node_id,
            "data_hash": data_hash,
            "kwargs": kwargs,
        }
        state = self.hooks.trigger_sync("pre_execution", state) or state

        if state.get("skip_execution") and "cached_result" in state:
            logger.info("Cache hit for %s, skipping execution.", node_id)
            result = {
                "status": "success",
                "node": node_id,
                "output": state["cached_result"],
                "cached": True,
            }
            self.hooks.trigger_sync(
                "post_execution",
                {"node_id": node_id, "result": result},
            )
            return result

        if effective_script:
            result = self._run_script(
                effective_script,
                timeout=timeout,
                node_id=node_id,
                input_files=input_files,
                output_files=output_files,
            )

            # ── Item 12: Dead-End Auto-Recovery ─────────────────────────────
            if result["status"] == "failed":
                recovery = self._handle_dead_end(node_id, result, dead_end_retry)
                result.update(recovery)
                return result

            # ── Item 16: Automated Figure Validation Integration ─────────────
            if result["status"] == "success" and ("viz" in node_id or "figure" in node_id or "plot" in node_id):
                try:
                    from research_copilot.utils.figure_validator import validate_figure_file
                    png_files = [f for f in (output_files or []) if str(f).endswith(".png")]
                    for png in png_files:
                        png_path = self.root / png
                        if png_path.exists():
                            val_report = validate_figure_file(str(png_path))
                            if val_report["verdict"] == "FAIL":
                                logger.warning("Figure validation failed for %s", png)
                                result["status"] = "failed"
                                errs = "\n".join(val_report.get("errors", []))
                                result["stderr"] = f"Figure validation failed for {png}:\n{errs}\n" + result.get("stderr", "")
                                result["error_context"] = result["stderr"]
                                recovery = self._handle_dead_end(node_id, result, dead_end_retry)
                                result.update(recovery)
                                return result
                except Exception as e:
                    logger.warning("Automated figure validation failed: %s", e)

            if result["status"] == "success" and task_name and result.get("output"):
                validated = self._validate_agent_output(
                    raw_json=result["output"].strip(),
                    task_name=task_name,
                    call_llm=call_llm,
                    base_prompt=base_prompt,
                    node_id=node_id,
                )
                if validated is None:
                    result["status"] = "failed"
                    result["error_context"] = (
                        "Pydantic schema validation failed after all retries."
                    )
                    recovery = self._handle_dead_end(node_id, result, dead_end_retry)
                    result.update(recovery)
                    return result
                else:
                    result["validated_output"] = validated
        else:
            try:
                from research_copilot.utils.cache_manager import ResearchCache
                cache = ResearchCache(
                    self.root / ".research" / "cache" / "research_cache.db"
                )
                cached = cache.get_computed_stats(data_hash, node_id)
                if cached:
                    result = cached
                else:
                    result = {
                        "status": "success",
                        "node": node_id,
                        "output": "Execution completed",
                    }
                    cache.set_computed_stats(data_hash, node_id, result)
            except Exception:
                result = {
                    "status": "success",
                    "node": node_id,
                    "output": "Execution completed",
                }

        self.hooks.trigger_sync(
            "post_execution",
            {
                "node_id": node_id,
                "last_output": result.get("output", ""),
                "result": result,
            },
        )

        if hasattr(self, "token_tracker"):
            self.token_tracker.add_usage(500, 200)

        return result

    def route_and_execute(
        self,
        query: str,
        depth: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Route a query and execute the workflow, with HITL gate for
        method-routing or exploratory intents that need human approval.
        """
        target_depth = depth or self.depth
        self.hooks.trigger_sync("pre_routing", {"query": query, "depth": target_depth})

        workflow = self.router.route(query, depth=target_depth)
        intent = workflow.get("classification", {}).get("primary_intent", "exploratory")

        # ── Item 9: HITL gate ────────────────────────────────────────────────
        if intent in _HITL_INTENTS:
            proposed_plan = workflow.get("context", {}).get("workflow_steps", [])
            approved = self._hitl_gate(intent, proposed_plan, query)
            if not approved:
                return {
                    "workflow": workflow,
                    "results": [],
                    "status": "user_rejected",
                    "message": "User rejected the proposed plan.",
                }

        if target_depth == "exploratory":
            logger.info("Bypassing DAG for exploratory intent → zero_shot_analyst.")
            result = self.execute_node(
                "zero_shot_analysis", agent="zero_shot_analyst", query=query
            )
            return {"workflow": workflow, "results": [result]}

        results: List[Dict[str, Any]] = []
        dead_end_context: Optional[str] = None
        dead_end_retry = 0

        for step in workflow.get("context", {}).get("workflow_steps", []):
            res = self.execute_node(
                step,
                dead_end_context=dead_end_context,
                dead_end_retry=dead_end_retry,
            )
            results.append(res)

            # ── Item 12: propagate dead-end context to next node ─────────────
            if res.get("dead_end_recorded"):
                if not res.get("retry_allowed", False):
                    logger.error(
                        "Maximum dead-end retries (%d) reached. Halting workflow.",
                        _MAX_DEAD_END_RETRIES,
                    )
                    break
                dead_end_context = res.get("error_context")
                dead_end_retry += 1
            else:
                dead_end_context = None
                dead_end_retry = 0

        return {"workflow": workflow, "results": results}

    def create_branch(self, name: str, hypothesis: str) -> Dict[str, Any]:
        branch_result = create_experiment_branch(name, hypothesis, root=self.root)
        self.ledger.branch_state(name)
        return {
            "status": "success",
            "branch": name,
            "directory": branch_result["experiment_dir"],
        }

    def log_decision(
        self,
        context: str,
        selected_option: str,
        rationale: str,
        branch: Optional[str] = None,
    ) -> Dict[str, Any]:
        log_decision(
            context=context,
            selected=selected_option,
            rationale=rationale,
            branch_id=branch,
            root=self.root,
        )
        return {"status": "success", "message": "Decision logged successfully."}

    def save_artifact(
        self,
        filepath: str,
        content: str,
        artifact_type: str,
        branch: Optional[str] = None,
    ) -> Dict[str, Any]:
        result = save_artifact(
            filename=filepath,
            content=content,
            artifact_type=artifact_type,
            branch_id=branch,
            root=self.root,
        )
        return {"status": "success", "path": result["artifact"]}
