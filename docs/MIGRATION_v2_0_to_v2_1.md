# Migration: v2.0.x → v2.1.0

v2.1.0 is a MINOR release with no breaking changes to the public
contract documented in `docs/CONTRACT.md`. Most projects will upgrade
with `pip install --upgrade research-os` and notice no visible
difference. A few surfaces evolve gently — this guide names them.

## Response envelope shape

**No action required for read-only consumers.** Every handler still
returns a JSON dict with `status: "success" | "error"` and a data
payload. The v2.0 access pattern `envelope["data"]` keeps working
throughout the v2.1.x cycle.

**Optional migration (for richer client integration):**

```python
# v2.0 access pattern (still works)
result = call_tool(...)
env = parse_envelope(result)
data = env["data"]

# v2.1.0 access pattern (canonical, future-proof)
env = parse_envelope(result)
payload = env["payload"]
recommended_next = env["next_recommended_call"]   # NEW
audit_findings   = env["audit_findings"]          # NEW
tier_transition  = env["tier_transition"]         # NEW
tokens_estimate  = env["tokens_estimate"]         # NEW
ro_version       = env["ro_version"]              # NEW
```

The `data` alias is removed in v2.2.0. Migrate when convenient.

## Error message format

**No action required.** Every error envelope still has
`{"status": "error", "error": <message>}`.

**v2.1.0 enrichments (visible if you want to use them):**

```python
env = parse_envelope(error_result)
print(env["error"])                  # composed sentence (old field)
print(env["payload"]["what"])        # WHAT — one-line description
print(env["payload"]["why"])         # WHY — explanation
print(env["payload"]["next_action"]) # NEXT — what to try
# next_action also lives at the envelope level:
print(env["next_recommended_call"])  # same string as next_action
```

For plugin authors raising structured errors from inside a handler:

```python
from research_os.server.errors import RoError

raise RoError(
    "manifest validation failed",
    why="required field 'protocols_dir' is missing from PackRegistration",
    next_action="add `protocols_dir=Path(__file__).parent / 'protocols'` to your registration",
)
```

The dispatcher catches it and emits the v2.1.0 error envelope with
WHAT/WHY/NEXT on `payload` and `next_action` promoted to
envelope-level `next_recommended_call`.

## Dashboard module rename

`dashboard_v2*` modules renamed to `dashboard_app*`. The legacy
`dashboard.py` (long-scroll renderer, still alive as the
`dashboard_legacy=true` fallback on `tool_dashboard_create`) keeps its
name.

| Old import | New import |
|---|---|
| `from research_os.tools.actions.synthesis.dashboard_v2 import render_dashboard_v2` | `from research_os.tools.actions.synthesis.dashboard_app import render_dashboard_app` |
| `from research_os.tools.actions.synthesis.dashboard_v2 import DASHBOARD_V2_CSS` | `from research_os.tools.actions.synthesis.dashboard_app import DASHBOARD_APP_CSS` |
| `from research_os.tools.actions.synthesis.dashboard_v2_humanities import render_humanities_section` | `from research_os.tools.actions.synthesis.dashboard_humanities import render_humanities_section` |
| `from research_os.tools.actions.synthesis.dashboard_v2_qualitative import render_qualitative_section` | `from research_os.tools.actions.synthesis.dashboard_qualitative import render_qualitative_section` |

The old module paths are kept as 1-line re-export shims through the
v2.1.x cycle. They emit no warning; pack authors and older user
scripts continue to work. Removed in v2.2.0.

## Paper compilation

`docs/PAPER_PIPELINE.md` is new — it documents the canonical model
(`paper.md` intermediate → `paper.typ`/`.tex` → `paper.pdf`).
No code changed; the new doc names a model that was already in
place. Configuration:

```yaml
# inputs/researcher_config.yaml
writing_preferences:
  pdf_compile_engine: typst   # default; opt-in: latex
```

## Validation matrix

v2.1.0 ships with `docs/V21_VALIDATION_REPORT.md` — 10 perspective
agents × scenarios + 20 random natural-language prompts. Read this if
you want to know how the system would behave for an AI/researcher in
your role before you commit to upgrading.

## Things explicitly NOT changed in v2.1.0

- Tool surface (146 live tools): unchanged. No additions, no removals.
- Protocol surface (117 core + 36 pack): unchanged at root names.
- Tool input schemas: unchanged.
- MCP `instructions` field: unchanged.
- Branch protection / release workflow: unchanged.

## Removed (per v2.0.0 migration table runway)

Per `docs/V2_MIGRATION_TABLE.md`, the following v1.x consolidation
aliases scheduled for removal in v2.1.0 have been removed:

- (none for this cycle — most v1.x aliases expire in v2.2.0, not
  v2.1.0).

The MINOR bump preserves backwards-compatibility for the entire
v2.1.x line. v2.2.0 will remove the deprecated `data` alias on the
envelope + the `dashboard_v2*` re-export shims.
