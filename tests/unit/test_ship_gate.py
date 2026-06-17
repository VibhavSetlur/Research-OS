"""Ship gate — the one server-enforced refusal of 'done'.

Covers: clear pass on a clean fixture, hard block on a stub /
ungrounded / invalid-PDF fixture, and the researcher override path.
"""

from pathlib import Path

from research_os.tools.actions.audit.ship_gate import finalize_project


# ── fixtures ─────────────────────────────────────────────────────────


def _clean_project(tmp_path: Path) -> Path:
    """A project whose deliverable is fully grounded with no stubs."""
    ws = tmp_path / "workspace"
    step = ws / "01_eda"
    (step / "outputs" / "reports").mkdir(parents=True)
    (step / "outputs" / "reports" / "stats.md").write_text(
        "mean accuracy = 0.84\nn = 100\n"
    )
    syn = tmp_path / "synthesis"
    syn.mkdir(parents=True)
    # Every number here appears in the workspace corpus above.
    (syn / "paper.typ").write_text(
        "= Results\n\nWe report accuracy 0.84 across 100 samples.\n"
    )
    (ws / "logs").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _stub_project(tmp_path: Path) -> Path:
    """A project with a stub section + an ungrounded number + a fake PDF."""
    ws = tmp_path / "workspace"
    step = ws / "01_eda"
    (step / "outputs" / "reports").mkdir(parents=True)
    (step / "outputs" / "reports" / "stats.md").write_text("mean = 0.50\n")
    # Fake PDF: named *.pdf but actually HTML.
    (step / "literature").mkdir(parents=True)
    (step / "literature" / "paywall.pdf").write_bytes(b"<html>403</html>")
    syn = tmp_path / "synthesis"
    syn.mkdir(parents=True)
    (syn / "paper.typ").write_text(
        "= Results\n\n"
        "We found AUROC = 0.9876 (TODO: confirm this number).\n"
    )
    (ws / "logs").mkdir(parents=True, exist_ok=True)
    return tmp_path


# ── clear path ───────────────────────────────────────────────────────


def test_ship_gate_clear_on_clean_fixture(tmp_path: Path):
    root = _clean_project(tmp_path)
    res = finalize_project(root, operation="finalize")
    assert res["status"] == "clear", res
    assert res["n_blockers"] == 0


def test_ship_gate_writes_report(tmp_path: Path):
    root = _clean_project(tmp_path)
    res = finalize_project(root, operation="check")
    assert (tmp_path / res["report_path"]).exists()


# ── block path ───────────────────────────────────────────────────────


def test_ship_gate_blocks_on_stub_fixture(tmp_path: Path):
    root = _stub_project(tmp_path)
    res = finalize_project(root, operation="finalize")
    assert res["status"] == "blocked", res
    assert res["n_blockers"] > 0
    cats = res["by_category"]
    # All three blocker categories should fire on this fixture.
    assert cats.get("stub_section", 0) >= 1
    assert cats.get("ungrounded_claim", 0) >= 1
    assert cats.get("invalid_pdf", 0) >= 1


def test_ship_gate_check_mode_is_advisory(tmp_path: Path):
    root = _stub_project(tmp_path)
    res = finalize_project(root, operation="check")
    # check mode reports 'blocked' but flags itself advisory (no refusal).
    assert res["status"] == "blocked"
    assert res.get("advisory") is True


# ── override path ────────────────────────────────────────────────────


def test_ship_gate_override_requires_rationale(tmp_path: Path):
    root = _stub_project(tmp_path)
    res = finalize_project(root, operation="finalize", override=True)
    assert res["status"] == "error"


def test_ship_gate_override_rejects_thin_rationale(tmp_path: Path):
    root = _stub_project(tmp_path)
    res = finalize_project(
        root, operation="finalize", override=True, override_rationale="ok",
    )
    assert res["status"] == "error"


def test_ship_gate_override_clears_with_substantive_rationale(tmp_path: Path):
    root = _stub_project(tmp_path)
    res = finalize_project(
        root,
        operation="finalize",
        override=True,
        override_rationale=(
            "PI preview at 3pm; paper draft is intentionally incomplete "
            "but figures are final and the PI knows."
        ),
    )
    assert res["status"] == "overridden", res
    # The override must be logged.
    log = tmp_path / "workspace" / "logs" / "override_log.md"
    assert log.exists()


# ── handler: blocked → hard error envelope ───────────────────────────


def test_handler_blocks_done_with_error_envelope(tmp_path: Path):
    from research_os.server.handlers.audit_gates import (
        _handle_tool_finalize_project,
    )

    root = _stub_project(tmp_path)
    out = _handle_tool_finalize_project(
        "tool_finalize_project", {"operation": "finalize"}, root,
    )
    # The dispatcher returns a TextContent list; the payload is JSON.
    import json
    payload = json.loads(out[0].text)
    assert payload["status"] == "error"
    assert "ship_gate_blocked" in (payload.get("error") or "") or \
        "ship_gate_blocked" in json.dumps(payload)


def test_handler_clear_returns_success(tmp_path: Path):
    from research_os.server.handlers.audit_gates import (
        _handle_tool_finalize_project,
    )

    root = _clean_project(tmp_path)
    out = _handle_tool_finalize_project(
        "tool_finalize_project", {"operation": "finalize"}, root,
    )
    import json
    payload = json.loads(out[0].text)
    assert payload["status"] == "success"
