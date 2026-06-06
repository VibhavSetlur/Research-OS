# Phase 13 — perspective-agent JSON report schema

Every perspective agent in `/tmp/ro_v21_validation/<perspective>__<scenario>/` returns a JSON object matching this schema. Workflow `agent(prompt, {schema: PERSPECTIVE_REPORT_SCHEMA})` enforces validity at the tool-call layer.

## Top-level shape

```json
{
  "perspective": "naive_ai",
  "scenario": "biology_rnaseq",
  "wall_clock_minutes": 28,
  "turns_total": 17,

  "tool_calls": [
    { "tool": "sys_boot", "turn": 1, "outcome": "success",
      "friction": "none", "doc_gap": null }
  ],

  "subagent_spawns": [
    { "purpose": "literature search for DE-method choice", "result": "ok" }
  ],

  "deliverables_produced": [
    "workspace/01_qc/conclusions.md",
    "synthesis/paper.pdf"
  ],
  "deliverables_missing": [
    "workspace/03_de/findings_vs_literature.md"
  ],

  "consistency_findings": [
    { "kind": "naming", "where": "src/research_os/tools/actions/synthesis/dashboard.py",
      "what": "dashboard_v2 still referenced in router_index",
      "severity": "medium", "suggested_fix": "update router_index entry" }
  ],

  "ai_use_grade": {
    "tool_surface_clarity_1_10": 8,
    "protocol_routing_accuracy_1_10": 9,
    "error_message_quality_1_10": 7,
    "envelope_consistency_1_10": 8,
    "rationale": "Tool names are clean; one error gave WHAT but no NEXT."
  },

  "researcher_use_grade": {
    "onboarding_smoothness_1_10": 8,
    "iteration_loop_clarity_1_10": 7,
    "output_quality_1_10": 9,
    "fits_my_level_1_10": 7,
    "rationale": "PDF output is great; dashboard story-mode unclear to undergrad."
  },

  "system_consistency_grade": {
    "internal_contradictions_count": 0,
    "stale_doc_references_count": 2,
    "stale_tool_references_count": 1,
    "stale_protocol_references_count": 0,
    "rating_1_10": 8
  },

  "top_10_friction_points": [
    { "rank": 1, "where": "tool_route output", "what": "no tier_transition shown",
      "severity": "medium", "suggested_fix": "add tier_transition to envelope",
      "target_version": "v2.1.0" }
  ],

  "top_5_worked_well": [
    "Semantic routing nailed 'I want to see my data'"
  ],

  "final_rating": 8.2,
  "final_rationale": "Solid end-to-end with two small friction items."
}
```

## Field semantics

- **perspective** — one of: `naive_ai`, `experienced_ai`, `undergrad`, `grad_dissertation`, `postdoc_audit`, `pi_review`, `industry`, `methodology_auditor`, `reproducibility`, `maintainer`
- **scenario** — one of: `biology_rnaseq`, `humanities_close_reading`, `qualitative_interviews`, `engineering_benchmark`, `flawed_biology_fixture`, `theory_math_proof`, `rapid_prototyping`, `read_p1_biology`, `read_p4_engineering`, `trace_core_api_refactor`
- **tool_calls** — every tool invocation; `friction ∈ {none, low, medium, high}`; `doc_gap` is the doc that should have mentioned this but didn't (or null)
- **subagent_spawns** — perspective agents are allowed to spawn sub-agents for specific sub-tests
- **consistency_findings.kind** — one of: `naming`, `envelope`, `error`, `protocol_ref`, `tool_ref`, `gate`, `workspace`
- **ai_use_grade** — perspective agent's grade of how usable the system is for an AI client
- **researcher_use_grade** — perspective agent's grade of how usable for the researcher persona that perspective embodies
- **system_consistency_grade** — perspective agent's grade of internal system coherence
- **top_10_friction_points.target_version** — one of: `v2.1.0`, `v2.1.x`, `v2.2.0`, `v3.0.0`
- **final_rating** — overall 1-10 rating for the perspective's experience; one decimal
- **final_rationale** — 1-3 sentences explaining the final_rating

## Aggregation (synthesis agent)

After all 10 perspective agents complete, one synthesis agent reads all 10 reports plus the 40 random-prompt reports and writes `docs/V21_VALIDATION_REPORT.md` with:

1. **Executive summary** — 10×6 grade matrix (rows=perspectives, cols=dimensions); top-20 friction points by frequency; top-20 consistency findings by frequency; routing accuracy %; worst-3 prompts.
2. **Per-perspective distillation** — one paragraph each.
3. **Cross-perspective themes** — findings in ≥3 perspectives.
4. **v2.1.0 fix list** — prioritized, with target file + estimated effort.
5. **v2.1.x patch list** — items deferred for the next patch cycle.
6. **v2.2.0+ future work** — items requiring a MINOR or MAJOR for scope reasons.
7. **v3.0.0 architectural ideas** — out-of-scope but logged.

## JSON Schema (validation)

```json
{
  "type": "object",
  "required": ["perspective", "scenario", "wall_clock_minutes", "turns_total",
               "tool_calls", "deliverables_produced", "deliverables_missing",
               "consistency_findings", "ai_use_grade", "researcher_use_grade",
               "system_consistency_grade", "top_10_friction_points",
               "top_5_worked_well", "final_rating", "final_rationale"],
  "properties": {
    "perspective": {"type": "string"},
    "scenario": {"type": "string"},
    "wall_clock_minutes": {"type": "number"},
    "turns_total": {"type": "integer"},
    "tool_calls": {"type": "array", "items": {"type": "object"}},
    "subagent_spawns": {"type": "array", "items": {"type": "object"}},
    "deliverables_produced": {"type": "array", "items": {"type": "string"}},
    "deliverables_missing": {"type": "array", "items": {"type": "string"}},
    "consistency_findings": {"type": "array", "items": {"type": "object"}},
    "ai_use_grade": {"type": "object"},
    "researcher_use_grade": {"type": "object"},
    "system_consistency_grade": {"type": "object"},
    "top_10_friction_points": {
      "type": "array",
      "minItems": 0, "maxItems": 10,
      "items": {"type": "object"}
    },
    "top_5_worked_well": {
      "type": "array",
      "minItems": 0, "maxItems": 5,
      "items": {"type": "string"}
    },
    "final_rating": {"type": "number", "minimum": 1, "maximum": 10},
    "final_rationale": {"type": "string"}
  }
}
```
