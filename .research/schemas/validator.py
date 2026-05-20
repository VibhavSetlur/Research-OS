"""Validate data payloads against Pydantic schemas."""

import json
from pathlib import Path
from typing import Any, Type, Union
from pydantic import BaseModel, ValidationError


def validate_payload(data: Union[dict, str, Path], schema_type: Type[BaseModel]) -> dict:
    """Validate data against a Pydantic schema.

    Args:
        data: The data to validate (dict, JSON string, or path to JSON file)
        schema_type: The Pydantic model class to validate against

    Returns:
        dict: Validated data as dict

    Raises:
        ValidationError: If data doesn't match schema
        FileNotFoundError: If data is a path and file doesn't exist
        json.JSONDecodeError: If data is a string/path and not valid JSON
    """
    if isinstance(data, Path):
        if not data.exists():
            raise FileNotFoundError(f"Schema data file not found: {data}")
        with open(data) as f:
            data = json.load(f)
    elif isinstance(data, str):
        # Try as file path first, then as JSON string
        path = Path(data)
        if path.exists():
            with open(path) as f:
                data = json.load(f)
        else:
            data = json.loads(data)

    validated = schema_type(**data)
    return validated.model_dump()


def validate_file(file_path: Union[str, Path], schema_type: Type[BaseModel]) -> dict:
    """Validate a JSON file against a Pydantic schema.

    Args:
        file_path: Path to JSON file
        schema_type: The Pydantic model class to validate against

    Returns:
        dict: Validated data as dict
    """
    return validate_payload(Path(file_path), schema_type)


def get_schema_for_task(task_name: str) -> Type[BaseModel]:
    """Get the appropriate schema class for a given task/agent.

    Args:
        task_name: Name of the task or agent

    Returns:
        Pydantic model class for the task
    """
    from .research_map_schema import ResearchMap, ResearchQuestion
    from .literature_schema import LiteratureCorpus, PaperEntry
    from .analysis_schema import AnalysisResults, StatisticalTest
    from .audit_schema import AuditReport, AuditCheck
    from .state_schema import ResearchState, TokenBudget

    schema_map = {
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
        "research_init": ResearchMap,
        "literature_deep": LiteratureCorpus,
        "execute_analysis": AnalysisResults,
        "audit_validate": AuditReport,
    }

    if task_name not in schema_map:
        raise ValueError(f"No schema registered for task: {task_name}")

    return schema_map[task_name]
