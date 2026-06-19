"""Theory + Math pack for Research-OS.

Adds 8 protocols + 3 tools for the formal sciences: proof verification
workflow, lemma library + theorem dependency graph, conjecture
tracking, Lean 4 / Coq integration, theory-paper structure, and
proof-strategy selection. Bundled with the core wheel; will split
into a separate PyPI package (`research-os-theory-math`) later.
"""
from pathlib import Path

from research_os.plugins import (
    PackRegistration,
    captured_tools,
)
from research_os_theory_math import tools as _tools  # noqa: F401
from research_os_theory_math.detector import detect_theory_math
from research_os_theory_math.router_entries import THEORY_MATH_ROUTER_ENTRIES

from research_os import __version__  # bundled pack reports the wheel version

PACK_NAME = "theory_math"
_PROTOCOLS_DIR = Path(__file__).parent / "protocols"


def register() -> PackRegistration:
    return PackRegistration(
        name=PACK_NAME,
        version=__version__,
        protocols_dir=_PROTOCOLS_DIR,
        tools=captured_tools(_tools.__name__),
        router_entries=THEORY_MATH_ROUTER_ENTRIES,
        domain_detector=detect_theory_math,
        description=(
            "Formal-sciences scaffolds: proof verification workflow, "
            "lemma library, theorem dependency graphs, conjecture "
            "tracking, Lean 4 / Coq integration, proof-strategy "
            "selection, theory-paper structure."
        ),
        # Theory papers are NOT IMRAD. They open with an introduction,
        # establish definitions + notation (preliminaries), state and
        # prove the headline results, then discuss implications. The
        # synthesis pipeline reads this tuple via pack_paper_sections()
        # and orders synthesis/paper.md accordingly. Closes the v1.11.1
        # known issue where tool_synthesize emitted IMRAD even for
        # formal-math projects.
        paper_sections=(
            "introduction",
            "preliminaries",
            "main_theorems",
            "proofs",
            "discussion",
        ),
    )
