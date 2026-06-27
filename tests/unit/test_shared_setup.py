"""Shared-server daemon setup helpers (no Docker, conda, custom ports)."""
from __future__ import annotations

import socket
import tempfile
from pathlib import Path

from research_os.daemon.shared_setup import (
    background_launch_command,
    find_free_port,
    research_os_executable,
)


def test_find_free_port_returns_bindable_port():
    port = find_free_port("127.0.0.1", 8787)
    # Must actually be bindable.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", port))


def test_find_free_port_skips_taken_port():
    # Occupy a port, confirm the picker moves past it.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as taken:
        taken.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        taken.bind(("127.0.0.1", 0))
        taken.listen(1)
        busy = taken.getsockname()[1]
        got = find_free_port("127.0.0.1", busy)
        assert got != busy


def test_executable_is_absolute_or_module_form():
    exe = research_os_executable()
    assert exe.endswith("research-os") or "-m research_os" in exe


def test_background_command_uses_absolute_exe_and_logs():
    root = Path(tempfile.mkdtemp()) / "p"
    root.mkdir(parents=True)
    cmd = background_launch_command(root, 8790, "127.0.0.1")
    assert "nohup" in cmd
    assert "--port 8790" in cmd
    assert "daemon.log" in cmd
    assert str(root) in cmd
