# Phase 16 — Final Docs + Migration Guide + 2.0.0 Release Prep

## Prerequisites
- Phases 9, 10, 14, 15b all landed
- All tests pass; preflight 22/22+; ruff clean
- V2_VALIDATION_REPORT.md exists (Phase 15b output) with GREEN verdict (or documented YELLOW/RED with rationale)

## Tasks

### 16a — Docs refresh (post-consolidation)
Sweep + update every public-facing doc to reflect the new ~120-tool surface:
- README.md (post-consolidation badges, counts, quickstart with new tool names)
- docs/START.md (post-CLI-fix walkthroughs from Phase 13)
- docs/AI_GUIDE.md (post-consolidation tool surface + the new MCP instructions field + sys_protocol_get summary default)
- docs/RESEARCHER_GUIDE.md
- docs/FAQ.md
- docs/PROTOCOLS.md (post-router-improvements + tier annotations)
- docs/TOOLS.md (post-consolidation list, alphabetical by canonical name; aliases as cross-references)
- docs/CONTRACT.md — finalize for v2.0.0; freeze the stable-surface promise

### 16b — Migration guide
docs/MIGRATION_v1_to_v2.md
- One section per surface change:
  - Tool rename + arg transformation table (sourced from V2_MIGRATION_TABLE.md)
  - Behavior changes (sys_protocol_get default = summary; tool_route now returns recommended_action + tier + why_matched; etc.)
  - Config field changes (anything removed in Phase 14e)
  - MCP initialize instructions field — note that pre-v2 IDEs won't see it
- "Upgrade in 5 steps" quick recipe at the top
- Per-pack migration notes

### 16c — Release notes
docs/V2_RELEASE_NOTES.md
- Celebratory summary linking all sub-docs
- Headline: tool surface 352 → ~120; server.py 7499 → modular; 5 CRAFT additions
- Pull baseline → revalidation numbers from V2_VALIDATION_REPORT.md
- Link to MIGRATION_v1_to_v2.md for breaking changes
- Validation matrix excerpt (4 perspectives × 5 scenarios)

### 16d — CHANGELOG finalize
Write the [2.0.0] entry in CHANGELOG.md (currently empty under Unreleased):
- Highlights (1 paragraph, ~3 sentences)
- Added (~15 bullets)
- Changed (~20 bullets)
- Deprecated (~5 bullets; aliases live for v2.0.x, removal in v2.1.0)
- Removed — Migration table reference to MIGRATION_v1_to_v2.md
- Fixed (~30 bullets from Phase 15a + 15b)
- Validation: full 4×5 matrix with baseline → final ratings

### 16e — Version bump
Bump 1.11.0 (or 2.0.0-dev) → 2.0.0 in:
- pyproject.toml
- src/research_os/__init__.py (__version__)
- CITATION.cff (version + date-released)

Plus: every protocol with a structural change gets its `version:` field bumped to 2.0.0. Use `scripts/proto_bump.py` if it exists; else sweep manually with sed.

Bump `_router_index.yaml` top-level `version:` field.

### 16f — Wheel build sanity
```bash
python -m build
unzip -l dist/research_os-2.0.0-*.whl | grep assets/ | head
# Confirm typst templates, fonts, reveal.js (Phase 2), Touying (Phase 2),
# poster Typst packages, and pack registrations are all vendored.
```

### 16g — PR & tag (HUMAN-IN-THE-LOOP)
DO NOT auto-push. The user owns release decisions. Just prepare:
- The feat/v2.0.0 → dev PR is ready to open
- The dev → main release PR is ready to open after dev lands
- The `git tag -a v2.0.0` command is ready to run from main
- All three commands written in the final report so the user can copy-paste

DO NOT push the tag. DO NOT merge to main. Surface the next manual steps clearly.

## Workflow shape (4 parallel agents + 1 sequential release prep)

- Agent A: 16a docs refresh
- Agent B: 16b migration guide
- Agent C: 16c release notes
- Agent D: 16d CHANGELOG finalize

Then sequential:
- Agent E: 16e version bump + 16f wheel sanity + 16g report

## Final report shape (~600 words, per the v2.0.0 master prompt)
- Phase 0 baseline → Phase 15b final delta (tools, protocols, server.py lines, usability rating, friction count, test count)
- 4×5 perspective × scenario rating matrix: baseline → final
- Top 10 improvements that moved the rating
- Top 5 CRAFT-inspired additions and their measured impact
- Remaining v2.0.1 / v2.1.0 deferred work + rationale
- Wheel-build status
- Manual next-steps for the user (PR open, tag push, PyPI verify)
- Total agent invocations + sessions
