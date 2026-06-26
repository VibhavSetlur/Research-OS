"""Unit tests for the durable run journal + provenance (Phase 1.7)."""
from __future__ import annotations

import subprocess
import time
from types import SimpleNamespace

from research_os.daemon import provenance as prov
from research_os.daemon.runstore import RunJournal, RunStore, build_manifest


# ── provenance ────────────────────────────────────────────────────────────


def test_provenance_env_always_present():
    env = prov.env_provenance()
    assert "python_version" in env
    assert "platform" in env
    assert "python_executable" in env


def test_provenance_packages_resolved():
    env = prov.env_provenance(packages=["pytest", "definitely-not-a-real-pkg-xyz"])
    pkgs = env["packages"]
    assert pkgs["pytest"] is not None
    assert pkgs["definitely-not-a-real-pkg-xyz"] is None


def test_provenance_git_on_real_repo(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "x"],
                   cwd=tmp_path, check=True,
                   env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
                        "PATH": __import__("os").environ["PATH"]})
    g = prov.git_provenance(tmp_path)
    assert len(g["commit"]) == 40
    assert g["dirty"] is False


def test_provenance_git_empty_on_non_repo(tmp_path):
    assert prov.git_provenance(tmp_path) == {}


def test_provenance_hash_file_and_inputs(tmp_path):
    f = tmp_path / "in.txt"
    f.write_text("reproducible")
    digest = prov.hash_file(f)
    assert digest.startswith("sha256:")
    inputs = prov.hash_inputs([f, tmp_path / "missing.txt"])
    assert str(f) in inputs
    assert str(tmp_path / "missing.txt") not in inputs  # unreadable skipped


def test_provenance_capture_never_raises_on_bad_root():
    # Non-existent root, weird inputs — must return a dict, never raise.
    out = prov.capture("/nonexistent/xyz", inputs=["/nope"], packages=["pytest"])
    assert isinstance(out, dict)
    assert "env" in out


# ── run store ─────────────────────────────────────────────────────────────


def test_runstore_write_read_roundtrip(tmp_path):
    rs = RunStore(tmp_path)
    m = build_manifest(run_id="abc123", name="t", kind="subprocess",
                       status="queued", root=str(tmp_path))
    rs.write_manifest("abc123", m)
    back = rs.read_manifest("abc123")
    assert back["id"] == "abc123"
    assert back["status"] == "queued"


def test_runstore_atomic_no_temp_left(tmp_path):
    rs = RunStore(tmp_path)
    rs.write_manifest("j1", build_manifest(run_id="j1", name="t", kind="callable",
                                           status="queued", root=None))
    leftovers = list((rs.runs_dir / "j1").glob("*.tmp"))
    assert leftovers == []


def test_runstore_log_append_and_tail(tmp_path):
    rs = RunStore(tmp_path)
    for i in range(5):
        rs.append_log("j2", f"line{i}")
    assert rs.read_log("j2") == [f"line{i}" for i in range(5)]
    assert rs.read_log("j2", tail=2) == ["line3", "line4"]


def test_runstore_list_newest_first(tmp_path):
    rs = RunStore(tmp_path)
    rs.write_manifest("old", build_manifest(run_id="old", name="a", kind="x",
                      status="succeeded", root=None, submitted_at=100.0))
    rs.write_manifest("new", build_manifest(run_id="new", name="b", kind="x",
                      status="succeeded", root=None, submitted_at=200.0))
    ids = [r["id"] for r in rs.list_runs()]
    assert ids == ["new", "old"]


def test_runstore_read_missing_returns_none(tmp_path):
    assert RunStore(tmp_path).read_manifest("nope") is None


def test_runstore_corrupt_manifest_returns_none(tmp_path):
    rs = RunStore(tmp_path)
    run_dir = rs.runs_dir / "bad"
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text("{not valid json")
    assert rs.read_manifest("bad") is None


def test_runstore_orphan_detection_and_mark(tmp_path):
    rs = RunStore(tmp_path)
    rs.write_manifest("live", build_manifest(run_id="live", name="x", kind="y",
                      status="running", root=None))
    rs.write_manifest("done", build_manifest(run_id="done", name="x", kind="y",
                      status="succeeded", root=None))
    assert rs.detect_orphans() == ["live"]
    rs.mark_interrupted("live")
    assert rs.read_manifest("live")["status"] == "interrupted"
    assert rs.detect_orphans() == []


# ── run journal (event-driven bridge) ─────────────────────────────────────


def _ev(kind, data):
    return SimpleNamespace(kind=kind, data=data)


def test_journal_persists_lifecycle(tmp_path):
    rs = RunStore(tmp_path)
    j = RunJournal(rs)
    snap = {"id": "r1", "name": "demo", "kind": "subprocess", "status": "queued",
            "root": str(tmp_path), "spec": {"cmd": "echo hi"},
            "provenance": {"git": {"commit": "deadbeef"}}, "submitted_at": time.time()}
    j.handle(_ev("job.submitted", {"job_id": "r1", "job": snap}))
    snap2 = dict(snap, status="succeeded", started_at=1.0, finished_at=2.0,
                 duration_s=1.0, result={"returncode": 0})
    j.handle(_ev("job.succeeded", {"job_id": "r1", "job": snap2}))
    m = rs.read_manifest("r1")
    assert m["status"] == "succeeded"
    assert m["provenance"]["git"]["commit"] == "deadbeef"
    assert m["spec"]["cmd"] == "echo hi"
    assert len(m["transitions"]) >= 2


def test_journal_logs_to_full_and_tail(tmp_path):
    rs = RunStore(tmp_path)
    j = RunJournal(rs)
    for i in range(3):
        j.handle(_ev("job.log", {"job_id": "r2", "line": f"l{i}"}))
    snap = {"id": "r2", "name": "x", "kind": "subprocess", "status": "succeeded",
            "root": None, "result": {"returncode": 0}}
    j.handle(_ev("job.succeeded", {"job_id": "r2", "job": snap}))
    assert rs.read_log("r2") == ["l0", "l1", "l2"]
    assert rs.read_manifest("r2")["log_tail"] == ["l0", "l1", "l2"]


def test_journal_nonzero_exit_is_failed(tmp_path):
    rs = RunStore(tmp_path)
    j = RunJournal(rs)
    snap = {"id": "r3", "name": "x", "kind": "subprocess", "status": "succeeded",
            "root": None, "result": {"returncode": 2}}
    j.handle(_ev("job.succeeded", {"job_id": "r3", "job": snap}))
    assert rs.read_manifest("r3")["status"] == "failed"


def test_journal_cancelled_result_stays_cancelled(tmp_path):
    rs = RunStore(tmp_path)
    j = RunJournal(rs)
    snap = {"id": "r4", "name": "x", "kind": "subprocess", "status": "succeeded",
            "root": None, "result": {"returncode": -15, "cancelled": True}}
    j.handle(_ev("job.succeeded", {"job_id": "r4", "job": snap}))
    assert rs.read_manifest("r4")["status"] == "cancelled"


def test_journal_never_raises_on_garbage(tmp_path):
    j = RunJournal(RunStore(tmp_path))
    j.handle(_ev("job.log", {}))           # missing fields
    j.handle(_ev("job.started", {}))       # no job
    j.handle(SimpleNamespace())            # no kind/data
    j.handle(_ev("unrelated.kind", {"x": 1}))
    # nothing persisted, no exception
    assert RunStore(tmp_path).list_runs() == []


def test_terminal_run_auto_writes_staleness_verdict(tmp_path):
    # A terminal run must auto-refresh the staleness verdict sidecar the
    # reasoning-side floor gate reads — so the gate actually fires in normal
    # use, not only after an authenticated POST /v1/staleness/verdict.
    (tmp_path / ".os_state").mkdir()
    rs = RunStore(tmp_path)
    j = RunJournal(rs)
    snap = {"id": "r9", "name": "run", "kind": "subprocess", "status": "queued",
            "root": str(tmp_path), "spec": {"cmd": "echo hi"},
            "provenance": {}, "submitted_at": time.time()}
    j.handle(_ev("job.submitted", {"job_id": "r9", "job": snap}))
    snap2 = dict(snap, status="succeeded", result={"returncode": 0})
    j.handle(_ev("job.succeeded", {"job_id": "r9", "job": snap2}))
    verdict = tmp_path / ".os_state" / "staleness" / "verdict.json"
    assert verdict.exists(), "terminal run did not persist a staleness verdict"



def test_list_runs_survives_a_malformed_manifest(tmp_path):
    """BLOCK-1: one bad manifest (non-dict result) must not sink list_runs /
    detect_orphans — recovery for good orphans alongside it must still work."""
    import json
    store = RunStore(tmp_path)
    runs = tmp_path / ".os_state" / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    # a GOOD orphan (non-terminal status)
    good = runs / "good1"
    good.mkdir()
    (good / "run.json").write_text(json.dumps(
        {"id": "good1", "status": "running", "submitted_at": 1.0}))
    # a MALFORMED manifest: result is a string, artifacts is an int
    bad = runs / "bad1"
    bad.mkdir()
    (bad / "run.json").write_text(json.dumps(
        {"id": "bad1", "status": "running", "result": "oops", "artifacts": 5}))
    # list_runs must not raise, and must include the good one
    listed = store.list_runs(limit=50)
    ids = {r.get("id") for r in listed}
    assert "good1" in ids
    # detect_orphans must still find the good orphan
    orphans = store.detect_orphans()
    assert "good1" in orphans


def test_paused_run_is_not_an_orphan(tmp_path):
    """F-1 (4.0.2): a paused run is a user intent, not a crash artifact —
    detect_orphans must NOT return it (so restart can't clobber it to interrupted)."""
    rs = RunStore(tmp_path)
    rs.runs_dir.mkdir(parents=True, exist_ok=True)
    for rid, status in (("paused1", "paused"), ("run1", "running")):
        (rs.runs_dir / rid).mkdir(exist_ok=True)
        (rs.runs_dir / rid / "run.json").write_text(
            '{"id":"%s","name":"%s","kind":"callable","status":"%s","spec":{},"transitions":[]}'
            % (rid, rid, status)
        )
    orphans = rs.detect_orphans()
    assert "paused1" not in orphans
    assert "run1" in orphans


def test_duplicate_terminal_event_is_idempotent(tmp_path):
    """F-2 (4.0.2): a replayed terminal event must not double-append a transition
    or double-fire on_terminal (which would double-advance autonomous continuation)."""
    rs = RunStore(tmp_path)
    rj = RunJournal(rs)
    fired: list[str] = []
    rj.on_terminal = lambda m: fired.append(m.get("id"))
    evt = {
        "job_id": "j1",
        "job": {"id": "j1", "name": "x", "kind": "callable",
                "status": "succeeded", "result": {"returncode": 0}},
    }
    rj._on_transition("job.succeeded", evt)
    rj._on_transition("job.succeeded", evt)  # duplicate replay
    m = rs.read_manifest("j1")
    assert len(fired) == 1
    succeeded = [t for t in m.get("transitions", []) if t.get("status") == "succeeded"]
    assert len(succeeded) == 1
