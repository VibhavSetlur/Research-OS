"""Humanities pack for Research-OS.

Adds 8 protocols + 3 tools for archival research, close reading,
distant reading, hermeneutics, digital humanities, citation chains,
and scholarly editions. The pack is bundled with the main wheel in
the current release for easy testing; it will split into a separate
PyPI package (`research-os-humanities`) in a future release. Until
then, no extras are needed to use it.
"""
from pathlib import Path

from research_os.plugins import (
    PackRegistration,
    captured_tools,
)
from research_os_humanities import tools as _tools  # noqa: F401 — load decorators
from research_os_humanities.detector import detect_humanities
from research_os_humanities.router_entries import HUMANITIES_ROUTER_ENTRIES

__version__ = "1.9.3"
PACK_NAME = "humanities"
_PROTOCOLS_DIR = Path(__file__).parent / "protocols"


def register() -> PackRegistration:
    """Entry-point callable invoked at server startup."""
    return PackRegistration(
        name=PACK_NAME,
        version=__version__,
        protocols_dir=_PROTOCOLS_DIR,
        tools=captured_tools(_tools.__name__),
        router_entries=HUMANITIES_ROUTER_ENTRIES,
        domain_detector=detect_humanities,
        description=(
            "Humanities research scaffolds: archival research, close + "
            "distant reading, hermeneutic method, digital humanities, "
            "citation chains, scholarly editions."
        ),
    )
