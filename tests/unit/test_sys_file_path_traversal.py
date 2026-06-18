"""Path-containment guard tests for sys_file_* handlers (W02).

Verifies that the MCP file handlers reject:
  * ``../../etc/passwd`` style relative escapes
  * absolute paths that fall outside the project root
  * symlinks that point outside the project root
  * writes to .os_state/ (and reads/lists/deletes from same)

Plus that the central ``check_write_permitted`` honours the new ``root``
parameter (only the root-relative path components are inspected, not
ancestor directories named ``inputs`` that just happen to host the
project).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from research_os.errors import WriteProtectedError, check_write_permitted
from research_os.server.handlers.meta_workspace import (
    _resolve_inside_root,
    _handle_sys_file_read,
    _handle_sys_file_write,
    _handle_sys_file_delete,
    _handle_sys_file_list,
    _handle_sys_export_share_archive,
)


def _payload(resp):
    """Extract the JSON payload from a TextContent envelope."""
    text = resp[0].text if hasattr(resp[0], "text") else resp[0]["text"]
    return json.loads(text)


def _make_project(tmp_path: Path) -> Path:
    """Scaffold a minimal project root for the handlers to operate on."""
    (tmp_path / ".os_state").mkdir()
    (tmp_path / "workspace").mkdir()
    (tmp_path / "inputs").mkdir()
    (tmp_path / "inputs" / "raw_data").mkdir()
    (tmp_path / "inputs" / "literature").mkdir()
    return tmp_path


# ── _resolve_inside_root ─────────────────────────────────────────────


class TestResolveInsideRoot:
    def test_normal_relative_path_allowed(self, tmp_path):
        root = _make_project(tmp_path)
        out = _resolve_inside_root(root, "workspace/foo.txt")
        assert out == (root / "workspace" / "foo.txt").resolve()

    def test_traversal_rejected(self, tmp_path):
        root = _make_project(tmp_path)
        with pytest.raises(WriteProtectedError):
            _resolve_inside_root(root, "../../etc/passwd")

    def test_absolute_outside_rejected(self, tmp_path):
        root = _make_project(tmp_path)
        with pytest.raises(WriteProtectedError):
            _resolve_inside_root(root, "/tmp/x")

    def test_symlink_outside_rejected(self, tmp_path):
        root = _make_project(tmp_path)
        outside = tmp_path.parent / "outside_target.txt"
        outside.write_text("secret")
        link = root / "workspace" / "evil"
        link.symlink_to(outside)
        with pytest.raises(WriteProtectedError):
            _resolve_inside_root(root, "workspace/evil")


# ── sys_file_read ────────────────────────────────────────────────────


class TestSysFileRead:
    def test_traversal_rejected(self, tmp_path):
        root = _make_project(tmp_path)
        resp = _handle_sys_file_read(
            "sys_file_read", {"filepath": "../../etc/passwd"}, root
        )
        body = _payload(resp)
        assert body["status"] == "error"
        msg = (body.get("error") or "").lower()
        assert "escape" in msg or "protect" in msg


# ── sys_file_write ───────────────────────────────────────────────────


class TestSysFileWrite:
    def test_absolute_outside_rejected(self, tmp_path):
        root = _make_project(tmp_path)
        resp = _handle_sys_file_write(
            "sys_file_write",
            {"filepath": "/tmp/x_writeprotect_test.txt", "content": "x"},
            root,
        )
        body = _payload(resp)
        assert body["status"] == "error"

    def test_dot_os_state_blocked(self, tmp_path):
        root = _make_project(tmp_path)
        resp = _handle_sys_file_write(
            "sys_file_write",
            {"filepath": ".os_state/manual_tamper.json", "content": "{}"},
            root,
        )
        body = _payload(resp)
        assert body["status"] == "error"
        msg = (body.get("error") or "").lower()
        assert "protect" in msg or "read-only" in msg

    def test_inputs_raw_data_blocked(self, tmp_path):
        # 3.2.2: original inputs are SOFT-guarded — a plain write (no force)
        # is still refused, but with a "pass force=true" hint, not a hard
        # write-protection error.
        root = _make_project(tmp_path)
        resp = _handle_sys_file_write(
            "sys_file_write",
            {"filepath": "inputs/raw_data/x.csv", "content": "a,b\n1,2"},
            root,
        )
        body = _payload(resp)
        assert body["status"] == "error"
        assert "force=true" in (body.get("error") or "")

    def test_inputs_raw_data_allowed_with_force(self, tmp_path):
        # 3.2.2: force=true lets the AI edit original inputs (with a warning).
        root = _make_project(tmp_path)
        resp = _handle_sys_file_write(
            "sys_file_write",
            {"filepath": "inputs/raw_data/x.csv", "content": "a,b\n1,2",
             "force": True},
            root,
        )
        body = _payload(resp)
        assert body["status"] == "success"
        assert (root / "inputs" / "raw_data" / "x.csv").read_text() == "a,b\n1,2"
        warning = (body.get("data") or {}).get("warning") or body.get("warning") or ""
        assert "provenance" in warning.lower()

    def test_inputs_context_allowed_freely(self, tmp_path):
        # 3.2.2: inputs/context is a free drop-zone — no force needed.
        root = _make_project(tmp_path)
        resp = _handle_sys_file_write(
            "sys_file_write",
            {"filepath": "inputs/context/note.md", "content": "a thought"},
            root,
        )
        body = _payload(resp)
        assert body["status"] == "success"
        assert (root / "inputs" / "context" / "note.md").read_text() == "a thought"

    def test_workspace_allowed(self, tmp_path):
        root = _make_project(tmp_path)
        resp = _handle_sys_file_write(
            "sys_file_write",
            {"filepath": "workspace/notes.md", "content": "hello"},
            root,
        )
        body = _payload(resp)
        assert body["status"] == "success"
        assert (root / "workspace" / "notes.md").read_text() == "hello"

    def test_literature_index_allowed(self, tmp_path):
        root = _make_project(tmp_path)
        resp = _handle_sys_file_write(
            "sys_file_write",
            {
                "filepath": "inputs/literature/literature_index.yaml",
                "content": "papers: []\n",
            },
            root,
        )
        body = _payload(resp)
        assert body["status"] == "success"


# ── sys_file_delete ──────────────────────────────────────────────────


class TestSysFileDelete:
    def test_dot_os_state_blocked(self, tmp_path):
        root = _make_project(tmp_path)
        target = root / ".os_state" / "test.json"
        target.write_text("{}")
        resp = _handle_sys_file_delete(
            "sys_file_delete", {"filepath": ".os_state/test.json"}, root
        )
        body = _payload(resp)
        assert body["status"] == "error"
        assert target.exists(), "delete should NOT have succeeded"

    def test_traversal_rejected(self, tmp_path):
        root = _make_project(tmp_path)
        resp = _handle_sys_file_delete(
            "sys_file_delete", {"filepath": "../../etc/passwd"}, root
        )
        body = _payload(resp)
        assert body["status"] == "error"


# ── sys_file_list ────────────────────────────────────────────────────


class TestSysFileList:
    def test_traversal_rejected(self, tmp_path):
        root = _make_project(tmp_path)
        resp = _handle_sys_file_list(
            "sys_file_list", {"directory": "../../etc"}, root
        )
        body = _payload(resp)
        assert body["status"] == "error"


# ── sys_export_share_archive ─────────────────────────────────────────


class TestSysExportShareArchive:
    def test_out_outside_root_rejected(self, tmp_path):
        root = _make_project(tmp_path)
        # The script is not scaffolded — but the path-guard should fire
        # BEFORE any scaffolding/exec attempt. We pass an out path that
        # escapes the project root.
        resp = _handle_sys_export_share_archive(
            "sys_export_share_archive",
            {"out": "/tmp/escape.tar.gz"},
            root,
        )
        body = _payload(resp)
        assert body["status"] == "error"


# ── check_write_permitted with root ──────────────────────────────────


class TestCheckWritePermittedRoot:
    def test_root_scoped_only_inspects_relative_parts(self, tmp_path):
        """If the project root itself lives under a path called .os_state,
        writes to ``workspace/`` should NOT be flagged."""
        nested = tmp_path / ".os_state" / "projects" / "my_proj"
        nested.mkdir(parents=True)
        target = nested / "workspace" / "x.txt"
        # No raise: root-relative parts are workspace/x.txt, no protected part.
        check_write_permitted(target, root=nested)

    def test_root_scoped_still_blocks_protected_relative(self, tmp_path):
        root = _make_project(tmp_path)
        with pytest.raises(WriteProtectedError):
            check_write_permitted(root / ".os_state" / "y.json", root=root)

    def test_legacy_no_root_still_works(self, tmp_path):
        root = _make_project(tmp_path)
        with pytest.raises(WriteProtectedError):
            check_write_permitted(root / ".os_state" / "y.json")
