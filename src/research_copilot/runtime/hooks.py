"""Lifecycle Hook Registry Engine.

Maps tasks to discrete hook decorators, enabling interceptor modules to interrupt
or modify agent payloads at five key stages of the lifecycle.

Designed for AI agent use: all hooks work synchronously (no asyncio required).
The registry accepts both sync and async interceptors and normalizes them.
"""

import json
import logging
import asyncio
from pathlib import Path
from typing import Callable, Dict, List, Any, Optional, Union
from datetime import datetime, timezone

logger = logging.getLogger("research.hooks")


def _run_async_in_sync(coro):
    """Run an async coroutine synchronously, reusing or creating an event loop.

    This is the bridge that allows AI agents (which call hooks synchronously)
    to use async interceptors without needing nest_asyncio or external hacks.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import nest_asyncio
        nest_asyncio.apply(loop)
        return loop.run_until_complete(coro)

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    if loop.is_closed():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(coro)


class HookRegistry:
    """Registry for lifecycle hooks that intercept and modify pipeline state.

    Usage:
        from research_copilot.runtime.hooks import hook_engine

        @hook_engine.register("pre_execution")
        def my_interceptor(state, **kwargs):
            state["validated"] = True
            return state

        # Trigger from sync code (AI agents, CLI):
        state = hook_engine.trigger_sync("pre_execution", state, task="analysis")

        # Trigger from async code:
        state = await hook_engine.trigger("pre_execution", state, task="analysis")
    """

    HOOK_NAMES = (
        "pre_routing",
        "pre_execution",
        "post_execution",
        "post_generation",
        "pre_ledger_commit",
        "on_failure",
        "compress_memory",
        "emergency_synthesize",
    )

    def __init__(self, log_path: Optional[Path] = None):
        self._hooks: Dict[str, List[Callable]] = {name: [] for name in self.HOOK_NAMES}
        self._log_path = log_path
        self._execution_log: List[dict] = []

    def register(self, hook_name: str):
        """Decorator to register a function to a specific lifecycle hook.

        Args:
            hook_name: One of the HOOK_NAMES

        Example:
            @hook_engine.register("pre_execution")
            def my_hook(state, **kwargs):
                state["checked"] = True
                return state
        """
        def decorator(func: Callable):
            if hook_name in self._hooks:
                self._hooks[hook_name].append(func)
                logger.debug("Registered %s to hook '%s'", func.__name__, hook_name)
            else:
                logger.warning("Unknown hook name: %s", hook_name)
            return func
        return decorator

    def trigger_sync(
        self, hook_name: str, state: Dict[str, Any], *args, **kwargs
    ) -> Dict[str, Any]:
        """Synchronous trigger — the primary interface for AI agents and CLI.

        Executes all registered interceptors sequentially. Handles both sync
        and async interceptors transparently.

        Args:
            hook_name: The hook event to trigger
            state: Current pipeline state dict
            *args, **kwargs: Additional context passed to interceptors

        Returns:
            Modified state dict after all interceptors have run
        """
        if hook_name not in self._hooks:
            logger.warning("Hook '%s' not found in registry", hook_name)
            return state

        if not self._hooks[hook_name]:
            return state

        current_state = dict(state)

        for interceptor in self._hooks[hook_name]:
            try:
                if asyncio.iscoroutinefunction(interceptor):
                    current_state = _run_async_in_sync(
                        interceptor(current_state, *args, **kwargs)
                    )
                else:
                    current_state = interceptor(current_state, *args, **kwargs)

                if current_state is None:
                    logger.error(
                        "Interceptor %s returned None — state lost",
                        interceptor.__name__,
                    )
                    current_state = state

                self._log_execution(hook_name, interceptor.__name__, "success")

            except Exception as e:
                logger.error(
                    "Interceptor %s failed on hook %s: %s",
                    interceptor.__name__,
                    hook_name,
                    e,
                )
                self._log_execution(hook_name, interceptor.__name__, "error", str(e))
                current_state.setdefault("hook_errors", []).append({
                    "hook": hook_name,
                    "interceptor": interceptor.__name__,
                    "error": str(e),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })

        return current_state

    async def trigger(
        self, hook_name: str, state: Dict[str, Any], *args, **kwargs
    ) -> Dict[str, Any]:
        """Async trigger — for use in async contexts.

        Mirrors trigger_sync but uses await natively.
        """
        if hook_name not in self._hooks:
            return state

        if not self._hooks[hook_name]:
            return state

        current_state = dict(state)

        for interceptor in self._hooks[hook_name]:
            try:
                if asyncio.iscoroutinefunction(interceptor):
                    current_state = await interceptor(current_state, *args, **kwargs)
                else:
                    current_state = interceptor(current_state, *args, **kwargs)

                if current_state is None:
                    current_state = state

                self._log_execution(hook_name, interceptor.__name__, "success")

            except Exception as e:
                logger.error(
                    "Interceptor %s failed on hook %s: %s",
                    interceptor.__name__,
                    hook_name,
                    e,
                )
                self._log_execution(hook_name, interceptor.__name__, "error", str(e))
                current_state.setdefault("hook_errors", []).append({
                    "hook": hook_name,
                    "interceptor": interceptor.__name__,
                    "error": str(e),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })

        return current_state

    def _log_execution(
        self, hook_name: str, interceptor_name: str, status: str, error: str = ""
    ):
        """Log a hook execution event."""
        entry = {
            "hook": hook_name,
            "interceptor": interceptor_name,
            "status": status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if error:
            entry["error"] = error
        self._execution_log.append(entry)

        if self._log_path:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._log_path, "a") as f:
                f.write(json.dumps(entry) + "\n")

    def get_execution_log(self) -> List[dict]:
        return list(self._execution_log)

    def list_hooks(self) -> Dict[str, List[str]]:
        return {
            name: [fn.__name__ for fn in funcs]
            for name, funcs in self._hooks.items()
        }

    def clear_hook(self, hook_name: str):
        if hook_name in self._hooks:
            self._hooks[hook_name] = []

    def unregister(self, hook_name: str, func_name: str) -> bool:
        if hook_name not in self._hooks:
            return False
        original_len = len(self._hooks[hook_name])
        self._hooks[hook_name] = [
            fn for fn in self._hooks[hook_name] if fn.__name__ != func_name
        ]
        return len(self._hooks[hook_name]) < original_len


hook_engine = HookRegistry()

import re
from research_copilot.project_ops import _resolve_root

@hook_engine.register("post_generation")
def citation_interceptor(state: Dict[str, Any], **kwargs) -> Dict[str, Any]:
    """Intercepts generated text and logs citations to workspace/sources.md."""
    output_text = state.get("output_text", "")
    if not output_text:
        return state
        
    # Extract naive citations [Author, Year] or similar
    citations = re.findall(r'\[([^\]]+, \d{4})\]', output_text)
    if citations:
        try:
            resolved_root = _resolve_root()
            sources_path = resolved_root / "workspace" / "sources.md"
            sources_path.parent.mkdir(parents=True, exist_ok=True)
            
            new_entries = []
            for citation in citations:
                new_entries.append(f"- {citation} (Extracted at {datetime.now(timezone.utc).isoformat()})")
                
            if new_entries:
                with open(sources_path, "a") as f:
                    f.write("\n" + "\n".join(new_entries))
                    
        except Exception as e:
            logger.error(f"Citation interceptor failed: {e}")
            
    return state

