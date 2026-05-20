# Skill: Validate Intake

> Runs before `research_init`. Ensures intake form is complete, coherent, and answerable.

## Purpose
Validate the intake form before any research begins. Catch unanswerable questions, missing variables, and incoherent specifications early.

---

## Protocol

### Step 1: Load Intake Form
1. Read `inputs/intake.md`
2. Check for alternative formats: `inputs/intake.json`, `inputs/intake.yaml`
3. If none found, report: "No intake form found. Create inputs/intake.md"

### Step 2: Check Required Fields
Verify all required fields are present AND filled (not placeholder text):

| Field | Validation |
|-------|-----------|
| Project title | Non-empty, not "[Your answer]" |
| Researcher name | Non-empty |
| Institution | Non-empty |
| Domain | Must match a domain in `.research/domains/` or be "custom" |
| Research questions | At least one question with text, type, hypothesis |
| Data files | At least one data file described |
| Target output | Specified (journal, report, presentation) |

### Step 3: Validate Research Questions
For each research question:

1. **Question is answerable** — Not circular, not untestable, not purely philosophical
2. **Type is valid** — Must be one of: descriptive, comparative, associational, causal, predictive, exploratory
3. **Variables are named** — Outcome and predictor variables specified
4. **Hypothesis direction stated** — If not, generate one and ask for confirmation
5. **Variables exist in data** — Cross-reference against `schema_cache.json`

### Step 4: Validate Data Specifications
1. Check that named variables exist in data files (using schema cache)
2. Verify data format is supported (CSV, TSV, Parquet, Excel, SPSS, Stata, SAS)
3. Check for minimum sample size feasibility based on question type

### Step 5: Validate Domain
1. Check domain against `.research/domains/` directory
2. If domain matches a config file, load domain-specific requirements
3. If domain is "custom", note that default standards will apply

### Step 6: Generate Validation Report
Output: `reports/baseline/intake_validation.json`

```json
{
  "schema_version": "1.0.0",
  "timestamp": "ISO 8601",
  "overall_status": "PASS|FAIL|CONDITIONAL",
  "field_validation": {
    "project_title": {"status": "PASS", "value": "..."},
    "researcher": {"status": "PASS", "value": "..."},
    "domain": {"status": "PASS", "value": "...", "matched_config": "psychology.yaml"}
  },
  "question_validation": [
    {
      "question_id": "Q1",
      "status": "PASS",
      "type_valid": true,
      "variables_found_in_data": true,
      "hypothesis_direction": "positive",
      "issues": []
    }
  ],
  "data_validation": {
    "files_found": 2,
    "formats_supported": true,
    "schema_matched": true,
    "issues": []
  },
  "generated_hypotheses": [
    {
      "question_id": "Q2",
      "generated_hypothesis": "...",
      "requires_confirmation": true
    }
  ],
  "issues": [],
  "recommendations": []
}
```

### Step 7: Gate Decision
- **PASS**: All validations pass, proceed to `research_init`
- **CONDITIONAL**: Minor issues (e.g., hypothesis direction missing but generated), proceed with notes
- **FAIL**: Critical issues (no data files, unanswerable questions), block and report to user

---

## Validation Rules

### Unanswerable Question Detection
Flag questions that:
- Are purely normative ("Should we...?")
- Require data not available and not collectable
- Are tautological or circular
- Are too broad to operationalize

### Variable Existence Check
For each named variable:
1. Look up in `schema_cache.json`
2. If not found, flag as MISSING
3. Suggest closest matching variable names from schema

### Domain Matching
1. Normalize domain name (lowercase, strip spaces)
2. Match against available `.research/domains/*.yaml` files
3. If no match, use `custom_template.yaml` defaults

---

## Integration
- Called by: `research_init` agent before any processing
- Outputs to: `reports/baseline/intake_validation.json`
- Blocks pipeline if: FAIL status
