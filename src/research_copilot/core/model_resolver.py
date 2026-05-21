#!/usr/bin/env python3
"""Multi-Agent LLM Model Resolver with graceful degradation.

Reads models.yaml and resolves which model to use for each task based on
available API keys. If a required key is missing, falls back to the best
available model with a visible warning.

Usage:
    from model_resolver import resolve_model, get_available_models
    
    # Get the model config for a specific task
    model = resolve_model("literature_deep")
    
    # Check what models are available
    available = get_available_models()
"""

import os
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Any
from research_copilot.utils.common import load_yaml

_MODELS_YAML = Path(__file__).resolve().parents[1] / "models.yaml"
_RESOLVED_CACHE = {}
_WARNINGS_SHOWN = set()


def _load_models_config() -> dict:
    """Load the models.yaml configuration."""
    try:
        from research_copilot.utils.asset_manager import AssetManager
        import yaml
        return yaml.safe_load(AssetManager().read_text("models.yaml")) or {"models": {}, "fallback": {}}
    except Exception:
        return {"models": {}, "fallback": {}}


def _check_api_key(env_var: str) -> bool:
    """Check if an API key environment variable is set."""
    return bool(os.environ.get(env_var))


def resolve_model(task_name: str, config: Optional[dict] = None) -> dict:
    """Resolve which model to use for a given task.
    
    Args:
        task_name: The task/agent name (e.g., 'literature_deep', 'orchestrator')
        config: Optional pre-loaded models config
        
    Returns:
        Dict with resolved model configuration including actual provider/model to use.
    """
    if config is None:
        config = _load_models_config()
    
    cache_key = task_name
    if cache_key in _RESOLVED_CACHE:
        return _RESOLVED_CACHE[cache_key]
    
    models = config.get("models", {})
    fallback = config.get("fallback", {})
    
    task_config = models.get(task_name)
    if not task_config:
        # Task not in models.yaml, use fallback
        return _resolve_with_fallback(fallback, f"Task '{task_name}' not in models.yaml")
    
    api_key_env = task_config.get("api_key_env", "")
    if _check_api_key(api_key_env):
        # Primary model is available
        resolved = {**task_config, "_fallback_used": False, "_original_task": task_name}
        _RESOLVED_CACHE[cache_key] = resolved
        return resolved
    
    # Primary model unavailable — find best fallback
    warning_msg = (
        f"Model fallback: {task_name} requires {api_key_env} (not set). "
        f"Falling back from {task_config.get('provider')}/{task_config.get('model')}."
    )
    
    resolved = _resolve_with_fallback(fallback, warning_msg, task_config)
    _log_model_fallback(task_name, task_config, resolved, warning_msg)
    _RESOLVED_CACHE[cache_key] = resolved
    return resolved


def _resolve_with_fallback(fallback: dict, warning_msg: str, original_config: Optional[dict] = None) -> dict:
    """Resolve to the best available fallback model."""
    if warning_msg not in _WARNINGS_SHOWN:
        warnings.warn(warning_msg, stacklevel=3)
        _WARNINGS_SHOWN.add(warning_msg)
    
    # Check if fallback itself is available
    fallback_key = fallback.get("api_key_env", "")
    if _check_api_key(fallback_key):
        return {
            **fallback,
            "_fallback_used": True,
            "_fallback_from": original_config.get("model", "unknown") if original_config else "unknown",
            "_warning": warning_msg,
        }
    
    # Try to find ANY available model
    available = _find_any_available_model()
    if available:
        return {
            **available,
            "_fallback_used": True,
            "_fallback_from": original_config.get("model", "unknown") if original_config else "unknown",
            "_warning": f"Multiple fallbacks: {warning_msg}",
        }
    
    # No models available
    return {
        **fallback,
        "_fallback_used": True,
        "_fallback_from": original_config.get("model", "unknown") if original_config else "unknown",
        "_warning": f"CRITICAL: No API keys available. {warning_msg}",
        "_no_keys_available": True,
    }


def _find_any_available_model() -> Optional[dict]:
    """Find any model whose API key is available, preferring high-context models."""
    config = _load_models_config()
    models = config.get("models", {})
    
    # Priority order: high context first
    priority = sorted(
        models.values(),
        key=lambda m: m.get("context_window", 0),
        reverse=True,
    )
    
    for model in priority:
        if _check_api_key(model.get("api_key_env", "")):
            return model
    
    # Check fallback
    fallback = config.get("fallback", {})
    if _check_api_key(fallback.get("api_key_env", "")):
        return fallback
    
    return None


def _find_project_root() -> Path:
    from research_copilot.utils.common import find_project_root
    return find_project_root()


def _active_experiment(root: Path) -> str:
    package_state = root / "03_synthesis" / "state_ledger.json"
    legacy_state = root / ".research" / "cache" / "state.json"
    for path in (package_state, legacy_state):
        try:
            import json

            with open(path) as f:
                state = json.load(f)
            branch = state.get("current_branch") or state.get("active_branch")
            if branch and branch != "main":
                return branch
        except Exception:
            pass
    return "exp_001_baseline"


def _log_model_fallback(task_name: str, original: dict, resolved: dict, warning_msg: str) -> None:
    """Record model fallback in the active experiment decisions ledger."""
    root = _find_project_root()
    experiment = _active_experiment(root)
    decisions = root / "02_experiments" / experiment / "decisions.yaml"
    if not decisions.parent.exists():
        return
    decisions.parent.mkdir(parents=True, exist_ok=True)

    original_model = f"{original.get('provider', 'unknown')}/{original.get('model', 'unknown')}"
    resolved_model = f"{resolved.get('provider', 'unknown')}/{resolved.get('model', 'unknown')}"
    now = datetime.now(timezone.utc)
    entry_id = f"model_fallback_{now.strftime('%Y%m%d_%H%M%S')}"
    entry = (
        f"\n  {entry_id}:\n"
        f"    date: {now.date().isoformat()}\n"
        f"    context: Model resolver fallback for task '{task_name}'.\n"
        f"    selected: {resolved_model}\n"
        f"    rationale: {warning_msg}\n"
        f"    original_model: {original_model}\n"
        f"    fallback_used: {str(resolved.get('_fallback_used', False)).lower()}\n"
        "    linked_literature: []\n"
    )

    if decisions.exists():
        text = decisions.read_text()
        if "decisions:" not in text:
            text += "\ndecisions:\n"
        decisions.write_text(text.rstrip() + entry)
    else:
        decisions.write_text(
            "schema_version: '1.0'\n"
            f"experiment_id: {experiment}\n"
            f"created: {now.isoformat()}\n"
            "decisions:\n"
            + entry
        )


def get_available_models(config: Optional[dict] = None) -> dict:
    """Get a summary of which models are available based on API keys.
    
    Returns:
        Dict with available/unavailable model lists and warnings.
    """
    if config is None:
        config = _load_models_config()
    
    models = config.get("models", {})
    fallback = config.get("fallback", {})
    
    available = []
    unavailable = []
    
    for name, model_config in models.items():
        key_env = model_config.get("api_key_env", "")
        if _check_api_key(key_env):
            available.append({
                "name": name,
                "provider": model_config.get("provider"),
                "model": model_config.get("model"),
                "context_window": model_config.get("context_window"),
            })
        else:
            unavailable.append({
                "name": name,
                "provider": model_config.get("provider"),
                "model": model_config.get("model"),
                "missing_key": key_env,
            })
    
    fallback_available = _check_api_key(fallback.get("api_key_env", ""))
    
    return {
        "available": available,
        "unavailable": unavailable,
        "fallback_available": fallback_available,
        "fallback_model": fallback.get("model"),
        "total_available": len(available),
        "total_unavailable": len(unavailable),
    }


def resolve_routing_matrix(config: Optional[dict] = None) -> dict:
    """Resolve every configured task to an available model in memory.

    Callers can use the returned matrix instead of raw models.yaml routes. Missing
    provider keys are degraded to the highest-context available model and cached
    for the current process.
    """
    if config is None:
        config = _load_models_config()
    matrix = {}
    for task_name in config.get("models", {}):
        matrix[task_name] = resolve_model(task_name, config=config)
    return matrix


def attach_schema(config: dict, schema: Any) -> dict:
    """Attach a Pydantic schema to the model configuration for native Structured Outputs.
    
    Args:
        config: The resolved model configuration
        schema: A Pydantic V2 schema model class
        
    Returns:
        Updated config with schema bindings
    """
    new_config = dict(config)
    try:
        # Check if it's a Pydantic V2 model
        if hasattr(schema, "model_json_schema"):
            json_schema = schema.model_json_schema()
            new_config["structured_output_schema"] = json_schema
            new_config["structured_output_name"] = schema.__name__
            new_config["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": schema.__name__,
                    "schema": json_schema,
                    "strict": True
                }
            }
        else:
            # Fallback for dict or older versions
            new_config["response_format"] = {"type": "json_object"}
            if callable(getattr(schema, "schema", None)):
                new_config["structured_output_schema"] = schema.schema()
            else:
                new_config["structured_output_schema"] = schema
    except Exception as e:
        new_config["response_format"] = {"type": "json_object"}
        new_config["_schema_error"] = str(e)
        
    return new_config


def print_availability_report(config: Optional[dict] = None) -> str:
    """Generate a human-readable availability report."""
    report = get_available_models(config)
    
    lines = [
        "=" * 60,
        "LLM MODEL AVAILABILITY",
        "=" * 60,
        "",
        f"Available: {report['total_available']}",
        f"Unavailable: {report['total_unavailable']}",
        f"Fallback ({report['fallback_model']}): {'OK' if report['fallback_available'] else 'MISSING KEY'}",
        "",
    ]
    
    if report["available"]:
        lines.append("Available models:")
        for m in report["available"]:
            lines.append(f"  ✓ {m['name']}: {m['provider']}/{m['model']} (context: {m['context_window']:,})")
        lines.append("")
    
    if report["unavailable"]:
        lines.append("Unavailable (will use fallback):")
        for m in report["unavailable"]:
            lines.append(f"  ✗ {m['name']}: {m['provider']}/{m['model']} (missing: {m['missing_key']})")
        lines.append("")
    
    if not report["available"] and not report["fallback_available"]:
        lines.append("WARNING: No API keys detected. Set at least one of:")
        lines.append("  - OPENAI_API_KEY")
        lines.append("  - ANTHROPIC_API_KEY")
        lines.append("  - GOOGLE_API_KEY")
        lines.append("")
    
    return "\n".join(lines)


if __name__ == "__main__":
    print(print_availability_report())


# ---------------------------------------------------------------------------
# Item 11 — Auto-Fallback Model Routing (Cascade)
# ---------------------------------------------------------------------------
# Try the cheapest model first (local ollama).  If Pydantic validation fails
# 3 times, automatically escalate to a cloud API model for that node, logging
# the fallback in the state ledger so every methodological deviation is
# traceable.
# ---------------------------------------------------------------------------

_OLLAMA_DEFAULT = "ollama/llama3"

# Ordered API fallback cascade — first available key wins.
_API_FALLBACK_CASCADE = [
    {"provider": "google", "model": "gemini-2.5-flash",  "api_key_env": "GOOGLE_API_KEY"},
    {"provider": "openai", "model": "gpt-4o-mini",       "api_key_env": "OPENAI_API_KEY"},
    {"provider": "anthropic", "model": "claude-haiku-3", "api_key_env": "ANTHROPIC_API_KEY"},
]


def _first_available_api_model() -> Optional[dict]:
    """Return the first API model whose key is present in the environment."""
    for m in _API_FALLBACK_CASCADE:
        if _check_api_key(m["api_key_env"]):
            return m
    return None


def cascade_resolve(
    task_name: str,
    call_model: "Callable[[str, str], str]",  # (model_id, prompt) -> raw_json
    prompt: str,
    schema: "Optional[Any]" = None,
    max_local_retries: int = 3,
    node_id: Optional[str] = None,
    config: Optional[dict] = None,
) -> dict:
    """Resolve a model call with automatic cheap-to-expensive cascade.

    Execution order:
      1. Try ``ollama/<local_model>`` up to *max_local_retries* times.
      2. If every local attempt fails Pydantic validation, escalate to the
         first available API model (gemini → gpt-4o-mini → claude-haiku).
      3. Log every fallback in the active experiment's ``decisions.yaml``.

    Args:
        task_name:         Task / agent name used to look up the task model.
        call_model:        Callable ``(model_id, prompt) -> raw_json_string``.
                           ``model_id`` is a string like ``"ollama/llama3"``
                           or ``"google/gemini-2.5-flash"``.
        prompt:            The prompt to send.
        schema:            Optional Pydantic model class for output validation.
        max_local_retries: Times to retry the local model before escalating.
        node_id:           DAG node ID for logging.
        config:            Optional pre-loaded models config.

    Returns:
        Dict with keys: raw_output, model_used, fallback_used, validated (if
        schema provided).

    Raises:
        RuntimeError: If all models in the cascade are exhausted.
    """
    from research_copilot.assets.schemas.validator import validate_with_retry

    # Determine the local model to try first.
    if config is None:
        config = _load_models_config()

    task_cfg = (config.get("models") or {}).get(task_name) or {}
    local_provider = task_cfg.get("provider", "")
    local_model    = task_cfg.get("model", "")

    if local_provider and local_provider.lower() in ("ollama", "local"):
        local_model_id = f"ollama/{local_model}"
    elif _check_api_key(task_cfg.get("api_key_env", "")):
        local_model_id = f"{local_provider}/{local_model}"
    else:
        local_model_id = _OLLAMA_DEFAULT

    prefix = f"[{node_id or task_name}] "
    last_error: Optional[Exception] = None
    validated_output: Optional[dict] = None

    # ── Phase 1: local / cheap model ─────────────────────────────────────────
    for attempt in range(max_local_retries):
        try:
            raw = call_model(local_model_id, prompt)

            if schema is not None:
                instance = validate_with_retry(
                    raw_json=raw,
                    schema=schema,
                    call_llm=lambda p: call_model(local_model_id, p),
                    base_prompt=prompt,
                    max_retries=0,  # single attempt here; outer loop handles retries
                    node_id=node_id,
                )
                validated_output = instance.model_dump()

            import logging as _logging
            _logging.getLogger("research.model_resolver").info(
                "%sLocal model '%s' succeeded on attempt %d.",
                prefix, local_model_id, attempt + 1,
            )
            return {
                "raw_output": raw,
                "model_used": local_model_id,
                "fallback_used": False,
                "validated": validated_output,
            }

        except Exception as exc:
            last_error = exc
            import logging as _logging
            _logging.getLogger("research.model_resolver").warning(
                "%sLocal attempt %d/%d failed: %s",
                prefix, attempt + 1, max_local_retries, exc,
            )

    # ── Phase 2: API fallback cascade ─────────────────────────────────────────
    api_model = _first_available_api_model()
    if api_model is None:
        raise RuntimeError(
            f"{prefix}All {max_local_retries} local attempts failed and no API key "
            f"is available for fallback. Last error: {last_error}"
        )

    api_model_id = f"{api_model['provider']}/{api_model['model']}"
    fallback_msg = (
        f"Auto-fallback: {local_model_id} failed {max_local_retries}× for "
        f"node '{node_id or task_name}' → escalating to {api_model_id}."
    )

    import warnings as _warnings
    _warnings.warn(fallback_msg)
    import logging as _logging
    _logging.getLogger("research.model_resolver").warning("%s%s", prefix, fallback_msg)

    # Log the fallback to the decisions ledger.
    _log_model_fallback(
        task_name,
        {"provider": local_model_id.split("/")[0], "model": local_model_id.split("/")[-1]},
        api_model,
        fallback_msg,
    )

    try:
        raw = call_model(api_model_id, prompt)
        if schema is not None:
            instance = validate_with_retry(
                raw_json=raw,
                schema=schema,
                call_llm=lambda p: call_model(api_model_id, p),
                base_prompt=prompt,
                node_id=node_id,
            )
            validated_output = instance.model_dump()

        return {
            "raw_output": raw,
            "model_used": api_model_id,
            "fallback_used": True,
            "fallback_from": local_model_id,
            "validated": validated_output,
        }

    except Exception as exc:
        raise RuntimeError(
            f"{prefix}Both local ({local_model_id}) and API ({api_model_id}) "
            f"models failed. Last error: {exc}"
        ) from exc

