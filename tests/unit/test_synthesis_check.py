"""Topic-named regression tests for the synthesis check + scaffold gates.

Covers:

1. ``synthesis_check`` (dashboard kind) flags the per-step recap
   antipattern: a dashboard organised as one section per workspace
   step ("Step 01", "Step 02", ...) is the bookkeeping leak the
   `synthesis_dashboard` protocol explicitly forbids. (v2.4.2)

2. ``synthesis_check`` (dashboard kind) flags missing hero / TL;DR /
   headline-finding sections so the first viewport always delivers
   the top-line result. (v2.4.2)

3. ``synthesis_hygiene`` flags non-canonical synthesis filenames
   (paper-lay.md, REPRODUCIBILITY.md, METHODS.md, CITATIONS.md, ...)
   that downstream tools do not recognise and that come from the AI
   improvising filenames outside the supported synthesis protocols.
   (v2.4.2)

4. ``workspace_hygiene`` flags loose files at workspace root that
   aren't one of the canonical rolling logs / certifications file.
   They should live under workspace/scratch/, workspace/logs/, or
   workspace/archive/. (v2.4.2)

5. ``curate_figures(mode='all')`` curates every step figure (not just
   the focal one) and copies / seeds caption sidecars for each, so a
   dashboard pulling in many per-step figures cannot end up with
   uncaptioned PNGs in synthesis/figures/. (v2.4.2)

6. ``output_types_gate`` consults
   ``researcher_config.yaml#research_goal.output_types`` and returns
   ``ask`` when the requested synthesis kind isn't declared. Empty
   ``output_types`` falls through to ``proceed`` so unfilled
   projects don't trip the gate. (v2.4.3)

7. ``synthesis_scaffold`` returns ``status='ask'`` instead of
   writing when the gate verdict is ``ask`` and the caller hasn't
   passed ``confirmed=true`` or ``overwrite=true``. (v2.4.3)

8. ``get_next_protocol`` filters the synthesis tail by declared
   ``output_types`` instead of hardcoding ``synthesis_paper`` as
   the terminal step. Empty ``output_types`` preserves the v2.4.2
   ``synthesis_paper`` fallback. (v2.4.3)

Filename note: this file was renamed from
``test_v242_synthesis_dashboard_lints.py`` in v2.4.3 to drop the
per-release naming convention. New tests for this surface should
land here, not in a new ``test_v<version>_*.py`` file.
"""

from __future__ import annotations

from pathlib import Path

from research_os.tools.actions.synthesis.check import (
    _check_dashboard,
    _check_poster,
    _check_slides,
    output_types_gate,
    synthesis_hygiene,
    workspace_hygiene,
)
from research_os.tools.actions.synthesis.curate import curate_figures
from research_os.tools.actions.synthesis.scaffold import SCAFFOLDS, synthesis_scaffold


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
    # Canonical workspace-root files — should NOT be flagged.
    (ws / "tools.md").write_text("tools")
    (ws / "workflow.mermaid").write_text("graph TD;")
    # Loose offenders — should be flagged.
    (ws / "v2_1_backlog.md").write_text("backlog")
    (ws / "v2_1_plan.md").write_text("plan")
    # A stale root-level audit dump left by a pre-3.2 release is clutter
    # (per-gate audits now live in workspace/logs/), so it's flagged.
    (ws / "step_completeness_audit.md").write_text("audit")
    (ws / "step_completeness_audit.json").write_text("{}")
    (ws / "planning").mkdir()
    out = workspace_hygiene(tmp_path)
    names = {o["name"] for o in out["offenders"]}
    assert "v2_1_backlog.md" in names
    assert "v2_1_plan.md" in names
    assert "step_completeness_audit.md" in names
    assert "step_completeness_audit.json" in names
    assert "planning" in names
    # Canonical files + dirs untouched (tools.md + workflow.mermaid are
    # Research-OS-generated workspace-root files, not clutter).
    for keep in ("methods.md", "analysis.md", "citations.md", "tools.md",
                 "workflow.mermaid", "logs", "scratch", "archive",
                 "01_baseline"):
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


# ---------------------------------------------------------------------------
# v2.4.3: output_types intent gate + scaffold + get_next_protocol
# ---------------------------------------------------------------------------


def _seed_config(tmp_path: Path, output_types: list[str]) -> None:
    """Write a minimal researcher_config.yaml with the given output_types."""
    inputs = tmp_path / "inputs"
    inputs.mkdir(exist_ok=True)
    lines = ["research_goal:", "  output_types:"]
    for t in output_types:
        lines.append(f"    - {t}")
    if not output_types:
        # Preserve YAML validity for "empty list" case.
        lines[-1] = "  output_types: []"
    (inputs / "researcher_config.yaml").write_text("\n".join(lines) + "\n")


def test_output_types_gate_proceeds_when_kind_in_declared(tmp_path: Path):
    _seed_config(tmp_path, ["paper", "dashboard"])
    out = output_types_gate(tmp_path, "dashboard")
    assert out["verdict"] == "proceed"
    assert "dashboard" in out["declared_outputs"]
    assert out["message"] == ""


def test_output_types_gate_asks_when_kind_not_declared(tmp_path: Path):
    _seed_config(tmp_path, ["dashboard"])
    out = output_types_gate(tmp_path, "paper")
    assert out["verdict"] == "ask"
    assert out["declared_outputs"] == ["dashboard"]
    assert "paper" in out["message"]
    assert "dashboard" in out["message"]


def test_output_types_gate_proceeds_on_empty_or_missing(tmp_path: Path):
    # Empty list.
    _seed_config(tmp_path, [])
    out = output_types_gate(tmp_path, "paper")
    assert out["verdict"] == "proceed"
    # No config file at all (fresh project).
    import shutil
    shutil.rmtree(tmp_path / "inputs")
    out2 = output_types_gate(tmp_path, "paper")
    assert out2["verdict"] == "proceed"


def test_output_types_gate_normalises_aliases(tmp_path: Path):
    # `lay-summary` (hyphen) should map to canonical lay_summary.
    _seed_config(tmp_path, ["lay_summary"])
    out = output_types_gate(tmp_path, "lay-summary")
    assert out["verdict"] == "proceed"


def test_output_types_gate_ignores_exploratory(tmp_path: Path):
    # `exploratory` is the "no deliverable yet" marker — it must NOT
    # by itself satisfy a paper / dashboard request.
    _seed_config(tmp_path, ["exploratory"])
    out = output_types_gate(tmp_path, "paper")
    # Filtered out → declared list is empty → falls back to proceed.
    assert out["verdict"] == "proceed"
    assert out["declared_outputs"] == []


def test_scaffold_returns_ask_when_kind_not_declared(tmp_path: Path):
    _seed_config(tmp_path, ["dashboard"])
    out = synthesis_scaffold(tmp_path, kind="paper")
    assert out["status"] == "ask"
    assert "paper" in out["message"]
    # Crucially: nothing was written.
    assert not (tmp_path / "synthesis" / "paper.typ").exists()


def test_scaffold_proceeds_with_confirmed_true(tmp_path: Path):
    _seed_config(tmp_path, ["dashboard"])
    out = synthesis_scaffold(tmp_path, kind="paper", confirmed=True)
    assert out["status"] == "success"
    assert (tmp_path / "synthesis" / "paper.typ").exists()


def test_scaffold_proceeds_when_kind_is_declared(tmp_path: Path):
    _seed_config(tmp_path, ["dashboard", "paper"])
    out = synthesis_scaffold(tmp_path, kind="paper")
    assert out["status"] == "success"
    assert (tmp_path / "synthesis" / "paper.typ").exists()


def test_scaffold_proceeds_on_empty_output_types(tmp_path: Path):
    _seed_config(tmp_path, [])
    out = synthesis_scaffold(tmp_path, kind="dashboard")
    assert out["status"] == "success"
    assert (tmp_path / "synthesis" / "dashboard.html").exists()


def test_get_next_protocol_respects_dashboard_only(tmp_path: Path):
    from research_os.tools.actions.protocol import _full_pipeline
    _seed_config(tmp_path, ["dashboard"])
    tail = [name for name, _ in _full_pipeline(tmp_path)]
    assert tail[-1] == "synthesis/synthesis_dashboard"
    assert "synthesis/synthesis_paper" not in tail


def test_get_next_protocol_respects_multi_output_order(tmp_path: Path):
    from research_os.tools.actions.protocol import _full_pipeline
    _seed_config(tmp_path, ["paper", "lay_summary"])
    tail_names = [n for n, _ in _full_pipeline(tmp_path)]
    # Both synthesis protocols present, in declared order.
    assert tail_names[-2:] == [
        "synthesis/synthesis_paper",
        "synthesis/synthesis_lay_summary",
    ]


def test_get_next_protocol_empty_falls_back_to_paper(tmp_path: Path):
    from research_os.tools.actions.protocol import _full_pipeline
    _seed_config(tmp_path, [])
    tail_names = [n for n, _ in _full_pipeline(tmp_path)]
    # v2.4.2 backwards-compat: empty output_types → paper terminal.
    assert tail_names[-1] == "synthesis/synthesis_paper"


def test_synthesis_check_envelope_includes_intent_gate(tmp_path: Path):
    """synthesis_check should surface intent_gate alongside hygiene."""
    from research_os.tools.actions.synthesis.check import synthesis_check
    _seed_config(tmp_path, ["dashboard"])
    syn = tmp_path / "synthesis"
    syn.mkdir()
    (syn / "paper.typ").write_text("// stub\n= Introduction\nbody\n")
    res = synthesis_check(tmp_path, file="synthesis/paper.typ")
    assert "intent_gate" in res
    assert res["intent_gate"]["verdict"] == "ask"
    # Warning surfaces the mismatch in human-readable form.
    assert any("dashboard" in w for w in res.get("warnings", []))


# ── SYN-2 / SYN-3 / SYN-8: dashboard scan correctness ────────────────


def test_check_dashboard_ignores_commented_markup(tmp_path: Path):
    """Markup inside <!-- ... --> is inert and must not trip the
    alt-text / <section> / placeholder scans (the bundled scaffold
    otherwise blocks its own audit). (SYN-2)"""
    html = (
        "<html><body>\n"
        "<!-- <img src=x.png>  TODO: fix  <section>no id</section> -->\n"
        "<h1>Headline finding</h1>\n"
        "<h2>A</h2><h2>B</h2>\n"
        '<img src="real.png" alt="a real image">\n'
        '<section id="hero">The finding: 42% lift over baseline.</section>\n'
        "</body></html>"
    )
    res = _check_dashboard(html, tmp_path)
    assert res["blockers"] == [], res["blockers"]


def test_check_dashboard_blocks_single_quoted_external_script(tmp_path: Path):
    """A single-quoted external <script src='https://...'> must still be
    caught as an offline-invariant violation. (SYN-3)"""
    html = (
        "<html><head>"
        "<script src='https://cdn.example.com/x.js'></script>"
        "</head><body><h1>x</h1></body></html>"
    )
    res = _check_dashboard(html, tmp_path)
    assert any(
        "offline" in b.lower() or "external script" in b.lower()
        for b in res["blockers"]
    ), res["blockers"]


def test_check_dashboard_data_alt_does_not_satisfy_alt(tmp_path: Path):
    """`data-alt=` must NOT satisfy the alt-text requirement. (SYN-8)"""
    html = (
        "<html><body><h1>x</h1><h2>a</h2><h2>b</h2>"
        '<img src="z.png" data-alt="nope">'
        '<section id="hero">finding 42%</section></body></html>'
    )
    res = _check_dashboard(html, tmp_path)
    assert any("alt text" in b.lower() for b in res["blockers"]), res["blockers"]


def test_check_dashboard_real_alt_satisfies(tmp_path: Path):
    html = (
        "<html><body><h1>x</h1><h2>a</h2><h2>b</h2>"
        '<img src="z.png" alt="a described image">'
        '<section id="hero">finding 42%</section></body></html>'
    )
    res = _check_dashboard(html, tmp_path)
    assert not any("alt text" in b.lower() for b in res["blockers"]), res["blockers"]


# ---------------------------------------------------------------------------
# Design lints (WARN-only) on poster + slides — 3.2.7.
# They must fire on hand-rolled overrides but stay SILENT on clean scaffolds
# (sizing + colour are delegated to the bundled templates).
# ---------------------------------------------------------------------------


def test_scaffolded_poster_trips_no_design_warnings():
    """A clean scaffolded poster has no inline pt sizing or rgb() fills, so the
    font-floor and CVD-colour lints must NOT fire (false-positive guard)."""
    _rel, body = SCAFFOLDS["poster"]
    res = _check_poster(body)
    assert res["hardcoded_font_pt"] == []
    assert res["hardcoded_hex_count"] == 0
    assert not any("hard-codes" in w for w in res["warnings"]), res["warnings"]


def test_handrolled_poster_trips_font_and_colour_lints():
    text = (
        '#set text(size: 10pt)\n'
        '#text(fill: rgb("#ff0000"))[a]\n'
        '#text(fill: rgb("#00ff00"))[b]\n'
        '#text(fill: rgb("#0000ff"))[c]\n'
        "= Background\n= Methods\n= Results\n"
    )
    res = _check_poster(text)
    assert 10.0 in res["hardcoded_font_pt"]
    assert res["hardcoded_hex_count"] >= 3
    assert any("read across a" in w for w in res["warnings"]), res["warnings"]
    assert any("colour-vision-deficiency" in w for w in res["warnings"]), res["warnings"]


def test_poster_size_string_is_not_a_font_size():
    """`size: "36x48"` (the poster dimensions) must not be read as a tiny font."""
    text = '#show: poster.with(size: "36x48")\n= A\n= B\n= C\n'
    res = _check_poster(text)
    assert res["hardcoded_font_pt"] == []
    assert not any("read across a" in w for w in res["warnings"]), res["warnings"]


def test_scaffolded_slides_trip_no_colour_warning():
    _rel, body = SCAFFOLDS["slides"]
    res = _check_slides(body)
    assert res["hardcoded_hex_count"] == 0
    assert not any("hard-codes" in w for w in res["warnings"]), res["warnings"]


def test_handrolled_deck_trips_colour_lint():
    text = (
        "#slide[a]\n#slide[b]\n#slide[c]\n#slide[d]\n"
        '#text(fill: rgb("#ff0000"))[x] rgb("#00ff00") rgb("#123456")\n'
    )
    res = _check_slides(text)
    assert res["hardcoded_hex_count"] >= 3
    assert any("colour-vision-deficiency" in w for w in res["warnings"]), res["warnings"]


def test_handout_scaffold_uses_bundled_font_not_inter():
    """D2: the handout must not request the unbundled 'Inter' family (it would
    warn + silently fall back); it uses the bundled NCM Sans like the others."""
    _rel, body = SCAFFOLDS["handout"]
    assert 'font: "Inter"' not in body
    assert "New Computer Modern Sans" in body


def test_handout_in_single_page_overflow_targets():
    """D8: a handout that overflows its one A4 page must trip the overflow gate."""
    from research_os.tools.actions.synthesis.typst_compile import _SINGLE_PAGE_TARGETS

    assert "handout" in _SINGLE_PAGE_TARGETS
