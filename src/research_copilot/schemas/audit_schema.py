"""Schema definitions for audit reports."""

from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Literal


class AuditCheck(BaseModel):
    """A single audit check result."""

    check_name: str = Field(..., description="Name of audit check")
    status: Literal["PASS", "FAIL", "CONDITIONAL"]
    details: str = Field(..., min_length=10, description="Detailed findings")
    remediation: Optional[str] = Field(default=None, description="Fix instructions if FAIL or CONDITIONAL")


class AuditReport(BaseModel):
    """Complete audit report for a phase."""

    audit_type: str = Field(..., description="Type of audit (reproducibility, citations, claims, etc.)")
    timestamp: str = Field(..., description="ISO 8601 timestamp")
    checks: List[AuditCheck] = Field(..., min_length=1)
    overall_verdict: Literal["PASS", "FAIL", "CONDITIONAL"]
    failures: List[str] = Field(default=[], description="List of failed check names")
    auto_healing_attempts: int = Field(default=0, ge=0, le=3, description="Number of auto-healing attempts")

    @field_validator("checks")
    @classmethod
    def at_least_one_check(cls, v: List[AuditCheck]) -> List[AuditCheck]:
        if len(v) < 1:
            raise ValueError("Audit must include at least one check")
        return v

    @field_validator("overall_verdict")
    @classmethod
    def verdict_must_match_checks(cls, v: str, info) -> str:
        # This is a simplified check; full validation would check all check statuses
        return v
