"""Engineering pack for Research-OS.

Adds 7 protocols + 3 tools for engineering work: design iteration,
requirements traceability (SRS/SDD), FMEA, fault tree analysis,
test-failure causation, build-test-fix loop, and engineering report
structure.
"""
from pathlib import Path

from research_os.plugins import (
    PackRegistration,
    captured_tools,
)
from research_os_engineering import tools as _tools  # noqa: F401
from research_os_engineering.detector import detect_engineering
from research_os_engineering.router_entries import ENGINEERING_ROUTER_ENTRIES

__version__ = "1.7.1"
PACK_NAME = "engineering"
_PROTOCOLS_DIR = Path(__file__).parent / "protocols"


def register() -> PackRegistration:
    return PackRegistration(
        name=PACK_NAME,
        version=__version__,
        protocols_dir=_PROTOCOLS_DIR,
        tools=captured_tools(_tools.__name__),
        router_entries=ENGINEERING_ROUTER_ENTRIES,
        domain_detector=detect_engineering,
        description=(
            "Engineering scaffolds: design iteration, requirements "
            "traceability (SRS/SDD), FMEA, fault tree analysis, "
            "test-failure causation (5-whys / fishbone), build-test-fix "
            "loop, engineering report structure."
        ),
    )
