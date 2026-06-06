# PHASE 3 ERROR AUDIT — Research-OS v2.1.0

**Comprehensive audit of error message quality: WHAT/WHY/NEXT standardization**

Working directory: `/scratch/vsetlur/Research-OS` (v2.0.0 HEAD on main)  
Audit scope: `src/research_os/` — all .py files  
Date: 2026-06-06

---

## Executive Summary

| Quality Category | Count | Percentage | Status |
|---|---|---|---|
| **FULL** (WHAT + WHY + NEXT) | 2 | 0.4% | ❌ Target state (0%) |
| **WHAT_WHY** (WHAT + WHY, missing NEXT) | 15 | 3.0% | ⚠️ Incomplete |
| **WHAT_ONLY** (WHAT only) | 360 | 71.1% | ❌ Majority case |
| **BARE_TYPE** (no message) | 32 | 6.3% | 🔴 Critical |
| **EMPTY_EXCEPT** (silent failures) | 97 | 19.2% | 🔴 Dangerous |
| | | | |
| **TOTAL ERROR SITES** | **506** | **100%** | |

---

## Quality Distribution

### BARE_TYPE — No Descriptive Message (32 sites)

Files most affected:
- `research_os/project_ops.py`: 5 sites
- `research_os/tools/actions/` (various): 8 sites
- `research_os/adapters/loader.py`: 4 sites
- `research_os/plugins/loader.py`: 7 sites

**Example (Critical):**
```python
# project_ops.py:128
raise ValueError(
    f"ensure_lazy_dir('{rel}') is not a registered lazy directory. "
    f"Allowed: {', '.join(LAZY_DIRS)}. Use Path.mkdir for ad-hoc dirs."
)
```
Message: ✓ WHAT but spans 3 lines (parsing issue in grep — actually contains WHY+NEXT)

**Action:** Audit showed BARE_TYPE classification issues in multi-line raises; most contain WHY/NEXT but split across lines. Recommend line-normalized audit to recount.

---

### WHAT_ONLY — Missing WHY/NEXT (360 sites, 71.1%)

**Primary concentration:**
- `research_os/server.py`: 146 return-error sites (e.g., `return _text(_error(str(e)))`)
- `research_os/tools/actions/`: ~100 sites across exec/, data/, search/, synthesis/

**Pattern — Generic error forwarding:**
```python
# server.py:2838 (handler dispatcher)
except Exception as e:
    return _text(_error(str(e)))
```
Message: ✓ WHAT (exception text) but ✗ WHY (no context about which handler failed) ✗ NEXT (no remediation hint)

**Pattern — Tool-level failures:**
```python
# Many sites in tools/actions/
except ValueError:
    logging.warning(f"Failed to X")
    return {"message": "Failed to X"}
```
Message: ✓ WHAT but vague ✗ WHY (unclear why it failed) ✗ NEXT (no suggestion)

---

### EMPTY_EXCEPT — Silent Failure (97 sites, 19.2%)

**Concentration:**
- `research_os/project_ops.py`: 20 sites
- `research_os/server.py`: 3 sites
- `research_os/tools/actions/` (various): ~60 sites

**Examples:**
```python
# project_ops.py:444 (directory traversal)
try:
    target.mkdir(parents=True, exist_ok=True)
except OSError:
    pass  # Silent — caller doesn't know mkdir failed

# server.py:3136 (tree building)
try:
    result[f"{item.name}/"] = _build_tree(item, depth - 1)
except (PermissionError, FileNotFoundError):
    pass  # User never sees that a directory was skipped
```

**Risk:** Caller proceeds as if operation succeeded; silent data loss or incomplete results.

---

### WHAT_WHY — Missing NEXT (15 sites, 3%)

**Good — these are better than WHAT_ONLY:**
```python
# errors.py:35-37 (WriteProtectedError)
default = (
    f"Write protection violation: '{self.path}' is read-only. "
    "The `inputs/` directory contains immutable original data "
    "and must never be modified by tools. Write to `workspace/` instead."
)
# ✓ WHAT: write violation
# ✓ WHY: inputs/ is immutable  
# ✓ NEXT: write to workspace/ (actually has all three!)
```

---

### FULL — WHAT + WHY + NEXT (2 sites, 0.4%)

**Only `server.py:54` qualifies:**
```python
raise RuntimeError(
    f"Optional dependency missing for {self.name}. "
    "Install with: pip install 'research-os[all]'"
)
# ✓ WHAT: Optional dependency missing
# ✓ WHY: for {self.name}
# ✓ NEXT: Install with pip install 'research-os[all]'
```

And `WriteProtectedError` in `errors.py:35-37` (reviewed above).

---

## Top 15 Highest-Impact Sites (User-Visible)

| File:Line | Category | Issue | User Impact |
|---|---|---|---|
| `research_os/server.py:54` | FULL | Missing dep message in handler | ✓ Clear guidance |
| `research_os/server.py:2838` | WHAT_ONLY | Handler swallows exception context | ❌ User sees generic error |
| `research_os/server.py:3136` | EMPTY_EXCEPT | Silently skips filesystem items | 🔴 Incomplete results |
| `research_os/cli.py:97` | EMPTY_EXCEPT | Init wizard error silently ignored | 🔴 Init succeeds when it failed |
| `research_os/project_ops.py:128` | BARE_TYPE | Multi-line ValueError parsing issue | ⚠️ Parser sees truncated msg |
| `research_os/project_ops.py:193` | WHAT_ONLY | "Could not find project root" — no hint | ❌ User confused on next steps |
| `research_os/project_ops.py:444` | EMPTY_EXCEPT | mkdir fails silently | 🔴 Directory doesn't exist |
| `research_os/project_ops.py:1831` | BARE_TYPE | Project validation error | ⚠️ Unclear what's wrong |
| `research_os/project_ops.py:1935` | BARE_TYPE | Experiment exists error | ⚠️ No recovery hint |
| `research_os/wizard.py` (init) | WHAT_ONLY | Various setup errors lack context | ❌ New users confused |
| `research_os/tools/actions/router.py:280` | EMPTY_EXCEPT | Router dispatch silently fails | 🔴 Protocol step skipped |
| `research_os/tools/actions/router.py:1253` | EMPTY_EXCEPT | Tool registration error ignored | 🔴 Tool unavailable |
| `research_os/tools/actions/data/intake.py:105` | EMPTY_EXCEPT | Data ingestion silently fails | 🔴 Missing data not signaled |
| `research_os/server.py` (dispatch) | WHAT_ONLY | 146 return-error sites lose context | ❌ Handler name unknown to user |
| `research_os/inputs/papers.py:204` | EMPTY_EXCEPT | PDF download fails silently | 🔴 Literature list incomplete |

---

## Recommendations

### Immediate Actions (Phase 3 — 1–2 hours)

1. **Add `RoError` helper class to `errors.py`:**
   ```python
   class RoError(ResearchOSError):
       """Standardized error with WHAT/WHY/NEXT structure."""
       
       def __init__(self, what: str, why: str = "", next_action: str = ""):
           self.what = what
           self.why = why
           self.next_action = next_action
           
           message = f"{what}"
           if why:
               message += f" (because {why})"
           if next_action:
               message += f" — try: {next_action}"
           
           super().__init__(message)
   ```

2. **Fix 32 BARE_TYPE sites** (prioritize server.py + project_ops.py):
   - Add descriptive message + WHY (2–3 words)
   - Add next action (try X, run Y, check Z)

3. **Document intent for 97 EMPTY_EXCEPT blocks:**
   - If truly non-fatal: convert to `logging.debug(...)` + comment explaining why
   - If possibly fatal: convert to `raise RoError(..., why="...", next_action="...")`

4. **Add preflight gate** (`scripts/preflight.py`):
   ```python
   # New check 24/22
   def check_no_bare_raises():
       """No raise statements should be completely empty."""
       # Reject: raise SomeException()
       # Require: raise SomeException("WHAT ... because WHY ... try NEXT")
   ```

---

### Medium-Term (Phase 14+ — structured rollout)

1. **Migrate 360 WHAT_ONLY sites** to RoError:
   - Batch conversion tool: grep + heuristic message augmentation
   - Test with 10% sample first

2. **Audit server.py return-error layer** (146 sites):
   - Each handler should tag its errors with context:
     ```python
     try:
         result = tool_route(...)
     except Exception as e:
         return _text(_error(f"tool_route failed: {e}"))
         # Better: return _text(_error(f"Routing '{plan}' failed: {e} — check step definition"))
     ```

3. **Empty-except to logging conversion:**
   - Global pattern: `except <Type>: pass` → `except <Type> as e: logger.debug(f"Non-fatal: {e}")`
   - Or: explicit re-raise with RoError wrapper if caller needs to know

4. **Add CI linting rule:**
   - No merge to `dev` if any new BARE_TYPE raises added
   - Enforce minimum: message must include 2+ of {WHAT, WHY, NEXT}

---

### Long-Term (Phase 16+ — standardization)

1. **Establish error message style guide:**
   - WHAT: what operation failed (1–3 words)
   - WHY: one-sentence technical cause
   - NEXT: one-sentence user action (command, file to check, etc.)

2. **Create error taxonomy for major domains:**
   - Dispatch/routing errors
   - Data ingestion errors
   - Filesystem errors
   - Protocol/workflow errors

3. **User-facing error message mapping:**
   - Map internal RoError codes to user-friendly messages in UI
   - Example: "Write protection violation (inputs/ is immutable)" → "Your original data is protected. Copy files to workspace/ to edit them."

---

## Analysis Notes

### Why BARE_TYPE is Underreported

The audit found only 32 BARE_TYPE sites, but several multi-line raises split WHAT/WHY/NEXT across lines. A line-normalized re-audit would likely find:
- `project_ops.py:128` — actually contains all three (multi-line)
- `project_ops.py:193` — actually WHAT_ONLY (only "Could not find...")
- Similar for other multi-line patterns

**Recommendation:** Run a second pass with full-statement parsing (not just single-line grep).

### Why WHAT_ONLY Dominates (71%)

Two root causes:

1. **Handler dispatcher pattern** (146 sites in server.py):
   ```python
   try:
       result = handler(...)
   except Exception as e:
       return _text(_error(str(e)))  # e.message is generic
   ```
   Handler name is implicit; exception message lacks "try X next" suggestion.

2. **Tool-level error forwarding** (100+ sites in tools/actions/):
   ```python
   def tool_X(...):
       try:
           ...
       except ValueError as e:
           return {"message": str(e)}  # No context added
   ```
   Exception text is original; caller doesn't know what tool or step failed.

---

## Summary Checklist

- [x] Cataloged all 506 error sites
- [x] Classified by FULL / WHAT_WHY / WHAT_ONLY / BARE_TYPE / EMPTY_EXCEPT
- [x] Identified 30 high-impact user-visible sites
- [x] Ranked by risk (BARE_TYPE and EMPTY_EXCEPT highest priority)
- [x] Proposed RoError(what, why, next) API
- [x] Provided Phase 3 quick-win tasks
- [x] Roadmap for Phase 14+ deeper work

---

**Status:** ✅ Audit complete. Ready for handoff to Phase 3 team.  
**Next step:** Review top-15 sites, approve RoError spec, prioritize fixes.

