"""Tests for the per-step synthesis step report (v3.10.0).

A step report is a single self-contained, presentation-grade HTML page
about ONE analysis step — the artefact you screen-share in a meeting or
attach to a milestone email. Three surfaces are covered:

1. ``synthesis_scaffold(kind='step_report')`` seeds a MINIMAL shell
   (palette + a11y baseline + offline-safety + author brief), routes it
   into ``synthesis/updates/step-NN-<slug>.html``, and refreshes the
   diary index. It mandates no sections — the AI designs the page.

2. ``_check_step_report`` enforces the trust INVARIANTS (authored-at-all,
   no left-in brief, offline, alt text, no placeholders, emailable) and
   NEVER a heading list. The empty shell must block; an authored page
   must pass. ``_file_kind`` must classify the stamped shell as
   ``step_report`` (the stamp lives ~9KB into the file, past any head
   slice).

3. ``rebuild_updates_index`` regenerates a navigation-only
   ``synthesis/updates/index.html`` listing every step report in
   chronological order, offline, with no claims of its own.
"""

from __future__ import annotations

from pathlib import Path

from research_os.tools.actions.synthesis.check import (
    _check_step_report,
    _file_kind,
    synthesis_check,
)
from research_os.tools.actions.synthesis.scaffold import (
    rebuild_updates_index,
    synthesis_scaffold,
)


def _seed_step_dir(root: Path, num: str, name: str) -> None:
    (root / "workspace" / f"{num}_{name}").mkdir(parents=True, exist_ok=True)


# A minimal AUTHORED step report — real prose, a local figure with alt
# text, fully offline, no placeholders, no left-in brief. Should pass.
_AUTHORED = """\
<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Step 21</title></head>
<body data-archetype="step-report">
<main>
<h1>Step 21 — baseline EDA</h1>
<p>The held-out accuracy landed at 0.84 (95% CI 0.81-0.87), a 6.5pp lift
over the prior baseline. The class imbalance we worried about did not
materially distort the per-class recall once we stratified the split.</p>
<figure>
  <img src="figures/recall_by_class.png" alt="Per-class recall bar chart,
  all classes above 0.78" />
  <figcaption>Per-class recall after stratification.</figcaption>
</figure>
<p>Next step rebalances the encoder; nothing here blocks that.</p>
</main>
</body>
</html>
"""


def test_scaffold_writes_into_updates_with_step_slug(tmp_path: Path):
    _seed_step_dir(tmp_path, "21", "baseline_eda")
    res = synthesis_scaffold(tmp_path, kind="step_report", step="21", confirmed=True)
    assert res["status"] == "success", res
    p = Path(res["path"])
    assert p.parent == tmp_path / "synthesis" / "updates"
    # The slug folds in the real step directory's descriptive tail.
    assert p.name == "step-21-baseline-eda.html"
    assert p.read_text(encoding="utf-8")  # non-empty shell written


def test_scaffold_shell_is_minimal_and_offline(tmp_path: Path):
    res = synthesis_scaffold(tmp_path, kind="step_report", step="3", confirmed=True)
    body = Path(res["path"]).read_text(encoding="utf-8")
    # Stamped so the check engine can route on kind.
    assert 'data-archetype="step-report"' in body
    # Offline: no external script/stylesheet/image URLs in the shell.
    assert "http://" not in body and "https://" not in body
    # Guidance-first: the brief is present (as a comment) for the AI to read.
    assert "author brief" in body.lower()


def test_file_kind_classifies_stamped_shell(tmp_path: Path):
    res = synthesis_scaffold(tmp_path, kind="step_report", step="7", confirmed=True)
    assert _file_kind(Path(res["path"])) == "step_report"


def test_empty_shell_blocks(tmp_path: Path):
    """The freshly scaffolded shell is NOT a finished page — it must block."""
    res = synthesis_scaffold(tmp_path, kind="step_report", step="9", confirmed=True)
    shell = Path(res["path"]).read_text(encoding="utf-8")
    r = _check_step_report(shell, tmp_path)
    assert r["blockers"], "empty shell should produce blockers"
    blob = " ".join(r["blockers"]).lower()
    # Either the body-empty blocker or the left-in-brief blocker (or both).
    assert "empty" in blob or "author-brief" in blob


def test_authored_page_passes(tmp_path: Path):
    r = _check_step_report(_AUTHORED, tmp_path)
    assert r["blockers"] == [], r["blockers"]
    assert r["img_count"] == 1


def test_check_is_not_a_heading_list(tmp_path: Path):
    """Step NN headings and a single-step focus are EXPECTED, never penalised."""
    r = _check_step_report(_AUTHORED, tmp_path)
    blob = " ".join(r["blockers"] + r["warnings"]).lower()
    assert "section heading" not in blob
    assert "per-step recap" not in blob
    assert "hero" not in blob


def test_check_blocks_external_image(tmp_path: Path):
    bad = _AUTHORED.replace(
        'src="figures/recall_by_class.png"',
        'src="https://example.com/recall.png"',
    )
    r = _check_step_report(bad, tmp_path)
    assert any("network url" in b.lower() for b in r["blockers"])


def test_check_blocks_missing_alt(tmp_path: Path):
    bad = _AUTHORED.replace(
        'alt="Per-class recall bar chart,\n  all classes above 0.78"', ""
    )
    r = _check_step_report(bad, tmp_path)
    assert any("alt text" in b.lower() for b in r["blockers"])


def test_synthesis_check_dispatches_to_step_report(tmp_path: Path):
    """End-to-end: synthesis_check routes the stamped file to the step gate."""
    res = synthesis_scaffold(tmp_path, kind="step_report", step="21", confirmed=True)
    out = synthesis_check(tmp_path, str(Path(res["path"]).relative_to(tmp_path)))
    # The empty shell must NOT report a clean success.
    assert out.get("status") != "success" or out.get("blockers")


# ---- diary index helper ------------------------------------------------


def test_index_orders_reports_chronologically(tmp_path: Path):
    for num, name in (("03", "x"), ("21", "y")):
        _seed_step_dir(tmp_path, num, name)
    synthesis_scaffold(tmp_path, kind="step_report", step="21", confirmed=True)
    res = synthesis_scaffold(tmp_path, kind="step_report", step="03", confirmed=True)
    assert res.get("updates_index_count") == 2
    idx = (tmp_path / "synthesis" / "updates" / "index.html").read_text("utf-8")
    # step 03 must appear before step 21.
    assert idx.index("step-03") < idx.index("step-21")


def test_index_is_offline_and_self_describing(tmp_path: Path):
    _seed_step_dir(tmp_path, "05", "z")
    synthesis_scaffold(tmp_path, kind="step_report", step="05", confirmed=True)
    idx = (tmp_path / "synthesis" / "updates" / "index.html").read_text("utf-8")
    assert "http://" not in idx and "https://" not in idx
    assert 'lang="en"' in idx
    # Stamped distinctly so it is never misclassified as a step report.
    assert 'data-archetype="updates-index"' in idx


def test_index_empty_returns_empty(tmp_path: Path):
    (tmp_path / "synthesis" / "updates").mkdir(parents=True)
    out = rebuild_updates_index(tmp_path)
    assert out["status"] == "empty"
    assert out["count"] == 0
    assert not (tmp_path / "synthesis" / "updates" / "index.html").exists()
