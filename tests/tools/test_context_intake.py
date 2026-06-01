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
