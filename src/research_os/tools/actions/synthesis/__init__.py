"""Final output generators: paper, poster, dashboard, verified citations."""

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
from research_os.tools.actions.synthesis.latex import (  # noqa: F401
    create_dashboard,
    create_poster,
    latex_compile,
)
from research_os.tools.actions.synthesis.synthesize import (  # noqa: F401
    synthesize_plan,
    synthesize_workspace,
)
from research_os.tools.actions.synthesis.discussion_from_verdicts import (  # noqa: F401  v1.5.0
    discussion_coverage_audit,
    emit_discussion_paragraphs,
)
