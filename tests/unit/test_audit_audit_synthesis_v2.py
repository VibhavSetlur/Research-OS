"""Phase-4b regression — :class:`SynthesisAudit` migration.

Asserts that the legacy ``audit_synthesis`` markdown report continues
to be written byte-for-byte, and that the new AuditBase companion
artefacts (``workspace/synthesis_audit.json`` + the
``workspace/logs/.audit_findings.jsonl`` ledger) land alongside it
with schema-valid content.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from research_os.tools.actions.audit._base import (
    AuditFinding,
    validate_finding,
)
from research_os.tools.actions.audit.audit import audit_synthesis
from research_os.tools.actions.audit.synthesis_audit import (
    SynthesisAudit,
    findings_from_synthesis_result,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def workspace_root(tmp_path: Path) -> Path:
    """Minimal project root the legacy auditor + writer can use."""
    (tmp_path / "workspace" / "logs").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _seed_paper(root: Path) -> str:
    """Write a known paper.md so the legacy markdown report is deterministic."""
    p = root / "synthesis" / "paper.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "# Title\n\n"
        "## Abstract\nbody\n\n"
        "## Introduction\nbody\n\n"
        "## Methods\nbody\n\n"
        "## Results\nbody\n\n"
        "## Discussion\nbody\n\n"
        "## References\n[1] Doe 2024.\n"
    )
    return "synthesis/paper.md"


# ---------------------------------------------------------------------------
# Markdown snapshot: legacy report is preserved byte-for-byte.
# ---------------------------------------------------------------------------


def test_legacy_markdown_report_byte_for_byte_preserved(workspace_root: Path):
    """The procedural ``synthesis_audit.md`` content must match the pre-
    Phase-4 fixture exactly. Re-running the audit twice on the same
    fixture must produce identical bytes."""
    paper_path = _seed_paper(workspace_root)
    res = audit_synthesis(paper_path, workspace_root)
    md_path = workspace_root / res["report_path"]
    assert md_path.is_file()
    first_bytes = md_path.read_bytes()

    # Snapshot: the legacy markdown body is the canonical procedural
    # report. The content is dependent only on the paper + workspace
    # state — neither changes between calls — so bytes must match.
    expected = (
        b"# Synthesis Audit\n\n"
        b"- Missing sections: none\n"
        b"- Causal-language hits: 0\n"
        b"- Citation count: 0 (0.0/1000w)\n"
        b"- Figures referenced: 0 (present 0 / missing 0)\n"
        b"- Bibliography present: True\n"
    )
    assert first_bytes == expected, (
        f"legacy markdown drifted; got:\n{first_bytes.decode()}"
    )

    # Idempotency: re-running on the same fixture yields the same bytes.
    audit_synthesis(paper_path, workspace_root)
    assert md_path.read_bytes() == first_bytes


# ---------------------------------------------------------------------------
# JSON companion: written + schema-valid.
# ---------------------------------------------------------------------------


def test_json_companion_written_and_schema_valid(workspace_root: Path):
    paper_path = _seed_paper(workspace_root)
    audit_synthesis(paper_path, workspace_root)

    json_path = workspace_root / "workspace" / "synthesis_audit.json"
    assert json_path.is_file(), (
        "Phase-4 JSON companion not written next to legacy markdown."
    )
    arr = json.loads(json_path.read_text())
    assert isinstance(arr, list) and arr, "JSON companion is empty."
    for entry in arr:
        # validate_finding raises ValueError on schema violation.
        validate_finding(entry)
    # The audit_name field is the stable migration identifier.
    assert {e["audit_name"] for e in arr} == {"synthesis"}


# ---------------------------------------------------------------------------
# JSONL roll-up: append-only ledger receives new lines per run.
# ---------------------------------------------------------------------------


def test_jsonl_rollup_appends_per_run(workspace_root: Path):
    paper_path = _seed_paper(workspace_root)
    jsonl_path = (
        workspace_root / "workspace" / "logs" / ".audit_findings.jsonl"
    )

    # Run once — capture line count.
    audit_synthesis(paper_path, workspace_root)
    assert jsonl_path.is_file(), "jsonl roll-up was not created."
    lines_after_first = [
        ln for ln in jsonl_path.read_text().splitlines() if ln.strip()
    ]
    n_first = len(lines_after_first)
    assert n_first >= 1, "no findings recorded on first run."

    # Each line must independently validate against the schema.
    for line in lines_after_first:
        validate_finding(json.loads(line))

    # Run again — ledger MUST grow (append-only). With deterministic ids
    # the new lines have the same ids as the first run, but the ledger
    # appends every time so reviewers can see the history.
    audit_synthesis(paper_path, workspace_root)
    lines_after_second = [
        ln for ln in jsonl_path.read_text().splitlines() if ln.strip()
    ]
    assert len(lines_after_second) == 2 * n_first, (
        f"jsonl ledger did not append — expected {2 * n_first} lines, "
        f"got {len(lines_after_second)}"
    )
    # The original n_first lines are still the first n_first lines.
    assert lines_after_second[:n_first] == lines_after_first


# ---------------------------------------------------------------------------
# SynthesisAudit class direct: returns findings + caches result dict.
# ---------------------------------------------------------------------------


def test_synthesis_audit_class_returns_findings(workspace_root: Path):
    paper_path = _seed_paper(workspace_root)
    audit = SynthesisAudit()
    findings = audit.run(workspace_root, paper_path=paper_path)

    assert isinstance(findings, list) and findings
    assert all(isinstance(f, AuditFinding) for f in findings)
    assert audit.last_result is not None
    assert audit.last_result["status"] in {"success", "warning"}
    # Heartbeat info finding is always present.
    assert any(f.severity == "info" for f in findings)


def test_findings_helper_emits_block_per_gate_blocker():
    """Pure-function helper: every entry in ``result['blockers']`` maps
    to exactly one block-severity finding."""
    fake_result = {
        "status": "error",
        "report": {
            "missing_sections": [],
            "causal_language_hits": [],
            "figures_missing": [],
            "has_bibliography": True,
            "quality_gates": {
                "figure_coverage_ratio": 1.0,
                "figure_coverage_target": 0.8,
                "total_words": 1234,
            },
            "citation_count": 5,
            "citation_density_per_1000_words": 4.05,
            "figures_referenced": 2,
        },
        "report_path": "workspace/logs/synthesis_audit.md",
        "blockers": [
            "Paper is 1234 words — minimum publishable bar is 1500.",
            "DEFAULT-DENY: synthesis blocked because zero PDFs are present.",
        ],
        "message": "two blockers",
    }
    findings = findings_from_synthesis_result(fake_result, "synthesis/paper.md")
    blocks = [f for f in findings if f.severity == "block"]
    assert len(blocks) == 2
    # The DEFAULT-DENY blocker carries the override metadata.
    deny = next(f for f in blocks if "DEFAULT-DENY" in f.suggested_fix)
    assert deny.override_kwarg == "override_no_pdfs"
    assert deny.override_log_format is not None
    # The non-deny blocker does not.
    non_deny = next(f for f in blocks if "DEFAULT-DENY" not in f.suggested_fix)
    assert non_deny.override_kwarg is None


def test_findings_deterministic_ids_across_runs(workspace_root: Path):
    """The uuid5-derived ids must be stable across re-runs against the
    same workspace + paper; this is what lets the .audit_findings.jsonl
    ledger be diffed cleanly without churn."""
    paper_path = _seed_paper(workspace_root)
    a = SynthesisAudit().run(workspace_root, paper_path=paper_path)
    b = SynthesisAudit().run(workspace_root, paper_path=paper_path)
    assert [f.id for f in a] == [f.id for f in b]
