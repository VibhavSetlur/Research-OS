"""Router-index entries for the theory_math pack."""
THEORY_MATH_ROUTER_ENTRIES = {
    "theory_math/proof/proof_verification_workflow": {
        "intent_class": "methodology",
        "sub_intent": "method_pick",
        "summary": "End-to-end proof workflow: claim → strategy → draft → review → optional formal check → publish.",
        "triggers": [
            "prove this", "proof workflow", "draft a proof",
            "proof verification", "iterate on this proof",
        ],
        "token_estimate": 1700,
        "decomposition": [
            {"protocol": "theory_math/proof/proof_verification_workflow",
             "purpose": "Walk the full proof loop."},
        ],
    },
    "theory_math/proof/lemma_library": {
        "intent_class": "memory",
        "sub_intent": "register",
        "summary": "Versioned lemma library with dependents tracking.",
        "triggers": [
            "lemma library", "register a lemma", "reusable lemma",
            "lemma versioning",
        ],
        "token_estimate": 1300,
        "decomposition": [
            {"protocol": "theory_math/proof/lemma_library",
             "purpose": "Add / version / depend on a lemma."},
        ],
    },
    "theory_math/proof/theorem_dependency_graph": {
        "intent_class": "audit_wrap",
        "sub_intent": "provenance",
        "summary": "Theorem → dependencies DAG; flags impact of changing a foundational result.",
        "triggers": [
            "dependency graph", "proof dependencies", "theorem dag",
            "what depends on this theorem", "impact of changing axiom",
        ],
        "shortcut_tool": "tool_theory_math_dep_graph",
        "token_estimate": 1400,
        "decomposition": [
            {"tool": "tool_theory_math_dep_graph",
             "purpose": "Build the DAG by parsing imports + theorem refs."},
            {"protocol": "theory_math/proof/theorem_dependency_graph",
             "purpose": "Walk the DAG to find downstream impact."},
        ],
    },
    "theory_math/conjecture/conjecture_tracking": {
        "intent_class": "memory",
        "sub_intent": "register",
        "summary": "Open-conjecture register with status (open / partial / proven / disproven / counter-example).",
        "triggers": [
            "open problem", "conjecture", "conjecture tracking",
            "open conjecture", "register a conjecture",
        ],
        "token_estimate": 1300,
        "decomposition": [
            {"protocol": "theory_math/conjecture/conjecture_tracking",
             "purpose": "Add / update / triage conjectures."},
        ],
    },
    "theory_math/formal/lean_integration": {
        "intent_class": "execute",
        "sub_intent": "new_experiment",
        "summary": "Lean 4 + Mathlib bridge: draft → .lean file → lean --make → interpret errors.",
        "triggers": [
            "lean proof", "lean 4", "mathlib", "formalise in lean",
            "lean integration",
        ],
        "shortcut_tool": "tool_theory_math_lean_check",
        "token_estimate": 1600,
        "decomposition": [
            {"protocol": "theory_math/formal/lean_integration",
             "purpose": "Scaffold the .lean file from informal draft."},
            {"tool": "tool_theory_math_lean_check",
             "purpose": "Run lean --make + parse errors."},
        ],
    },
    "theory_math/formal/coq_integration": {
        "intent_class": "execute",
        "sub_intent": "new_experiment",
        "summary": "Coq bridge: tactic-language scaffolds + coqc + error parsing.",
        "triggers": [
            "coq proof", "formalise in coq", "ltac", "coq integration",
        ],
        "shortcut_tool": "tool_theory_math_coq_check",
        "token_estimate": 1600,
        "decomposition": [
            {"protocol": "theory_math/formal/coq_integration",
             "purpose": "Scaffold the .v file."},
            {"tool": "tool_theory_math_coq_check",
             "purpose": "Run coqc + parse errors."},
        ],
    },
    "theory_math/output/theory_paper_structure": {
        "intent_class": "synthesize",
        "sub_intent": "paper",
        "summary": "Theory-paper format (NOT IMRAD): Intro / Preliminaries / Main Results / Proofs / Examples / Open Questions.",
        "triggers": [
            "theory paper", "math paper structure", "preliminaries section",
            "open questions section",
        ],
        "token_estimate": 1500,
        "decomposition": [
            {"protocol": "theory_math/output/theory_paper_structure",
             "purpose": "Build the theory-paper skeleton + section bars."},
        ],
    },
    "theory_math/method/proof_strategy_selection": {
        "intent_class": "methodology",
        "sub_intent": "method_pick",
        "summary": "Pick proof strategy: direct | contradiction | induction | contrapositive | construction.",
        "triggers": [
            "proof strategy", "how should I prove", "induction or contradiction",
            "direct proof", "pick a proof method",
            "maximum degree", "minimum degree", "graph coloring",
            "planar graph", "sub-cubic", "subcubic",
        ],
        "token_estimate": 1400,
        "decomposition": [
            {"protocol": "theory_math/method/proof_strategy_selection",
             "purpose": "Compare strategies; name the chosen approach."},
        ],
    },
}
