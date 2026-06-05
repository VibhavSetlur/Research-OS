"""Qualitative-research pack for Research-OS.

Extends core qualitative coverage with 5 protocols + 2 tools:
multi-round coding-scheme iteration, member checking, grounded-theory
iteration, Braun & Clarke 2006 thematic analysis, and qualitative
report formats (COREQ / SRQR). Tools support versioned codebook
diffing + quote-to-participant provenance.

Bundled with the core wheel in this release; will split into a
separate PyPI package (`research-os-qualitative`) later.
"""
from pathlib import Path

from research_os.plugins import (
    PackRegistration,
    captured_tools,
)
from research_os_qualitative import tools as _tools  # noqa: F401 — load decorators
from research_os_qualitative.detector import detect_qualitative
from research_os_qualitative.router_entries import QUALITATIVE_ROUTER_ENTRIES

__version__ = "1.9.3"
PACK_NAME = "qualitative"
_PROTOCOLS_DIR = Path(__file__).parent / "protocols"


def register() -> PackRegistration:
    """Entry-point callable invoked at server startup."""
    return PackRegistration(
        name=PACK_NAME,
        version=__version__,
        protocols_dir=_PROTOCOLS_DIR,
        tools=captured_tools(_tools.__name__),
        router_entries=QUALITATIVE_ROUTER_ENTRIES,
        domain_detector=detect_qualitative,
        description=(
            "Qualitative-research extensions: multi-round coding "
            "iteration, member checking, grounded-theory saturation, "
            "Braun & Clarke thematic analysis, COREQ / SRQR report "
            "formats. Codebook-diff + quote-provenance tools."
        ),
    )
