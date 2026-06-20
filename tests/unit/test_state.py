"""State ledger and checkpoint tests."""

from research_os.project_ops import (
    create_numbered_experiment,
    default_state,
    load_state,
    save_state,
    scaffold_minimal_workspace,
)
from research_os.state.state_ledger import ResearchLedger
from research_os.tools.actions.state.checkpoint import (
    create_checkpoint,
    list_checkpoints,
    rollback_checkpoint,
)


# ── default_state ─────────────────────────────────────────────────────


def test_default_state_structure():
    state = default_state()
    assert state["current_path"] == "main"
    assert "main" in state["paths"]
    assert "project_id" in state
    assert "pipeline_stage" in state
    assert state["pipeline_stage"] == "init"


def test_load_state_returns_default_for_empty(tmp_path):
    (tmp_path / "inputs").mkdir()
    state = load_state(tmp_path)
    assert "paths" in state
    assert "main" in state["paths"]


# ── save / load cycle ─────────────────────────────────────────────────


def test_save_then_load_preserves_state(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Test Project")
    state = load_state(tmp_path)
    state["step"] = 7
    save_state(tmp_path, state)

    reloaded = load_state(tmp_path)
    assert reloaded["step"] == 7
    assert reloaded["project_name"] == "Test Project"


def test_save_state_updates_timestamp(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Test")
    saved = save_state(tmp_path, load_state(tmp_path))
    assert "updated_at" in saved


def test_save_state_writes_state_md_at_root(tmp_path):
    """v1.3.0 round-2: the canonical human-readable status file is now
    STATE.md at the project root (was `.os_state/os_state.md`). The
    project-root location means a fresh AI session finds it without
    inside knowledge of the `.os_state/` directory structure."""
    scaffold_minimal_workspace(tmp_path, "Test")
    state_md = tmp_path / "STATE.md"
    assert state_md.exists(), "STATE.md should be at project root"
    content = state_md.read_text()
    # Sanity: it should be researcher-readable, no internal jargon.
    assert "Research question" in content or "Pipeline phase" in content
    # The old buried path should not exist either (init-time scaffold
    # never wrote it, and the migration in _write_os_state_summary
    # removes it if present).
    old = tmp_path / ".os_state" / "os_state.md"
    assert not old.exists(), (
        "old `.os_state/os_state.md` shouldn't exist on a fresh init"
    )


# ── ResearchLedger ────────────────────────────────────────────────────


def test_ledger_update_persists(tmp_path):
    ledger = ResearchLedger(tmp_path / ".os_state" / "state_ledger.json")
    ledger.update(pipeline_stage="execution", step=2)
    s = ledger.get()
    assert s["pipeline_stage"] == "execution"
    assert s["step"] == 2


def test_ledger_phase_lifecycle(tmp_path):
    ledger = ResearchLedger(tmp_path / ".os_state" / "state_ledger.json")
    ledger.set_phase("analysis", step=3)
    assert ledger.get()["checkpoints"]["analysis"] == "in_progress"
    ledger.complete_phase("analysis")
    s = ledger.get()
    assert s["checkpoints"]["analysis"] == "complete"
    assert s["resumable_from"] == "analysis"


def test_ledger_migrates_legacy_state(tmp_path):
    """Schema v4.0 migration: legacy fields normalised on load."""
    import json

    state_path = tmp_path / ".os_state" / "state_ledger.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps({
        "project": "Legacy",
        "phase": "analysis",
        "run_id": "old-uuid",
        "token_budget": {"used": 0},
        "paths": {"main": {"input_data_hashes": {"x": "y"}, "status": "active"}},
    }))
    ledger = ResearchLedger(state_path)
    s = ledger.get()
    assert "phase" not in s
    assert "project" not in s
    assert "token_budget" not in s
    assert s["project_name"] == "Legacy"
    assert s["pipeline_stage"] == "analysis"
    assert s["project_id"] == "old-uuid"
    assert "input_data_hashes" not in s["paths"]["main"]


def test_ledger_hypothesis_lifecycle(tmp_path):
    ledger = ResearchLedger(tmp_path / ".os_state" / "state_ledger.json")
    ledger.add_hypothesis("H1", status="testing", effect=0.5)
    ledger.add_hypothesis("H1", status="supported")
    s = ledger.get()
    h1 = next(h for h in s["active_hypotheses"] if h["id"] == "H1")
    assert h1["status"] == "supported"


def test_ledger_dead_ends_deduplicate(tmp_path):
    ledger = ResearchLedger(tmp_path / ".os_state" / "state_ledger.json")
    ledger.add_dead_end("approach_A")
    ledger.add_dead_end("approach_A")
    assert ledger.get()["dead_ends"] == ["approach_A"]


def test_ledger_self_heals_corrupted_state(tmp_path):
    """E3: a truncated/corrupted state_ledger.json must not crash every
    state-touching tool. _load() backs the broken file up and reseeds the
    default state, mirroring tool_workspace_repair."""
    state_path = tmp_path / ".os_state" / "state_ledger.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text("{ truncated", encoding="utf-8")
    ledger = ResearchLedger(state_path)
    s = ledger.get()  # exercises _load() — must not raise JSONDecodeError
    assert isinstance(s, dict)
    assert s["current_path"] == "main"  # reseeded defaults
    backups = list((tmp_path / ".os_state").glob("state_ledger.broken_*.json"))
    assert len(backups) == 1, "corrupted ledger must be backed up, not deleted"
    assert backups[0].read_text(encoding="utf-8") == "{ truncated"


# ── Checkpoints ────────────────────────────────────────────────────────


def test_checkpoint_create_returns_id(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Test")
    res = create_checkpoint("test checkpoint", root=tmp_path)
    assert res["status"] == "success"
    assert res["checkpoint_id"].startswith("ckpt_")


def test_checkpoint_list_after_create(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Test")
    create_checkpoint("first", root=tmp_path)
    res = list_checkpoints(root=tmp_path)
    assert res["status"] == "success"
    assert len(res["checkpoints"]) >= 1


def test_checkpoint_rollback_restores(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Test")
    note = tmp_path / "workspace" / "note.md"
    note.write_text("original")
    cp = create_checkpoint("snap", root=tmp_path)
    note.write_text("modified")
    rb = rollback_checkpoint(cp["checkpoint_id"], root=tmp_path)
    assert rb["status"] == "success"
    assert note.read_text() == "original"


def test_checkpoint_rollback_unknown(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Test")
    res = rollback_checkpoint("ghost", root=tmp_path)
    assert res["status"] == "error"


def test_rollback_removes_post_checkpoint_file_but_preserves_ref_only_data(tmp_path):
    """B2: rollback is restore-TO, not restore-OVER.

    A file created after the checkpoint is deleted; a captured file is
    restored; a large ref-only data file (skip-ext) the snapshot never
    copies is NEVER deleted even though it's absent from the manifest;
    and the deletion stays strictly inside workspace/.
    """
    scaffold_minimal_workspace(tmp_path, "Test")
    ws = tmp_path / "workspace"
    captured = ws / "note.md"
    captured.write_text("original")

    # A file that exists OUTSIDE workspace/ must never be touched.
    outside = tmp_path / "inputs" / "keep_me.txt"
    outside.parent.mkdir(parents=True, exist_ok=True)
    outside.write_text("untouched")

    cp = create_checkpoint("snap", root=tmp_path)

    # Mutate after the checkpoint: edit captured, add a post-checkpoint
    # text file + a whole new step dir, and a ref-only data file.
    captured.write_text("modified")
    post_file = ws / "after.txt"
    post_file.write_text("created after checkpoint")
    bad_step = ws / "99_bad_step"
    bad_step.mkdir()
    (bad_step / "result.txt").write_text("phantom")
    data_file = ws / "01_step" / "data" / "big.csv"
    data_file.parent.mkdir(parents=True, exist_ok=True)
    data_file.write_text("a,b\n1,2\n")

    rb = rollback_checkpoint(cp["checkpoint_id"], root=tmp_path)
    assert rb["status"] == "success"

    # Captured file restored.
    assert captured.read_text() == "original"
    # Post-checkpoint text file + entire bad step dir removed.
    assert not post_file.exists()
    assert not (bad_step / "result.txt").exists()
    assert not bad_step.exists(), "empty post-checkpoint dir should be pruned"
    # Ref-only data file (skip-ext) preserved — its bytes are unrecoverable.
    assert data_file.exists(), "ref-only .csv must never be deleted on rollback"
    # Nothing outside workspace/ touched.
    assert outside.read_text() == "untouched"
    # files_removed reported (at least after.txt + result.txt).
    assert rb.get("files_removed", 0) >= 2


def test_checkpoint_gc_prunes_untagged_beyond_keep(tmp_path):
    """_prune_old_checkpoints keeps the newest N untagged checkpoints
    and removes the rest. Tagged checkpoints survive regardless of age.
    """
    import json
    import os
    import time
    from research_os.project_ops import _prune_old_checkpoints

    ckpt_dir = tmp_path / ".os_state" / "checkpoints"
    ckpt_dir.mkdir(parents=True)

    # 8 untagged + 2 tagged. Use distinct mtimes via os.utime so the
    # "newest N" GC has a stable ordering — the production path
    # naturally separates checkpoints by seconds, so this just
    # short-circuits the rate-limit in the test.
    base = time.time() - 1000
    untagged_paths: list = []
    for i in range(8):
        cid = f"ckpt_u{i:02d}"
        (ckpt_dir / cid).mkdir()
        meta = ckpt_dir / f"{cid}.meta.json"
        meta.write_text(json.dumps({"checkpoint_id": cid, "description": f"u{i}"}))
        os.utime(meta, (base + i, base + i))
        untagged_paths.append(meta)
    for i in range(2):
        cid = f"ckpt_t{i:02d}"
        (ckpt_dir / cid).mkdir()
        meta = ckpt_dir / f"{cid}.meta.json"
        meta.write_text(json.dumps({"checkpoint_id": cid, "description": f"t{i}", "tag": "release"}))
        os.utime(meta, (base + i, base + i))

    report = _prune_old_checkpoints(tmp_path, keep=5)
    # 8 untagged → keep 5, remove 3. 2 tagged → keep both regardless.
    assert report["removed"] == 3
    assert report["tagged"] == 2
    # 5 surviving untagged + 2 tagged = 7 total sidecars + 7 dirs on disk.
    remaining_meta = list(ckpt_dir.glob("*.meta.json"))
    remaining_dirs = [p for p in ckpt_dir.iterdir() if p.is_dir()]
    assert len(remaining_meta) == 7
    assert len(remaining_dirs) == 7
    # Tagged checkpoints must still be present.
    for i in range(2):
        assert (ckpt_dir / f"ckpt_t{i:02d}.meta.json").exists()
        assert (ckpt_dir / f"ckpt_t{i:02d}").is_dir()
    # Oldest 3 untagged should be gone (u00, u01, u02).
    for i in range(3):
        assert not (ckpt_dir / f"ckpt_u{i:02d}.meta.json").exists()
        assert not (ckpt_dir / f"ckpt_u{i:02d}").exists()


def test_prerollback_backups_have_own_gc_bucket(tmp_path):
    """B8: pre_rollback backups are pruned in a separate budget so a
    rollback can never evict a deliberate user checkpoint."""
    import json
    import os
    import time
    from research_os.project_ops import _prune_old_checkpoints

    ckpt_dir = tmp_path / ".os_state" / "checkpoints"
    ckpt_dir.mkdir(parents=True)

    base = time.time() - 1000
    # 3 user checkpoints (within keep=5) ...
    for i in range(3):
        cid = f"ckpt_u{i:02d}"
        (ckpt_dir / cid).mkdir()
        meta = ckpt_dir / f"{cid}.meta.json"
        meta.write_text(json.dumps({"checkpoint_id": cid, "description": f"u{i}"}))
        os.utime(meta, (base + i, base + i))
    # ... plus 6 pre_rollback backups (their own bucket, keep_backups=3).
    for i in range(6):
        cid = f"pre_rollback_x_{i:02d}"
        (ckpt_dir / cid).mkdir()
        meta = ckpt_dir / f"{cid}.meta.json"
        meta.write_text(
            json.dumps({"checkpoint_id": cid, "kind": "pre_rollback"})
        )
        os.utime(meta, (base + 100 + i, base + 100 + i))

    report = _prune_old_checkpoints(tmp_path, keep=5, keep_backups=3)

    # No user checkpoint evicted — 3 < keep, and backups don't compete.
    assert report["removed"] == 0
    for i in range(3):
        assert (ckpt_dir / f"ckpt_u{i:02d}.meta.json").exists()
    # Backups pruned in their own bucket: 6 → keep 3, remove 3.
    assert report["backups_removed"] == 3
    surviving_backups = list(ckpt_dir.glob("pre_rollback_*.meta.json"))
    assert len(surviving_backups) == 3


def test_rollback_does_not_evict_user_checkpoints(tmp_path):
    """B8 (integration): repeated rollbacks (each writes a pre_rollback
    backup) leave the user's original checkpoint intact."""
    scaffold_minimal_workspace(tmp_path, "Test")
    note = tmp_path / "workspace" / "note.md"
    note.write_text("v0")
    cp = create_checkpoint("keep-me", root=tmp_path)
    cid = cp["checkpoint_id"]

    # Several rollbacks, each producing a pre_rollback backup + GC pass.
    for i in range(6):
        note.write_text(f"v{i + 1}")
        create_checkpoint(f"snap {i}", root=tmp_path)
        rollback_checkpoint(cid, root=tmp_path)

    ids = [c["id"] for c in list_checkpoints(root=tmp_path)["checkpoints"]]
    assert cid in ids, "the original user checkpoint must survive rollbacks"


def test_checkpoint_create_runs_gc_and_returns_report(tmp_path):
    """create_checkpoint(keep=N) prunes after writing + returns gc report."""
    scaffold_minimal_workspace(tmp_path, "Test")
    res = create_checkpoint("first", root=tmp_path, keep=3)
    assert res["status"] == "success"
    assert "gc" in res, "GC report must be surfaced in the return envelope"


def test_checkpoint_tag_survives_in_meta_and_list(tmp_path):
    """A tagged checkpoint records its tag in the sidecar + list output."""
    scaffold_minimal_workspace(tmp_path, "Test")
    res = create_checkpoint("rc snapshot", root=tmp_path, tag="release-candidate")
    assert res["status"] == "success"
    assert res.get("tag") == "release-candidate"

    listed = list_checkpoints(root=tmp_path)["checkpoints"]
    tagged = [c for c in listed if c.get("tag") == "release-candidate"]
    assert len(tagged) == 1, "tagged checkpoint should appear in list output"


# ── Numbered experiments ──────────────────────────────────────────────


def test_create_numbered_experiment(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Test")
    res = create_numbered_experiment(tmp_path, "data_prep", hypothesis="Clean data", enforce_predecessor_finalized=False)
    state = load_state(tmp_path)
    assert res["path_id"] in state["paths"]
    assert state["current_path"] == res["path_id"]


def test_numbered_experiments_auto_increment(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Test")
    r1 = create_numbered_experiment(tmp_path, "first", enforce_predecessor_finalized=False)
    r2 = create_numbered_experiment(tmp_path, "second", enforce_predecessor_finalized=False)
    assert r1["path_id"].startswith("01_")
    assert r2["path_id"].startswith("02_")
