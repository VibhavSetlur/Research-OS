"""Synthesis tooling: planning, validation, and Typst compilation.

The AI authors synthesis outputs (paper.typ, slides.typ, poster.typ,
essay.typ, dashboard.html) directly, guided by the synthesis protocols.
This package provides the supporting tools — planning helpers,
quality-check audits, scaffolds, and the Typst compiler.
"""

from research_os.tools.actions.synthesis.check import (  # noqa: F401
    synthesis_check,
)
from research_os.tools.actions.synthesis.curate import (  # noqa: F401
    audit_figure_coverage,
    curate_figures,
)
from research_os.tools.actions.synthesis.citations import (  # noqa: F401
    cap_for,
    collect_for_section,
    format_apa,
    format_bib,
    format_vancouver,
    verify_all_in_workspace,
    verify_citation_key,
    write_references_bib,
)
from research_os.tools.actions.synthesis.discussion_from_verdicts import (  # noqa: F401
    discussion_coverage_audit,
    emit_discussion_paragraphs,
)
from research_os.tools.actions.synthesis.plan import (  # noqa: F401
    synthesize_plan,
)
from research_os.tools.actions.synthesis.scaffold import (  # noqa: F401
    SCAFFOLDS,
    synthesis_scaffold,
)
from research_os.tools.actions.synthesis.typst_compile import (  # noqa: F401
    typst_compile,
)
