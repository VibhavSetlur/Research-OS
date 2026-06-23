"""Unit tests for artifact detection (Phase 1.8)."""
from __future__ import annotations

import os
import time

from research_os.daemon import artifacts
from research_os.daemon.runners import SubprocessRunner


# ── snapshot ──────────────────────────────────────────────────────────────


def test_snapshot_empty_dir(tmp_path):
    assert artifacts.snapshot(tmp_path) == {}


def test_snapshot_missing_dir_is_empty():
    assert artifacts.snapshot("/nonexistent/xyz/123") == {}


def test_snapshot_records_files(tmp_path):
    (tmp_path / "a.txt").write_text("x")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.txt").write_text("yy")
    snap = artifacts.snapshot(tmp_path)
    assert "a.txt" in snap
    assert os.path.join("sub", "b.txt") in snap
    assert snap["a.txt"][1] == 1  # size


def test_snapshot_prunes_ignored_dirs(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("nope")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "x.pyc").write_text("nope")
    (tmp_path / ".os_state").mkdir()
    (tmp_path / ".os_state" / "j.json").write_text("nope")
    (tmp_path / "keep.txt").write_text("yes")
    snap = artifacts.snapshot(tmp_path)
    assert "keep.txt" in snap
    assert not any(".git" in k or "__pycache__" in k or ".os_state" in k for k in snap)


# ── diff ──────────────────────────────────────────────────────────────────


def test_diff_detects_created(tmp_path):
    before = artifacts.snapshot(tmp_path)
    (tmp_path / "out.csv").write_text("col\n1\n")
    res = artifacts.diff(tmp_path, before)
    paths = {a["path"]: a for a in res["artifacts"]}
    assert "out.csv" in paths
    assert paths["out.csv"]["change"] == "created"
    assert paths["out.csv"]["sha256"].startswith("sha256:")


def test_diff_detects_modified(tmp_path):
    f = tmp_path / "data.txt"
    f.write_text("v1")
    before = artifacts.snapshot(tmp_path)
    time.sleep(0.01)
    f.write_text("v2-longer")  # size changes -> detected even if mtime res is coarse
    res = artifacts.diff(tmp_path, before)
    paths = {a["path"]: a for a in res["artifacts"]}
    assert paths["data.txt"]["change"] == "modified"


def test_diff_ignores_unchanged(tmp_path):
    (tmp_path / "stable.txt").write_text("same")
    before = artifacts.snapshot(tmp_path)
    res = artifacts.diff(tmp_path, before)
    assert res["artifacts"] == []


def test_diff_skips_hash_over_size_limit(tmp_path):
    before = artifacts.snapshot(tmp_path)
    big = tmp_path / "big.bin"
    big.write_bytes(b"0" * 2048)
    res = artifacts.diff(tmp_path, before, max_hash_bytes=1024)
    a = res["artifacts"][0]
    assert a["path"] == "big.bin"
    assert a["sha256"] is None  # too big to hash, still listed
    assert a["size"] == 2048


def test_diff_caps_artifact_count(tmp_path):
    before = artifacts.snapshot(tmp_path)
    for i in range(10):
        (tmp_path / f"f{i}.txt").write_text("x")
    res = artifacts.diff(tmp_path, before, max_artifacts=3)
    assert len(res["artifacts"]) == 3
    assert res["truncated"] is True


def test_diff_missing_root_is_empty():
    res = artifacts.diff("/nonexistent/xyz", {})
    assert res == {"artifacts": [], "truncated": False}


# ── integration via SubprocessRunner ──────────────────────────────────────


def test_runner_reports_created_artifact(tmp_path):
    r = SubprocessRunner("echo data > result.txt", cwd=str(tmp_path), shell=True)
    out = r()
    assert out["returncode"] == 0
    arts = {a["path"]: a for a in out["artifacts"]}
    assert "result.txt" in arts
    assert arts["result.txt"]["change"] == "created"


def test_runner_no_artifacts_when_nothing_written(tmp_path):
    (tmp_path / "pre.txt").write_text("exists")
    r = SubprocessRunner("echo hi", cwd=str(tmp_path), shell=True)
    out = r()
    assert out["artifacts"] == []


def test_runner_track_artifacts_off(tmp_path):
    r = SubprocessRunner("echo x > y.txt", cwd=str(tmp_path),
                         shell=True, track_artifacts=False)
    out = r()
    assert out["artifacts"] == []
    assert out["artifacts_truncated"] is False
