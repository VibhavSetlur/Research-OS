"""Wizard UX hardening: identity validation + early already-exists exit."""
from __future__ import annotations

import types

import pytest

from research_os import wizard


def test_email_regex():
    assert wizard._EMAIL_RE.match("a@b.co")
    assert not wizard._EMAIL_RE.match("not-an-email")
    assert not wizard._EMAIL_RE.match("a@b")


def test_orcid_regex():
    assert wizard._ORCID_RE.match("0000-0002-1825-0097")
    assert wizard._ORCID_RE.match("0000-0002-1825-009X")
    assert not wizard._ORCID_RE.match("1825-0097")


def test_prompt_validated_reprompts_then_accepts(monkeypatch):
    answers = iter(["garbage", "you@uni.edu"])
    monkeypatch.setattr(wizard.tui, "text", lambda *a, **k: next(answers))
    out = wizard._prompt_validated("Email", wizard._EMAIL_RE, "you@uni.edu")
    assert out == "you@uni.edu"


def test_prompt_validated_blank_accepts(monkeypatch):
    monkeypatch.setattr(wizard.tui, "text", lambda *a, **k: "")
    assert wizard._prompt_validated("ORCID", wizard._ORCID_RE, "0000-...") == ""


def test_run_wizard_exits_early_when_already_initialized(tmp_path, monkeypatch):
    root = tmp_path / "proj"
    (root / ".os_state").mkdir(parents=True)
    monkeypatch.setattr(wizard.logo, "render", lambda **k: "")
    args = types.SimpleNamespace(directory=str(root), force=False, name=None)
    with pytest.raises(SystemExit) as exc:
        wizard.run_wizard(args)
    assert exc.value.code == 1


def test_slugify_empty_falls_back():
    """A name with no slug-safe chars must fall back, not yield '---'.
    (CWC-2)"""
    assert wizard.slugify("!!!") == "research-project"
    assert wizard.slugify("   ") == "research-project"
    assert wizard.slugify("My Cool Project!") == "my-cool-project"
    assert wizard.slugify("---") == "research-project"
