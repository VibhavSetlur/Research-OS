"""F2.5 drift guard: every tool_audit(scope=…, dimension=…) named in a protocol
must resolve in the server's _AUDIT_DISPATCH table.

Audit protocols mix the unified tool_audit(scope, dimension) form with prose; if
a protocol names a (scope, dimension) pair the dispatcher doesn't know, the AI is
told to call a gate that doesn't exist. This guard keeps protocol prose in sync
with the dispatch table so it can't drift again.
"""
from __future__ import annotations

import re
from pathlib import Path

from research_os.server._helpers import _AUDIT_DISPATCH

_PROTO_DIR = Path(__file__).resolve().parent.parent.parent / "src" / "research_os" / "protocols"

# scope='x', dimension='y' (quotes optional, order tolerant of whitespace)
_PAT = re.compile(
    r"tool_audit\(\s*scope=['\"]?(?P<scope>[a-z_]+)['\"]?\s*,\s*dimension=['\"]?(?P<dim>[a-z_]+)['\"]?"
)


def test_protocol_audit_gate_refs_resolve_in_dispatch():
    valid = set(_AUDIT_DISPATCH.keys())
    bad: list[str] = []
    for yaml_file in _PROTO_DIR.rglob("*.yaml"):
        if yaml_file.name.startswith("_"):
            continue
        text = yaml_file.read_text(encoding="utf-8")
        for m in _PAT.finditer(text):
            pair = (m.group("scope"), m.group("dim"))
            if pair not in valid:
                bad.append(f"{yaml_file.relative_to(_PROTO_DIR)}: tool_audit{pair} not in _AUDIT_DISPATCH")
    assert not bad, "Protocol audit-gate refs drifted from _AUDIT_DISPATCH:\n" + "\n".join(bad)
