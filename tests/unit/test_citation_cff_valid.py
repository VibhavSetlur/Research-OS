"""CITATION.cff validity + project-level emitter tests."""
from __future__ import annotations

from pathlib import Path

from research_os.tools.actions.state.citation import emit_project_citation_cff

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_repo_citation_cff_has_valid_cff_version():
    """Repo-root CITATION.cff must use the published 1.2.0 schema."""
    text = (REPO_ROOT / "CITATION.cff").read_text(encoding="utf-8")
    assert "cff-version: 1.2.0" in text
    # cff-version: 1.0.0 was never a real version of the spec.
    assert "cff-version: 1.0.0" not in text


def test_repo_citation_cff_required_fields():
    text = (REPO_ROOT / "CITATION.cff").read_text(encoding="utf-8")
    for field in ("title:", "authors:", "version:", "date-released:",
                   "type: software", "license: MIT",
                   "repository-code:", "abstract:", "keywords:"):
        assert field in text, f"missing field: {field}"
    # ORCID URI form for the maintainer.
    assert "orcid: \"https://orcid.org/" in text


def test_repo_citation_cff_passes_cffconvert_when_available():
    """If cffconvert is installed, the repo CITATION.cff must validate.

    Optional check: cffconvert is not a runtime dep, but when the dev
    has it, we want a hard signal that the file is publishable.
    """
    try:
        from cffconvert.cli.create_citation import create_citation  # type: ignore
    except Exception:
        return  # cffconvert not installed in this env; skip.
    citation = create_citation(str(REPO_ROOT / "CITATION.cff"), None)
    # Will raise if schema-invalid.
    citation.validate()


def test_emit_project_citation_cff_writes_file(tmp_path: Path):
    out = emit_project_citation_cff(
        tmp_path,
        project_name="my-study",
        researcher={
            "name": "Vibhav Setlur",
            "orcid": "0009-0008-7415-3654",
            "email": "vibhav@example.org",
            "institution": "UT Austin",
        },
    )
    assert out == tmp_path / "CITATION.cff"
    body = out.read_text(encoding="utf-8")
    assert "cff-version: 1.2.0" in body
    assert "title: \"my-study\"" in body
    assert "given-names: \"Vibhav\"" in body
    assert "family-names: \"Setlur\"" in body
    assert "orcid: \"https://orcid.org/0009-0008-7415-3654\"" in body
    assert "affiliation: \"UT Austin\"" in body


def test_emit_project_citation_cff_is_idempotent(tmp_path: Path):
    """Existing file is preserved unless overwrite=True."""
    first = emit_project_citation_cff(tmp_path, project_name="study-a",
                                       researcher={"name": "Anne Author"})
    first_body = first.read_text(encoding="utf-8")
    second = emit_project_citation_cff(tmp_path, project_name="study-b",
                                        researcher={"name": "Bea Better"})
    assert second.read_text(encoding="utf-8") == first_body
    # overwrite=True replaces it.
    third = emit_project_citation_cff(tmp_path, project_name="study-c",
                                       researcher={"name": "Cee Champ"},
                                       overwrite=True)
    assert "study-c" in third.read_text(encoding="utf-8")


def test_emit_handles_missing_researcher(tmp_path: Path):
    out = emit_project_citation_cff(tmp_path, project_name="empty")
    body = out.read_text(encoding="utf-8")
    assert "given-names: \"Anonymous\"" in body
    assert "family-names: \"Researcher\"" in body
