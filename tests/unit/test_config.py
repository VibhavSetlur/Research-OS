"""Config-action tests."""

import os
import yaml
import pytest

from research_os.tools.actions.state.config import (
    get_config,
    init_config,
    set_config,
    validate_config,
)


@pytest.fixture
def tmp_root(tmp_path):
    return tmp_path


@pytest.fixture
def initialised_root(tmp_root):
    init_config(tmp_root)
    return tmp_root


class TestInitConfig:
    def test_creates_file(self, tmp_root):
        result = init_config(tmp_root)
        assert result["status"] == "success"
        assert (tmp_root / "inputs" / "researcher_config.yaml").exists()

    def test_defaults_are_sensible(self, tmp_root):
        init_config(tmp_root)
        cfg = yaml.safe_load((tmp_root / "inputs" / "researcher_config.yaml").read_text())
        assert "researcher" in cfg
        assert "interaction" in cfg
        assert "api_keys" in cfg
        assert cfg["model_profile"] == "medium"
        assert cfg["interaction"]["autonomy_level"] == "supervised"

    def test_overrides_apply(self, tmp_root):
        # researcher_config.yaml now only holds the who-and-how (researcher
        # / interaction / model_profile / api_keys). Project content like
        # domain / research_question is persisted to state + intake.md by
        # tool_intake_autofill, not to the config.
        init_config(tmp_root, overrides={
            "project_name": "Cohort 2024",
            "model_profile": "small",
        })
        cfg = yaml.safe_load((tmp_root / "inputs" / "researcher_config.yaml").read_text())
        assert cfg["project_name"] == "Cohort 2024"
        assert cfg["model_profile"] == "small"

    def test_permissions_are_600(self, tmp_root):
        init_config(tmp_root)
        if os.name == "nt":
            return
        mode = os.stat(tmp_root / "inputs" / "researcher_config.yaml").st_mode & 0o777
        assert mode == 0o600


class TestGetConfig:
    def test_returns_config(self, initialised_root):
        res = get_config(initialised_root)
        assert res["status"] == "success"
        assert res["config"]["model_profile"] == "medium"

    def test_masks_api_keys(self, initialised_root):
        set_config("api_keys.firecrawl", "fc-1234567890abcdef", initialised_root)
        res = get_config(initialised_root)
        assert "…" in res["config"]["api_keys"]["firecrawl"]

    def test_missing_config_returns_error(self, tmp_root):
        res = get_config(tmp_root)
        assert res["status"] == "error"


class TestSetConfig:
    def test_set_top_level(self, initialised_root):
        res = set_config("model_profile", "large", initialised_root)
        assert res["status"] == "success"
        assert get_config(initialised_root)["config"]["model_profile"] == "large"

    def test_set_nested(self, initialised_root):
        res = set_config("researcher.name", "Dr. Smith", initialised_root)
        assert res["status"] == "success"
        assert get_config(initialised_root)["config"]["researcher"]["name"] == "Dr. Smith"


class TestValidateConfig:
    def test_returns_structure(self, initialised_root):
        res = validate_config(initialised_root)
        assert res["status"] == "success"
        assert "api_keys_configured" in res
        assert "api_keys_blank" in res

    def test_flags_keys_present(self, initialised_root):
        set_config("api_keys.firecrawl", "fc-valid-key", initialised_root)
        res = validate_config(initialised_root)
        assert "firecrawl" in res["api_keys_configured"]


class TestSetConfigSafety:
    """Regression coverage for set_config: comment-preservation, chmod
    re-lock, and typed-field coercion (CWC-1 / CWC-5 / CWC-7)."""

    def _write_cfg(self, root):
        cfg = root / "inputs" / "researcher_config.yaml"
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text(
            "# A guiding comment that must survive an AI-driven edit\n"
            "project_name: demo  # inline comment\n"
            "research_goal:\n"
            "  output_types: []   # paper | dashboard | report\n"
        )
        return cfg

    def test_preserves_inline_comments(self, tmp_root):
        # CWC-1: round-trip through ruamel — comments are NOT stripped.
        cfg = self._write_cfg(tmp_root)
        res = set_config("researcher.name", "Dr. Smith", tmp_root)
        assert res["status"] == "success"
        txt = cfg.read_text()
        assert "A guiding comment that must survive an AI-driven edit" in txt
        assert "inline comment" in txt

    def test_relocks_to_0600(self, tmp_root):
        # CWC-5: the file may carry API keys, so re-lock after writing.
        cfg = self._write_cfg(tmp_root)
        cfg.chmod(0o644)
        set_config("api_keys.firecrawl", "fc-secret", tmp_root)
        assert oct(os.stat(cfg).st_mode & 0o777) == "0o600"

    def test_coerces_bare_string_to_list(self, tmp_root):
        # CWC-7: output_types is list-valued — a bare string must coerce
        # to a list, not be stored as a string downstream gates iterate
        # character by character.
        self._write_cfg(tmp_root)
        set_config("research_goal.output_types", "paper", tmp_root)
        cfg = get_config(tmp_root)["config"]
        assert cfg["research_goal"]["output_types"] == ["paper"]

    def test_coerces_comma_separated_to_list(self, tmp_root):
        self._write_cfg(tmp_root)
        set_config("research_goal.output_types", "paper, dashboard", tmp_root)
        cfg = get_config(tmp_root)["config"]
        assert cfg["research_goal"]["output_types"] == ["paper", "dashboard"]

    def test_passes_through_actual_list(self, tmp_root):
        self._write_cfg(tmp_root)
        set_config("research_goal.output_types", ["poster"], tmp_root)
        cfg = get_config(tmp_root)["config"]
        assert cfg["research_goal"]["output_types"] == ["poster"]
