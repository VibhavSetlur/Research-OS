# PHASE 2 ENVELOPE AUDIT: Research-OS v2.1.0 Handler Return Shape Standardization

**Date**: 2026-06-06  
**Scope**: v2.0.0 code at `origin/dev` (13 handler files, 212 total handlers)  
**Target Envelope** (v2.1.0):
```json
{
  "status": "success" | "warning" | "error",
  "payload": {...},
  "audit_findings": [...],
  "next_recommended_call": "tool_X(...)" | null,
  "tier_transition": "tier_* → tier_*" | null,
  "tokens_estimate": int,
  "ro_version": "2.1.0"
}
```

---

## Handler Inventory by File

| File | Count | Current Shape | Status | Payload | audit_findings | next_call | tier_trans | Notes |
|------|-------|---------------|--------|---------|----------------|-----------|-----------|-------|
| **meta_routing.py** | 18 | FLAT_DICT | ✓ | ✓ data | ✗ | ⊗ (in data) | ✗ | Routing + dispatcher; tool_route/semantic_route manually inject recommended_action |
| **meta_sys.py** | 18 | FLAT_DICT | ✓ | ✓ data | ✗ | ✗ | ✗ | Config, env, packs, adapters |
| **meta_help.py** | 1 | FLAT_DICT | ✓ | ✓ data | ✗ | ✗ | ✗ | Single orientation handler |
| **meta_workspace.py** | 18 | FLAT_DICT | ✓ | ✓ data | ✗ | ✗ | ✗ | Files, paths, checkpoints, state |
| **research_search.py** | 16 | FLAT_DICT | ✓ | ✓ data | ✗ | ✗ | ✗ | Search, scrape, literature, profiling |
| **research_exec.py** | 20 | FLAT_DICT | ✓ | ✓ data | ✗ | ✗ | ✗ | Python, script, SLURM, tasks, notebooks |
| **audit_core.py** | 26 | FLAT_DICT | ✓ | ✓ data | ✗ | ✗ | ✗ | 26 audit dimensions + dispatcher |
| **audit_gates.py** | 11 | FLAT_DICT | ✓ | ✓ data | ✗ | ✗ | ✗ | Freshness, rigor, gates (status='blocked' ok) |
| **synthesis_writing.py** | 10 | FLAT_DICT | ✓ | ✓ data | ✗ | ✗ | ✗ | Synthesize, compile (LaTeX/Typst), preview |
| **synthesis_visual.py** | 14 | FLAT_DICT | ✓ | ✓ data | ✗ | ✗ | ✗ | Dashboard, story, figures, slides, poster |
| **synthesis_reviewer.py** | 5 | FLAT_DICT | ✓ | ✓ data | ✗ | ✗ | ✗ | Reviewer sim, rebuttal, response |
| **methodology.py** | 31 | FLAT_DICT | ✓ | ✓ data | ✗ | ✗ | ✗ | Plan, step, pipeline, preregister, sensitivity (largest) |
| **grounding.py** | 24 | FLAT_DICT | ✓ | ✓ data | ✗ | ✗ | ✗ | Memory logs, thought, lessons, reliability (second largest) |

**TOTAL**: 212 handlers

---

## Summary

### Return Shape Distribution

| Category | Count | % | Details |
|----------|-------|---|---------|
| **FLAT_DICT** | 212 | 100% | All return `_text(_success({...}))` or `_text(_error(...))` |
| **ENVELOPED** | 0 | 0% | None yet use v2.1.0 envelope |
| **TUPLE_MCP** | 212 | 100% | Wrapped in `[TextContent(...)]` |
| **NESTED/OTHER** | 0 | 0% | N/A |

### Current v2.0.0 Envelope Shape

```python
_success(data_dict) → {"status": "success", "data": data_dict}
_error(msg)         → {"status": "error", "error": msg}
_text(payload)      → [TextContent(type="text", text=json_string)]
```

### Fields Present vs. Missing

| Field | Present in v2.0.0 | Missing | Target v2.1.0 Map |
|-------|-------------------|---------|------------------|
| status | ✓ all | — | → status (unchanged) |
| data | ✓ all | — | → payload (rename) |
| audit_findings | ✗ | ✓ all | New field; opportunity |
| next_recommended_call | ⊗ (in data only: meta_routing) | ✓ most | Elevator to envelope level |
| tier_transition | ✗ | ✓ all | New field; opportunity |
| tokens_estimate | ✗ | ✓ all | New field; heuristic |
| ro_version | ✗ | ✓ all | New field (constant "2.1.0") |

---

## Migration Complexity Assessment

### Easiest (Already Close)

1. **All 212 handlers uniformly use `_success()` / `_error()`** → batch wrapper straightforward
2. **meta_routing.py** (tool_route, tool_semantic_route) → already populate recommended_action in payload
3. **audit_gates.py** → already handle status='blocked' informational; envelope preserves enum
4. **Synthesis modules** (writing, visual, reviewer) → thin wrappers around action functions

### Hardest (Semantic Complexity)

1. **Dispatchers** (tool_audit, tool_dashboard, tool_figure, tool_step, tool_plan) → delegate to sub-handlers; must preserve chain transparently
2. **Mixed success/error states** (e.g., tool_plan_advance with bypassed_blockers) → envelope semantics needed
3. **Handler returning status != 'success'** (audit_gates.blocked) → requires careful enum handling in v2.1.0

---

## Recommended Approach: Subclass Dict for Backwards Compat

```python
class V21Envelope(dict):
    """Transparent dict subclass; old 'data' key aliases to 'payload'."""
    def __init__(self, status, data=None, **extras):
        super().__init__(
            status=status,
            payload=data or {},
            audit_findings=extras.get("audit_findings", []),
            next_recommended_call=extras.get("next_recommended_call"),
            tier_transition=extras.get("tier_transition"),
            tokens_estimate=extras.get("tokens_estimate", 0),
            ro_version="2.1.0"
        )
    
    @classmethod
    def from_success(cls, data, **extras):
        return cls("success", data, **extras)
    
    @classmethod
    def from_error(cls, error_msg, **extras):
        return cls("error", {"error": error_msg}, **extras)
    
    # Optional: Provide __getitem__ alias for backward compat
    # def __getitem__(self, key):
    #     if key == "data":
    #         return self.get("payload", {})
    #     return super().__getitem__(key)
```

**Benefits**:
- Incremental migration (handlers rewritten one at a time)
- Old code accessing envelope["data"] still works (dict semantics)
- New code uses envelope["payload"] + enrichment fields
- MCP _text() wrapper unchanged (dict→JSON-serialized)

**Transition Path**:
- Phase 2a: Create V21Envelope + new helpers
- Phase 2b: Migrate high-value handlers (audit, synthesis, methodology)
- Phase 2c: Batch-migrate remaining handlers
- Phase 2d: Retire old _success/_error at v2.2.0

---

## Implementation Effort Estimate

| Task | Hours | Handlers | Notes |
|------|-------|----------|-------|
| 1. Finalize V21Envelope spec + create envelopes_v21.py | 6 | — | Design + docstrings |
| 2. Update _handlers_runtime.py imports | 2 | — | Add v21 exports, keep v2.0 compat |
| 3. Migrate meta_* handlers | 12 | 55 | Rename _success calls; add recommended_action mapping |
| 4. Migrate research_* handlers | 10 | 36 | Action fn delegation; add search hints |
| 5. Migrate audit_* handlers | 14 | 37 | Dispatcher + audit_findings rich field |
| 6. Migrate synthesis_* handlers | 10 | 29 | Token estimation hints |
| 7. Migrate grounding + methodology | 16 | 55 | Largest; preserve enrichment |
| 8. Testing + validation | 8 | All | Round-trip, MCP compat, backward-compat |
| 9. Documentation + migration guide | 4 | — | Update V2_MIGRATION_TABLE.md |
| **TOTAL** | **82h** | **212** | ~2 weeks FTE; parallelizable |

---

## Key Findings

- **No structural blockers** — all handlers already return dicts; no raw strings or non-dict types
- **Dispatcher pattern widely used** — tool_audit, tool_dashboard, tool_figure, tool_step, tool_plan, tool_sensitivity all delegate transparently
- **Enrichment data scattered** — v2.1.0 centralizes recommended_action, tier transitions, audit_findings
- **Token estimation missing** — opportunity to add heuristics (e.g., payload_size / 4 tokens)
- **Status='blocked' handling** — audit_gates already use non-success status; v2.1.0 enum accommodates this

**Conclusion**: All 212 handlers are well-positioned for standardized wrapping. Recommend Option A (subclass dict) for minimal disruption.

