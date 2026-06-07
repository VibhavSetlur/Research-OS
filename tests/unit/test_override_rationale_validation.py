"""W11 — validate_override_rationale rejects thin/placeholder rationales.

ai-qwen audit (W11) flagged that small models routinely supply 'TODO',
'preview', or single-word strings as override_rationale, so override_log.md
fills up with noise that the pre-submission audit cannot meaningfully
flag. This module pins the validator's accept/reject behavior and the
shape of the error envelope returned to the AI.

Coverage:
  * empty / whitespace-only rationale → rejected
  * common placeholder strings (TODO, preview, n/a, …) → rejected
  * single-word, no-spaces rationale → rejected
  * 'too short' (<20 chars, even multi-word) → rejected
  * substantive multi-word rationale → accepted
"""

from __future__ import annotations

import pytest

from research_os.project_ops import (
    _OVERRIDE_RATIONALE_PLACEHOLDERS,
    validate_override_rationale,
)


# ── rejection cases ───────────────────────────────────────────────────


@pytest.mark.parametrize("bad", ["", "   ", "\n\t", None])
def test_empty_rationale_rejected(bad):
    err = validate_override_rationale(bad)
    assert err is not None
    assert err["status"] == "error"
    assert err["payload"]["what"] == "override_rationale_too_thin"


@pytest.mark.parametrize(
    "placeholder",
    [
        "TODO",
        "todo",
        "Todo",
        "preview",
        "PREVIEW",
        "test",
        "tmp",
        "temporary",
        "idk",
        "na",
        "n/a",
        "N/A",
        "placeholder",
        "tbd",
        "TBD",
        "fix later",
        "check later",
    ],
)
def test_placeholder_rationale_rejected(placeholder):
    err = validate_override_rationale(placeholder)
    assert err is not None
    assert err["payload"]["what"] == "override_rationale_too_thin"
    # The hint must point the AI at supplying a real reason.
    assert "substantive" in err["payload"]["next_action"]


def test_single_word_rationale_rejected_even_if_long():
    # 'supercalifragilisticexpialidocious' is >20 chars but a single
    # word — small models love this kind of bypass.
    err = validate_override_rationale("supercalifragilisticexpialidocious")
    assert err is not None
    assert err["payload"]["what"] == "override_rationale_too_thin"


def test_short_multiword_rationale_rejected():
    # 'too short' is multi-word but only 9 chars — fails the length rule.
    err = validate_override_rationale("too short")
    assert err is not None
    assert err["payload"]["what"] == "override_rationale_too_thin"


def test_nineteen_char_rationale_rejected():
    # Boundary: 19 chars (post-strip) must fail; 20 must pass.
    nineteen = "abc def ghi jkl mno"  # 19 chars, 5 words
    assert len(nineteen) == 19
    err = validate_override_rationale(nineteen)
    assert err is not None


# ── acceptance cases ──────────────────────────────────────────────────


def test_substantive_rationale_accepted():
    real = (
        "3pm preview for PI; methods.md is still a stub but figures "
        "are final."
    )
    assert validate_override_rationale(real) is None


def test_twenty_char_multiword_rationale_accepted():
    # Boundary: exactly 20 chars + has a space.
    twenty = "abc def ghi jkl mnop"
    assert len(twenty) == 20
    assert " " in twenty
    assert validate_override_rationale(twenty) is None


def test_leading_trailing_whitespace_stripped_before_check():
    # 20-char body wrapped in whitespace still accepted.
    padded = "    abc def ghi jkl mnop    "
    assert validate_override_rationale(padded) is None


# ── invariant: the placeholder set is non-empty and case-folded ──────


def test_placeholder_set_includes_audit_flagged_strings():
    # ai-qwen specifically called out 'TODO' and 'preview' — locking
    # them in here so a future refactor cannot silently drop them.
    assert "todo" in _OVERRIDE_RATIONALE_PLACEHOLDERS
    assert "preview" in _OVERRIDE_RATIONALE_PLACEHOLDERS
    assert "n/a" in _OVERRIDE_RATIONALE_PLACEHOLDERS
    # Empty string MUST be in the set so the length+placeholder check
    # rejects bare overrides even when length somehow passes.
    assert "" in _OVERRIDE_RATIONALE_PLACEHOLDERS


# ── error envelope shape (consumer contract) ──────────────────────────


def test_error_envelope_shape():
    err = validate_override_rationale("todo")
    assert isinstance(err, dict)
    assert err["status"] == "error"
    # The envelope MUST expose what/why/next_action so the caller can
    # surface a coachable error instead of a bare 400.
    payload = err["payload"]
    assert payload["what"] == "override_rationale_too_thin"
    assert "chars" in payload["why"]
    assert "single-word" in payload["why"] or "placeholder" in payload["why"]
    assert payload["next_action"].startswith("Provide a substantive")
