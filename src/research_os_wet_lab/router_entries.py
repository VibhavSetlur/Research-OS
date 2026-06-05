"""Router-index entries for the wet_lab pack."""
WET_LAB_ROUTER_ENTRIES = {
    "wet_lab/protocol/sop_versioning": {
        "intent_class": "memory",
        "sub_intent": "register",
        "summary": "Every SOP is a versioned document with explicit changelog. Avoids 'lab tribal knowledge' drift.",
        "triggers": [
            "sop", "standard operating procedure", "protocol versioning",
            "sop changelog", "lab protocol",
        ],
        "token_estimate": 1500,
        "decomposition": [
            {"protocol": "wet_lab/protocol/sop_versioning",
             "purpose": "Set up + maintain a versioned SOP."},
        ],
    },
    "wet_lab/protocol/reagent_lot_tracking": {
        "intent_class": "memory",
        "sub_intent": "register",
        "summary": "Every reagent has lot + supplier + COA + expiry tracked in workspace/<step>/reagents.yaml.",
        "triggers": [
            "reagent tracking", "lot number", "antibody catalog",
            "primer order", "coa", "certificate of analysis",
        ],
        "shortcut_tool": "tool_wet_lab_reagent_query",
        "token_estimate": 1500,
        "decomposition": [
            {"tool": "tool_wet_lab_reagent_query",
             "purpose": "Stub a reagent entry + portal link."},
            {"protocol": "wet_lab/protocol/reagent_lot_tracking",
             "purpose": "Walk the per-reagent tracking loop."},
        ],
    },
    "wet_lab/protocol/plate_map_provenance": {
        "intent_class": "execute",
        "sub_intent": "new_experiment",
        "summary": "Plate-based assays: layout file is a versioned artifact; controls + replicates + blanks documented.",
        "triggers": [
            "plate map", "plate layout", "96-well", "384-well",
            "1536-well", "plate design",
        ],
        "shortcut_tool": "tool_wet_lab_plate_map_render",
        "token_estimate": 1500,
        "decomposition": [
            {"tool": "tool_wet_lab_plate_map_render",
             "purpose": "Render the layout to PNG + ASCII for sanity check."},
            {"protocol": "wet_lab/protocol/plate_map_provenance",
             "purpose": "Walk control / replicate / blank documentation."},
        ],
    },
    "wet_lab/protocol/instrument_run_log": {
        "intent_class": "memory",
        "sub_intent": "register",
        "summary": "Per-run log: instrument ID, calibration date, parameters, raw output path, operator. Flow / qPCR / sequencing / mass spec / microscopy.",
        "triggers": [
            "instrument run", "run log", "qpcr run", "facs run",
            "sequencer run", "instrument session",
        ],
        "token_estimate": 1300,
        "decomposition": [
            {"protocol": "wet_lab/protocol/instrument_run_log",
             "purpose": "Capture a single instrument-session record."},
        ],
    },
    "wet_lab/protocol/sample_lineage": {
        "intent_class": "audit_wrap",
        "sub_intent": "provenance",
        "summary": "Parent sample → splits → aliquots → readouts. Every readout traces upward through the lineage tree.",
        "triggers": [
            "sample lineage", "sample provenance", "aliquot tracking",
            "lineage tree", "where did this sample come from",
        ],
        "shortcut_tool": "tool_wet_lab_sample_lineage_export",
        "token_estimate": 1400,
        "decomposition": [
            {"tool": "tool_wet_lab_sample_lineage_export",
             "purpose": "Render lineage as Mermaid + JSON."},
            {"protocol": "wet_lab/protocol/sample_lineage",
             "purpose": "Walk parent → splits → readouts."},
        ],
    },
    "wet_lab/method/wet_lab_experiment_design": {
        "intent_class": "methodology",
        "sub_intent": "method_pick",
        "summary": "n / condition justified, controls explicit (positive / negative / vehicle), randomization, blinding, technical-vs-biological replicate disambiguation.",
        "triggers": [
            "wet lab experiment", "design a wet-lab experiment",
            "n per condition", "controls and replicates",
            "biological replicate", "technical replicate",
        ],
        "token_estimate": 1600,
        "decomposition": [
            {"protocol": "wet_lab/method/wet_lab_experiment_design",
             "purpose": "Walk power → controls → randomization → blinding."},
        ],
    },
    "wet_lab/audit/wet_lab_reproducibility_audit": {
        "intent_class": "audit_wrap",
        "sub_intent": "pre_submission",
        "summary": "Before publication: SOPs versioned, reagents lot-tracked, plate maps archived, instrument runs logged.",
        "triggers": [
            "wet lab reproducibility", "can another lab repeat",
            "wet lab audit", "pre-submission wet lab",
        ],
        "token_estimate": 1600,
        "decomposition": [
            {"protocol": "wet_lab/audit/wet_lab_reproducibility_audit",
             "purpose": "Audit the four wet-lab provenance pillars."},
        ],
    },
    "wet_lab/output/methods_section_wet_lab": {
        "intent_class": "synthesize",
        "sub_intent": "methods",
        "summary": "Materials & Methods format for wet-lab papers (antibody clone + lot + RRID, not just 'we used an anti-FLAG antibody').",
        "triggers": [
            "wet lab methods", "materials and methods",
            "antibody methods section", "rrid",
        ],
        "token_estimate": 1500,
        "decomposition": [
            {"protocol": "wet_lab/output/methods_section_wet_lab",
             "purpose": "Build the wet-lab Materials & Methods section."},
        ],
    },
}
