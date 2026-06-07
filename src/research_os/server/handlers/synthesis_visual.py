"""Handlers — synthesis_visual sub-domain.

Carved out of handlers/synthesis.py to stay under the 600-line ceiling.
"""
from __future__ import annotations

from .._handlers_runtime import *  # noqa: F401,F403

__all__ = [
    "_handle_tool_dashboard",
    "_handle_tool_dashboard_story_generate",
    "_handle_tool_dashboard_story_edit",
    "_handle_tool_dashboard_story_quality_bar",
    "_handle_tool_figure_interactive_autogen",
    "_handle_tool_dashboard_reviewer_sim",
    "_handle_tool_slides_create",
    "_handle_tool_poster_create",
    "_handle_tool_dashboard_create",
    "_handle_tool_figure_caption_synthesise",
    "_handle_tool_figure_palette",
    "_handle_tool_figure",
    "_handle_tool_dashboard_test_generate",
    "_handle_tool_dashboard_test_run",
]

def _handle_tool_dashboard(name, arguments, root):
    """Unified dashboard dispatcher.

    Routes operation → the matching per-operation handler. Every legacy
    ``tool_dashboard_*`` name is aliased to this entry point and has its
    operation injected via ``_ALIAS_PARAM_INJECTION`` so callers
    (researchers, scripts, protocols) using the older per-operation
    names keep working unchanged. operation defaults to 'create' when
    omitted — the historically dominant call site.
    """
    op = arguments.get("operation") or "create"
    handler_name = _DASHBOARD_DISPATCH.get(op)
    if not handler_name:
        valid = ", ".join(sorted(_DASHBOARD_DISPATCH))
        return _text(_error(
            f"tool_dashboard: unknown operation '{op}'. "
            f"Valid operations: {valid}."
        ))
    handler = globals().get(handler_name)
    if not callable(handler):
        return _text(_error(
            f"tool_dashboard: handler '{handler_name}' is not callable."
        ))
    return handler(name, arguments, root)


def _handle_tool_dashboard_story_generate(name, arguments, root):
    from research_os.tools.actions.synthesis.dashboard_story import (
        dashboard_story_generate,
    )
    res = dashboard_story_generate(root)
    if res.get("status") == "error":
        return _text(_error(res.get("message", "dashboard_story_generate failed")))
    return _text(_success(res))


def _handle_tool_dashboard_story_edit(name, arguments, root):
    from research_os.tools.actions.synthesis.dashboard_story import (
        dashboard_story_edit,
    )
    res = dashboard_story_edit(
        root,
        edits=arguments.get("edits"),
        mode=arguments.get("mode", "patch"),
    )
    if res.get("status") == "error":
        return _text(_error(res.get("message", "dashboard_story_edit failed")))
    return _text(_success(res))


def _handle_tool_dashboard_story_quality_bar(name, arguments, root):
    from research_os.tools.actions.synthesis.dashboard_story import (
        dashboard_story_quality_bar,
    )
    res = dashboard_story_quality_bar(root)
    if res.get("status") == "error":
        return _text(_error(res.get("message", "dashboard_story_quality_bar failed")))
    return _text(_success(res))


def _handle_tool_figure_interactive_autogen(name, arguments, root):
    from research_os.tools.actions.audit.figure_interactivity import (
        figure_interactive_autogen,
    )

    fig_path = Path(arguments["figure_path"])
    if not fig_path.is_absolute():
        fig_path = root / fig_path
    if not fig_path.exists():
        return _text(_error(f"figure not found: {fig_path}"))
    res = figure_interactive_autogen(fig_path, root)
    if res.get("status") == "error":
        return _text(_error(res.get("message", "figure_interactive_autogen failed")))
    return _text(_success(res))


def _handle_tool_dashboard_reviewer_sim(name, arguments, root):
    from research_os.tools.actions.audit.dashboard_content import reviewer_simulator

    dpath = root / arguments.get("dashboard_path", "synthesis/dashboard.html")
    if not dpath.exists():
        return _text(_error(f"{dpath.name} not found. Run tool_dashboard(operation='create') first."))
    html = dpath.read_text(encoding="utf-8", errors="replace")
    return _text(_success(reviewer_simulator(html)))


def _handle_tool_slides_create(name, arguments, root):
    """tool_slides_create — real engine (Reveal.js HTML / Touying Typst)."""
    from research_os.tools.actions.synthesis.drafter_loop import (
        draft_with_review_rewrite,
        persona_reviewer,
    )
    from research_os.tools.actions.synthesis.slides import compile_slides
    from research_os.tools.actions.state.config import get_research_config

    cfg = get_research_config(root) or {}
    synth = cfg.get("synthesis") or {}
    loop_enabled = bool(synth.get("drafter_loop_enabled", True))
    # Slides default is 2 iterations per spec; researcher can raise via
    # drafter_loop_max_iterations.
    max_iter = int(
        synth.get(
            "drafter_loop_max_iterations_slides",
            min(2, int(synth.get("drafter_loop_max_iterations", 3))),
        )
    )
    threshold = float(synth.get("drafter_loop_quality_threshold", 0.10))
    tier = (cfg.get("project_tier") or "production").strip().lower()
    if tier == "throwaway":
        max_iter = 1
    if arguments.get("drafter_loop") is False:
        loop_enabled = False

    def _do_compile():
        return compile_slides(
            root,
            engine=arguments.get("engine", "reveal"),
            template=arguments.get("template", "conference_15min"),
            theme=arguments.get("theme", ""),
            speaker_notes_enabled=bool(
                arguments.get("speaker_notes_enabled", True)
            ),
            print_handout=bool(arguments.get("print_handout", True)),
            audience=arguments.get("audience"),
            output_format=arguments.get("output_format"),
        )

    try:
        if not loop_enabled:
            result = _do_compile()
        else:
            def _drafter(prior_output=None, findings=None, root=root):
                return _do_compile()
            reviewer = persona_reviewer(
                ["presentation_critic", "scope_creep_critic"]
            )
            loop_res = draft_with_review_rewrite(
                _drafter,
                reviewer,
                drafter_name="slides",
                root=Path(root),
                max_iter=max_iter,
                improvement_threshold=threshold,
            )
            result = loop_res.get("final_output") or {}
            if isinstance(result, dict):
                result["drafter_loop"] = {
                    "iterations": loop_res["iterations"],
                    "converged": loop_res["converged"],
                    "stop_reason": loop_res["stop_reason"],
                    "quality_progression": loop_res["quality_progression"],
                }
    except Exception as exc:
        return _text(_error(f"tool_slides_create crashed: {exc}"))
    if result.get("status") != "success":
        return _text(_error(result.get("message", "slide compilation failed")))
    return _text(_success(result))


def _handle_tool_poster_create(name, arguments, root):
    from research_os.tools.actions.synthesis.drafter_loop import (
        draft_with_review_rewrite,
        persona_reviewer,
    )
    from research_os.tools.actions.synthesis.poster_typst import compile_poster
    from research_os.tools.actions.state.config import get_research_config

    cfg = get_research_config(root) or {}
    synth = cfg.get("synthesis") or {}

    # The legacy tikzposter LaTeX path is gone. `engine` and
    # `poster_engine` are still accepted for back-compat but anything
    # other than typst is a hard error directing the caller to the
    # supported Typst path.
    engine = (arguments.get("engine") or synth.get("poster_engine") or "typst").lower()
    if engine != "typst":
        return _text(_error(
            f"poster engine '{engine}' is no longer supported. "
            "The tikzposter LaTeX path has been removed; "
            "tool_poster_create now renders via Typst only. "
            "Remove the engine= argument (or set "
            "researcher_config.synthesis.poster_engine='typst')."
        ))

    # Typst. Pull template/theme/qr/handout from config when the caller
    # didn't override.
    template = arguments.get("template")
    theme = arguments.get("theme")
    qr_url = arguments.get("qr_url")
    handout_pdf = arguments.get("handout_pdf")
    if template is None:
        template = synth.get("poster_template", "academic_36x48")
    if theme is None:
        theme = synth.get("poster_theme", "light")
    if qr_url is None:
        qr_url = synth.get("poster_qr_url") or None
    if handout_pdf is None:
        handout_pdf = bool(synth.get("poster_handout_pdf", True))

    loop_enabled = bool(synth.get("drafter_loop_enabled", True))
    max_iter = int(
        synth.get(
            "drafter_loop_max_iterations_poster",
            min(2, int(synth.get("drafter_loop_max_iterations", 3))),
        )
    )
    threshold = float(synth.get("drafter_loop_quality_threshold", 0.10))
    tier = (cfg.get("project_tier") or "production").strip().lower()
    if tier == "throwaway":
        max_iter = 1
    if arguments.get("drafter_loop") is False:
        loop_enabled = False

    def _do_compile():
        return compile_poster(
            root,
            template=template,
            theme=theme,
            qr_url=qr_url,
            handout_pdf=bool(handout_pdf),
        )

    if not loop_enabled:
        return _text(_success(_do_compile()))

    def _drafter(prior_output=None, findings=None, root=root):
        return _do_compile()

    reviewer = persona_reviewer(
        ["presentation_critic", "novelty_critic"]
    )
    loop_res = draft_with_review_rewrite(
        _drafter,
        reviewer,
        drafter_name="poster",
        root=Path(root),
        max_iter=max_iter,
        improvement_threshold=threshold,
    )
    result = loop_res.get("final_output") or {}
    if isinstance(result, dict):
        result["drafter_loop"] = {
            "iterations": loop_res["iterations"],
            "converged": loop_res["converged"],
            "stop_reason": loop_res["stop_reason"],
            "quality_progression": loop_res["quality_progression"],
        }
    return _text(_success(result))


def _handle_tool_dashboard_create(name, arguments, root):
    from research_os.tools.actions.audit.audit import audit_step_completeness
    from research_os.tools.actions.synthesis.latex import create_dashboard
    from research_os.project_ops import log_override, validate_override_rationale
    from research_os.tools.actions.state.config import get_interaction_policy

    override_requested = bool(arguments.get("override_completeness_gate", False))
    rationale = arguments.get("override_rationale")
    completeness_warnings: list[str] | None = None
    policy = get_interaction_policy(root)["quality_gate_policy"]
    if (policy == "enforce" and override_requested
            and (not rationale or not str(rationale).strip())):
        return _text(_error(
            "interaction.quality_gate_policy=enforce: override_completeness_gate=true "
            "requires a one-line override_rationale."
        ))
    if override_requested and rationale:
        thin = validate_override_rationale(rationale)
        if thin is not None:
            return _text(thin)

    gate = audit_step_completeness(root)
    if gate.get("status") == "error":
        completeness_warnings = gate.get("blockers")
        if override_requested:
            # Real bypass: blockers existed AND researcher authorised
            # suppression of the warning panel. Log it for the audit.
            log_override(
                root,
                tool="tool_dashboard_create",
                gate="step_completeness",
                rationale=rationale,
                extra={"blocker_count": len(completeness_warnings or [])},
            )

    legacy = bool(arguments.get("dashboard_legacy", False))
    if legacy:
        res = create_dashboard(
            root,
            title=arguments.get("title"),
            audience=arguments.get("audience", "academic"),
            suppress_audit_panel=override_requested and bool(completeness_warnings),
        )
    else:
        from research_os.tools.actions.synthesis.dashboard_app import render_dashboard_app
        res = render_dashboard_app(
            root,
            title=arguments.get("title"),
            audience=arguments.get("audience", "academic"),
            default_mode=arguments.get("dashboard_default_mode", "explore"),
            search_enabled=bool(arguments.get("dashboard_search_enabled", True)),
            print_optimized=bool(arguments.get("dashboard_print_optimized", True)),
            suppress_audit_panel=override_requested and bool(completeness_warnings),
        )
    if res.get("status") == "success":
        if completeness_warnings and not override_requested:
            res["completeness_warnings"] = completeness_warnings
            res["advice"] = (
                "Dashboard rendered, but step-completeness audit flagged "
                f"{len(completeness_warnings)} blocker(s). "
                "Resolve them before the FINAL deliverable."
            )
        return _text(_success(res))
    return _text(_error(res.get("message", "dashboard create failed")))


def _handle_tool_figure_caption_synthesise(name, arguments, root):
    from research_os.tools.actions.viz import caption_synthesise

    res = caption_synthesise(
        root=root,
        figure_path=arguments["figure_path"],
        technical_caption=arguments.get("technical_caption"),
        findings_context=arguments.get("findings_context"),
        overwrite=bool(arguments.get("overwrite", False)),
    )
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "caption_synthesise failed")))


def _handle_tool_figure_palette(name, arguments, root):
    from research_os.tools.actions.viz import palette_for

    colors = palette_for(arguments.get("kind", "qualitative"),
                         n=int(arguments.get("n", 8)))
    return _text(_success({"kind": arguments.get("kind", "qualitative"),
                           "colors": colors}))


def _handle_tool_figure(name, arguments, root):
    """Unified figure dispatcher.

    Operations:
      palette             → tool_figure_palette             (CVD-safe colour palette)
      caption_synthesise  → tool_figure_caption_synthesise  (plain-English <name>.summary.md)
      interactive_autogen → tool_figure_interactive_autogen (interactive HTML companion)
      paper_autoembed     → tool_paper_figures_autoembed    (embed figures into synthesis/paper.md)

    Every legacy ``tool_figure_palette`` / ``tool_figure_caption_synthesise``
    / ``tool_figure_interactive_autogen`` / ``tool_paper_figures_autoembed``
    name is aliased to this entry point and has its operation injected via
    ``_ALIAS_PARAM_INJECTION`` so callers (researchers, scripts, protocols)
    using the older per-operation names keep working unchanged.
    """
    op = arguments.get("operation")
    if not op:
        return _text(_error(
            "tool_figure requires operation='palette'|'caption_synthesise'|"
            "'interactive_autogen'|'paper_autoembed'."
        ))
    if op == "palette":
        return _handle_tool_figure_palette(name, arguments, root)
    if op == "caption_synthesise":
        return _handle_tool_figure_caption_synthesise(name, arguments, root)
    if op == "interactive_autogen":
        return _handle_tool_figure_interactive_autogen(name, arguments, root)
    if op == "paper_autoembed":
        return _handle_tool_paper_figures_autoembed(name, arguments, root)
    return _text(_error(
        f"tool_figure: unknown operation '{op}'. "
        "Valid: palette | caption_synthesise | interactive_autogen | paper_autoembed."
    ))


def _handle_tool_dashboard_test_generate(name, arguments, root):
    from research_os.tools.actions.viz.dashboard_tests import (
        generate_dashboard_test_suite,
    )

    return _text(_success(generate_dashboard_test_suite(
        root, overwrite=bool(arguments.get("overwrite", False)),
    )))


def _handle_tool_dashboard_test_run(name, arguments, root):
    from research_os.tools.actions.viz.dashboard_tests import run_dashboard_tests

    return _text(_success(run_dashboard_tests(
        root,
        only=arguments.get("only"),
        visual=bool(arguments.get("visual", False)),
        update_snapshots=bool(arguments.get("update_snapshots", False)),
        timeout=int(arguments.get("timeout", 300)),
    )))


HANDLERS = {
    "tool_dashboard": _handle_tool_dashboard,
    "tool_slides_create": _handle_tool_slides_create,
    "tool_poster_create": _handle_tool_poster_create,
    "tool_figure": _handle_tool_figure,
}
