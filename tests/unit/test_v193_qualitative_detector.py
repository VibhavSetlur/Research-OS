"""v1.9.3 — qualitative detector picks up .txt transcripts with 3+ turns
(AUDIT-v1.9.2-013).

Before this fix, ``_INTERVIEW_HINT_EXTS`` excluded ``.txt`` and the
speaker-turn threshold required 5 matches per file. A 12-person study
with short transcripts (4 turns each) scored ~0.1, far below the
auto-load threshold.
"""

from __future__ import annotations


def test_txt_transcript_with_three_turns_scores(tmp_path):
    """A .txt file with 3+ speaker turns (e.g. Interviewer / P1 / P2)
    now scores well above the auto-load threshold.

    The fix lowers the per-file speaker-turn threshold from 5 to 3 so
    short transcripts from a 12-person study aren't ignored, and adds
    .txt / .md to the interview-extension hint list.
    """
    from research_os_qualitative.detector import detect_qualitative

    inputs = tmp_path / "inputs"
    inputs.mkdir(parents=True, exist_ok=True)
    transcript = inputs / "p01.txt"
    transcript.write_text(
        "Interviewer: What did you experience?\n"
        "P1: It was hard at first, then better.\n"
        "Interviewer: Tell me more.\n"
        "P1: We adapted over time.\n"
    )

    res = detect_qualitative(inputs)
    assert res["confidence"] >= 0.3, f"expected score >= 0.3, got {res}"
    assert any("speaker-turn" in s.lower() for s in res["signals"]), res["signals"]


def test_md_extension_is_also_an_interview_hint(tmp_path):
    """.md files now count as interview hints (notes from a Markdown editor)."""
    from research_os_qualitative.detector import _INTERVIEW_HINT_EXTS

    assert ".txt" in _INTERVIEW_HINT_EXTS
    assert ".md" in _INTERVIEW_HINT_EXTS


def test_empty_inputs_dir_still_safe(tmp_path):
    """No inputs/ → 0.0 confidence, no crash."""
    from research_os_qualitative.detector import detect_qualitative

    res = detect_qualitative(tmp_path / "inputs")
    assert res["confidence"] == 0.0
