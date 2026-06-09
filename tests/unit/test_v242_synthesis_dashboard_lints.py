"""Regression tests for v2.4.2 synthesis check + curate fixes.

Three classes of fix shipped in this PATCH release:

1. ``synthesis_check`` (dashboard kind) flags the per-step recap
   antipattern: a dashboard organised as one section per workspace
   step ("Step 01", "Step 02", ...) is the bookkeeping leak the
   `synthesis_dashboard` protocol explicitly forbids.

2. ``synthesis_check`` (dashboard kind) flags missing hero / TL;DR /
   headline-finding sections so the first viewport always delivers
   the top-line result.

3. ``synthesis_hygiene`` flags non-canonical synthesis filenames
   (paper-lay.md, REPRODUCIBILITY.md, METHODS.md, CITATIONS.md, ...)
   that downstream tools do not recognise and that come from the AI
   improvising filenames outside the supported synthesis protocols.

4. ``workspace_hygiene`` flags loose files at workspace root that
   aren't one of the canonical rolling logs / certifications file.
   They should live under workspace/scratch/, workspace/logs/, or
   workspace/archive/.

5. ``curate_figures(mode='all')`` curates every step figure (not just
   the focal one) and copies / seeds caption sidecars for each, so a
   dashboard pulling in many per-step figures cannot end up with
   uncaptioned PNGs in synthesis/figures/.
"""

from __future__ import annotations

from pathlib import Path

from research_os.tools.actions.synthesis.check import (
    _check_dashboard,
    synthesis_hygiene,
    workspace_hygiene,
)
from research_os.tools.actions.synthesis.curate import curate_figures


_GOOD_DASHBOARD = """\
<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>p</title></head>
<body>
<header><h1>Project title</h1></header>
<main>
<section id="headline">
  <h2>Headline finding</h2>
  <p>We lifted accuracy by 8.5 pp on the held-out split.</p>
</section>
<section id="key-findings">
  <h2>Key findings — what lifted accuracy</h2>
  <p>One paragraph per finding.</p>
  <img src="figures/01.png" alt="lift histogram" />
</section>
<section id="comparison">
  <h2>What we tried (adopted vs ruled out)</h2>
  <p>Comparison table.</p>
</section>
<section id="methods">
  <h2>Methods</h2>
  <p>One paragraph.</p>
</section>
<section id="limitations">
  <h2>Limitations + open questions</h2>
  <p>One paragraph.</p>
</section>
<section id="references">
  <h2>References</h2>
  <p>Refs.</p>
</section>
</main>
</body>
</html>
"""


_STEP_BY_STEP_DASHBOARD = """\
<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>p</title></head>
<body>
<h1>Project</h1>
<section id="s1"><h2>Step 01 — baseline</h2><img src="a.png" alt="a" /></section>
<section id="s2"><h2>Step 02 — encoder</h2><img src="b.png" alt="b" /></section>
<section id="s3"><h2>Step 03 — rerank</h2><img src="c.png" alt="c" /></section>
<section id="s4"><h2>Step 04 — eval</h2><img src="d.png" alt="d" /></section>
<section id="s5"><h2>Step 05 — final</h2><img src="e.png" alt="e" /></section>
</body>
</html>
"""


def test_dashboard_check_passes_on_story_driven_structure(tmp_path: Path):
    r = _check_dashboard(_GOOD_DASHBOARD, tmp_path)
    assert r["blockers"] == []
    # No step-by-step / no missing-hero warnings on the canonical
    # story-driven scaffold.
    warn_blob = " ".join(r["warnings"]).lower()
    assert "step nn" not in warn_blob
    assert "hero" not in warn_blob


def test_dashboard_check_blocks_step_by_step_recap(tmp_path: Path):
    r = _check_dashboard(_STEP_BY_STEP_DASHBOARD, tmp_path)
    msg = " ".join(r["blockers"]).lower()
    assert "step nn" in msg or "step" in msg
    # 5 'Step NN' headings should trip the BLOCKER threshold (>=4),
    # not just the warning threshold (>=2).
    assert any("section headings" in b.lower() for b in r["blockers"])


def test_dashboard_check_warns_on_missing_hero(tmp_path: Path):
    # No 'headline' / 'TL;DR' / 'hero' / 'key finding' / 'summary' in
    # any heading or section id.
    no_hero = """\
<!doctype html><html><head><title>x</title></head><body>
<h1>p</h1>
<section id="background"><h2>Background</h2><p>x</p></section>
<section id="results"><h2>Results</h2><p>x</p></section>
<section id="conclusion"><h2>Conclusion</h2><p>x</p></section>
</body></html>
"""
    r = _check_dashboard(no_hero, tmp_path)
    warn_blob = " ".join(r["warnings"]).lower()
    assert "hero" in warn_blob or "headline" in warn_blob or "tl;dr" in warn_blob


def test_synthesis_hygiene_flags_forbidden_filenames(tmp_path: Path):
    syn = tmp_path / "synthesis"
    syn.mkdir()
    (syn / "paper.md").write_text("# paper")
    (syn / "paper-lay.md").write_text("# lay")
    (syn / "REPRODUCIBILITY.md").write_text("# repro")
    (syn / "METHODS.md").write_text("# methods")
    (syn / "CITATIONS.md").write_text("# cites")
    (syn / "lay_summary.md").write_text("# canonical lay")
    out = synthesis_hygiene(tmp_path)
    names = {o["name"] for o in out["offenders"]}
    assert "paper-lay.md" in names
    assert "REPRODUCIBILITY.md" in names
    assert "METHODS.md" in names
    assert "CITATIONS.md" in names
    # canonical names pass through
    assert "paper.md" not in names
    assert "lay_summary.md" not in names
    # rename hints are surfaced
    rn = " ".join(out["renames_needed"])
    assert "lay_summary.md" in rn
    assert "[delete]" in rn or "delete" in rn


def test_synthesis_hygiene_ignores_subdirectories(tmp_path: Path):
    syn = tmp_path / "synthesis"
    syn.mkdir()
    (syn / "figures").mkdir()
    (syn / "archive").mkdir()
    (syn / "scripts").mkdir()
    (syn / "dashboard_data").mkdir()
    (syn / "figures" / "anything.md").write_text("anything")
    out = synthesis_hygiene(tmp_path)
    assert out["offenders"] == []


def test_workspace_hygiene_flags_loose_files_and_dirs(tmp_path: Path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    # Canonical files — should pass.
    (ws / "methods.md").write_text("# m")
    (ws / "analysis.md").write_text("# a")
    (ws / "citations.md").write_text("# c")
    (ws / "researcher_certifications.yaml").write_text("v: 1")
    # Canonical dirs — should pass.
    (ws / "logs").mkdir()
    (ws / "scratch").mkdir()
    (ws / "archive").mkdir()
    (ws / "01_baseline").mkdir()
    # Loose offenders — should be flagged.
    (ws / "v2_1_backlog.md").write_text("backlog")
    (ws / "v2_1_plan.md").write_text("plan")
    (ws / "tools.md").write_text("tools")
    (ws / "workflow.mermaid").write_text("graph TD;")
    (ws / "step_completeness_audit.md").write_text("audit")
    (ws / "step_completeness_audit.json").write_text("{}")
    (ws / "planning").mkdir()
    out = workspace_hygiene(tmp_path)
    names = {o["name"] for o in out["offenders"]}
    assert "v2_1_backlog.md" in names
    assert "v2_1_plan.md" in names
    assert "tools.md" in names
    assert "workflow.mermaid" in names
    assert "step_completeness_audit.md" in names
    assert "step_completeness_audit.json" in names
    assert "planning" in names
    # Canonical files + dirs untouched.
    for keep in ("methods.md", "analysis.md", "citations.md",
                 "logs", "scratch", "archive", "01_baseline"):
        assert keep not in names


def test_curate_figures_mode_all_curates_every_step_figure(tmp_path: Path):
    # Build a workspace with two steps, each with two figures and a
    # caption sidecar for one. Mode 'all' must copy every figure plus
    # each figure's caption sidecar (or seed a placeholder).
    ws = tmp_path / "workspace"
    s = ws / "17_sapbert_lora" / "outputs" / "figures"
    s.mkdir(parents=True)
    (s / "17_hits10_by_split.png").write_text("png-bytes-a")
    (s / "17_hits10_by_split.caption.md").write_text("**Figure 17a.** Lift is real.")
    (s / "17_embedding_drift.png").write_text("png-bytes-b")
    # NB: no .caption.md for embedding_drift — placeholder expected.
    s2 = ws / "23_v2_1_final_eval" / "outputs" / "figures"
    s2.mkdir(parents=True)
    (s2 / "23_v2_1_headline.png").write_text("png-bytes-c")
    (s2 / "23_v2_1_headline.caption.md").write_text("**Figure 23.** Final.")

    out = curate_figures(tmp_path, mode="all")
    assert out["status"] == "success"
    assert out["curated"] == 3
    target = tmp_path / "synthesis" / "figures"
    assert (target / "17_hits10_by_split.png").exists()
    assert (target / "17_hits10_by_split.caption.md").exists()
    assert (target / "17_embedding_drift.png").exists()
    # Placeholder caption seeded for the figure without a sidecar.
    placeholder = (target / "17_embedding_drift.caption.md").read_text()
    assert "Caption pending" in placeholder
    assert (target / "23_v2_1_headline.png").exists()
    assert (target / "23_v2_1_headline.caption.md").exists()


def test_curate_figures_focal_mode_remains_default(tmp_path: Path):
    ws = tmp_path / "workspace"
    s = ws / "01_baseline" / "outputs" / "figures"
    s.mkdir(parents=True)
    (s / "01_main.png").write_text("png")
    (s / "01_supplementary.png").write_text("png")
    out = curate_figures(tmp_path)  # default mode='focal'
    assert out["status"] == "success"
    assert out["curated"] == 1  # focal only
    assert out["mode"] == "focal"


def test_curate_figures_rejects_unknown_mode(tmp_path: Path):
    (tmp_path / "workspace").mkdir()
    out = curate_figures(tmp_path, mode="bogus")
    assert out["status"] == "error"
    assert "mode" in out["message"]
