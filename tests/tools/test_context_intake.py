"""Tests for tool_context_intake — mid-flow file injection."""

from research_os.project_ops import scaffold_minimal_workspace
from research_os.tools.actions.data.context_intake import context_intake


def test_intake_routes_pdf_to_literature(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Test", ide_flags=[], copy_agents=False)
    # Drop a PDF outside inputs/
    dropbox = tmp_path / "dropbox"
    dropbox.mkdir()
    (dropbox / "new_paper.pdf").write_text("%PDF-1.4 …")
    res = context_intake(tmp_path)
    assert res["status"] == "success"
    assert res["new_files_count"] == 1
    assert (tmp_path / "inputs" / "literature" / "new_paper.pdf").exists()


def test_intake_routes_csv_to_raw_data(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Test", ide_flags=[], copy_agents=False)
    dropbox = tmp_path / "incoming"
    dropbox.mkdir()
    (dropbox / "fresh.csv").write_text("a,b\n1,2\n")
    res = context_intake(tmp_path)
    assert res["status"] == "success"
    assert (tmp_path / "inputs" / "raw_data" / "fresh.csv").exists()


def test_intake_routes_md_to_context(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Test", ide_flags=[], copy_agents=False)
    (tmp_path / "stray_note.md").write_text("# Hi")
    res = context_intake(tmp_path)
    assert res["status"] == "success"
    assert (tmp_path / "inputs" / "context" / "stray_note.md").exists()


def test_intake_never_overwrites(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Test", ide_flags=[], copy_agents=False)
    # inputs/literature/ is a LAZY dir — created at first write.
    (tmp_path / "inputs" / "literature").mkdir(parents=True, exist_ok=True)
    (tmp_path / "inputs" / "literature" / "paper.pdf").write_text("existing")
    (tmp_path / "extra" / "paper.pdf").parent.mkdir()
    (tmp_path / "extra" / "paper.pdf").write_text("new content")
    res = context_intake(tmp_path)
    assert res["status"] == "success"
    # Original preserved
    assert (tmp_path / "inputs" / "literature" / "paper.pdf").read_text() == "existing"
    # Renamed with _imported_N
    renamed = list((tmp_path / "inputs" / "literature").glob("paper_imported_*.pdf"))
    assert len(renamed) == 1


def test_intake_dry_run_does_not_copy(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Test", ide_flags=[], copy_agents=False)
    (tmp_path / "incoming").mkdir()
    (tmp_path / "incoming" / "f.csv").write_text("a,b\n")
    res = context_intake(tmp_path, dry_run=True)
    assert res["status"] == "success"
    assert res["new_files_count"] == 1
    assert not (tmp_path / "inputs" / "raw_data" / "f.csv").exists()


def test_intake_unchanged_file_skipped_on_rerun(tmp_path):
    """An unchanged drop-file already imported is NOT re-detected on re-run."""
    scaffold_minimal_workspace(tmp_path, "Test", ide_flags=[], copy_agents=False)
    (tmp_path / "drop").mkdir()
    (tmp_path / "drop" / "paper.pdf").write_text("%PDF v1")
    first = context_intake(tmp_path)
    assert first["new_files_count"] == 1
    # Re-run with no change — must report zero new files.
    second = context_intake(tmp_path)
    assert second["new_files_count"] == 0


def test_intake_changed_file_reimported_on_rerun(tmp_path):
    """C9: a replaced/edited drop-file (same basename, new content) must be
    re-detected on re-run via mtime/size change, not silently skipped. The
    original import is preserved (never overwrite); the new content lands as
    paper_imported_N.pdf."""
    import os
    import time

    scaffold_minimal_workspace(tmp_path, "Test", ide_flags=[], copy_agents=False)
    drop = tmp_path / "drop"
    drop.mkdir()
    src = drop / "paper.pdf"
    src.write_text("%PDF v1")
    first = context_intake(tmp_path)
    assert first["new_files_count"] == 1
    lit = tmp_path / "inputs" / "literature"
    assert (lit / "paper.pdf").read_text() == "%PDF v1"

    # Overwrite the drop file with corrected v2 content + bump mtime so the
    # change is unambiguous regardless of filesystem mtime granularity.
    src.write_text("%PDF v2 corrected — longer content here")
    future = time.time() + 10
    os.utime(src, (future, future))

    second = context_intake(tmp_path)
    assert second["new_files_count"] == 1
    # Original preserved, corrected content imported under a new name.
    assert (lit / "paper.pdf").read_text() == "%PDF v1"
    renamed = list(lit.glob("paper_imported_*.pdf"))
    assert len(renamed) == 1
    assert "v2 corrected" in renamed[0].read_text()
