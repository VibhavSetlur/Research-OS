"""Router-index entries for the qualitative pack."""
QUALITATIVE_ROUTER_ENTRIES = {
    "qualitative/coding/coding_scheme_iteration": {
        "intent_class": "methodology",
        "sub_intent": "method_pick",
        "summary": "Multi-round coding: open → axial → selective (Strauss & Corbin) with version tracking.",
        "triggers": [
            "coding scheme iteration", "open coding", "axial coding",
            "selective coding", "code refinement", "second round of coding",
        ],
        "shortcut_tool": "tool_qualitative_codebook_diff",
        "token_estimate": 1700,
        "decomposition": [
            {"protocol": "qualitative/coding/coding_scheme_iteration",
             "purpose": "Walk the open → axial → selective loop."},
            {"tool": "tool_qualitative_codebook_diff",
             "purpose": "Per-round diff + κ per code."},
        ],
    },
    "qualitative/validity/member_checking": {
        "intent_class": "audit_wrap",
        "sub_intent": "validity",
        "summary": "Share interpretations back with participants; record + integrate their feedback.",
        "triggers": [
            "member checking", "respondent validation",
            "share findings with participants",
            "participant validation", "interpretive validity",
        ],
        "token_estimate": 1500,
        "decomposition": [
            {"protocol": "qualitative/validity/member_checking",
             "purpose": "Plan + run + record member-check rounds."},
        ],
    },
    "qualitative/method/grounded_theory_iteration": {
        "intent_class": "methodology",
        "sub_intent": "method_pick",
        "summary": "Theoretical sampling + constant comparison + saturation tracking.",
        "triggers": [
            "grounded theory", "constant comparison", "theoretical sampling",
            "theoretical saturation", "glaser straussian", "gt methodology",
        ],
        "token_estimate": 1700,
        "decomposition": [
            {"protocol": "qualitative/method/grounded_theory_iteration",
             "purpose": "Iterate sampling → compare → memo → saturate."},
        ],
    },
    "qualitative/method/thematic_analysis_braun_clarke": {
        "intent_class": "methodology",
        "sub_intent": "method_pick",
        "summary": "Braun & Clarke 2006 six-phase thematic analysis, parametrized.",
        "triggers": [
            "thematic analysis", "braun and clarke", "braun & clarke",
            "ta methodology", "ta protocol", "reflexive thematic",
        ],
        "token_estimate": 1600,
        "decomposition": [
            {"protocol": "qualitative/method/thematic_analysis_braun_clarke",
             "purpose": "Walk the 6 phases with reflexivity gates."},
        ],
    },
    "qualitative/output/qualitative_report_format": {
        "intent_class": "synthesize",
        "sub_intent": "report",
        "summary": "Reporting standards: COREQ (interviews) | SRQR (general qualitative).",
        "triggers": [
            "qualitative report", "coreq", "srqr",
            "qualitative reporting standard", "write up qualitative",
        ],
        "shortcut_tool": "tool_qualitative_select_standard",
        "token_estimate": 1500,
        "decomposition": [
            {"protocol": "qualitative/output/qualitative_report_format",
             "purpose": "Pick COREQ vs SRQR; build the report against it."},
            {"tool": "tool_qualitative_select_standard",
             "purpose": "Auto-pick standard + copy 32- or 21-item checklist into workspace."},
            {"tool": "tool_qualitative_quote_provenance",
             "purpose": "Audit every quote → registry entry."},
        ],
    },
}
