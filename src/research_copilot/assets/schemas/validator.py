"""Pydantic guardrail validator with auto-retry logic.

Wraps every agent LLM call with:
  1. Strict Pydantic schema validation via model_validate_json()
  2. Automatic prompt augmentation on ValidationError (up to MAX_RETRIES)
  3. Full error chain logged to the state ledger

Usage::

    from research_copilot.assets.schemas.validator import validate_with_retry
    from research_copilot.assets.schemas.analysis_schema import AnalysisResults

    validated = validate_with_retry(
        raw_json=llm_response,
        schema=AnalysisResults,
        call_llm=my_llm_fn,     # callable(prompt: str) -> str
        base_prompt=my_prompt,
    )
"""

import json
import logging
from pathlib import Path
from typing import Any, Callable, Optional, Type, Union

from pydantic import BaseModel, ValidationError

logger = logging.getLogger("research.validator")

MAX_RETRIES = 3


# ---------------------------------------------------------------------------
# Core validate-with-retry
# ---------------------------------------------------------------------------

def validate_with_retry(
    raw_json: str,
    schema: Type[BaseModel],
    call_llm: Optional[Callable[[str], str]] = None,
    base_prompt: str = "",
    max_retries: int = MAX_RETRIES,
    node_id: Optional[str] = None,
) -> BaseModel:
    """Validate *raw_json* against *schema*, retrying on ValidationError.

    On each validation failure the exact Python error string is appended to
    the prompt and sent back to the model (up to *max_retries* times) before
    raising the final ValidationError.

    Args:
        raw_json:    Raw JSON string returned by the LLM.
        schema:      Pydantic model class to validate against.
        call_llm:    Callable that accepts a string prompt and returns a new
                     JSON string from the LLM.  Required for retries; if None
                     the first failure raises immediately.
        base_prompt: The original prompt sent to the LLM (used to build the
                     retry prompt with the error appended).
        max_retries: Maximum number of retry attempts (default 3).
        node_id:     Optional DAG node ID used for log context.

    Returns:
        Validated Pydantic model instance.

    Raises:
        ValidationError: After *max_retries* failed attempts.
        json.JSONDecodeError: If the final attempt cannot be parsed as JSON.
    """
    prefix = f"[{node_id}] " if node_id else ""
    attempt = 0
    current_json = raw_json
    last_error: Optional[Exception] = None

    while attempt <= max_retries:
        try:
            instance = schema.model_validate_json(current_json)
            if attempt > 0:
                logger.info("%sValidation succeeded on attempt %d.", prefix, attempt + 1)
            return instance

        except (ValidationError, json.JSONDecodeError, ValueError) as exc:
            last_error = exc
            attempt += 1

            error_str = str(exc)
            logger.warning(
                "%sValidation attempt %d/%d failed:\n%s",
                prefix, attempt, max_retries + 1, error_str,
            )

            if call_llm is None or attempt > max_retries:
                break

            # Build retry prompt: append the error and ask for a corrected JSON.
            retry_prompt = (
                f"{base_prompt}\n\n"
                f"---\n"
                f"Your previous response failed schema validation with this error:\n"
                f"```\n{error_str}\n```\n\n"
                f"Your previous response was:\n"
                f"```json\n{current_json}\n```\n\n"
                f"Return ONLY a corrected JSON object that satisfies the schema. "
                f"No explanations, no markdown fences — pure JSON only."
            )
            try:
                current_json = call_llm(retry_prompt)
            except Exception as llm_exc:
                logger.error("%sLLM call failed during retry: %s", prefix, llm_exc)
                break

    raise last_error  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Original API (backwards compatible)
# ---------------------------------------------------------------------------

def validate_payload(
    data: Union[dict, str, Path],
    schema_type: Type[BaseModel],
) -> dict:
    """Validate data against a Pydantic schema.

    Args:
        data:        The data to validate (dict, JSON string, or path to JSON file).
        schema_type: The Pydantic model class to validate against.

    Returns:
        Validated data as a plain dict.

    Raises:
        ValidationError: If data doesn't match schema.
        FileNotFoundError: If data is a path and file doesn't exist.
        json.JSONDecodeError: If data is a string/path and not valid JSON.
    """
    if isinstance(data, Path):
        if not data.exists():
            raise FileNotFoundError(f"Schema data file not found: {data}")
        with open(data) as f:
            data = json.load(f)
    elif isinstance(data, str):
        path = Path(data)
        if path.exists():
            with open(path) as f:
                data = json.load(f)
        else:
            data = json.loads(data)

    validated = schema_type(**data)
    return validated.model_dump()


def validate_file(file_path: Union[str, Path], schema_type: Type[BaseModel]) -> dict:
    """Validate a JSON file against a Pydantic schema."""
    return validate_payload(Path(file_path), schema_type)


def get_schema_for_task(task_name: str) -> Type[BaseModel]:
    """Return the appropriate schema class for a given task/agent name.

    Raises:
        ValueError: If no schema is registered for the given task name.
    """
    from .research_map_schema import ResearchMap, ResearchQuestion
    from .literature_schema import LiteratureCorpus, PaperEntry
    from .analysis_schema import AnalysisResults, StatisticalTest
    from .audit_schema import AuditReport, AuditCheck
    from .state_schema import ResearchState, TokenBudget

    schema_map: dict[str, Type[BaseModel]] = {
        "research_map": ResearchMap,
        "research_question": ResearchQuestion,
        "literature_corpus": LiteratureCorpus,
        "paper_entry": PaperEntry,
        "analysis_results": AnalysisResults,
        "statistical_test": StatisticalTest,
        "audit_report": AuditReport,
        "audit_check": AuditCheck,
        "research_state": ResearchState,
        "token_budget": TokenBudget,
        # Legacy aliases
        "research_init": ResearchMap,
        "literature_deep": LiteratureCorpus,
        "execute_analysis": AnalysisResults,
        "audit_validate": AuditReport,
    }

    if task_name not in schema_map:
        raise ValueError(f"No schema registered for task: {task_name}")

    return schema_map[task_name]
