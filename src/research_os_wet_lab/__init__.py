"""Wet-Lab pack for Research-OS.

Adds 8 protocols + 3 tools for bench science: SOP versioning,
reagent lot tracking, plate-map provenance, instrument run logs,
sample lineage, experiment design, reproducibility audit, and
wet-lab Materials & Methods sections.
"""
from pathlib import Path

from research_os.plugins import (
    PackRegistration,
    captured_tools,
)
from research_os_wet_lab import tools as _tools  # noqa: F401
from research_os_wet_lab.detector import detect_wet_lab
from research_os_wet_lab.router_entries import WET_LAB_ROUTER_ENTRIES

__version__ = "1.9.3"
PACK_NAME = "wet_lab"
_PROTOCOLS_DIR = Path(__file__).parent / "protocols"


def register() -> PackRegistration:
    return PackRegistration(
        name=PACK_NAME,
        version=__version__,
        protocols_dir=_PROTOCOLS_DIR,
        tools=captured_tools(_tools.__name__),
        router_entries=WET_LAB_ROUTER_ENTRIES,
        domain_detector=detect_wet_lab,
        description=(
            "Bench-science scaffolds: SOP versioning, reagent + lot "
            "tracking, plate-map provenance, instrument run logs, "
            "sample lineage, wet-lab experiment design, reproducibility "
            "audit, wet-lab Materials & Methods."
        ),
    )
