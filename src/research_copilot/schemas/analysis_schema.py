"""Schema definitions for analysis results."""

from pydantic import BaseModel, Field, field_validator
from typing import List, Optional


class StatisticalTest(BaseModel):
    """Results of a single statistical test."""

    test_name: str = Field(..., description="Name of statistical test (e.g., 't-test', 'ANOVA', 'OLS regression')")
    statistic: float = Field(..., description="Test statistic value")
    degrees_of_freedom: Optional[float] = Field(default=None, description="Degrees of freedom")
    p_value: float = Field(..., ge=0, le=1, description="Exact p-value (not thresholded)")
    effect_size: float = Field(..., description="Effect size estimate")
    effect_size_type: str = Field(..., description="Type of effect size (cohens_d, r, eta_squared, odds_ratio, etc.)")
    confidence_interval: List[float] = Field(
        ..., min_length=2, max_length=2, description="[lower_bound, upper_bound]"
    )
    sample_size: int = Field(..., gt=0, description="Sample size used in test")
    assumptions_checked: List[str] = Field(default=[], description="List of assumptions verified")
    runtime: Optional[str] = Field(default=None, description="Runtime used (python, r, bash, etc.)")
    tool_id: Optional[str] = Field(default=None, description="Tool registry ID")
    container: Optional[str] = Field(default=None, description="Container used for execution")

    @field_validator("confidence_interval")
    @classmethod
    def ci_lower_must_be_less_than_upper(cls, v: List[float]) -> List[float]:
        if v[0] >= v[1]:
            raise ValueError("CI lower bound must be less than upper bound")
        return v


class AnalysisResults(BaseModel):
    """Complete analysis results for a research question."""

    question_id: str = Field(..., description="Research question identifier (Q1, Q2, etc.)")
    tests: List[StatisticalTest] = Field(..., min_length=1)
    conclusion: str = Field(..., min_length=20, description="Narrative conclusion")
    limitations: List[str] = Field(default=[], description="Limitations of the analysis")
    data_file: str = Field(..., description="Path to analytical data used")
    script: str = Field(..., description="Path to analysis script that produced results")
    timestamp: str = Field(..., description="ISO 8601 timestamp of analysis")

    @field_validator("tests")
    @classmethod
    def at_least_one_test(cls, v: List[StatisticalTest]) -> List[StatisticalTest]:
        if len(v) < 1:
            raise ValueError("Analysis must include at least one statistical test")
        return v
