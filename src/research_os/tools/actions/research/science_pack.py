"""Science-pack integration: the K-Dense scientific-agent-skills library.

Research OS provides the GUIDANCE (the rigorous, provenance-first research
workflow); domain skills provide the CAPABILITY (how to actually run a
bulk-RNA-seq pipeline, design a factorial experiment, dock a ligand, verify a
literature review). The community K-Dense library
(https://github.com/K-Dense-AI/scientific-agent-skills, MIT) is 140 such
skills in the open Agent-Skills SKILL.md standard — the SAME standard Hermes
and the per-IDE rules already consume — so they slot straight in.

This module is the single source of truth for:
  * which upstream repo + pin we reference (we do NOT vendor the skills;
    they update often and are heavy),
  * a curated DOMAIN/MODE → relevant-skill map so recommend_skills() can pull
    the right capability per project,
  * a PROTOCOL/STAGE → skill map so guidance can point the AI at the matching
    skill at the right step.

Stdlib-only, no import of server/daemon. Pure data + small helpers.
"""
from __future__ import annotations

from pathlib import Path

# Upstream reference (pinned by tag for reproducibility; bump deliberately).
SCIENCE_PACK_REPO = "https://github.com/K-Dense-AI/scientific-agent-skills"
SCIENCE_PACK_NAME = "scientific-agent-skills"
SCIENCE_PACK_LICENSE = "MIT"
# Pin to a tag/commit so a project records exactly which skill set it used.
# 'main' is the moving default; the installer records the resolved commit.
SCIENCE_PACK_DEFAULT_REF = "main"

# Domain → the K-Dense skills most relevant to that field. Names are the
# upstream skill directory names (skills/<name>/SKILL.md). Kept conservative:
# better to recommend a few high-signal skills than flood the list.
SCIENCE_PACK_BY_DOMAIN: dict[str, list[str]] = {
    "clinical": [
        "literature-review", "experimental-design", "statistical-power",
        "statistical-analysis", "scikit-survival", "clinical-decision-support",
        "pyhealth", "scientific-writing",
    ],
    "genomics": [
        "biopython", "gget", "bulk-rnaseq", "pydeseq2", "scanpy", "anndata",
        "pysam", "phylogenetics", "literature-review",
    ],
    "bioinformatics": [
        "biopython", "bioservices", "scanpy", "anndata", "pysam", "gget",
        "nextflow", "pathway-enrichment", "literature-review",
    ],
    "chemistry": [
        "rdkit", "datamol", "deepchem", "molfeat", "medchem", "pyopenms",
        "molecular-dynamics", "literature-review",
    ],
    "drug_discovery": [
        "rdkit", "deepchem", "diffdock", "torchdrug", "pytdc", "medchem",
        "primekg", "literature-review",
    ],
    "ml": [
        "scikit-learn", "pytorch-lightning", "transformers", "shap",
        "experimental-design", "statistical-analysis", "scientific-writing",
    ],
    "nlp": [
        "transformers", "literature-review", "scikit-learn",
        "scientific-writing", "statistical-analysis",
    ],
    "neuroscience": [
        "neurokit2", "neuropixels-analysis", "statistical-analysis",
        "experimental-design", "literature-review",
    ],
    "physics": [
        "astropy", "sympy", "fluidsim", "matplotlib",
        "scientific-visualization", "statistical-analysis",
    ],
    "materials": [
        "pymatgen", "molecular-dynamics", "rowan", "scientific-visualization",
        "literature-review",
    ],
    "quantum": [
        "qiskit", "cirq", "pennylane", "qutip", "sympy",
        "scientific-writing",
    ],
    "ecology": [
        "geopandas", "phylogenetics", "statistical-analysis",
        "experimental-design", "scientific-visualization",
    ],
    "economics": [
        "statsmodels", "pymc", "statistical-analysis", "polars",
        "scientific-writing",
    ],
    "finance": [
        "statsmodels", "timesfm-forecasting", "polars", "pymc",
        "statistical-analysis",
    ],
    "social_science": [
        "statistical-analysis", "statistical-power", "experimental-design",
        "pymc", "scientific-writing",
    ],
}

# Workspace-mode → broadly useful science skills regardless of field.
SCIENCE_PACK_BY_MODE: dict[str, list[str]] = {
    "analysis": [
        "exploratory-data-analysis", "statistical-analysis",
        "scientific-visualization", "scientific-writing",
    ],
    "exploration": [
        "exploratory-data-analysis", "scientific-brainstorming",
        "hypothesis-generation",
    ],
    "notebook": ["exploratory-data-analysis", "scientific-visualization"],
    "tool_build": ["optimize-for-gpu", "scikit-learn"],
    "multi_study": ["literature-review", "statistical-analysis"],
    "hybrid": ["exploratory-data-analysis", "statistical-analysis"],
}

# Research-OS protocol / stage → the science skill that supercharges it. Lets
# guidance point the AI at the right capability at the right step. This is the
# TASK-KIND layer: whatever the AI is about to do, it can pull the matching
# capability skill first, then keep working inside Research-OS.
SCIENCE_PACK_BY_PROTOCOL: dict[str, list[str]] = {
    "guidance/analysis_plan": ["experimental-design", "statistical-power"],
    "guidance/deep_planning": ["experimental-design", "scientific-brainstorming"],
    "guidance/iterative_planning": ["scientific-brainstorming",
                                    "hypothesis-generation"],
    "methodology/deep_planning": ["experimental-design",
                                  "scientific-brainstorming"],
    "research/literature_review": ["literature-review", "citation-management"],
    "literature/literature_per_step": ["literature-review",
                                       "citation-management"],
    "research/intake": ["hypothesis-generation", "literature-review"],
    "methodology/data_quality_audit": ["exploratory-data-analysis",
                                       "statistical-analysis"],
    "execute/new_experiment": ["statistical-analysis", "experimental-design"],
    "execute/run_analysis": ["statistical-analysis",
                             "exploratory-data-analysis"],
    "visualization/figure_guidelines": ["scientific-visualization"],
    "visualization/visualization_workflow": ["scientific-visualization"],
    "synthesis/synthesis_paper": ["scientific-writing"],
    "synthesis/synthesis_poster": ["latex-posters", "pptx-posters"],
    "synthesis/synthesis_slides": ["scientific-slides"],
    "audit/pre_submission_checklist": ["peer-review",
                                       "scientific-critical-thinking"],
    "audit/audit_and_validation": ["scientific-critical-thinking",
                                   "statistical-analysis"],
    "reproducibility/reproducibility": ["optimize-for-gpu"],
    "build/spec_and_design": ["scikit-learn"],
    "build/sample_data_and_validation": ["statistical-analysis",
                                         "exploratory-data-analysis"],
}

# Sub-intent (the L2 routing key) → capability tags. Coarser than the protocol
# map but covers task kinds that route to many protocols. Keys are REAL router
# sub_intents (see protocols/_route_meta.json). Advisory tags the AI matches
# against whatever skills are available (Hermes / science-pack / its own).
SUB_INTENT_SKILL_TAGS: dict[str, list[str]] = {
    # planning
    "deep_plan": ["experimental-design", "scientific-brainstorming"],
    "roadmap": ["experimental-design", "scientific-brainstorming"],
    "hypothesis": ["hypothesis-generation", "scientific-brainstorming"],
    # data + analysis
    "new_experiment": ["statistical-analysis", "experimental-design"],
    "eda": ["exploratory-data-analysis", "statistical-analysis"],
    "data_audit": ["exploratory-data-analysis", "statistical-analysis"],
    "data_prep": ["exploratory-data-analysis"],
    "causal": ["causal-inference", "statistical-analysis"],
    "bayesian": ["pymc", "statistical-analysis"],
    "timeseries": ["timesfm-forecasting", "statistical-analysis"],
    "ml": ["scikit-learn", "model-eval"],
    "power": ["statistical-power", "experimental-design"],
    # literature
    "intake": ["literature-review", "hypothesis-generation"],
    "per_step_grounding": ["literature-review", "citation-management"],
    "systematic": ["literature-review", "citation-management"],
    # visualization
    "viz_build": ["scientific-visualization"],
    "figure": ["scientific-visualization"],
    "figures": ["scientific-visualization"],
    "dashboard": ["scientific-visualization"],
    "poster": ["latex-posters", "pptx-posters"],
    "slides": ["scientific-slides"],
    # synthesis / writing
    "paper": ["scientific-writing"],
    "writing": ["scientific-writing"],
    "abstract": ["scientific-writing"],
    "grant": ["scientific-writing"],
    # audit
    "audit": ["scientific-critical-thinking", "peer-review"],
    "reviewer_sim": ["peer-review", "scientific-critical-thinking"],
    "submission": ["peer-review", "scientific-writing"],
    # tool_build / hybrid
    "build_implement": ["software-testing", "scikit-learn"],
    "build_evaluate": ["benchmarking", "model-eval"],
    "build_test": ["software-testing"],
    "build_benchmark": ["benchmarking", "model-eval"],
    "build_sample_data": ["exploratory-data-analysis", "statistical-analysis"],
    # reproducibility
    "repro": ["optimize-for-gpu"],
    "reproduce": ["optimize-for-gpu"],
}


def science_skills_for(
    domain: str | None, mode: str | None, protocol: str | None = None,
) -> list[dict]:
    """Return curated K-Dense skill recommendations for a domain + mode +
    (optionally) the specific protocol/stage the AI is about to run.

    Each item: {name, reason, source='science_pack', repo}. Deduped, capped
    by the caller. Pure data lookup; safe with unknown domain/mode/protocol.
    The protocol mapping is listed FIRST so the task-specific capability the
    AI needs for THIS step leads the recommendations.
    """
    out: list[dict] = []
    seen: set[str] = set()
    dom = (domain or "").strip().lower()
    mode_k = (mode or "analysis").strip().lower()
    proto = (protocol or "").strip()

    def _add(name: str, reason: str) -> None:
        if name in seen:
            return
        seen.add(name)
        out.append({
            "name": name, "reason": reason, "source": "science_pack",
            "repo": SCIENCE_PACK_REPO,
        })

    # Task-specific first: the skill that supercharges THIS protocol/stage.
    for name in SCIENCE_PACK_BY_PROTOCOL.get(proto, []):
        _add(name, f"K-Dense science skill for {proto}")
    for name in SCIENCE_PACK_BY_DOMAIN.get(dom, []):
        _add(name, f"K-Dense science skill for {dom}")
    for name in SCIENCE_PACK_BY_MODE.get(mode_k, []):
        _add(name, f"K-Dense science skill for {mode_k} work")
    return out


def default_install_dir() -> Path:
    """Where the science pack is cloned by default (shared across projects)."""
    import os
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "research-os" / SCIENCE_PACK_NAME


def install_science_pack(
    dest: Path | str | None = None, ref: str = SCIENCE_PACK_DEFAULT_REF,
    wire_hermes: bool = True,
) -> dict:
    """Clone/refresh the K-Dense science-skills repo and wire it into Hermes.

    We REFERENCE (clone + pin) rather than vendor: the library is large and
    updates often. The clone's ``skills/`` dir is registered into Hermes
    ``skills.external_dirs`` so Hermes loads all of them alongside its own +
    RO's skill. IDEs that follow the Agent-Skills standard can point at the
    same ``skills/`` dir. Returns a summary dict; never raises out — failures
    come back as ``status='error'`` with a hint so the CLI can report cleanly.
    """
    import shutil
    import subprocess

    dest_path = Path(dest) if dest else default_install_dir()
    skills_dir = dest_path / "skills"
    try:
        if not shutil.which("git"):
            return {"status": "error",
                    "message": "git not found; install git to fetch the science pack."}
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        if (dest_path / ".git").exists():
            subprocess.run(["git", "-C", str(dest_path), "fetch", "--depth", "1",
                            "origin", ref], check=True, capture_output=True, text=True)
            subprocess.run(["git", "-C", str(dest_path), "checkout", ref],
                           check=True, capture_output=True, text=True)
            subprocess.run(["git", "-C", str(dest_path), "reset", "--hard",
                            f"origin/{ref}"], check=False, capture_output=True, text=True)
            action = "updated"
        else:
            subprocess.run(["git", "clone", "--depth", "1", "--branch", ref,
                            SCIENCE_PACK_REPO, str(dest_path)],
                           check=True, capture_output=True, text=True)
            action = "cloned"
        # Resolve the exact commit for provenance.
        commit = subprocess.run(["git", "-C", str(dest_path), "rev-parse", "HEAD"],
                                capture_output=True, text=True).stdout.strip()
        n_skills = len([p for p in skills_dir.glob("*/SKILL.md")]) if skills_dir.is_dir() else 0
    except subprocess.CalledProcessError as e:
        return {"status": "error",
                "message": f"git operation failed: {e.stderr or e}".strip()}
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "message": str(e)}

    result = {
        "status": "success",
        "action": action,
        "path": str(dest_path),
        "skills_dir": str(skills_dir),
        "ref": ref,
        "commit": commit,
        "n_skills": n_skills,
        "repo": SCIENCE_PACK_REPO,
        "license": SCIENCE_PACK_LICENSE,
    }
    if wire_hermes:
        try:
            from research_os import hermes_integration
            wired = hermes_integration.register_external_skill_dir(skills_dir)
            result["hermes"] = wired
        except Exception as e:  # noqa: BLE001
            result["hermes"] = {"status": "skipped", "reason": str(e)}
    return result
