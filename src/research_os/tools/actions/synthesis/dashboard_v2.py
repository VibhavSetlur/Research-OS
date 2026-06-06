"""Migration alias — renamed to `dashboard_app`; removed in v2.2.0.

Re-exports from the canonical module so external callers (pack authors,
older scripts) keep working through one minor cycle. Update imports to
`from research_os.tools.actions.synthesis.dashboard_app import ...`.

The exported `render_dashboard_v2` name is preserved here as an alias for
`render_dashboard_app` so back-compat callers keep working.
"""
from research_os.tools.actions.synthesis.dashboard_app import *  # noqa: F401,F403
from research_os.tools.actions.synthesis.dashboard_app import (
    render_dashboard_app as render_dashboard_v2,  # noqa: F401
    DASHBOARD_APP_CSS as DASHBOARD_V2_CSS,  # noqa: F401
)
