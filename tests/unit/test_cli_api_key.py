"""W19 — `research-os api-key {add,list,rotate,remove,test}` subcommand.

Stores secrets in ``inputs/researcher_config.yaml`` under ``api_keys:``,
re-applying chmod 600 after every write. Uses getpass for interactive
input so secrets never echo. ``--from-env`` is the CI-friendly path.

Tests exercise the underlying config helpers (add/list/rotate/remove)
directly. ``test_api_key`` is exercised against a mocked urllib so we
don't hit the real network.
"""

from __future__ import annotations

import os
from unittest import mock

import pytest
import yaml

from research_os.tools.actions.state.config import (
    _config_path,
    add_api_key,
    init_config,
    list_api_keys,
    remove_api_key,
    check_api_key,
)


pytestmark = pytest.mark.skipif(
    os.name == "nt",
    reason="chmod / mode-bit checks are POSIX-only.",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fresh_ws(tmp_path):
    """A workspace with a freshly-initialised researcher_config.yaml."""
    (tmp_path / ".os_state").mkdir()
    init_config(tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# add_api_key
# ---------------------------------------------------------------------------


class TestAddApiKey:
    def test_add_writes_value_and_chmod_600(self, fresh_ws):
        res = add_api_key(fresh_ws, "semantic_scholar", "abc123XYZ")
        assert res["status"] == "success"
        assert res["rotated"] is False
        cfg_path = _config_path(fresh_ws)
        cfg = yaml.safe_load(cfg_path.read_text()) or {}
        assert cfg["api_keys"]["semantic_scholar"] == "abc123XYZ"
        # chmod 600 is re-applied after every write — even if some other
        # process loosened the perms in the meantime.
        mode = cfg_path.stat().st_mode & 0o777
        assert mode == 0o600, f"expected 0o600, got {oct(mode)}"

    def test_re_add_reports_rotated(self, fresh_ws):
        add_api_key(fresh_ws, "pubmed", "first-value")
        res = add_api_key(fresh_ws, "pubmed", "second-value")
        assert res["rotated"] is True
        cfg = yaml.safe_load(_config_path(fresh_ws).read_text()) or {}
        assert cfg["api_keys"]["pubmed"] == "second-value"

    def test_empty_value_rejected(self, fresh_ws):
        res = add_api_key(fresh_ws, "pubmed", "")
        assert res["status"] == "error"

    def test_creates_config_if_missing(self, tmp_path):
        # No init_config first — add_api_key should auto-init.
        (tmp_path / ".os_state").mkdir()
        res = add_api_key(tmp_path, "crossref", "key")
        assert res["status"] == "success"
        assert _config_path(tmp_path).exists()


# ---------------------------------------------------------------------------
# remove_api_key
# ---------------------------------------------------------------------------


class TestRemoveApiKey:
    def test_remove_clears_value(self, fresh_ws):
        add_api_key(fresh_ws, "pubmed", "some-secret")
        res = remove_api_key(fresh_ws, "pubmed")
        assert res["status"] == "success"
        cfg = yaml.safe_load(_config_path(fresh_ws).read_text()) or {}
        assert cfg["api_keys"]["pubmed"] == ""
        # chmod must still be 600 after the rewrite.
        mode = _config_path(fresh_ws).stat().st_mode & 0o777
        assert mode == 0o600

    def test_remove_missing_is_noop(self, fresh_ws):
        res = remove_api_key(fresh_ws, "never-set")
        assert res["status"] == "noop"


# ---------------------------------------------------------------------------
# list_api_keys — uses _mask_api_keys helper
# ---------------------------------------------------------------------------


class TestListApiKeys:
    def test_list_returns_masked_values(self, fresh_ws):
        add_api_key(fresh_ws, "pubmed", "abcdefghijklmnop")
        res = list_api_keys(fresh_ws)
        assert res["status"] == "success"
        masked = res["api_keys"]["pubmed"]
        # Full secret must NOT appear; only first 4 / last 4 chars.
        assert "abcdefghijklmnop" not in masked
        assert masked.startswith("abcd")
        assert masked.endswith("mnop")

    def test_list_short_value_uses_stars(self, fresh_ws):
        add_api_key(fresh_ws, "pubmed", "short")
        res = list_api_keys(fresh_ws)
        assert res["api_keys"]["pubmed"] == "***"


# ---------------------------------------------------------------------------
# test_api_key — mocked urllib, never hits the real network
# ---------------------------------------------------------------------------


class _FakeResp:
    def __init__(self, code: int) -> None:
        self._code = code

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def getcode(self):
        return self._code


class TestCheckApiKey:
    def test_pubmed_ok_reports_ok(self, fresh_ws):
        with mock.patch("urllib.request.urlopen", return_value=_FakeResp(200)):
            res = check_api_key(fresh_ws, "pubmed")
        assert res["status"] == "ok"
        assert res["provider"] == "pubmed"

    def test_pubmed_network_error_reports_fail(self, fresh_ws):
        with mock.patch("urllib.request.urlopen", side_effect=OSError("ECONNREFUSED")):
            res = check_api_key(fresh_ws, "pubmed")
        assert res["status"] == "fail"
        assert "ECONNREFUSED" in res["detail"]

    def test_unknown_provider_reports_fail(self, fresh_ws):
        res = check_api_key(fresh_ws, "imaginary_service")
        assert res["status"] == "fail"
        assert "no test endpoint" in res["detail"]

    def test_semantic_scholar_uses_key_in_header(self, fresh_ws):
        add_api_key(fresh_ws, "semantic_scholar", "MYKEY")
        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["headers"] = dict(req.header_items())
            return _FakeResp(200)

        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            res = check_api_key(fresh_ws, "semantic_scholar")
        assert res["status"] == "ok"
        # Header names get normalised by urllib (X-api-key); accept either.
        header_vals = list(captured["headers"].values())
        assert "MYKEY" in header_vals


# ---------------------------------------------------------------------------
# CLI parser smoke test
# ---------------------------------------------------------------------------


class TestApiKeyCliParserShape:
    def test_add_parses(self):
        from research_os.cli import build_parser
        args = build_parser().parse_args(["api-key", "add", "pubmed"])
        assert args.command == "api-key"
        assert args.action == "add"
        assert args.provider == "pubmed"
        assert args.from_env is None

    def test_add_from_env_parses(self):
        from research_os.cli import build_parser
        args = build_parser().parse_args(
            ["api-key", "add", "openai", "--from-env", "OPENAI_API_KEY"]
        )
        assert args.from_env == "OPENAI_API_KEY"

    def test_test_parses(self):
        from research_os.cli import build_parser
        args = build_parser().parse_args(["api-key", "test", "pubmed"])
        assert args.action == "test"
        assert args.provider == "pubmed"

    def test_list_parses(self):
        from research_os.cli import build_parser
        args = build_parser().parse_args(["api-key", "list"])
        assert args.action == "list"
        assert args.provider is None
