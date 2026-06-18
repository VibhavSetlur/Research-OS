"""3.2 project-root literature corpus aggregation.

Every paper used anywhere — inputs/literature, a step's literature/, or a
step's context/ — is mirrored into the project corpus of record at
literature/ during step finalization, and flows into citations.md.
"""
from __future__ import annotations

from pathlib import Path

from research_os.project_ops import (
    create_numbered_experiment,
    generate_citations_md,
    scaffold_minimal_workspace,
)
from research_os.tools.actions.state.path import finalize_path

_PDF = b"%PDF-1.4\n%fake\n"


def _seed(tmp_path: Path) -> str:
    scaffold_minimal_workspace(tmp_path, "Test", ide_flags=[], copy_agents=False)
    res = create_numbered_experiment(
        tmp_path, "eda", enforce_predecessor_finalized=False,
    )
    return res["path_id"]


def test_root_literature_corpus_scaffolded(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Test", ide_flags=[], copy_agents=False)
    assert (tmp_path / "literature" / "README.md").exists()


def test_step_literature_and_context_mirrored_to_corpus(tmp_path):
    step_id = _seed(tmp_path)
    step = tmp_path / "workspace" / step_id
    # A paper in the step's literature/ + one dropped into context/.
    (step / "literature").mkdir(parents=True, exist_ok=True)
    (step / "literature" / "smith2020_method.pdf").write_bytes(_PDF)
    (step / "literature" / "smith2020_method.pdf.meta.yaml").write_text(
        "citation_key: smith2020\ntitle: A Method\nyear: 2020\n"
    )
    (step / "context").mkdir(parents=True, exist_ok=True)
    (step / "context" / "jones2019_review.pdf").write_bytes(_PDF)
    (step / "context" / "jones2019_review.pdf.meta.yaml").write_text(
        "citation_key: jones2019\ntitle: A Review\nyear: 2019\n"
    )
    (step / "conclusions.md").write_text(
        "## Findings\n\n- ok.\n\n## Decision\n\nPROCEED.\n"
    )
    finalize_path(step_id, tmp_path)

    corpus = tmp_path / "literature" / "steps" / step_id
    assert (corpus / "smith2020_method.pdf").exists()
    assert (corpus / "jones2019_review.pdf").exists()  # context paper too

    # Both flow into the bibliography.
    generate_citations_md(tmp_path)
    cites = (tmp_path / "workspace" / "citations.md").read_text()
    assert "smith2020" in cites
    assert "jones2019" in cites


def test_inputs_literature_mirrored_to_corpus(tmp_path):
    step_id = _seed(tmp_path)
    (tmp_path / "inputs" / "literature" / "proj2021.pdf").write_bytes(_PDF)
    (tmp_path / "inputs" / "literature" / "proj2021.pdf.meta.yaml").write_text(
        "citation_key: proj2021\ntitle: Project Paper\n"
    )
    step = tmp_path / "workspace" / step_id
    (step / "conclusions.md").write_text(
        "## Findings\n\n- ok.\n\n## Decision\n\nPROCEED.\n"
    )
    finalize_path(step_id, tmp_path)
    assert (tmp_path / "literature" / "inputs" / "proj2021.pdf").exists()
