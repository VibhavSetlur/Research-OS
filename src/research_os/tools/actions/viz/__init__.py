"""Figure utilities — palette lookup, caption sidecars, quality audit, style.

Research-OS is a **guidance system**, not a chart library. The AI writes
its own visualization scripts (matplotlib / ggplot2 / Altair / d3 / …);
the ``visualization/figure_guidelines`` protocol tells it HOW to think
about that script, and this module provides:

* ``palette_for`` — colour-blind-safe palette lookup (Okabe-Ito,
  viridis, PuOr) the AI's script can call.
* ``apply_research_os_style`` + ``RO_PALETTE`` + ``DESTINATION_FIGSIZES``
  + ``label_bars_above`` + ``label_diverging_bars`` + ``polish_axes`` +
  ``apply_suptitle`` — the publication style preset that matches the
  Research-OS dashboard aesthetic (cream bg, italic serif titles,
  muted accent palette, clean spines, value-labels-above-bars). The AI
  imports once at the top of the plotting script and the FIRST render
  already sits in the Research-OS visual identity — no v2 needed for
  spacing in most cases.
* ``caption_synthesise`` — write a plain-English ``<name>.summary.md``
  next to a figure when the AI hasn't yet drafted one in its own voice.
* ``audit_figure_quality`` — DPI + dimensions + sidecar presence + SVG
  companion + SVG label-overlap heuristic. Surfaces warnings + blockers
  consumed by ``tool_path_finalize`` / ``tool_audit_step_completeness``.
* ``step_figure_inventory`` — used by the completeness gate.

The dashboard test-suite scaffold (``generate_dashboard_test_suite`` /
``run_dashboard_tests``) was tied to the auto-dashboard generator and
removed alongside it. AI-authored dashboards write their own tests if
needed.
"""

from research_os.tools.actions.viz.figures import (
    audit_figure_quality,
    caption_synthesise,
    palette_for,
    step_figure_inventory,
)
from research_os.tools.actions.viz.style import (
    DESTINATION_FIGSIZES,
    RO_BG,
    RO_FG,
    RO_MUTED,
    RO_PALETTE,
    RO_RULE,
    STYLE_RCPARAMS,
    apply_research_os_style,
    apply_suptitle,
    label_bars_above,
    label_diverging_bars,
    polish_axes,
)

__all__ = [
    "DESTINATION_FIGSIZES",
    "RO_BG",
    "RO_FG",
    "RO_MUTED",
    "RO_PALETTE",
    "RO_RULE",
    "STYLE_RCPARAMS",
    "apply_research_os_style",
    "apply_suptitle",
    "audit_figure_quality",
    "caption_synthesise",
    "label_bars_above",
    "label_diverging_bars",
    "palette_for",
    "polish_axes",
    "step_figure_inventory",
]
