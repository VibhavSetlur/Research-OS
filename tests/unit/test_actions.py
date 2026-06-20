"""Tests for top-level tool actions (web, env, checkpoint, literature)."""

from unittest.mock import MagicMock, patch

from research_os.tools.actions.search.literature import download_literature
from research_os.tools.actions.search.search import scrape_web, search_web
from research_os.tools.actions.state.checkpoint import (
    create_checkpoint,
    list_checkpoints,
    rollback_checkpoint,
)
from research_os.tools.actions.exec.environment import env_snapshot, package_install


# ── package_install ────────────────────────────────────────────────────


class TestPackageInstall:
    @patch("research_os.tools.actions.exec.environment.subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="installed", stderr="")
        res = package_install(["requests"])
        assert res["code"] == 0
        assert res["status"] == "success"

    @patch("research_os.tools.actions.exec.environment.subprocess.run")
    def test_error(self, mock_run):
        mock_run.side_effect = Exception("pip not found")
        res = package_install(["nonexistent"])
        assert res["status"] == "error"


# ── env_snapshot ───────────────────────────────────────────────────────


class TestEnvSnapshot:
    @patch("research_os.tools.actions.exec.environment.subprocess.run")
    def test_creates_requirements_and_session(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=0, stdout="requests==2.31.0\n", stderr="")
        res = env_snapshot(tmp_path)
        assert res["status"] == "success"
        env_dir = tmp_path / "environment"
        assert (env_dir / "requirements.txt").exists()
        assert (env_dir / "session.yaml").exists()


# ── web search ─────────────────────────────────────────────────────────


class TestSearchWeb:
    def test_no_provider_returns_warning(self, monkeypatch):
        monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
        monkeypatch.delenv("SERPAPI_API_KEY", raising=False)
        res = search_web("q")
        assert res["count"] == 0
        assert "warning" in res

    @patch("urllib.request.urlopen")
    def test_serpapi_fallback(self, mock_urlopen, monkeypatch):
        import json as _json
        monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
        monkeypatch.setenv("SERPAPI_API_KEY", "sk_test")
        body = _json.dumps(
            {"organic_results": [{"title": "T", "link": "http://x.com", "snippet": "D"}]}
        ).encode()
        mock_urlopen.return_value.__enter__.return_value.read.return_value = body
        res = search_web("q", limit=1)
        assert res["source"] == "serpapi"
        assert res["count"] == 1


class TestScrapeWeb:
    def test_no_scraper_returns_warning(self, monkeypatch):
        monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
        res = scrape_web("http://example.com")
        assert "content" in res


# ── Checkpoints ────────────────────────────────────────────────────────


class TestCheckpoints:
    def test_create_returns_id(self, tmp_path):
        (tmp_path / "workspace").mkdir()
        (tmp_path / "workspace" / "note.md").write_text("hello")
        res = create_checkpoint("first", tmp_path)
        assert res["status"] == "success"
        assert res["checkpoint_id"].startswith("ckpt_")

    def test_list_after_create(self, tmp_path):
        (tmp_path / "workspace").mkdir()
        (tmp_path / "workspace" / "note.md").write_text("hello")
        create_checkpoint("first", tmp_path)
        res = list_checkpoints(tmp_path)
        assert res["status"] == "success"
        assert len(res["checkpoints"]) >= 1

    def test_rollback_unknown(self, tmp_path):
        res = rollback_checkpoint("does-not-exist", tmp_path)
        assert res["status"] == "error"


# ── Literature download ───────────────────────────────────────────────


class TestDownloadLiterature:
    @patch("research_os.tools.actions.search.literature._check_unpaywall")
    @patch("research_os.tools.actions.search.literature.urllib.request.urlopen")
    def test_success(self, mock_urlopen, mock_unpaywall, tmp_path):
        mock_unpaywall.return_value = {"is_oa": True, "reason": "OA"}

        # The download now streams via urlopen(..., timeout=...) (C3) instead
        # of urlretrieve, validating the %PDF- magic header. The fake response
        # yields a genuine PDF so the integrity gate passes.
        from contextlib import contextmanager

        class _Resp:
            def __init__(self) -> None:
                self._data = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\nbody\n"
            def read(self, n: int = -1) -> bytes:
                d, self._data = self._data, b""
                return d

        @contextmanager
        def _fake(req, timeout=None):
            yield _Resp()

        mock_urlopen.side_effect = _fake
        res = download_literature("https://example.com/paper.pdf", "paper.pdf", tmp_path)
        assert res["status"] == "success"
        assert (tmp_path / "inputs" / "literature").exists()

    @patch("research_os.tools.actions.search.literature._check_unpaywall")
    def test_paywall(self, mock_unpaywall, tmp_path):
        mock_unpaywall.return_value = {"is_oa": False, "reason": "Closed access."}
        res = download_literature("https://example.com/paper.pdf", "paper.pdf", tmp_path)
        assert res["status"] == "error"


def test_all_action_imports_resolve():
    from research_os.tools.actions.protocol import load_protocol as _l
    from research_os.tools.actions.search import search_pubmed as _p
    from research_os.tools.actions.search import search_web as _w
    from research_os.tools.actions.state import create_checkpoint as _c

    assert callable(_c)
    assert callable(_l)
    assert callable(_p)
    assert callable(_w)
