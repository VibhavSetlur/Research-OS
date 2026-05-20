"""Schema definitions for the global research state ledger."""

from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Dict


class TokenBudget(BaseModel):
    """Token budget tracking for context window management."""

    used: int = Field(..., ge=0, description="Tokens used so far")
    remaining: int = Field(..., ge=0, description="Tokens remaining")
    limit: int = Field(..., gt=0, description="Total token limit")

    @field_validator("remaining")
    @classmethod
    def remaining_must_match(cls, v: int, info) -> int:
        if "used" in info.data and "limit" in info.data:
            expected = info.data["limit"] - info.data["used"]
            if v != expected:
                raise ValueError(f"Remaining ({v}) must equal limit - used ({expected})")
        return v


class ResearchState(BaseModel):
    """Global research state ledger — single source of truth."""

    run_id: str = Field(..., description="UUID for this research run")
    project: str = Field(..., description="Project title")
    phase: str = Field(..., description="Current pipeline phase")
    step: int = Field(..., ge=0, description="Current step within phase")
    checkpoints: Dict[str, str] = Field(
        default={}, description="Phase completion status: {phase: status}"
    )
    active_hypotheses: List[dict] = Field(default=[], description="Active hypotheses being tested")
    dead_ends: List[str] = Field(default=[], description="Approaches tried and abandoned")
    loaded_data: List[str] = Field(default=[], description="Paths to loaded data files")
    token_budget: TokenBudget = Field(...)
    last_checkpoint: str = Field(..., description="ISO 8601 timestamp of last checkpoint")
    errors: List[str] = Field(default=[], description="List of error messages")
    resumable_from: Optional[str] = Field(default=None, description="Phase:step to resume from")
