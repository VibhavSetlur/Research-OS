"""Unit tests for the daemon background task queue (Phase 1)."""
from __future__ import annotations

import threading
import time

import pytest

from research_os.daemon.tasks import Job, JobStatus, TaskQueue, _jsonsafe


def _drain(q: TaskQueue, job_id: str, timeout: float = 2.0) -> Job:
    """Wait until a job reaches a terminal state (or timeout)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = q.get(job_id)
        if job is not None and job.status.terminal:
            return job
        time.sleep(0.01)
    raise AssertionError(f"job {job_id} did not finish within {timeout}s")


def test_submit_runs_and_records_result():
    q = TaskQueue(max_workers=2)
    q.start()
    try:
        jid = q.submit(lambda a, b: a + b, 2, 3, name="add")
        job = _drain(q, jid)
        assert job.status == JobStatus.SUCCEEDED
        assert job.result == 5
        d = job.to_dict()
        assert d["duration_s"] is None or d["duration_s"] >= 0
    finally:
        q.shutdown()


def test_job_failure_is_captured_not_raised():
    q = TaskQueue(max_workers=1)
    q.start()
    try:
        def boom():
            raise ValueError("nope")

        jid = q.submit(boom, name="boom")
        job = _drain(q, jid)
        assert job.status == JobStatus.FAILED
        assert job.error is not None
        assert "ValueError" in job.error
        assert "nope" in job.error
    finally:
        q.shutdown()


def test_cooperative_cancel_of_running_job():
    q = TaskQueue(max_workers=1)
    q.start()
    try:
        started = threading.Event()

        def slow(cancel_event=None):
            started.set()
            for _ in range(200):
                if cancel_event and cancel_event.is_set():
                    return "bailed"
                time.sleep(0.01)
            return "ran-full"

        jid = q.submit(slow, name="slow")
        assert started.wait(1.0)
        assert q.cancel(jid) is True
        job = _drain(q, jid)
        assert job.status == JobStatus.CANCELLED
    finally:
        q.shutdown()


def test_cancel_unknown_or_terminal_returns_false():
    q = TaskQueue(max_workers=1)
    q.start()
    try:
        assert q.cancel("does-not-exist") is False
        jid = q.submit(lambda: 1, name="quick")
        _drain(q, jid)
        # already terminal -> cancel is a no-op returning False
        assert q.cancel(jid) is False
    finally:
        q.shutdown()


def test_submit_before_start_raises():
    q = TaskQueue()
    with pytest.raises(RuntimeError, match="before start"):
        q.submit(lambda: 1)


def test_submit_after_shutdown_raises():
    q = TaskQueue()
    q.start()
    q.shutdown()
    with pytest.raises(RuntimeError):
        q.submit(lambda: 1)


def test_snapshot_shape_and_filtering():
    q = TaskQueue(max_workers=2)
    q.start()
    try:
        a = q.submit(lambda: 1, name="a", root="/tmp/projA")
        b = q.submit(lambda: 2, name="b", root="/tmp/projB")
        _drain(q, a)
        _drain(q, b)
        snap = q.snapshot()
        assert snap["total"] == 2
        assert snap["counts"].get("succeeded") == 2
        assert snap["max_workers"] == 2
        # newest-first ordering
        names = [j["name"] for j in snap["jobs"]]
        assert names == ["b", "a"]
        # root filter
        only_a = q.snapshot(root="/tmp/projA")
        assert [j["name"] for j in only_a["jobs"]] == ["a"]
        # limit
        limited = q.snapshot(limit=1)
        assert len(limited["jobs"]) == 1
    finally:
        q.shutdown()


def test_history_eviction_drops_old_terminal_jobs():
    q = TaskQueue(max_workers=2, max_history=5)
    q.start()
    try:
        ids = [q.submit(lambda: 1, name=f"j{i}") for i in range(20)]
        # Wait for all submitted work to complete (poll the queue's counts
        # rather than individual ids, which may be evicted).
        deadline = time.time() + 3.0
        while time.time() < deadline:
            snap = q.snapshot()
            done = snap["counts"].get("succeeded", 0)
            if done >= 1 and snap["total"] <= q._max_history:
                break
            time.sleep(0.02)
        snap = q.snapshot()
        # Eviction caps retained jobs near max_history (small slack for any
        # still-running job that can't be evicted).
        assert snap["total"] <= q._max_history + q._max_workers
        assert len(ids) == 20  # all were submitted
    finally:
        q.shutdown()


def test_max_workers_must_be_positive():
    with pytest.raises(ValueError):
        TaskQueue(max_workers=0)


def test_jsonsafe_handles_nonserializable():
    class Weird:
        pass

    assert _jsonsafe(Weird()) == "<Weird>"
    assert _jsonsafe({"a": [1, 2, Weird()]}) == {"a": [1, 2, "<Weird>"]}
    assert _jsonsafe(None) is None
    assert _jsonsafe(3.5) == 3.5
