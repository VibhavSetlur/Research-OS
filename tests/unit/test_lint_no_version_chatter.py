"""Regression tests for scripts/lint_no_version_chatter.py."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
LINT_PATH = REPO_ROOT / "scripts" / "lint_no_version_chatter.py"


def _load_lint_module():
    spec = importlib.util.spec_from_file_location("lint_chatter", LINT_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["lint_chatter"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def lint_mod():
    return _load_lint_module()


def test_lint_script_exists():
    assert LINT_PATH.exists(), f"missing: {LINT_PATH}"


def test_scan_text_flags_version_ref(lint_mod):
    hits = lint_mod.scan_text("# v1.5.0 — Theme 1: do thing\n")
    assert len(hits) == 1
    assert hits[0][1] == "version-ref"


def test_scan_text_flags_as_of_version(lint_mod):
    hits = lint_mod.scan_text("As of version 1.4.0, this rule applies.\n")
    labels = {h[1] for h in hits}
    assert "as-of-version" in labels


def test_scan_text_flags_previously_this(lint_mod):
    hits = lint_mod.scan_text("# previously this clobbered foo, now we keep it\n")
    labels = {h[1] for h in hits}
    assert "previously-this" in labels


def test_scan_text_flags_warn_to_block(lint_mod):
    hits = lint_mod.scan_text(
        "# this rule was promoted from WARN to BLOCK in v1.5.0\n"
    )
    labels = {h[1] for h in hits}
    assert "warn-to-block" in labels


def test_scan_text_flags_deferred_to_v(lint_mod):
    hits = lint_mod.scan_text("# deferred to v1.6.0\n")
    labels = {h[1] for h in hits}
    assert "deferred-to-v" in labels


def test_scan_text_clean_timeless_rule(lint_mod):
    hits = lint_mod.scan_text(
        "# Filter by extension so caption / summary / prov sidecars don't get scanned as scripts\n"
    )
    assert hits == []


def test_scan_text_skips_baai_model_name(lint_mod):
    # BAAI/bge-small-en-v1.5 is the embedding model identifier, not RO version.
    hits = lint_mod.scan_text('_EMBEDS_MODEL = "BAAI/bge-small-en-v1.5"\n')
    assert hits == []


def test_scan_text_skips_v1_py_naming_convention(lint_mod):
    # The user-facing script naming convention scripts/NN_<slug>_v1.py is allowed.
    hits = lint_mod.scan_text(
        '"  scripts/01_analysis_v1.py — user-bumped as analyses evolve"\n'
    )
    assert hits == []


def test_scan_text_skips_dashboard_user_example(lint_mod):
    # The dashboard-semver example in interactive_dashboard_design.yaml is a user-example.
    hits = lint_mod.scan_text(
        "  - VERSION the dashboard (semver: v1.0 first conference\n"
        "    demo, v1.1 fixed filters, v2.0 added new view)\n"
    )
    assert hits == []


def test_live_codebase_is_clean(lint_mod):
    """The release gate: live surfaces have zero hits."""
    files = lint_mod._iter_files()
    total = 0
    bad: list[str] = []
    for f in files:
        try:
            text = f.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        hits = lint_mod.scan_text(text)
        if hits:
            total += len(hits)
            bad.append(f"{f.relative_to(REPO_ROOT)} ({len(hits)})")
    assert total == 0, f"found {total} chatter hits in {len(bad)} file(s): {bad[:5]}"
