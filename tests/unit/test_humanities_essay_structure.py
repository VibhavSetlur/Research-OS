"""Tests for the humanities_essay_structure protocol +
tool_humanities_essay_scaffold handler (v1.11.0).

Coverage:
    * protocol YAML parses + has the required structural fields
    * quality_bar is a dict (NOT a list) as the spec requires
    * shortcut_tool field is wired to tool_humanities_essay_scaffold
    * scaffold writes synthesis/paper.md with all six interpretive
      sections (introduction, contextual framing, three close
      readings, critical conversation, counter-argument + reply,
      conclusion + stakes)
    * scaffold is idempotent — re-running does not clobber
      substantive content the researcher added
    * scaffold returns the relative paper_path + sections list
    * IMRAD section headings (Methods, Results) are absent — this
      protocol explicitly rejects IMRAD for the humanities essay
"""
from __future__ import annotations

from pathlib import Path

import yaml


PROTOCOL_PATH = (
    Path(__file__).resolve().parents[2]
    / "src" / "research_os" / "protocols" / "synthesis"
    / "humanities_essay_structure.yaml"
)


def _load_protocol() -> dict:
    return yaml.safe_load(PROTOCOL_PATH.read_text())


# ── Protocol parses + structural shape ──────────────────────────────────


def test_humanities_essay_structure_protocol_parses():
    proto = _load_protocol()
    assert proto["id"] == "humanities_essay_structure"
    assert "name" in proto
    assert "description" in proto
    assert "steps" in proto and len(proto["steps"]) >= 5
    assert "expected_outputs" in proto
    assert "synthesis/paper.md" in proto["expected_outputs"]


def test_humanities_essay_structure_quality_bar_is_dict_not_list():
    """quality_bar must be a dict (NOT a list) per the feature spec."""
    proto = _load_protocol()
    assert isinstance(proto["quality_bar"], dict)
    # Sanity: the key constraints the humanities form demands.
    qb = proto["quality_bar"]
    assert qb.get("thesis_one_sentence_falsifiable") is True
    assert qb.get("close_readings_minimum") == 3
    assert qb.get("counter_argument_steelmanned") is True
    assert qb.get("conclusion_names_stakes") is True
    assert qb.get("no_imrad_headings") is True


def test_humanities_essay_structure_shortcut_tool_wired():
    proto = _load_protocol()
    assert proto.get("shortcut_tool") == "tool_humanities_essay_scaffold"


def test_humanities_essay_structure_next_protocol_points_to_synthesis_paper():
    proto = _load_protocol()
    assert proto.get("next_protocol") == "synthesis/synthesis_paper"


def test_humanities_essay_structure_steps_cover_the_six_sections():
    """The protocol must describe all six interpretive sections."""
    proto = _load_protocol()
    step_ids = {s["id"] for s in proto["steps"]}
    # The scaffold step is the central one — it is the shortcut tool's seat.
    assert "scaffold_essay" in step_ids
    assert "lock_the_thesis" in step_ids
    assert "draft_close_readings" in step_ids
    assert "draft_critical_conversation" in step_ids
    assert "draft_counter_argument_and_reply" in step_ids
    assert "draft_conclusion_and_stakes" in step_ids


# ── Scaffold handler ────────────────────────────────────────────────────


def test_scaffold_writes_paper_md_with_all_sections(tmp_path: Path):
    from research_os.tools.actions.synthesis.humanities_essay import (
        scaffold_humanities_essay,
    )

    res = scaffold_humanities_essay(tmp_path)
    paper = tmp_path / "synthesis" / "paper.md"
    assert paper.exists(), "scaffold must write synthesis/paper.md"

    text = paper.read_text()
    # All six interpretive sections (the three close readings count as
    # one section family with three sub-sections, per the spec).
    assert "## Introduction" in text
    assert "## Contextual Framing" in text
    assert "## Close Reading: Passage 1" in text
    assert "## Close Reading: Passage 2" in text
    assert "## Close Reading: Passage 3" in text
    assert "## Critical Conversation" in text
    assert "## Counter-Argument and Reply" in text
    assert "## Conclusion and Stakes" in text

    # Returned metadata.
    assert res["paper_path"] == "synthesis/paper.md"
    assert "introduction" in res["sections"]
    assert "conclusion_and_stakes" in res["sections"]
    assert res["venue_template"] == "humanities_essay"


def test_scaffold_omits_imrad_headings(tmp_path: Path):
    """A humanities essay is non-IMRAD by design. The scaffold must NOT
    seed Methods / Results / Discussion headings (those belong to
    synthesis_paper)."""
    from research_os.tools.actions.synthesis.humanities_essay import (
        scaffold_humanities_essay,
    )

    scaffold_humanities_essay(tmp_path)
    text = (tmp_path / "synthesis" / "paper.md").read_text()
    assert "## Methods" not in text
    assert "## Results" not in text
    assert "## Discussion" not in text


def test_scaffold_is_idempotent_when_unedited(tmp_path: Path):
    """Re-running the scaffold on its own un-edited output is a no-op
    in terms of section count."""
    from research_os.tools.actions.synthesis.humanities_essay import (
        scaffold_humanities_essay,
    )

    scaffold_humanities_essay(tmp_path)
    text_after_first = (tmp_path / "synthesis" / "paper.md").read_text()
    res2 = scaffold_humanities_essay(tmp_path)
    text_after_second = (tmp_path / "synthesis" / "paper.md").read_text()

    # Idempotent: file unchanged + nothing new written.
    assert text_after_first == text_after_second
    assert res2["sections_written"] == []
    # Every section is preserved on the second pass.
    assert set(res2["sections_preserved"]) == {key for key, _ in [
        ("introduction", "Introduction"),
        ("contextual_framing", "Contextual Framing"),
        ("close_reading_one", "Close Reading: Passage 1"),
        ("close_reading_two", "Close Reading: Passage 2"),
        ("close_reading_three", "Close Reading: Passage 3"),
        ("critical_conversation", "Critical Conversation"),
        ("counter_argument_and_reply", "Counter-Argument and Reply"),
        ("conclusion_and_stakes", "Conclusion and Stakes"),
    ]}


def test_scaffold_preserves_substantive_researcher_content(tmp_path: Path):
    """If the researcher has written real prose under a section,
    re-running the scaffold MUST NOT clobber it."""
    from research_os.tools.actions.synthesis.humanities_essay import (
        scaffold_humanities_essay,
    )

    # First scaffold the file.
    scaffold_humanities_essay(tmp_path)
    paper = tmp_path / "synthesis" / "paper.md"

    # The researcher writes substantive prose into the Introduction.
    real = (
        "## Introduction\n\n"
        "Milton's Satan, on the standard view, is a Royalist figure who "
        "ventriloquises the Restoration's verdict on the regicides. "
        "Empson saw this; so did Hill; so, more recently, did Quint. "
        "The reading I will defend in what follows complicates that "
        "consensus by showing that the rhetorical Satan is Royalist "
        "where Milton himself is republican, and that this gap is the "
        "interpretive event of the poem's opening books. Three "
        "passages in particular let us see the gap working: Satan's "
        "first speech on the burning lake, the council in Pandaemonium, "
        "and the address to the sun in Book IV.\n\n"
    )
    # Replace the introduction section with substantive content; leave
    # the rest as-is.
    text = paper.read_text()
    before_intro = text.split("## Introduction", 1)[0]
    rest = text.split("## Introduction", 1)[1]
    next_section = rest.find("\n## ")
    rest_after = rest[next_section:]
    paper.write_text(before_intro + real + rest_after.lstrip("\n"))

    # Re-run the scaffold.
    res = scaffold_humanities_essay(tmp_path)
    text_after = paper.read_text()
    assert "Milton's Satan" in text_after, (
        "scaffold must preserve substantive researcher content"
    )
    assert "introduction" in res["sections_preserved"]
    assert "introduction" not in res["sections_written"]


def test_scaffold_creates_synthesis_dir_when_missing(tmp_path: Path):
    """The handler must create synthesis/ if it doesn't already exist."""
    from research_os.tools.actions.synthesis.humanities_essay import (
        scaffold_humanities_essay,
    )

    assert not (tmp_path / "synthesis").exists()
    scaffold_humanities_essay(tmp_path)
    assert (tmp_path / "synthesis").is_dir()
    assert (tmp_path / "synthesis" / "paper.md").is_file()


def test_scaffold_accepts_str_root(tmp_path: Path):
    """Handler dispatch may pass root as a str — the scaffold must coerce."""
    from research_os.tools.actions.synthesis.humanities_essay import (
        scaffold_humanities_essay,
    )

    res = scaffold_humanities_essay(str(tmp_path))
    assert (tmp_path / "synthesis" / "paper.md").exists()
    assert res["paper_path"] == "synthesis/paper.md"
