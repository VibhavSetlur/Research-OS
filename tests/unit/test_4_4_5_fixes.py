"""Tests for three 4.4.5 bug fixes:
  1. Large raw-data files are symlinked into inputs/raw_data/, not copied.
  2. workspace/scratch/ is the single canonical throwaway dir (no cache/),
     and it supports organized subfolders.
  3. Figure captions require a paper-ready prose `## Caption` block.
"""
from __future__ import annotations

from pathlib import Path

from research_os.tools.actions.data.context_intake import (
    _SYMLINK_THRESHOLD_BYTES,
    _stage_input_file,
)
from research_os.tools.actions.state.scratch import (
    scratch_list,
    scratch_run,
    scratch_write,
)
from research_os.tools.actions.viz.figures import (
    _paper_caption_issue,
    caption_template,
)


# ── 1. large-data symlink ─────────────────────────────────────────────


def test_small_file_is_copied(tmp_path):
    src = tmp_path / "small.csv"
    src.write_text("a,b\n1,2\n")
    dest = tmp_path / "dest.csv"
    method = _stage_input_file(src, dest)
    assert method == "copy"
    assert dest.is_file() and not dest.is_symlink()


def test_large_file_is_symlinked(tmp_path, monkeypatch):
    # Don't actually write GBs — lower the threshold for the test.
    import sys

    ci = sys.modules["research_os.tools.actions.data.context_intake"]
    src = tmp_path / "big.bam"
    src.write_text("x" * 1024)
    monkeypatch.setattr(ci, "_SYMLINK_THRESHOLD_BYTES", 100)
    dest = tmp_path / "dest.bam"
    method = ci._stage_input_file(src, dest)
    assert method == "symlink"
    assert dest.is_symlink()
    # The link resolves to the absolute source.
    assert dest.resolve() == src.resolve()


def test_symlink_falls_back_to_copy_on_error(tmp_path, monkeypatch):
    import sys

    ci = sys.modules["research_os.tools.actions.data.context_intake"]
    src = tmp_path / "big.bam"
    src.write_text("x" * 1024)
    monkeypatch.setattr(ci, "_SYMLINK_THRESHOLD_BYTES", 100)

    def _boom(*a, **k):
        raise OSError("symlinks unsupported")

    monkeypatch.setattr(Path, "symlink_to", _boom)
    dest = tmp_path / "dest.bam"
    method = ci._stage_input_file(src, dest)
    assert method == "copy"
    assert dest.is_file() and not dest.is_symlink()


def test_threshold_is_reasonable():
    # 1 GB — small data copies, huge data symlinks.
    assert _SYMLINK_THRESHOLD_BYTES == 1024 ** 3


# ── 2. scratch (canonical, organized subfolders) ──────────────────────


def test_scratch_uses_canonical_dir(tmp_path):
    res = scratch_write("probe.py", "print(1)", tmp_path)
    assert res["status"] == "success"
    assert (tmp_path / "workspace" / "scratch" / "probe.py").exists()
    # There is no workspace/cache.
    assert not (tmp_path / "workspace" / "cache").exists()


def test_scratch_allows_subfolders(tmp_path):
    res = scratch_write("probes/test_x.py", "print(1)", tmp_path)
    assert res["status"] == "success"
    assert (tmp_path / "workspace" / "scratch" / "probes" / "test_x.py").exists()


def test_scratch_rejects_traversal(tmp_path):
    res = scratch_write("../escape.py", "x", tmp_path)
    assert res["status"] == "error"
    res2 = scratch_write("/etc/passwd", "x", tmp_path)
    assert res2["status"] == "error"


def test_scratch_list_is_recursive(tmp_path):
    scratch_write("plans/idea.md", "# idea", tmp_path)
    scratch_write("flat.py", "x", tmp_path)
    res = scratch_list(tmp_path)
    names = {e["name"] for e in res["files"]}
    assert "flat.py" in names
    assert "plans/idea.md" in names


def test_scratch_run_in_subfolder(tmp_path):
    scratch_write("probes/p.py", "print('hi')", tmp_path)
    res = scratch_run("probes/p.py", tmp_path)
    assert res["status"] == "success"
    assert res["exit_code"] == 0
    assert "hi" in res["stdout"]


# ── 3. paper-ready caption ────────────────────────────────────────────


def test_caption_missing_caption_heading_flagged(tmp_path):
    cap = tmp_path / "fig.caption.md"
    cap.write_text("# Figure: X\n\nSome notes.\n\n**File:** fig.png\n")
    issue = _paper_caption_issue(cap)
    assert issue is not None
    assert "Caption" in issue


def test_caption_with_only_bullets_flagged(tmp_path):
    cap = tmp_path / "fig.caption.md"
    cap.write_text("## Caption\n\n- bullet one\n- bullet two\n")
    issue = _paper_caption_issue(cap)
    assert issue is not None


def test_caption_with_real_prose_passes(tmp_path):
    cap = tmp_path / "fig.caption.md"
    cap.write_text(
        "## Caption\n\n"
        "Across 3,988 genomes RAST assigns a function to a median of 64.2% "
        "of proteins per genome, leaving a substantial annotation gap.\n\n"
        "## Panels\n\n- (A) call rate\n"
    )
    assert _paper_caption_issue(cap) is None


def test_caption_template_has_caption_block_and_passes(tmp_path):
    tmpl = caption_template("Per-genome recovery", "Median recovery is 64%.")
    assert "## Caption" in tmpl
    assert "Median recovery is 64%." in tmpl
    cap = tmp_path / "fig.caption.md"
    cap.write_text(tmpl)
    assert _paper_caption_issue(cap) is None


def test_caption_template_skeleton_without_finding_is_flagged(tmp_path):
    # An un-filled template (bracketed placeholder, no real sentence) must
    # still nudge the AI to write the actual caption.
    tmpl = caption_template("Some figure")
    cap = tmp_path / "fig.caption.md"
    cap.write_text(tmpl)
    assert "## Caption" in tmpl
    assert _paper_caption_issue(cap) is not None
