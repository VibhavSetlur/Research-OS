"""Humanities essay scaffold — writes synthesis/paper.md as the
interpretive shell the `synthesis/humanities_essay_structure` protocol
prescribes.

The scaffold is structural, not generative: it lays down the six
section headings (Introduction + thesis, Contextual framing, Close
readings 1-3, Critical conversation, Counter-argument + reply,
Conclusion + stakes) with one-paragraph stubs the AI fills in across
subsequent turns.

Idempotent: re-running on a file the researcher has already filled in
does NOT clobber substantive content (>200 non-blank chars under a
section heading); only missing sections are scaffolded back in. This
mirrors the multi-turn discipline `synthesis_paper` enforces.

The scaffold pairs with the bundled `humanities_essay.typ` Typst
template, which provides the venue layer (1.25in margins, 12pt serif,
MLA-style unnumbered headings, footnote apparatus, 0.5in block-quote
indent). Layout is the template's job; structure is this scaffold's.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SECTION_TITLES: list[tuple[str, str]] = [
    ("introduction", "Introduction"),
    ("contextual_framing", "Contextual Framing"),
    ("close_reading_one", "Close Reading: Passage 1"),
    ("close_reading_two", "Close Reading: Passage 2"),
    ("close_reading_three", "Close Reading: Passage 3"),
    ("critical_conversation", "Critical Conversation"),
    ("counter_argument_and_reply", "Counter-Argument and Reply"),
    ("conclusion_and_stakes", "Conclusion and Stakes"),
]

_STUB_TEMPLATES: dict[str, str] = {
    "introduction": (
        "_Three to five paragraphs that frame the text, the problem, and the "
        "stakes. The final sentence of the introduction is the thesis — one "
        "sentence, falsifiable by passage-level evidence, non-obvious to a "
        "reader who knows the text. Draft the thesis first in "
        "`workspace/.outline/thesis.md`, then carry it here._"
    ),
    "contextual_framing": (
        "_Seat the argument in the field, period, or tradition. What is the "
        "received reading? What does the most-cited critic say? What "
        "historical / formal / theoretical context does the reader need "
        "before the close readings make sense?_"
    ),
    "close_reading_one": (
        "_Quote the first passage (block quote for verse > 4 lines or prose "
        "> 40 words, per MLA convention). Identify the formal feature(s) "
        "doing the work (metre, enjambment, imagery, syntactic pattern, "
        "lexical register, framing device). Link the feature to the thesis: "
        "what does THIS passage show that supports the claim? Footnote the "
        "secondary critics who have or have not noticed the feature._"
    ),
    "close_reading_two": (
        "_Second close reading. Same shape: passage + formal feature + "
        "link to thesis + secondary-critic footnote. Choose a passage that "
        "EXTENDS the argument (covers terrain the first passage did not), "
        "not one that just repeats it._"
    ),
    "close_reading_three": (
        "_Third close reading. Same shape. Use this slot for the strongest "
        "passage — the one a sceptical reader has to account for. Optional "
        "fourth and fifth close readings may be appended if the argument "
        "demands them; below three, the essay is a note rather than an "
        "essay._"
    ),
    "critical_conversation": (
        "_Three to seven named critics whose readings of this text (or this "
        "tradition) are the closest neighbours to yours. Per critic: one "
        "sentence on their position (cite the work in a footnote) + your "
        "relation to it (extends, qualifies, contests, ignores-and-replaces). "
        "A reading that does not know its neighbours is exegesis, not "
        "scholarship._"
    ),
    "counter_argument_and_reply": (
        "_Steelman the strongest objection — either a counter-reading of "
        "the same passages or a counter-frame that argues against this kind "
        "of reading. Then the reply: show that your reading accounts for "
        "MORE passages, OR accounts for them more parsimoniously, OR "
        "accounts for a feature the counter cannot._"
    ),
    "conclusion_and_stakes": (
        "_Two paragraphs. First: restate the thesis + the evidence in "
        "compressed form. Second: stakes — what your reading tells us "
        "BEYOND THE TEXT (about the genre, the period, the author's "
        "relation to a tradition, the reception of an idea, the "
        "methodological lesson for reading similar texts)._"
    ),
}

_HEADER_TEMPLATE = (
    "# {title}\n\n"
    "_Humanities essay — scaffolded by `tool_humanities_essay_scaffold` on "
    "{stamp}. Drafted under `synthesis/humanities_essay_structure`. "
    "Structure is non-IMRAD by design (essays argue; they do not report)._\n\n"
)


def _project_title(root: Path) -> str:
    try:
        from research_os.project_ops import load_state

        s = load_state(root)
        return (
            s.get("project_name")
            or s.get("project")
            or "Humanities Essay (untitled)"
        )
    except Exception:
        return "Humanities Essay (untitled)"


def _has_substantive_section(
    full_text: str, heading: str, *, min_chars: int = 200
) -> bool:
    """True if the named section already has > min_chars of non-stub
    content, so the scaffold should leave it alone (idempotency)."""
    if not full_text:
        return False
    marker = f"\n## {heading}\n"
    if marker not in full_text:
        # Maybe at start of file without leading newline.
        if not full_text.startswith(f"## {heading}\n"):
            return False
        start = full_text.find(f"## {heading}\n") + len(f"## {heading}\n")
    else:
        start = full_text.find(marker) + len(marker)
    # Find the next "## " heading or EOF.
    rest = full_text[start:]
    next_h = rest.find("\n## ")
    body = rest if next_h == -1 else rest[:next_h]
    # Strip out italic-stub paragraphs (lines wrapped in `_..._`) since
    # those are the scaffold output and should not count as substantive.
    real = []
    for line in body.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("_") and s.endswith("_"):
            continue
        real.append(s)
    return sum(len(line) for line in real) >= min_chars


def _render_section(heading: str, stub: str) -> str:
    return f"## {heading}\n\n{stub}\n\n"


def scaffold_humanities_essay(root: Path) -> dict[str, Any]:
    """Write `synthesis/paper.md` as a six-section humanities-essay shell.

    Returns a dict the caller wraps in `_text(_success(...))` (the
    server.py handler does this — see the spec).
    """
    root = Path(root)
    synthesis_dir = root / "synthesis"
    synthesis_dir.mkdir(parents=True, exist_ok=True)
    paper_path = synthesis_dir / "paper.md"

    title = _project_title(root)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    existing = paper_path.read_text() if paper_path.exists() else ""

    sections_written: list[str] = []
    sections_preserved: list[str] = []

    if existing.strip():
        # Idempotent path — only fill in missing sections, preserve the rest.
        updated = existing
        # Make sure file ends with a newline so concatenation is clean.
        if not updated.endswith("\n"):
            updated += "\n"
        for key, heading in _SECTION_TITLES:
            if _has_substantive_section(updated, heading):
                sections_preserved.append(key)
                continue
            if f"## {heading}\n" in updated:
                # Heading exists but body is empty / stub-only — leave it
                # alone too. The idempotency contract says: do not clobber
                # anything once the scaffold has placed it.
                sections_preserved.append(key)
                continue
            updated += _render_section(heading, _STUB_TEMPLATES[key])
            sections_written.append(key)
        paper_path.write_text(updated)
    else:
        # Fresh scaffold — write the full shell.
        out = _HEADER_TEMPLATE.format(title=title, stamp=stamp)
        for key, heading in _SECTION_TITLES:
            out += _render_section(heading, _STUB_TEMPLATES[key])
            sections_written.append(key)
        paper_path.write_text(out)

    return {
        "paper_path": str(paper_path.relative_to(root)),
        "sections": [key for key, _ in _SECTION_TITLES],
        "sections_written": sections_written,
        "sections_preserved": sections_preserved,
        "venue_template": "humanities_essay",
        "next_step": (
            "Lock the thesis sentence in workspace/.outline/thesis.md, "
            "then draft the close readings one section per turn (see "
            "synthesis/humanities_essay_structure)."
        ),
    }
