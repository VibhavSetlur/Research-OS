from unittest.mock import patch, MagicMock
from pathlib import Path

from research_os.tools.actions.web_search import search_web, scrape_web
from research_os.tools.actions.environment import (
    package_install,
    env_freeze,
    env_restore,
)
from research_os.tools.actions.checkpoint import (
    create_checkpoint,
    rollback_checkpoint,
    list_checkpoints,
)
from research_os.tools.actions.literature import download_literature


# ── Environment ───────────────────────────────────────────────────────────────


class TestPackageInstall:
    @patch("subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="installed", stderr="")
        res = package_install(["requests"])
        assert res["code"] == 0
        assert res["stdout"] == "installed"

    @patch("subprocess.run")
    def test_error(self, mock_run):
        mock_run.side_effect = Exception("pip not found")
        res = package_install(["nonexistent"])
        assert res["code"] == 1
        assert "pip not found" in res["error"]


class TestEnvFreeze:
    @patch("subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="requests==2.31.0", stderr=""
        )
        res = env_freeze()
        assert res["code"] == 0
        assert "requests" in res["stdout"]

    @patch("subprocess.run")
    def test_error(self, mock_run):
        mock_run.side_effect = Exception("freeze failed")
        res = env_freeze()
        assert res["code"] == 1
        assert "freeze failed" in res["error"]


class TestEnvRestore:
    @patch("subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="installed", stderr="")
        res = env_restore("requests==2.31.0")
        assert res["code"] == 0
        args, _ = mock_run.call_args
        assert "-r" in args[0]

    @patch("subprocess.run")
    def test_error(self, mock_run):
        mock_run.side_effect = Exception("restore failed")
        res = env_restore("requests==2.31.0")
        assert res["code"] == 1
        assert "restore failed" in res["error"]


# ── Web Search ────────────────────────────────────────────────────────────────


class TestSearchWeb:
    @patch("research_os.tools.actions.web_search.settings")
    @patch("research_os.tools.actions.web_search._firecrawl_search")
    def test_success(self, mock_firecrawl, mock_settings):
        mock_settings.FIRECRAWL_API_KEY = "test_key"
        mock_firecrawl.return_value = {
            "data": [{"title": "T", "url": "http://x.com", "description": "D"}]
        }
        res = search_web("q", limit=5)
        assert res["count"] == 1
        assert res["source"] == "web"
        assert res["results"][0]["title"] == "T"

    @patch("research_os.tools.actions.web_search.settings")
    def test_no_api_key(self, mock_settings):
        mock_settings.FIRECRAWL_API_KEY = ""
        res = search_web("q")
        assert res["count"] == 0
        assert "stub" in res["source"]


class TestScrapeWeb:
    @patch("research_os.tools.actions.web_search.settings")
    @patch("firecrawl.FirecrawlApp")
    def test_firecrawl(self, mock_app_cls, mock_settings):
        mock_settings.FIRECRAWL_API_KEY = "key"
        mock_app_cls.return_value.scrape_url.return_value = {"markdown": "# hello"}
        res = scrape_web("http://x.com")
        assert res["content"] == "# hello"

    @patch("research_os.tools.actions.web_search.settings")
    def test_no_api_key(self, mock_settings):
        mock_settings.FIRECRAWL_API_KEY = ""
        res = scrape_web("http://x.com")
        assert "content" in res


# ── Checkpoint ────────────────────────────────────────────────────────────────


class TestCreateCheckpoint:
    @patch("research_os.tools.actions.checkpoint._snapshot_workspace")
    @patch("research_os.state.checkpoint_manager.CheckpointManager")
    def test_success(self, MockCM, mock_snapshot):
        instance = MockCM.return_value
        instance.save.return_value = Path(
            "/tmp/.research/checkpoints/manual_20250101_120000.json"
        )

        res = create_checkpoint("test cp", Path("/tmp"))
        assert res["status"] == "success"
        assert res["checkpoint_id"] == "manual_20250101_120000"
        MockCM.assert_called_once_with(Path("/tmp/.research/checkpoints"))
        instance.save.assert_called_once_with(
            phase="manual", data={}, metadata={"description": "test cp"}
        )
        mock_snapshot.assert_called_once_with(Path("/tmp"), "manual_20250101_120000")

    def test_creates_zip(self, tmp_path):
        (tmp_path / "workspace").mkdir()
        (tmp_path / "workspace" / "notes.md").write_text("research notes")
        (tmp_path / "workspace" / "data").mkdir()
        (tmp_path / "workspace" / "data" / "large.csv").write_text("a,b\n1,2")

        ckpt_dir = tmp_path / ".research" / "checkpoints"
        ckpt_dir.mkdir(parents=True)
        mock_path = ckpt_dir / "manual_20250101_120000.json"
        mock_path.write_text("{}")

        with patch("research_os.state.checkpoint_manager.CheckpointManager") as MockCM:
            MockCM.return_value.save.return_value = mock_path
            res = create_checkpoint("test cp", tmp_path)

        assert res["status"] == "success"
        zip_path = ckpt_dir / "manual_20250101_120000_workspace.zip"
        assert zip_path.exists()

        import zipfile

        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
            assert any("notes.md" in n for n in names)
            assert not any("large.csv" in n for n in names)

    def test_no_workspace(self, tmp_path):
        ckpt_dir = tmp_path / ".research" / "checkpoints"
        ckpt_dir.mkdir(parents=True)
        mock_path = ckpt_dir / "manual_20250101_120000.json"
        mock_path.write_text("{}")

        with patch("research_os.state.checkpoint_manager.CheckpointManager") as MockCM:
            MockCM.return_value.save.return_value = mock_path
            res = create_checkpoint("test cp", tmp_path)

        assert res["status"] == "success"
        zip_path = ckpt_dir / "manual_20250101_120000_workspace.zip"
        assert not zip_path.exists()


class TestRollbackCheckpoint:
    def test_success(self, tmp_path):
        ckpt_dir = tmp_path / ".research" / "checkpoints"
        ckpt_dir.mkdir(parents=True)
        (ckpt_dir / "cp1.json").write_text("{}")

        with patch("research_os.state.checkpoint_manager.CheckpointManager"):
            with patch(
                "research_os.tools.actions.checkpoint._restore_workspace"
            ) as mock_restore:
                res = rollback_checkpoint("cp1", tmp_path)

        assert res["status"] == "success"
        assert "cp1" in res["message"]
        mock_restore.assert_called_once_with(tmp_path, "cp1")

    def test_not_found(self, tmp_path):
        with patch("research_os.state.checkpoint_manager.CheckpointManager"):
            res = rollback_checkpoint("nonexistent", tmp_path)
        assert res["status"] == "error"
        assert "not found" in res["message"].lower()


class TestListCheckpoints:
    @patch("research_os.state.checkpoint_manager.CheckpointManager")
    def test_success(self, MockCM):
        instance = MockCM.return_value
        instance.list_all.return_value = [
            {
                "file": "cp1.json",
                "phase": "manual",
                "timestamp": "2025-01-01T12:00:00",
                "metadata": {},
            }
        ]
        res = list_checkpoints(Path("/tmp"))
        assert res["status"] == "success"
        assert len(res["checkpoints"]) == 1
        assert res["checkpoints"][0]["phase"] == "manual"


# ── Literature ────────────────────────────────────────────────────────────────


class TestDownloadLiterature:
    @patch("research_os.tools.actions.literature._check_unpaywall")
    @patch("urllib.request.urlretrieve")
    def test_success(self, mock_retrieve, mock_unpaywall, tmp_path):
        mock_unpaywall.return_value = {"is_oa": True, "reason": "OA"}
        mock_retrieve.return_value = (
            str(tmp_path / "inputs/literature/paper.pdf"),
            None,
        )

        res = download_literature(
            "https://example.com/paper.pdf", "paper.pdf", tmp_path
        )
        assert res["status"] == "success"
        assert "paper.pdf" in res["filepath"]
        expected = tmp_path / "inputs" / "literature" / "paper.pdf"
        assert expected.parent.exists()
        mock_retrieve.assert_called_once_with("https://example.com/paper.pdf", expected)

    @patch("research_os.tools.actions.literature._check_unpaywall")
    def test_paywall(self, mock_unpaywall, tmp_path):
        mock_unpaywall.return_value = {"is_oa": False, "reason": "Closed access."}
        res = download_literature(
            "https://example.com/paper.pdf", "paper.pdf", tmp_path
        )
        assert res["status"] == "error"
        assert "paywall" in res["message"].lower()


def test_all_action_imports_resolve():
    """Verify every action module is importable and exposes expected callables."""
    import research_os.tools.actions as actions

    module = actions
    assert module is not None

    from research_os.tools.actions.web_search import search_web
    from research_os.tools.actions.checkpoint import (
        create_checkpoint,
    )
    from research_os.tools.actions.protocol import get_protocol
    from research_os.tools.actions.search import search_pubmed

    assert callable(search_web)
    assert callable(get_protocol)
    assert callable(search_pubmed)
    assert callable(create_checkpoint)
