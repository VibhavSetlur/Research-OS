"""Router-index entries for the engineering pack."""
ENGINEERING_ROUTER_ENTRIES = {
    "engineering/design/design_iteration": {
        "intent_class": "execute",
        "sub_intent": "new_experiment",
        "summary": "Versioned design revisions; each with rationale + diff from prior. Mechanical / electrical / software.",
        "triggers": [
            "design iteration", "design revision", "rev N to rev N+1",
            "design diff", "design changelog",
        ],
        "token_estimate": 1500,
        "decomposition": [
            {"protocol": "engineering/design/design_iteration",
             "purpose": "Capture + justify a design revision."},
        ],
    },
    "engineering/design/requirements_traceability": {
        "intent_class": "audit_wrap",
        "sub_intent": "provenance",
        "summary": "Requirements (SRS) ↔ design elements (SDD) ↔ test cases ↔ test results. Bidirectional matrix.",
        "triggers": [
            "requirements traceability", "srs", "sdd",
            "traceability matrix", "verification + validation",
            "v&v", "trace requirements to tests",
        ],
        "shortcut_tool": "tool_engineering_requirements_matrix",
        "token_estimate": 1600,
        "decomposition": [
            {"tool": "tool_engineering_requirements_matrix",
             "purpose": "Render the bidirectional matrix + flag orphans."},
            {"protocol": "engineering/design/requirements_traceability",
             "purpose": "Walk the requirement → design → test → result loop."},
        ],
    },
    "engineering/safety/fmea_protocol": {
        "intent_class": "audit_wrap",
        "sub_intent": "safety",
        "summary": "Failure Mode & Effects Analysis. Per failure mode: severity × occurrence × detection → RPN → mitigation.",
        "triggers": [
            "fmea", "failure mode", "risk priority number",
            "rpn analysis", "failure mode analysis",
        ],
        "shortcut_tool": "tool_engineering_fmea_render",
        "token_estimate": 1600,
        "decomposition": [
            {"tool": "tool_engineering_fmea_render",
             "purpose": "Render the FMEA + sort by RPN + flag high-priority."},
            {"protocol": "engineering/safety/fmea_protocol",
             "purpose": "Walk failure-mode enumeration + scoring + mitigation."},
        ],
    },
    "engineering/safety/fault_tree_analysis": {
        "intent_class": "audit_wrap",
        "sub_intent": "safety",
        "summary": "Top-down failure decomposition: top event → AND/OR gates → basic events. Safety-critical systems.",
        "triggers": [
            "fault tree", "fault tree analysis", "fta",
            "top event", "basic event",
        ],
        "shortcut_tool": "tool_engineering_fault_tree_render",
        "token_estimate": 1500,
        "decomposition": [
            {"tool": "tool_engineering_fault_tree_render",
             "purpose": "Render the fault tree as Mermaid."},
            {"protocol": "engineering/safety/fault_tree_analysis",
             "purpose": "Decompose top event into contributing events."},
        ],
    },
    "engineering/test/test_failure_causation": {
        "intent_class": "methodology",
        "sub_intent": "debug",
        "summary": "When a test fails: 5-whys + fishbone + classify (design / impl / test / env). Find the root, not the symptom.",
        "triggers": [
            "test failure", "5 whys", "five whys", "fishbone",
            "ishikawa", "root cause analysis", "rca",
        ],
        "token_estimate": 1400,
        "decomposition": [
            {"protocol": "engineering/test/test_failure_causation",
             "purpose": "Walk 5-whys + fishbone + classify."},
        ],
    },
    "engineering/test/build_test_fix_loop": {
        "intent_class": "execute",
        "sub_intent": "new_experiment",
        "summary": "Iterative cycle protocol with cycle-time tracking (build → test → diagnose → fix → re-build).",
        "triggers": [
            "build test fix", "build-test-fix", "iterative test cycle",
            "cycle time tracking",
        ],
        "token_estimate": 1400,
        "decomposition": [
            {"protocol": "engineering/test/build_test_fix_loop",
             "purpose": "Run + log a single iteration of the loop."},
        ],
    },
    "engineering/output/engineering_report_structure": {
        "intent_class": "synthesize",
        "sub_intent": "report",
        "summary": "Engineering report format (NOT IMRAD): Background → Requirements → Design → Verification → Validation → Conclusions.",
        "triggers": [
            "engineering report", "engineering report structure",
            "v&v report", "design report",
        ],
        "token_estimate": 1500,
        "decomposition": [
            {"protocol": "engineering/output/engineering_report_structure",
             "purpose": "Build the engineering report skeleton."},
        ],
    },
}
