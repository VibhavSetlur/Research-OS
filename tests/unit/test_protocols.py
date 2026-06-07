"""Protocol loader, listing, and validation tests."""

from pathlib import Path

import pytest
import yaml

from research_os.tools.actions.protocol import (
    list_protocols,
    load_protocol,
    validate_protocol,
)


SAMPLE_PROTOCOL = {
    "id": "test_protocol",
    "name": "Test Protocol",
    "version": "4.0.0",
    "schema_version": "2.0",
    "description": "A test protocol",
    "steps": [
        {"id": "step_one", "name": "Step One", "description": "First step"},
    ],
}


@pytest.fixture
def protocol_dir(tmp_path, monkeypatch):
    """Point the loader at a temp protocols/ directory."""
    import research_os.tools.actions.protocol as proto

    p = tmp_path / "src" / "research_os" / "protocols"
    p.mkdir(parents=True)
    monkeypatch.setattr(proto, "PROTOCOLS_DIR", p)
    return p


@pytest.fixture
def full_protocol_dir(protocol_dir):
    """Create three categorised protocols under the temp dir."""
    cat = protocol_dir / "guidance"
    cat.mkdir(exist_ok=True)
    for name in ("alpha", "beta", "gamma"):
        data = {
            "id": name,
            "name": name.title(),
            "version": "4.0.0",
            "schema_version": "2.0",
            "description": f"Protocol for {name}",
            "steps": [
                {"id": f"{name}_step1", "name": "Step 1", "description": "First step"},
                {"id": f"{name}_step2", "name": "Step 2", "description": "Second step"},
            ],
            "next_protocol": None,
        }
        (cat / f"{name}.yaml").write_text(yaml.dump(data))
    return protocol_dir


class TestProtocolLoading:
    def test_load_valid_protocol(self, protocol_dir):
        (protocol_dir / "test.yaml").write_text(yaml.dump(SAMPLE_PROTOCOL))
        loaded = load_protocol("test")
        assert loaded["id"] == "test_protocol"
        # Loader auto-injects a completion step.
        assert any(step.get("id") == "protocol_completion" for step in loaded["steps"])

    def test_load_nonexistent_protocol_raises(self):
        from research_os.server.errors import RoError
        with pytest.raises((RoError, FileNotFoundError)):
            load_protocol("nonexistent_xyz")

    def test_load_with_subdir(self, full_protocol_dir):
        loaded = load_protocol("guidance/alpha")
        assert loaded["id"] == "alpha"

    def test_load_summary_returns_lean_shape(self, full_protocol_dir):
        summary = load_protocol("guidance/alpha", format="summary")
        # summary should NOT include 'content' or full step bodies.
        assert "step_summary" in summary
        assert all("name" in s for s in summary["step_summary"])
        # Step bodies are NOT included in summary mode.
        for s in summary["step_summary"]:
            assert "description" not in s
        assert "_load_hint" in summary

    def test_load_step_returns_one_step_body(self, full_protocol_dir):
        step = load_protocol(
            "guidance/alpha", format="step", step_id="alpha_step1"
        )
        assert step["step"]["id"] == "alpha_step1"
        assert "description" in step["step"]
        assert step["position"] == 1
        assert step["of"] >= 2

    def test_load_step_missing_id_raises(self, full_protocol_dir):
        with pytest.raises(ValueError):
            load_protocol("guidance/alpha", format="step", step_id="ghost")

    def test_load_step_without_step_id_raises(self, full_protocol_dir):
        with pytest.raises(ValueError):
            load_protocol("guidance/alpha", format="step")


class TestProtocolList:
    def test_list_all_protocols(self, full_protocol_dir):
        # `list_protocols()` now also walks pack-registered dirs (v1.11.1).
        # Restrict to core entries for this fixture's strict-equality check.
        names = {
            p["name"] for p in list_protocols() if p.get("pack_or_core") == "core"
        }
        assert names == {"guidance/alpha", "guidance/beta", "guidance/gamma"}

    def test_list_protocols_have_required_metadata(self, full_protocol_dir):
        for p in list_protocols():
            assert "name" in p
            assert "summary" in p
            assert "pack_or_core" in p


class TestProtocolFields:
    REQUIRED_FIELDS = {"id", "name", "version", "description", "steps"}

    def test_each_protocol_has_required_fields(self, full_protocol_dir):
        # Skip pack-contributed entries; their files live outside the fixture.
        for entry in list_protocols():
            if entry.get("pack_or_core") != "core":
                continue
            loaded = yaml.safe_load(
                (full_protocol_dir / f"{entry['name']}.yaml").read_text()
            )
            for field in self.REQUIRED_FIELDS:
                assert field in loaded, f"{entry['name']} missing {field}"

    def test_summary_non_empty(self, full_protocol_dir):
        for entry in list_protocols():
            if entry.get("pack_or_core") != "core":
                continue
            assert entry["summary"], f"{entry['name']} has empty summary"


class TestProtocolValidation:
    def test_validate_with_expected_outputs(self, protocol_dir):
        data = dict(SAMPLE_PROTOCOL)
        data["expected_outputs"] = [
            "workspace/results.txt",
            "workspace/log.txt",
        ]
        (protocol_dir / "check.yaml").write_text(yaml.dump(data))
        root = protocol_dir.parent.parent.parent
        (root / "workspace").mkdir(parents=True)
        (root / "workspace" / "results.txt").touch()
        result = validate_protocol("check", root)
        assert result["all_passed"] is False
        statuses = [item["status"] for item in result["checklist"]]
        assert statuses == ["pass", "fail"]

    def test_validate_nonexistent_returns_error(self, protocol_dir):
        result = validate_protocol("ghost", protocol_dir.parent.parent.parent)
        assert "error" in result


class TestRealProtocols:
    def test_every_real_protocol_loads(self):
        root = Path(__file__).resolve().parent.parent.parent
        pdir = root / "src" / "research_os" / "protocols"
        assert pdir.exists()
        for p in sorted(pdir.rglob("*.yaml")):
            if "light" in p.parts:
                continue
            # Registry / index files (e.g. _router_index.yaml) are not
            # protocols and intentionally lack id/steps.
            if p.name.startswith("_"):
                continue
            data = yaml.safe_load(p.read_text())
            assert "id" in data, f"{p} missing id"
            # Redirect stubs are thin aliases; they intentionally do NOT
            # carry steps (the loader follows redirect_to: and the target
            # supplies the steps). Preflight enforces this exclusivity.
            if isinstance(data.get("redirect_to"), str):
                continue
            assert "steps" in data, f"{p} missing steps"

    def test_no_light_folder(self):
        root = Path(__file__).resolve().parent.parent.parent
        light = root / "src" / "research_os" / "protocols" / "light"
        assert not light.exists(), "light/ folder should not exist (merged into single source)"
