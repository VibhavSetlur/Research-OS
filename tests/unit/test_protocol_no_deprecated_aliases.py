"""AUDIT-047: assert no deprecated tool aliases appear in shipped protocol YAMLs.

The dispatcher (_resolve_tool_name in server.py) still rewrites old names to
their canonical handlers so end-user projects on older versions keep working,
but our own protocol files must reference only canonical names. Drift here
makes copy-paste guidance silently route through the deprecation telemetry
path and confuses readers grepping the source for tool usage.

This test grep-walks every protocol YAML under src/research_os/protocols and
src/research_os_<pack>/protocols and fails if any of the 21 names listed in
server._DEPRECATED_ALIASES appears as a whole word.

Scope:
- Includes core protocols + every domain pack (humanities, qualitative,
  theory_math, wet_lab, engineering).
- Excludes the router index (handled by the integration agent in lockstep
  with this sweep; it is the only file that may keep a transition entry).
- Excludes tests and server.py themselves — the aliases are defined there.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Mirror of server._DEPRECATED_ALIASES; kept inline so this test doesn't
# import the server module (cheap + decoupled).
DEPRECATED_ALIASES: frozenset[str] = frozenset(
    {
        "tool_search_semantic_scholar",
        "tool_search_pubmed",
        "tool_search_crossref",
        "tool_search_arxiv",
        "tool_search_web",
        "tool_plan_turn",
        "tool_plan_advance",
        "tool_plan_clear",
        "tool_grounding_register",
        "tool_ground_from_context",
        "tool_claim_verify",
        "tool_grounding_verify",
        "tool_lessons_record",
        "tool_lessons_consult",
        "sys_path_create",
        "sys_path_abandon",
        "sys_path_list",
        "mem_methods_append",
        "mem_decision_log",
        "mem_hypothesis_update",
        "mem_analysis_log",
    }
)

# Whole-word regex: \b includes underscore on the right of the alias which
# would let "sys_path_create_v2" match; rebuild boundaries explicitly so we
# only catch the bare alias.
_ALIAS_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_])(?:" + "|".join(re.escape(a) for a in DEPRECATED_ALIASES) + r")(?![A-Za-z0-9_])"
)

# Router index is swept by the integration agent in lockstep with this
# feature; do not enforce here so this test can land before the router PR.
_EXCLUDE_RELATIVE: frozenset[str] = frozenset(
    {
        "src/research_os/protocols/_router_index.yaml",
    }
)


def _protocol_yaml_files() -> list[Path]:
    """All shipped protocol YAMLs across core + domain packs."""
    roots: list[Path] = [REPO_ROOT / "src" / "research_os" / "protocols"]
    for pack_dir in (REPO_ROOT / "src").glob("research_os_*"):
        proto = pack_dir / "protocols"
        if proto.is_dir():
            roots.append(proto)

    files: list[Path] = []
    for root in roots:
        files.extend(root.rglob("*.yaml"))
        files.extend(root.rglob("*.yml"))

    excluded = {REPO_ROOT / p for p in _EXCLUDE_RELATIVE}
    return sorted(f for f in files if f not in excluded)


def test_protocol_yamls_found() -> None:
    """Guard: if the glob returns nothing the assertion below trivially passes."""
    files = _protocol_yaml_files()
    assert len(files) >= 50, (
        f"expected >=50 protocol YAMLs across core + packs, found {len(files)}; "
        "the discovery glob is probably broken"
    )


def test_no_deprecated_aliases_in_protocol_yamls() -> None:
    """Every shipped protocol must reference only canonical tool names."""
    offenders: list[str] = []
    for path in _protocol_yaml_files():
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for match in _ALIAS_PATTERN.finditer(text):
            line_no = text.count("\n", 0, match.start()) + 1
            rel = path.relative_to(REPO_ROOT)
            offenders.append(f"{rel}:{line_no}: {match.group(0)}")

    assert not offenders, (
        f"found {len(offenders)} deprecated-alias reference(s) in protocol YAMLs "
        f"(first 10): {offenders[:10]}"
    )
