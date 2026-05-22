"""Schema definitions for research questions and research map."""

from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Literal, Dict, Any


class ResearchQuestion(BaseModel):
    """A single research question with all required metadata."""

    text: str = Field(..., min_length=10, description="The research question text")
    type: Literal["descriptive", "comparative", "associational", "causal", "predictive", "exploratory"]
    hypothesis: str = Field(..., min_length=10, description="The hypothesis to test")
    outcome: str = Field(..., description="Outcome variable name")
    predictor: str = Field(..., description="Predictor variable name")
    covariates: Optional[List[str]] = Field(default=[], description="Covariate variables")
    files: Optional[List[str]] = Field(default=[], description="Data files needed")
    prep: Optional[str] = Field(default=None, description="Data preparation needed")
    prior: Optional[str] = Field(default=None, description="Prior research context")

    @field_validator("text")
    @classmethod
    def question_must_be_substantive(cls, v: str) -> str:
        if len(v.strip()) < 10:
            raise ValueError("Research question must be at least 10 characters")
        return v.strip()


class DataFile(BaseModel):
    """A single data file entry in the research map."""

    path: str = Field(..., description="Relative path to the data file")
    format: str = Field(..., description="Detected file format")
    size_kb: Optional[float] = Field(default=None, description="File size in KB")
    format_class: Optional[str] = Field(default=None, description="High-level format class")
    pandera_applicable: bool = Field(default=False, description="Whether Pandera checks apply")
    domain_hint: Optional[str] = Field(default=None, description="Domain hint from format routing")


class DataSection(BaseModel):
    """Data section of the research map."""

    files: List[DataFile] = Field(default=[], description="Detected data files")
    schema_cache: Dict[str, Any] = Field(default={}, description="Schema cache for tabular files")
    format_manifest: Optional[str] = Field(default=None, description="Path to format manifest JSON")
    format_summary: Dict[str, Any] = Field(default={}, description="Summary counts for format scan")


class ResearchMap(BaseModel):
    """Complete research map for a project."""

    schema_version: str = Field(..., pattern=r"^\d+\.\d+\.\d+$")
    project: dict = Field(..., description="Project metadata (title, researcher, etc.)")
    questions: List[ResearchQuestion] = Field(..., min_length=1)
    data: DataSection = Field(..., description="Data file information and schema cache")
    domain: dict = Field(..., description="Domain configuration")
    feasibility: dict = Field(..., description="Feasibility assessment")
    follow_up: List[str] = Field(default=[], description="Follow-up questions for user")
    required_containers: List[str] = Field(default=[], description="Containers required by the project")
    required_tools: List[str] = Field(default=[], description="Tool IDs required by the project")

    @field_validator("questions")
    @classmethod
    def at_least_one_question(cls, v: List[ResearchQuestion]) -> List[ResearchQuestion]:
        if len(v) < 1:
            raise ValueError("Must have at least one research question")
        return v

    @field_validator("feasibility")
    @classmethod
    def feasibility_must_have_verdict(cls, v: dict) -> dict:
        if "verdict" not in v:
            raise ValueError("Feasibility must include a verdict")
        if v["verdict"] not in ("go", "caution", "stop"):
            raise ValueError("Invalid feasibility verdict. Must be: go, caution, or stop")
        return v
