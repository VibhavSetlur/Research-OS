"""State compression utilities for Research Copilot.

Provides deterministic, zero-cost head/tail compression of node outputs
to prevent catastrophic context window overflow.
"""

import sqlite3
from pathlib import Path

from research_copilot.core.hooks import hook_engine
from research_copilot.utils.asset_manager import AssetManager


_HEAD_CHARS = 250
_TAIL_CHARS = 250
_TRUNCATION_MARKER = "\n...[DATA TRUNCATED]...\n"


def compress_output_heuristic(text: str, max_chars: int = 500) -> str:
    """Deterministic head/tail compressor for node output text.

    Preserves the first *head* characters (command invocation, shapes, early
    diagnostics) and the last *tail* characters (final metric, result, or
    traceback), separated by a truncation marker.  No LLM required.

    Args:
        text:      Raw output string from a DAG node.
        max_chars: Total character budget.  Defaults to 500 (250 head + 250
                   tail).  Must be >= 10.

    Returns:
        Compressed string ≤ max_chars + len(marker) characters, or the
        original string unchanged if it already fits.
    """
    if len(text) <= max_chars:
        return text

    head = max_chars // 2
    tail = max_chars - head

    head_part = text[:head].rstrip()
    tail_part = text[-tail:].lstrip()

    return head_part + _TRUNCATION_MARKER + tail_part


# ---------------------------------------------------------------------------
# Legacy alias kept for any callers that used compress_output() directly.
# ---------------------------------------------------------------------------
def compress_output(output_text: str) -> str:
    """Backwards-compatible wrapper around compress_output_heuristic."""
    return compress_output_heuristic(output_text)


@hook_engine.register("post_execution")
def compress_state_hook(state: dict, **kwargs) -> dict:
    """Post-execution hook: compress output and persist raw text to SQLite."""
    node_id = kwargs.get("node_id")
    if not node_id:
        return state

    output_text = state.get("last_output", "")
    summary = compress_output_heuristic(output_text)

    root = AssetManager.find_project_root()
    db_path = root / ".research" / "cache" / "state_cache.sqlite"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS outputs (node_id TEXT PRIMARY KEY, raw_output TEXT)"
    )
    cursor.execute(
        "INSERT OR REPLACE INTO outputs (node_id, raw_output) VALUES (?, ?)",
        (node_id, output_text),
    )
    conn.commit()
    conn.close()

    # Append compressed summary to global context roll-up.
    current_summary = state.get("global_context_summary", "")
    state["global_context_summary"] = current_summary + f"\nNode {node_id}: {summary}"

    # Flush raw output; keep only compressed version in live state.
    if "last_output" in state:
        state["immediate_previous_output"] = state["last_output"]
        state["last_output"] = summary

    return state
