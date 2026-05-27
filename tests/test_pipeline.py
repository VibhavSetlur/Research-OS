"""Pipeline progression test — sys_protocol_next should walk in order."""

from research_os.project_ops import scaffold_minimal_workspace
from research_os.tools.actions.protocol import get_next_protocol, log_protocol_execution


def _complete(root, protocol_name):
    log_protocol_execution(root, protocol_name, "completed", "test")


def test_fresh_workspace_starts_at_session_boot(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Test")
    # Manually clear the execution log scaffold may have created.
    log = tmp_path / ".os_state" / "protocol_execution_log.jsonl"
    if log.exists():
        log.unlink()
    res = get_next_protocol(tmp_path)
    assert res["next_protocol"] == "guidance/session_boot"


def test_after_session_boot_goes_to_project_startup(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Test")
    _complete(tmp_path, "guidance/session_boot")
    res = get_next_protocol(tmp_path)
    assert res["next_protocol"] == "guidance/project_startup"


def test_after_project_startup_goes_to_domain_analysis(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Test")
    _complete(tmp_path, "guidance/session_boot")
    _complete(tmp_path, "guidance/project_startup")
    res = get_next_protocol(tmp_path)
    assert res["next_protocol"] == "domain/domain_analysis"


def test_walk_all_pipeline_stages(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Test")
    chain = [
        "guidance/session_boot",
        "guidance/project_startup",
        "domain/domain_analysis",
        "domain/research_design",
        "methodology/methodology_selection",
        "literature/literature_search",
    ]
    seen = []
    for expected in chain:
        res = get_next_protocol(tmp_path)
        seen.append(res["next_protocol"])
        _complete(tmp_path, expected)
    assert seen == chain
