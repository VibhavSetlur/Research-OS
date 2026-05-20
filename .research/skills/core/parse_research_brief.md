# Skill: Parse Research Brief

> Converts a free-form paragraph description of research into a structured intake form.

## Purpose
When a user pastes a paragraph description of their research (voice transcript, email, or free-form text), this skill structures it into a valid intake format that can be used by `research_init`.

---

## Protocol

### Step 1: Read Input Text
1. Accept free-form text from user (pasted paragraph, voice transcript, email body)
2. Save raw input to `inputs/raw_brief.txt`

### Step 2: Extract Project Metadata
Parse the text for:
- **Project title**: Look for phrases like "study on", "research about", "investigating"
- **Researcher name**: Look for "by", "I am", named entities
- **Institution**: Look for university, organization names
- **Domain/field**: Look for discipline keywords (psychology, economics, biology, etc.)

### Step 3: Extract Research Questions
Identify research questions by:
- Sentences ending with "?"
- Phrases like "we want to know", "the goal is to determine", "whether"
- Implicit questions from objectives ("to examine the relationship between X and Y")

For each question, determine:
- **Type**: descriptive, comparative, associational, causal, predictive, exploratory
- **Outcome variable**: What is being measured/predicted
- **Predictor variable**: What is being manipulated/compared
- **Hypothesis**: Directional prediction if stated

### Step 4: Extract Data Information
Look for:
- Data source mentions ("survey data", "experimental data", "archival records")
- Sample size mentions ("N=500", "500 participants")
- Variable mentions ("age", "income", "test scores")
- Data format hints ("Excel file", "CSV", "database")

### Step 5: Extract Context and Constraints
Look for:
- Target output ("journal article", "report", "presentation")
- Timeline/deadline mentions
- Ethics considerations
- Prior research mentions

### Step 6: Generate Structured Intake
Create `inputs/intake.yaml` from extracted information:

```yaml
title: "[extracted title]"
researcher: "[extracted name]"
institution: "[extracted institution]"
domain: "[extracted domain]"
questions:
  - text: "[question 1]"
    type: "[type]"
    hypothesis: "[hypothesis]"
    outcome: "[outcome variable]"
    predictor: "[predictor variable]"
  - text: "[question 2]"
    type: "[type]"
    hypothesis: "[hypothesis]"
    outcome: "[outcome variable]"
    predictor: "[predictor variable]"
data:
  - description: "[data description]"
    format: "[format]"
    estimated_size: "[sample size]"
    variables: ["var1", "var2"]
target_output: "[journal/report/etc.]"
timeline: "[if mentioned]"
notes: "[additional context]"
```

### Step 7: Generate Confidence Report
Create `inputs/brief_parsing_report.json`:

```json
{
  "schema_version": "1.0.0",
  "timestamp": "ISO 8601",
  "source": "inputs/raw_brief.txt",
  "confidence": {
    "title": "HIGH|MEDIUM|LOW",
    "researcher": "HIGH|MEDIUM|LOW|NOT_FOUND",
    "institution": "HIGH|MEDIUM|LOW|NOT_FOUND",
    "domain": "HIGH|MEDIUM|LOW",
    "questions": "HIGH|MEDIUM|LOW",
    "data": "HIGH|MEDIUM|LOW"
  },
  "missing_fields": ["list of fields that could not be extracted"],
  "requires_user_confirmation": true
}
```

### Step 8: Present for Confirmation
1. Show generated intake to user
2. Highlight fields with LOW confidence or NOT_FOUND
3. Ask user to confirm or correct
4. Write confirmed intake to `inputs/intake.yaml` and `inputs/intake.md`

---

## Extraction Heuristics

### Question Type Detection
| Keywords | Type |
|----------|------|
| "how many", "what is the distribution", "describe" | descriptive |
| "compare", "difference between", "versus" | comparative |
| "relationship", "association", "correlation", "linked" | associational |
| "effect of", "impact", "causes", "influence" | causal |
| "predict", "forecast", "will" | predictive |
| "explore", "understand", "patterns" | exploratory |

### Domain Detection
| Keywords | Domain |
|----------|--------|
| "patient", "clinical", "treatment", "disease" | epidemiology |
| "student", "learning", "education", "achievement" | education |
| "market", "stock", "financial", "investment" | finance |
| "gene", "protein", "expression", "sequencing" | genomics |
| "behavior", "cognitive", "psychological", "mental" | psychology |
| "voter", "policy", "election", "political" | political_science |
| "temperature", "climate", "emission", "carbon" | climate_science |
| "social", "community", "inequality", "demographic" | sociology |

---

## Integration
- Called by: User pastes free-form text, or CLI command `research parse-brief`
- Outputs to: `inputs/intake.yaml`, `inputs/intake.md`, `inputs/brief_parsing_report.json`
- Requires: User confirmation before proceeding to `research_init`
