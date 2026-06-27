"""Background-job reproducibility: full conda/env snapshot in provenance."""
from __future__ import annotations

from research_os.daemon.provenance import capture, env_provenance


def test_env_snapshot_opt_in():
    e = env_provenance(snapshot_env=True)
    assert "env_snapshot" in e
    assert e["env_snapshot_count"] >= 1
    # versions are strings
    assert all(isinstance(v, str) for v in e["env_snapshot"].values())


def test_env_snapshot_off_by_default():
    e = env_provenance()
    assert "env_snapshot" not in e
    # but the lightweight fields are always there
    assert "python_version" in e and "platform" in e


def test_capture_threads_snapshot_flag():
    c = capture(".", snapshot_env=True)
    assert "env_snapshot" in c.get("env", {})
    c2 = capture(".")
    assert "env_snapshot" not in c2.get("env", {})
