"""sys_export_ro_crate — RO-Crate 1.1 + CodeMeta 2.0 emitter tests."""
from __future__ import annotations

import json
from pathlib import Path

from research_os.tools.actions.state.ro_crate import (
    build_codemeta,
    build_ro_crate,
    sys_export_ro_crate,
)


def _seed_project(root: Path, with_orcid: bool = True) -> None:
    """Lay down the minimal researcher_config + intake + outputs."""
    (root / "inputs").mkdir(parents=True, exist_ok=True)
    (root / "synthesis").mkdir(parents=True, exist_ok=True)
    (root / "workspace" / "01_step" / "outputs").mkdir(parents=True,
                                                        exist_ok=True)
    (root / "environment").mkdir(parents=True, exist_ok=True)

    orcid_line = '  orcid: "0009-0008-7415-3654"\n' if with_orcid else ""
    (root / "inputs" / "researcher_config.yaml").write_text(
        "researcher:\n"
        '  name: "Vibhav Setlur"\n'
        '  email: "vibhav@example.org"\n'
        '  institution: "UT Austin"\n'
        f"{orcid_line}"
        "licenses:\n"
        '  data: "CC-BY-4.0"\n'
        '  code: "MIT"\n'
        f'project_name: "demo-project"\n',
        encoding="utf-8",
    )
    (root / "inputs" / "intake.md").write_text(
        "# Research Intake\n\nA tiny demo project for testing.\n",
        encoding="utf-8",
    )
    (root / "synthesis" / "paper.md").write_text("# Paper\n", encoding="utf-8")
    (root / "workspace" / "01_step" / "outputs" / "fig.png").write_bytes(
        b"\x89PNG\r\n"
    )
    (root / "workspace" / "01_step" / "outputs" / "fig.prov.json").write_text(
        json.dumps({"step_id": "01_step", "tool": "test"}), encoding="utf-8"
    )
    (root / "environment" / "requirements.txt").write_text(
        "numpy==1.26.0\npandas==2.1.0\n", encoding="utf-8"
    )


def test_build_ro_crate_emits_jsonld_manifest(tmp_path: Path):
    _seed_project(tmp_path)
    manifest = build_ro_crate(tmp_path)

    out = tmp_path / "ro-crate-metadata.json"
    assert out.exists()
    assert manifest["@context"] == "https://w3id.org/ro/crate/1.1/context"
    graph = manifest["@graph"]

    # Descriptor entity at head, root Dataset present.
    descriptor = graph[0]
    assert descriptor["@id"] == "ro-crate-metadata.json"
    assert descriptor["conformsTo"]["@id"] == "https://w3id.org/ro/crate/1.1"

    root_entity = next(e for e in graph if e.get("@id") == "./")
    assert root_entity["@type"] == "Dataset"
    assert root_entity["name"] == "demo-project"
    assert "hasPart" in root_entity
    assert any(p["@id"].endswith("fig.prov.json")
               for p in root_entity["hasPart"])

    # Author Person entity carries the ORCID URI form.
    author = next(e for e in graph if e.get("@type") == "Person")
    assert author["@id"].startswith("https://orcid.org/")
    assert author["name"] == "Vibhav Setlur"


def test_build_ro_crate_valid_json(tmp_path: Path):
    """The emitted file is parseable JSON-LD on disk."""
    _seed_project(tmp_path)
    build_ro_crate(tmp_path)
    payload = json.loads(
        (tmp_path / "ro-crate-metadata.json").read_text(encoding="utf-8")
    )
    assert payload["@context"].endswith("/ro/crate/1.1/context")
    assert isinstance(payload["@graph"], list)


def test_build_codemeta_emits_v2_manifest(tmp_path: Path):
    _seed_project(tmp_path)
    cm = build_codemeta(tmp_path)
    assert (tmp_path / "codemeta.json").exists()
    assert cm["@context"] == "https://doi.org/10.5063/schema/codemeta-2.0"
    assert cm["@type"] == "SoftwareSourceCode"
    assert cm["name"] == "demo-project"
    # Author block carries ORCID + affiliation pulled from researcher_config.
    author = cm["author"][0]
    assert author["@id"] == "https://orcid.org/0009-0008-7415-3654"
    assert author["affiliation"]["name"] == "UT Austin"
    # Software requirements come from environment/requirements.txt.
    assert "numpy==1.26.0" in cm["softwareRequirements"]


def test_sys_export_ro_crate_preview_does_not_write(tmp_path: Path):
    _seed_project(tmp_path)
    res = sys_export_ro_crate(tmp_path, operation="preview")
    assert res["status"] == "success"
    assert res["operation"] == "preview"
    assert not (tmp_path / "ro-crate-metadata.json").exists()
    assert res["has_part_count"] >= 2  # fig.png + fig.prov.json + paper.md


def test_sys_export_ro_crate_unknown_op(tmp_path: Path):
    res = sys_export_ro_crate(tmp_path, operation="explode")
    assert res["status"] == "error"
    assert "unknown operation" in res["message"]
