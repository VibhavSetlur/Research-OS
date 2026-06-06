# Lens 05 — Cross-protocol reference + recommendation graph

**Audit scope:** every `*.yaml` under `src/**/protocols/` (excluding `_router_index.yaml`, `_embeddings*`, and `tests/fixtures/*`).
**Audit version:** Research-OS v1.9.1 → discovery sprint for v1.9.2.
**Tool used:** `/tmp/audit_protocol_graph3.py` + `/tmp/audit_chain_depth.py` + `/tmp/audit_components.py` (yaml + tarjan SCC + topo-longest-path; no networkx required).
**Canonical reference fields found:** `next_protocol`, `prerequisites`, `redirect_to`. **No `see_also` field exists in any protocol** (the task hint asked for it; it is not a real schema field in v1.9.1).
**Routing fields found (router-side):** `triggers`, `decomposition`, `shortcut_tool`, `intent_class`, `sub_intent` — these live in `_router_index.yaml` (core) and `src/research_os_*/router_entries.py` (plugins).

---

## Graph stats

| Metric | Value |
|---|---|
| Protocol YAML files | **150** (core: 114, plugin: 36) |
| Plugin breakdown | theory_math 8, humanities 8, wet_lab 8, engineering 7, qualitative 5 |
| Router keys (core `_router_index.yaml`) | **114** |
| Router keys (plugin `router_entries.py` total) | **36** |
| Router-addressable protocols | **150 / 150** (every protocol has a router entry) |
| `next_protocol` edges (resolved) | **92** |
| Terminal protocols (`next_protocol: null` explicit) | **56** |
| Protocols with no `next_protocol` field at all | **2** (intentional deprecation stubs; see below) |
| Broken `next_protocol` references | **0** |
| Cycles (in next-protocol graph) | **3** (all 2-cycles) |
| Bootstrap roots (router `session/boot` + `session/resume`) | **2** — `session_boot`, `session_resume` |
| Reachable from bootstrap via `next_protocol` chain | **2 / 150** (by design — boot ends with `null`, router takes over) |
| Reachable from router (router-keys + chain) | **150 / 150** |
| Weakly connected components in the `next_protocol` graph | **18** |
| Largest component | 48 protocols (the core "intake → synthesis" flow) |
| Longest acyclic chain | **9 nodes / 8 edges**: `project_startup → domain_analysis → deep_domain_research → methodology_selection → literature_search → analysis_plan → reproducibility → audit_and_validation → synthesis_paper` |
| Protocols with zero in/out `next_protocol` edges | 43 (router-only, intentional) |

**Interpretation.** Research-OS is router-first, not chain-first. The protocol DAG is sparse on purpose: `next_protocol` is the *pipeline hint* for the linear paper-track, but most protocols are dispatched via `tool_route` (semantic + trigger boost) and so do not need chain edges. That is why "depth from bootstrap" is 0 — the bootstrap protocols (`session_boot`, `session_resume`) end with `next_protocol: null` and the router decides where the user goes next.

The meaningful depth metric is the **longest acyclic chain = 8 edges**, traversing the core paper-research pipeline.

---

## Orphans

**Count: 0.**

After accounting for plugin `router_entries.py` (which the first pass missed), every parsed protocol has a router entry and is therefore reachable through `tool_route`. A naive chain-only orphan check produced false positives — e.g. `engineering_report_structure` and `conjecture_tracking` look orphan in the chain graph but are dispatched via `engineering/output/engineering_report_structure` and `theory_math/conjecture/conjecture_tracking` router keys in the plugin packs.

---

## Dead ends

**Count: 0 unintentional.**

Two protocols have no `next_protocol` field at all, but both are intentional deprecation stubs:

| Protocol | File | Status |
|---|---|---|
| `synthesis_handout` | `src/research_os/protocols/synthesis/synthesis_handout.yaml` | Uses `redirect_to: synthesis/printable` + `redirect_params: { format: handout }` |
| `synthesis_poster` | `src/research_os/protocols/synthesis/synthesis_poster.yaml` | Uses `redirect_to: synthesis/printable` + `redirect_params: { format: poster }` |

Redirect target `synthesis/printable` (id `printable`) exists. These are legitimate v1.7→v1.9 deprecations (old per-format protocols folded into a single `printable` with a format parameter). Not a bug.

The 56 protocols with explicit `next_protocol: null` are correct terminals — most are leaf outputs (`synthesis_paper`, `defense_prep`, plugin outputs), session-level controls (`session_boot`, `session_resume`, `chat_handoff`, `collaboration_handoff`, `constructive_disagreement`), or standalone tools (`code_review`, `glossary_update`, `printable`, etc.).

---

## Cycles

**Count: 3 — all 2-cycles between paired protocols.**

| # | Cycle | Files |
|---|---|---|
| 1 | `external_tool_setup` ↔ `mcp_ecosystem_integration` | `methodology/external_tool_setup.yaml`, `methodology/mcp_ecosystem_integration.yaml` |
| 2 | `uncertainty_quantification` ↔ `fairness_audit` | `methodology/uncertainty_quantification.yaml`, `methodology/fairness_audit.yaml` |
| 3 | `coding_scheme_development` ↔ `inter_rater_reliability` | `methodology/coding_scheme_development.yaml`, `methodology/inter_rater_reliability.yaml` |

**Why this matters.** Each pair declares the other as its `next_protocol`. This is *defensible* — they are conceptual siblings ("if you just did UQ, you should sanity-check fairness; if you just did fairness, you should sanity-check UQ"), and the bidirectional hint helps the router suggest the other when one is done. But an AI client following `next_protocol` blindly will ping-pong forever.

**Recommended fix (v1.9.3 or v1.10.0)**: introduce a `recommended_followups: [a, b, c]` field (list) for the multi-direction case, and reserve `next_protocol` for *single, non-circular* successor in the linear pipeline. Until then, document the ping-pong risk in `PROTOCOL_DOCTRINE.md`.

**Severity:** MEDIUM. The router prevents infinite traversal at runtime (each `tool_route` call is independent), but the `next_protocol` chain itself is mis-shaped as a recommendation graph.

---

## Broken refs

**Count: 0.** Every `next_protocol` value resolves to an existing protocol id.

No protocol uses a `see_also` field (the task hint suggested it; verified absent across all 150 files). If `see_also` is intended to exist in v1.10.0+, it is currently undefined.

---

## Weakly connected components (informational)

The `next_protocol` graph fragments into **18 weakly connected components**. The big component (48 protocols) is the core paper-research pipeline. The other 17 are tightly-themed subgraphs: visualization family, wet_lab provenance family, theory_math proof family, humanities textual family, qualitative coding family, etc.

Plus 43 isolated nodes that participate in zero `next_protocol` edges — these are router-only protocols (e.g. `casual_exploration`, `chat_handoff`, `code_review`, `printable`, `collaboration_handoff`). This is expected for utility / session-control protocols that have no fixed successor.

---

## Findings sent to the synthesis agent

| Severity | Category | Title | File hint |
|---|---|---|---|
| MEDIUM | INCONSISTENCY | 3 two-cycles in `next_protocol` (UQ↔fairness, IRR↔coding-scheme, MCP↔tool-setup) | `src/research_os/protocols/methodology/{uncertainty_quantification, fairness_audit, inter_rater_reliability, coding_scheme_development, external_tool_setup, mcp_ecosystem_integration}.yaml` |
| LOW | DOC_GAP | `PROTOCOL_DOCTRINE.md` does not document the `next_protocol: null` + router-takeover pattern; new authors may assume chain reachability is required | `docs/PROTOCOL_DOCTRINE.md` |
| LOW | ARCH_SMELL | No `see_also` or `related_protocols` field; the lateral-suggestion graph lives only inside router triggers / decomposition, which is harder to traverse for callers wanting "related work" | schema-wide |

No CRITICAL or HIGH findings. No bugs that block release.

---

## Trivial fixes applied

**None.** No typos, dead imports, broken markdown, trailing whitespace, or ruff-fixable issues found in the protocol YAMLs or `_router_index.yaml`. The graph is internally consistent; the only structural issue is the three intentional-feeling 2-cycles, which are a design decision to surface (not a code fix to apply).

---

## Mermaid graph

Written to `docs/PROTOCOL_GRAPH.mermaid` (158 lines). Renders the 92 `next_protocol` edges plus a synthetic `bootstrap → {session_boot, session_resume}` entry. Terminal protocols are dashed to a sink node `END_TERM` and the three cycles are annotated as comments. Open the file in any mermaid renderer (e.g. mermaid.live) to visualize the recommendation skeleton.
