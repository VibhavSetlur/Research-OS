"""Reasoning, planning, grounding, and lessons-learned.

* ``planning``  — branch + plan_next_step.
* ``research``  — research_method, research_tool, plan_step (decompose).
* ``grounding`` — ReAct thought log + PROV-O grounding registry + CoVe.
* ``lessons``   — Reflexion-style lessons + relevance ranking.
* ``gradient``  — beginner↔PI on-ramps: explain_scaffold + deliverable_chooser.
"""

from research_os.tools.actions.research.gradient import (  # noqa: F401
    deliverable_chooser,
    explain_scaffold,
)
from research_os.tools.actions.research.grounding import (  # noqa: F401
    claim_verify,
    ground_from_context,
    grounding_for_decision,
    grounding_register,
    grounding_verify,
    thought_log,
    thought_trace,
)
from research_os.tools.actions.research.lessons import (  # noqa: F401
    lessons_consult,
    lessons_record,
)
from research_os.tools.actions.research.planning import (  # noqa: F401
    branch_recommendation,
    plan_next_step,
)
from research_os.tools.actions.research.research import (  # noqa: F401
    external_tool_instructions,
    plan_step,
    plan_step_grounded,
    research_method,
    research_tool,
)
