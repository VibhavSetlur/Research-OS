"""Router-index entries for the humanities pack.

Merged into the core router map at startup. Every key is prefixed
with `humanities/...` per the namespace convention; the loader rejects
unprefixed keys.
"""
HUMANITIES_ROUTER_ENTRIES = {
    "humanities/archival/archival_research": {
        "intent_class": "execute",
        "sub_intent": "new_experiment",
        "summary": "Workflow for working with primary sources: locate → photograph/scan → transcribe → annotate → cite.",
        "triggers": [
            "archival research", "work with primary sources",
            "go to the archive", "manuscript work", "archive trip",
            "primary source", "transcribe a manuscript",
        ],
        "shortcut_tool": "tool_humanities_archive_lookup",
        "token_estimate": 1700,
        "decomposition": [
            {"tool": "tool_humanities_archive_lookup",
             "purpose": "Plan + execute archive queries."},
            {"tool": "tool_humanities_transcribe",
             "purpose": "OCR + side-by-side correction template per image."},
            {"protocol": "humanities/archival/archival_research",
             "purpose": "Walk the locate → transcribe → annotate loop."},
        ],
    },
    "humanities/archival/source_provenance": {
        "intent_class": "audit_wrap",
        "sub_intent": "provenance",
        "summary": "Chain-of-custody for quotations: ms → critical edition → translation → secondary citation.",
        "triggers": [
            "source provenance", "where does this quote come from",
            "translation chain", "citation chain", "trace this quotation",
        ],
        "shortcut_tool": "tool_humanities_citation_chain",
        "token_estimate": 1300,
        "decomposition": [
            {"tool": "tool_humanities_citation_chain",
             "purpose": "Scaffold the chain-of-custody markdown."},
            {"protocol": "humanities/archival/source_provenance",
             "purpose": "Walk the chain back link by link."},
        ],
    },
    "humanities/textual/close_reading": {
        "intent_class": "methodology",
        "sub_intent": "method_pick",
        "summary": "Annotation-based textual analysis with provenance per claim.",
        "triggers": [
            "close reading", "annotate a passage", "explication de texte",
            "line-by-line reading", "marginalia",
        ],
        "token_estimate": 1500,
        "decomposition": [
            {"protocol": "humanities/textual/close_reading",
             "purpose": "Walk the annotate → claim → ground loop."},
        ],
    },
    "humanities/textual/distant_reading": {
        "intent_class": "methodology",
        "sub_intent": "method_pick",
        "summary": "Text-as-data corpus analysis (NLP / topic models / stylometry) WITH humanistic interpretation gate.",
        "triggers": [
            "distant reading", "corpus analysis", "topic model",
            "stylometry", "text mining", "computational literary",
        ],
        "token_estimate": 1800,
        "decomposition": [
            {"protocol": "humanities/textual/distant_reading",
             "purpose": "Build the corpus + analysis + interpretation gate."},
        ],
    },
    "humanities/method/hermeneutic_method": {
        "intent_class": "methodology",
        "sub_intent": "method_pick",
        "summary": "Make the theory of interpretation explicit (Schleiermacher / Gadamer / Ricoeur).",
        "triggers": [
            "hermeneutic", "interpretive method", "what theory of reading",
            "gadamer", "ricoeur", "schleiermacher", "horizon of",
        ],
        "token_estimate": 1500,
        "decomposition": [
            {"protocol": "humanities/method/hermeneutic_method",
             "purpose": "Pick + name the hermeneutic framework, then read."},
        ],
    },
    "humanities/method/digital_humanities_workflow": {
        "intent_class": "methodology",
        "sub_intent": "method_pick",
        "summary": "Hybrid distant + close reading. Includes the 'computers don't read meaning' caveat.",
        "triggers": [
            "digital humanities", "dh project", "computational humanities",
            "mixed reading", "scale and close-read",
        ],
        "token_estimate": 1700,
        "decomposition": [
            {"protocol": "humanities/method/digital_humanities_workflow",
             "purpose": "Distant scan + close-read sampling + interpretation."},
        ],
    },
    "humanities/citation/citation_chains": {
        "intent_class": "literature",
        "sub_intent": "per_step",
        "summary": "Genealogy of an idea across centuries (Aristotle → Aquinas → Heidegger).",
        "triggers": [
            "intellectual history", "genealogy of an idea",
            "trace an argument", "reception history",
            "how did this idea evolve",
        ],
        "shortcut_tool": "tool_humanities_citation_chain",
        "token_estimate": 1600,
        "decomposition": [
            {"tool": "tool_humanities_citation_chain",
             "purpose": "Scaffold the chain markdown."},
            {"protocol": "humanities/citation/citation_chains",
             "purpose": "Walk the chain forward (Aristotle → us) AND backward."},
        ],
    },
    "humanities/output/scholarly_edition": {
        "intent_class": "synthesize",
        "sub_intent": "edition",
        "summary": "Prepare a critical edition: text + apparatus criticus + textual notes + translation.",
        "triggers": [
            "critical edition", "scholarly edition", "apparatus criticus",
            "diplomatic edition", "edit the text",
        ],
        "token_estimate": 2000,
        "decomposition": [
            {"protocol": "humanities/output/scholarly_edition",
             "purpose": "Stemma → base text → apparatus → notes → translation."},
        ],
    },
}
