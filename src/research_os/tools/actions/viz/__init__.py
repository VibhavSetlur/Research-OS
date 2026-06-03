"""Figure utilities — palette lookup, caption sidecars, quality audit.

Research-OS is a **guidance system**, not a chart library. The AI writes
its own visualization scripts (matplotlib / ggplot2 / Altair / d3 / …);
the ``visualization/figure_guidelines`` protocol tells it HOW to think
about that script, and this module provides:

* ``palette_for`` — colour-blind-safe palette lookup (Okabe-Ito,
  viridis, PuOr) the AI's script can call.
* ``caption_synthesise`` — write a plain-English ``<name>.summary.md``
  next to a figure when the AI hasn't yet drafted one in its own voice.
* ``audit_figure_quality`` — DPI + dimensions + sidecar presence + SVG
  companion + SVG label-overlap heuristic. Surfaces warnings + blockers
  consumed by ``tool_path_finalize`` / ``tool_audit_step_completeness``.
* ``step_figure_inventory`` — used by the completeness gate.

Removed in v1.3.0: ``figure_create`` / ``tool_figure_create`` and the
30+ ``_render_*`` chart-kind dispatchers. The AI writes its own
plotting code now. See CHANGELOG migration notes.
"""

from research_os.tools.actions.viz.dashboard_tests import (
    generate_dashboard_test_suite,
    run_dashboard_tests,
)
from research_os.tools.actions.viz.figures import (
    audit_figure_quality,
    caption_synthesise,
    palette_for,
    step_figure_inventory,
)

__all__ = [
    "audit_figure_quality",
    "caption_synthesise",
    "generate_dashboard_test_suite",
    "palette_for",
    "run_dashboard_tests",
    "step_figure_inventory",
]
