# Skill: Schema Enforcement

> Validates all inter-agent data payloads against Pydantic schemas before acceptance.

## Purpose
Ensure that malformed output from one agent cannot corrupt the next agent's input. Every agent output must validate against a Pydantic schema before being accepted.

---

## Protocol

### Step 1: Load Schema Registry
1. Read `.research/schemas/` directory for available schemas
2. Match current agent/task to appropriate schema
3. Load the Pydantic model for validation

### Step 2: Validate Agent Output
For each agent output:
1. Parse the output into the expected data structure
2. Run validation against the appropriate Pydantic model
3. If validation passes: accept output, proceed
4. If validation fails: reject output, trigger auto-healing

### Step 3: Handle Validation Failures
1. Log validation error to `docs/dead_ends/schema_validation_error.md`
2. Extract specific field(s) that failed validation
3. Provide specific error message to agent
4. Allow agent to retry with corrected output
5. Max 3 retry attempts before dead end

---

## Schema Definitions

### Research Question Schema
```python
from pydantic import BaseModel, Field, validator
from typing import List, Optional, Literal
from datetime import datetime

class ResearchQuestion(BaseModel):
    text: str = Field(..., min_length=10, description="The research question text")
    type: Literal["descriptive", "comparative", "associational", "causal", "predictive", "exploratory"]
    hypothesis: str = Field(..., min_length=10, description="The hypothesis to test")
    outcome: str = Field(..., description="Outcome variable name")
    predictor: str = Field(..., description="Predictor variable name")
    covariates: Optional[List[str]] = Field(default=[], description="Covariate variables")
    files: Optional[List[str]] = Field(default=[], description="Data files needed")
    prep: Optional[str] = Field(default=None, description="Data preparation needed")

    @validator("text")
    def question_must_end_with_question_mark(cls, v):
        if not v.strip().endswith("?"):
            raise ValueError("Research question must end with a question mark")
        return v
```

### Research Map Schema
```python
class ResearchMap(BaseModel):
    schema_version: str = Field(..., pattern=r"^\d+\.\d+\.\d+$")
    project: dict = Field(..., description="Project metadata")
    questions: List[ResearchQuestion] = Field(..., min_items=1)
    data: dict = Field(..., description="Data file information")
    domain: dict = Field(..., description="Domain configuration")
    feasibility: dict = Field(..., description="Feasibility assessment")
    follow_up: List[str] = Field(default=[], description="Follow-up questions")

    @validator("questions")
    def at_least_one_question(cls, v):
        assert len(v) >= 1, "Must have at least one research question"
        return v

    @validator("feasibility")
    def feasibility_must_have_verdict(cls, v):
        assert "verdict" in v, "Feasibility must include a verdict"
        assert v["verdict"] in ["go", "caution", "stop"], "Invalid feasibility verdict"
        return v
```

### Literature Corpus Schema
```python
class PaperEntry(BaseModel):
    doi: Optional[str] = Field(default=None, description="Digital Object Identifier")
    title: str = Field(..., min_length=5)
    authors: List[str] = Field(..., min_items=1)
    year: int = Field(..., ge=1900, le=2030)
    journal: Optional[str] = Field(default=None)
    abstract: Optional[str] = Field(default=None)
    citations: Optional[int] = Field(default=None, ge=0)
    relevance_score: Optional[float] = Field(default=None, ge=0, le=1)
    verification_status: Literal["verified", "unverified", "retracted"] = Field(default="unverified")

class LiteratureCorpus(BaseModel):
    schema_version: str = Field(..., pattern=r"^\d+\.\d+\.\d+$")
    papers: List[PaperEntry] = Field(..., min_items=1)
    search_queries: List[str] = Field(default=[], description="Search queries used")
    last_updated: str = Field(..., description="ISO 8601 timestamp")

    @validator("papers")
    def at_least_one_paper(cls, v):
        assert len(v) >= 1, "Corpus must contain at least one paper"
        return v
```

### Analysis Results Schema
```python
class StatisticalTest(BaseModel):
    test_name: str = Field(..., description="Name of statistical test")
    statistic: float = Field(..., description="Test statistic value")
    degrees_of_freedom: Optional[float] = Field(default=None)
    p_value: float = Field(..., ge=0, le=1, description="Exact p-value")
    effect_size: float = Field(..., description="Effect size estimate")
    effect_size_type: str = Field(..., description="Type of effect size (cohens_d, r, eta_squared, etc.)")
    confidence_interval: List[float] = Field(..., min_items=2, max_items=2, description="[lower, upper]")
    sample_size: int = Field(..., gt=0)
    assumptions_checked: List[str] = Field(default=[], description="Assumptions verified")

class AnalysisResults(BaseModel):
    question_id: str = Field(..., description="Research question identifier (Q1, Q2, etc.)")
    tests: List[StatisticalTest] = Field(..., min_items=1)
    conclusion: str = Field(..., min_length=20)
    limitations: List[str] = Field(default=[])
    data_file: str = Field(..., description="Path to analytical data used")
    script: str = Field(..., description="Path to analysis script")
    timestamp: str = Field(..., description="ISO 8601 timestamp")
```

### Audit Report Schema
```python
class AuditCheck(BaseModel):
    check_name: str = Field(..., description="Name of audit check")
    status: Literal["PASS", "FAIL", "CONDITIONAL"]
    details: str = Field(..., description="Detailed findings")
    remediation: Optional[str] = Field(default=None, description="Fix instructions if FAIL")

class AuditReport(BaseModel):
    audit_type: str = Field(..., description="Type of audit")
    timestamp: str = Field(..., description="ISO 8601 timestamp")
    checks: List[AuditCheck] = Field(..., min_items=1)
    overall_verdict: Literal["PASS", "FAIL", "CONDITIONAL"]
    failures: List[str] = Field(default=[], description="List of failed check names")
    auto_healing_attempts: int = Field(default=0, ge=0, le=3)
```

### State Ledger Schema
```python
class TokenBudget(BaseModel):
    used: int = Field(..., ge=0)
    remaining: int = Field(..., ge=0)
    limit: int = Field(..., gt=0)

class ResearchState(BaseModel):
    run_id: str = Field(..., description="UUID for this research run")
    project: str = Field(..., description="Project title")
    phase: str = Field(..., description="Current pipeline phase")
    step: int = Field(..., ge=0)
    checkpoints: dict = Field(default={}, description="Phase completion status")
    active_hypotheses: List[dict] = Field(default=[])
    dead_ends: List[str] = Field(default=[])
    loaded_data: List[str] = Field(default=[])
    token_budget: TokenBudget = Field(...)
    last_checkpoint: str = Field(..., description="ISO 8601 timestamp")
    errors: List[str] = Field(default=[])
    resumable_from: Optional[str] = Field(default=None)
```

---

## Validation Function

```python
# .research/schemas/validator.py
from pydantic import ValidationError
from typing import Any, Type
import json

def validate_payload(data: Any, schema_type: Type[BaseModel]) -> dict:
    """Validate data against a Pydantic schema.
    
    Args:
        data: The data to validate (dict or JSON string)
        schema_type: The Pydantic model class to validate against
    
    Returns:
        dict: Validated data as dict
    
    Raises:
        ValidationError: If data doesn't match schema
    """
    if isinstance(data, str):
        data = json.loads(data)
    
    try:
        validated = schema_type(**data)
        return validated.model_dump()
    except ValidationError as e:
        raise ValidationError(
            f"Schema validation failed for {schema_type.__name__}:\n{e}"
        )
```

---

## Integration
- Called by: Every agent before writing output files
- Interceptors: `pre_ledger_commit` hook runs schema validation
- Blocks pipeline if: Validation fails after 3 retry attempts
- Location: `.research/schemas/`
