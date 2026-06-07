"""Unit tests for `research-os completion`.

Covers:
  * Each shell choice (bash, zsh, fish) returns a non-empty sourceable
    script on stdout with exit code 0.
  * The script mentions the top-level subcommand names (so a TAB after
    `research-os ` would offer them).
  * The script mentions the IDE choices (so `research-os init --ide TAB`
    offers cursor / claude / all / none / ...).
  * argparse rejects an unknown shell name.
  * The ASCII-fallback glyph helpers swap unicode for `[+]`/`[x]`/`[!]`
    when stdout encoding is not UTF-*.
  * The `# PYTHON_ARGCOMPLETE_OK` marker is present at the top of cli.py
    so argcomplete's global-completion hook recognises this script.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from research_os import cli


# ── happy-path: each shell choice emits a script ─────────────────────────


@pytest.mark.parametrize("shell", ["bash", "zsh", "fish"])
def test_completion_emits_script_for_each_shell(shell, capsys):
    """`research-os completion <shell>` writes a non-empty script to stdout."""
    parser = cli.build_parser()
    args = parser.parse_args(["completion", shell])
    rc = cli.cmd_completion(args)
    captured = capsys.readouterr()
    assert rc == 0
    assert captured.out, f"completion {shell} produced empty stdout"
    # Every emitted script must mention the binary name.
    assert "research-os" in captured.out


def test_fish_completion_mentions_subcommands(capsys):
    """Fish: subcommands appear literally in the hand-rolled script."""
    parser = cli.build_parser()
    args = parser.parse_args(["completion", "fish"])
    cli.cmd_completion(args)
    out = capsys.readouterr().out
    for sub in ("init", "ide", "start", "doctor", "completion"):
        assert sub in out, f"fish: subcommand {sub!r} missing from script"


def test_fish_completion_mentions_ide_values(capsys):
    """Fish: --ide values appear literally in the hand-rolled script."""
    parser = cli.build_parser()
    args = parser.parse_args(["completion", "fish"])
    cli.cmd_completion(args)
    out = capsys.readouterr().out
    for ide in ("cursor", "claude", "all", "none"):
        assert ide in out, f"fish: ide value {ide!r} missing from script"


@pytest.mark.parametrize("shell", ["bash", "zsh"])
def test_bash_zsh_completion_emits_sourceable_block(shell, capsys):
    """Bash/zsh output may be argcomplete-emitted (runtime-introspected) or
    our hand-rolled fallback. Either way the output should be sourceable
    and reference the binary name + a completion-registration directive."""
    parser = cli.build_parser()
    args = parser.parse_args(["completion", shell])
    cli.cmd_completion(args)
    out = capsys.readouterr().out
    assert "research-os" in out
    # Either argcomplete's `complete -o ... -F _python_argcomplete research-os`
    # or our fallback `complete -F _research_os research-os` / `compdef`.
    assert ("complete " in out) or ("compdef " in out)


def test_completion_rejects_unknown_shell():
    """argparse `choices=` enforces the shell whitelist."""
    parser = cli.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["completion", "powershell"])


# ── fish: structure sanity ───────────────────────────────────────────────


def test_fish_completion_contains_complete_directives(capsys):
    parser = cli.build_parser()
    args = parser.parse_args(["completion", "fish"])
    cli.cmd_completion(args)
    out = capsys.readouterr().out
    # Fish completions register via the `complete` builtin.
    assert "complete -c research-os" in out
    # The fish long-option declaration uses `-l ide` (not `--ide` literal),
    # paired with the IDE choices in `-xa "cursor ... none"`.
    assert "-l ide" in out


# ── ASCII fallback for non-UTF stdout ────────────────────────────────────


class _StubStdout:
    """Plain stub with a settable `encoding` attribute (StringIO's is read-only)."""

    def __init__(self, encoding):
        self.encoding = encoding

    def write(self, _):  # pragma: no cover — never reached in these tests
        return 0


def test_glyph_uses_unicode_when_stdout_is_utf8(monkeypatch):
    monkeypatch.setattr(sys, "stdout", _StubStdout("UTF-8"))
    assert cli._supports_utf8() is True
    assert cli._check() == "✓"
    assert cli._cross() == "✗"
    assert cli._warn_glyph() == "⚠"


def test_glyph_falls_back_to_ascii_when_stdout_not_utf(monkeypatch):
    monkeypatch.setattr(sys, "stdout", _StubStdout("ascii"))
    assert cli._supports_utf8() is False
    assert cli._check() == "[+]"
    assert cli._cross() == "[x]"
    assert cli._warn_glyph() == "[!]"


def test_glyph_handles_missing_encoding_attr(monkeypatch):
    """Some sandboxed stdouts (e.g. pytest capture) report encoding=None."""

    class _NoEnc:
        encoding = None

        def write(self, _):  # pragma: no cover — never reached
            return 0

    monkeypatch.setattr(sys, "stdout", _NoEnc())
    # Should be safe (no AttributeError) and pick the ASCII fallback.
    assert cli._supports_utf8() is False
    assert cli._check() == "[+]"


# ── argcomplete shebang marker ───────────────────────────────────────────


def test_cli_py_has_python_argcomplete_ok_marker():
    """argcomplete's global hook only completes scripts marked OK."""
    cli_path = Path(cli.__file__)
    head = cli_path.read_text(encoding="utf-8").splitlines()[:5]
    assert any("PYTHON_ARGCOMPLETE_OK" in line for line in head), (
        "src/research_os/cli.py is missing the `# PYTHON_ARGCOMPLETE_OK` "
        "marker required for argcomplete's global completion hook."
    )


# ── end-to-end via the installed `research-os` console script ────────────


def test_research_os_completion_zsh_end_to_end():
    """`research-os completion zsh` returns 0 + a non-empty sourceable script."""
    import shutil
    binary = shutil.which("research-os")
    if not binary:
        pytest.skip("research-os not on PATH in this test environment")
    res = subprocess.run(
        [binary, "completion", "zsh"],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert res.returncode == 0, f"stderr: {res.stderr}"
    assert res.stdout.strip(), "completion zsh produced empty stdout"
    # The output should reference research-os at least once.
    assert "research-os" in res.stdout
