"""Unit tests for the daemon event spine (Phase 1.5)."""
from __future__ import annotations

import threading
import time

from research_os.daemon.events import Event, EventBus, _kind_matches


def test_publish_assigns_monotonic_seq():
    bus = EventBus()
    a = bus.publish("job.started", {"id": "x"})
    b = bus.publish("job.succeeded", {"id": "x"})
    assert a.seq == 1
    assert b.seq == 2
    assert bus.last_seq == 2


def test_recent_filters_by_kind_and_root():
    bus = EventBus()
    bus.publish("job.started", {}, root="/a")
    bus.publish("state.changed", {}, root="/a")
    bus.publish("job.failed", {}, root="/b")
    assert len(bus.recent(kinds={"job.*"})) == 2
    assert len(bus.recent(kinds={"job"})) == 2  # bare namespace
    assert len(bus.recent(kinds={"job.started"})) == 1  # exact
    assert len(bus.recent(root="/a")) == 2
    assert len(bus.recent(root="/b")) == 1


def test_recent_after_seq_resume():
    bus = EventBus()
    for i in range(5):
        bus.publish("tick", {"i": i})
    out = bus.recent(after_seq=3)
    assert [e.data["i"] for e in out] == [3, 4]


def test_history_is_bounded():
    bus = EventBus(history=3)
    for i in range(10):
        bus.publish("tick", {"i": i})
    seqs = [e.seq for e in bus.recent(limit=100)]
    assert seqs == [8, 9, 10]  # only last 3 retained


def test_subscribe_backfill_then_live():
    bus = EventBus()
    bus.publish("job.started", {})  # will be backfilled
    received: list[str] = []

    def consume():
        gen = bus.subscribe(kinds={"job"}, backfill=5)
        for e in gen:
            if e.kind == "heartbeat":
                continue
            received.append(e.kind)
            if len(received) >= 2:
                gen.close()
                break

    t = threading.Thread(target=consume)
    t.start()
    time.sleep(0.2)
    bus.publish("job.succeeded", {})
    bus.publish("noise.event", {})  # filtered out
    t.join(timeout=5)
    assert received == ["job.started", "job.succeeded"]


def test_subscribe_after_seq_no_duplicate():
    bus = EventBus()
    e1 = bus.publish("a", {})
    received: list[int] = []

    def consume():
        gen = bus.subscribe(after_seq=e1.seq)
        for e in gen:
            if e.kind == "heartbeat":
                continue
            received.append(e.seq)
            gen.close()
            break

    t = threading.Thread(target=consume)
    t.start()
    time.sleep(0.2)
    bus.publish("b", {})
    t.join(timeout=5)
    assert received == [2]  # did not replay seq 1


def test_slow_subscriber_drops_oldest_not_blocks():
    # subscriber_buffer tiny -> overflow must drop, never block the publisher.
    bus = EventBus(subscriber_buffer=2)
    gen = bus.subscribe()
    try:
        for i in range(50):
            bus.publish("flood", {"i": i})  # must not hang
        # publisher returned -> success; the bus didn't block on a full sub.
    finally:
        gen.close()
    assert bus.last_seq == 50


def test_subscriber_count_tracks_lifecycle():
    bus = EventBus()
    assert bus.subscriber_count() == 0
    gen = bus.subscribe()
    next_called = threading.Event()

    def consume():
        for _e in gen:
            next_called.set()
            break

    t = threading.Thread(target=consume)
    t.start()
    time.sleep(0.1)
    assert bus.subscriber_count() == 1
    bus.publish("x", {})
    next_called.wait(2)
    gen.close()
    t.join(timeout=2)


def test_kind_matches_patterns():
    assert _kind_matches("job.started", {"job.started"})
    assert _kind_matches("job.started", {"job.*"})
    assert _kind_matches("job.started", {"job"})
    assert not _kind_matches("state.changed", {"job.*"})
    assert not _kind_matches("jobs.x", {"job"})  # bare ns must match exactly


def test_event_to_dict_is_jsonsafe():
    class Weird:
        pass

    e = Event(seq=1, kind="x", data={"ok": 1, "bad": Weird()})
    d = e.to_dict()
    assert d["seq"] == 1
    assert d["data"]["ok"] == 1
    assert d["data"]["bad"] == "<Weird>"


def test_stats_shape():
    bus = EventBus(history=5)
    bus.publish("x", {})
    s = bus.stats()
    assert s["last_seq"] == 1
    assert s["history"] == 1
    assert s["history_cap"] == 5
    assert s["subscribers"] == 0
