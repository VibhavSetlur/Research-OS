"""Verify the action-module subfolder layout exposes everything cleanly.

After the v1.0.0 cleanup, the back-compat shims at the flat ``tools/actions/``
level were removed. Every import now goes through the proper package paths.
"""


def test_subpackage_imports():
    """The eight subpackages expose every public function via their __init__."""
    # state/
    from research_os.tools.actions.state import (  # noqa: F401
        abandon_path,
        create_checkpoint,
        create_path,
        get_config,
        init_config,
        list_checkpoints,
        list_paths,
        notify_researcher,
        rollback_checkpoint,
        scratch_clear,
        scratch_list,
        scratch_run,
        scratch_write,
        session_handoff,
        set_config,
        validate_config,
        workspace_repair,
    )

    # data/
    from research_os.tools.actions.data import (  # noqa: F401
        _profile_inputs,
        context_intake,
        data_convert,
        data_profile,
        data_sample,
        intake_autofill,
    )

    # exec/
    from research_os.tools.actions.exec import (  # noqa: F401
        env_docker_generate,
        env_snapshot,
        execute_bash_script,
        execute_julia_script,
        execute_notebook,
        execute_r_script,
        package_install,
        render_rmarkdown,
        task_kill,
        task_list,
        task_run,
        task_status,
    )

    # search/
    from research_os.tools.actions.search import (  # noqa: F401
        download_literature,
        retrieve_literature,
        scrape_web,
        search_arxiv,
        search_crossref,
        search_pubmed,
        search_semantic_scholar,
        search_web,
    )

    # research/
    from research_os.tools.actions.research import (  # noqa: F401
        branch_recommendation,
        external_tool_instructions,
        plan_next_step,
        plan_step,
        research_method,
        research_tool,
    )

    # audit/
    from research_os.tools.actions.audit import (  # noqa: F401
        audit_assumptions,
        audit_citations,
        audit_figure,
        audit_power,
        audit_reproducibility_full,
        audit_synthesis,
        get_current_path,
        validate_md_template,
    )

    # synthesis/
    # NOTE: ``create_poster`` (the tikzposter LaTeX renderer) was
    # removed in v2.0.0 (phase-14b). Poster compilation now lives
    # exclusively in ``synthesis/poster_typst.py:compile_poster``.
    from research_os.tools.actions.synthesis import (  # noqa: F401
        cap_for,
        collect_for_section,
        create_dashboard,
        format_apa,
        format_bib,
        format_vancouver,
        latex_compile,
        synthesize_plan,
        synthesize_workspace,
        verify_all_in_workspace,
        verify_citation_key,
        write_references_bib,
    )

    # memory/
    from research_os.tools.actions.memory import (  # noqa: F401
        hypothesis_add,
        hypothesis_list,
        hypothesis_update,
    )

    # protocol.py stays at top level (it's the loader — fundamental).
    from research_os.tools.actions.protocol import (  # noqa: F401
        get_next_protocol,
        get_protocol_history,
        list_protocols,
        load_protocol,
        log_protocol_execution,
        validate_protocol,
    )


def test_top_level_actions_namespace_is_minimal():
    """Tightly allowlisted top-level modules at tools/actions/.

    These are the cross-cutting modules that touch every category and
    would create a circular sub-package if nested:
      - protocol.py — YAML loader + protocol-completion injector
      - router.py   — sys_boot + tool_route + trigger-based hierarchy
      - semantic.py — embedding-based semantic router (sibling of router)
      - listers.py  — flat protocol + tool catalog listers (re-exports
                       from protocol.py + reads server.TOOL_DEFINITIONS)

    Anything else MUST be moved into the appropriate subpackage (state/,
    data/, exec/, search/, research/, audit/, synthesis/, memory/)."""
    from pathlib import Path

    actions_dir = (
        Path(__file__).resolve().parent.parent.parent
        / "src" / "research_os" / "tools" / "actions"
    )
    flat_py_files = sorted(
        f.name for f in actions_dir.iterdir()
        if f.is_file() and f.suffix == ".py"
    )
    assert flat_py_files == [
        "__init__.py", "listers.py", "protocol.py", "router.py", "semantic.py",
    ], (
        f"Unexpected flat .py files in tools/actions/: {flat_py_files}. "
        "Move them into the right subpackage."
    )
