#!/usr/bin/env python3
"""Semantic File System Hook — enforces experiment-driven artifact taxonomy.

Post-generation hook that forces every AI-generated artifact into a strict,
immutable directory structure. Ensures data lineage and methodological
decisions are instantly auditable.

Taxonomy:
  00_inputs/raw_data/     — Immutable raw data (AI never modifies after ingest)
  00_inputs/literature/   — User-provided papers and literature cache exports

  01_workspace/scratchpad/    — Random thoughts, links, and triage queue
  01_workspace/lab_notebook.md — Append-only chronological notebook

  02_experiments/<exp>/scripts/             — Experiment scripts
  02_experiments/<exp>/outputs/figures/     — Figures plus .meta.yaml sidecars
  02_experiments/<exp>/outputs/tables/      — Tables plus .meta.yaml sidecars
  02_experiments/<exp>/outputs/artifacts/   — Models/data chunks plus .meta.yaml sidecars
  02_experiments/<exp>/decisions.yaml       — Experiment assumption ledger

  03_synthesis/           — Manuscript, final figures, global methods, audit

Usage (as interceptor):
    from semantic_filesystem import enforce_semantic_taxonomy
    state = enforce_semantic_taxonomy(state, generated_file="results.csv")
"""

import json
import logging
import re
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("research.semantic_filesystem")

SEMANTIC_TAXONOMY = {
    "raw_data": {
        "pattern": r".*\.(csv|parquet|tsv|json|feather|arrow|xlsx|sav|dta)$",
        "destination": "00_inputs/raw_data/",
        "writable": False,
        "description": "Immutable raw data — AI never modifies",
    },
    "derived_data": {
        "pattern": r".*\.(csv|parquet|tsv|json|feather|arrow)$",
        "destination": "02_experiments/{experiment_id}/outputs/artifacts/",
        "writable": True,
        "description": "User-provided derived data",
    },
    "metadata": {
        "pattern": r".*(metadata|codebook|dictionary|schema).*\.(json|yaml|csv|md)$",
        "destination": "00_inputs/",
        "writable": True,
        "description": "Data dictionaries and codebooks",
    },
    "decision_doc": {
        "pattern": r".*(decision|rationale|choice|why).*\.(md|json)$",
        "destination": "02_experiments/{experiment_id}/",
        "writable": True,
        "description": "Methodological decisions with rationale",
    },
    "method_doc": {
        "pattern": r".*(method|methodology|approach).*\.(md|json)$",
        "destination": "03_synthesis/",
        "writable": True,
        "description": "Methodological documentation",
    },
    "assumption_doc": {
        "pattern": r".*(assumption|assumptions|diagnostic).*\.(md|json|csv)$",
        "destination": "02_experiments/{experiment_id}/outputs/analysis/",
        "writable": True,
        "description": "Statistical assumption checks",
    },
    "ingest_script": {
        "pattern": r"01_.*\.(py|R|jl)$",
        "destination": "02_experiments/{experiment_id}/scripts/",
        "writable": True,
        "description": "Data ingestion scripts",
    },
    "eda_script": {
        "pattern": r"02_.*\.(py|R|jl)$",
        "destination": "02_experiments/{experiment_id}/scripts/",
        "writable": True,
        "description": "Exploratory data analysis scripts",
    },
    "model_script": {
        "pattern": r"03_.*\.(py|R|jl)$",
        "destination": "02_experiments/{experiment_id}/scripts/",
        "writable": True,
        "description": "Statistical model scripts",
    },
    "output_script": {
        "pattern": r"04_.*\.(py|R|jl)$",
        "destination": "02_experiments/{experiment_id}/scripts/",
        "writable": True,
        "description": "Report generation scripts",
    },
    "figure": {
        "pattern": r".*\.(png|pdf|svg|jpg|jpeg)$",
        "destination": "02_experiments/{experiment_id}/outputs/figures/",
        "writable": True,
        "description": "Generated figures",
    },
    "table": {
        "pattern": r".*table.*\.(md|tex|csv|xlsx)$",
        "destination": "02_experiments/{experiment_id}/outputs/tables/",
        "writable": True,
        "description": "Generated tables",
    },
    "manuscript": {
        "pattern": r".*(manuscript|draft|section|paper).*\.(md|tex|docx)$",
        "destination": "03_synthesis/manuscript/",
        "writable": True,
        "description": "Draft manuscript sections",
    },
    "rebuttal": {
        "pattern": r".*(rebuttal|response|reviewer).*\.(md|json)$",
        "destination": "03_synthesis/audit/",
        "writable": True,
        "description": "Reviewer 2 rebuttal memos",
    },
    "interpretation": {
        "pattern": r".*\.interpret\.md$",
        "destination": "02_experiments/{experiment_id}/outputs/figures/",
        "writable": True,
        "description": "Auto-generated figure interpretations",
    },
}

OUTPUT_CATEGORIES_REQUIRING_SIDECAR = {"figure", "table", "derived_data", "assumption_doc"}


class SemanticFilesystemEnforcer:
    """Enforces semantic file system taxonomy on all generated artifacts."""

    def __init__(self, project_root: Optional[Path] = None):
        if project_root is None:
            project_root = self._find_project_root()
        self.root = Path(project_root)

    @staticmethod
    def _find_project_root() -> Path:
        p = Path.cwd()
        for _ in range(10):
            if (p / ".research").exists():
                return p
            if p.parent == p:
                break
            p = p.parent
        return Path.cwd()

    def classify_file(self, filename: str, content_type: str = "") -> Tuple[str, str]:
        """Classify a file and determine its correct destination.

        Args:
            filename: Name of the file
            content_type: Optional content type hint

        Returns:
            Tuple of (category, destination_path)
        """
        for category, rule in SEMANTIC_TAXONOMY.items():
            if re.match(rule["pattern"], filename, re.IGNORECASE):
                return category, rule["destination"]

        if content_type:
            if "image" in content_type:
                return "figure", "02_experiments/{experiment_id}/outputs/figures/"
            if "table" in content_type or "csv" in content_type:
                return "table", "02_experiments/{experiment_id}/outputs/tables/"

        return "unknown", "02_experiments/{experiment_id}/outputs/artifacts/"

    def resolve_path(
        self,
        filename: str,
        branch_id: str = "exp_001_baseline",
        question_id: str = "",
        content_type: str = "",
    ) -> Path:
        """Resolve the full path for a generated file.

        Args:
            filename: Name of the file
            branch_id: Current branch (for branch-aware directories)
            question_id: Research question ID (e.g., 'q1')
            content_type: Optional content type hint

        Returns:
            Full Path object for the file
        """
        category, base_dest = self.classify_file(filename, content_type)
        rule = SEMANTIC_TAXONOMY.get(category, {})

        if rule.get("writable") is False:
            raise ValueError(
                f"File '{filename}' classified as '{category}' — "
                f"AI cannot write to {rule['destination']}"
            )

        dest_template = base_dest.format(experiment_id=branch_id)
        dest = self.root / dest_template

        if question_id and "/outputs/" in dest_template:
            dest = dest / question_id

        dest.mkdir(parents=True, exist_ok=True)
        return dest / filename

    def write_sidecar_metadata(
        self,
        file_path: Path,
        *,
        generated_by: str,
        source_script: str,
        input_files: Optional[list[str]] = None,
        decisions_applied: Optional[list[str]] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Path:
        """Write `<artifact>.meta.yaml` next to a generated output.

        The sidecar is required for experiment outputs so a future reader can
        recover agent, script, input hashes, and local decision lineage.
        """
        file_path = Path(file_path)
        input_files = input_files or []
        decisions_applied = decisions_applied or []
        extra = extra or {}
        data_hashes = {}
        for item in input_files:
            path = self.root / item if not Path(item).is_absolute() else Path(item)
            if path.exists() and path.is_file():
                data_hashes[item] = hashlib.sha256(path.read_bytes()).hexdigest()

        meta_path = file_path.with_name(f"{file_path.stem}.meta.yaml")
        lines = [
            f"generated_by: \"{generated_by}\"",
            f"timestamp: \"{datetime.now(timezone.utc).isoformat()}\"",
            f"source_script: \"{source_script}\"",
            "input_files:",
        ]
        lines.extend(f"  - \"{item}\"" for item in input_files)
        lines.append("data_hashes:")
        if data_hashes:
            lines.extend(f"  \"{k}\": \"{v}\"" for k, v in data_hashes.items())
        else:
            lines.append("  {}")
        lines.append("decisions_applied:")
        lines.extend(f"  - \"{item}\"" for item in decisions_applied)
        for key, value in extra.items():
            lines.append(f"{key}: {json.dumps(value)}")
        meta_path.write_text("\n".join(lines) + "\n")
        return meta_path

    def validate_artifact(
        self,
        file_path: Path,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Validate that an artifact is in the correct location with proper metadata.

        Args:
            file_path: Path to the artifact
            metadata: Optional metadata to attach

        Returns:
            Validation result dict
        """
        relative = file_path.relative_to(self.root) if file_path.is_absolute() else file_path
        parts = relative.parts

        result = {
            "file": str(file_path),
            "valid": True,
            "category": "unknown",
            "warnings": [],
        }

        for category, rule in SEMANTIC_TAXONOMY.items():
            if rule["destination"].rstrip("/") in str(relative):
                result["category"] = category
                break

        if result["category"] == "unknown":
            result["warnings"].append(
                f"File not classified into any taxonomy category: {file_path}"
            )

        if metadata:
            result["metadata"] = metadata

        if result["category"] in OUTPUT_CATEGORIES_REQUIRING_SIDECAR:
            sidecar = Path(file_path).with_name(f"{Path(file_path).stem}.meta.yaml")
            if not sidecar.exists():
                result["valid"] = False
                result["warnings"].append(f"Missing sidecar provenance file: {sidecar}")

        return result

    def enforce_on_generation(
        self,
        filename: str,
        content: str,
        branch_id: str = "main",
        question_id: str = "",
        generating_agent: str = "",
        generating_skill: str = "",
    ) -> Path:
        """Enforce taxonomy when generating a new artifact.

        Args:
            filename: Name of the file to create
            content: File content
            branch_id: Current branch
            question_id: Research question ID
            generating_agent: Agent that generated this file
            generating_skill: Skill that generated this file

        Returns:
            Path where the file was written
        """
        dest_path = self.resolve_path(filename, branch_id, question_id)

        if not filename.endswith((".md", ".json", ".yaml")):
            frontmatter = self._generate_frontmatter(
                generating_agent, generating_skill, filename
            )
            content = frontmatter + "\n" + content

        with open(dest_path, "w") as f:
            f.write(content)

        logger.info("Enforced taxonomy: %s -> %s", filename, dest_path)
        return dest_path

    def _generate_frontmatter(
        self, agent: str, skill: str, filename: str
    ) -> str:
        """Generate YAML frontmatter for provenance tracking."""
        return f"""---
producing_agent: {agent}
producing_skill: {skill}
generated_at: {datetime.now(timezone.utc).isoformat()}
filename: {filename}
project_root: {self.root}
---"""

    def ensure_base_structure(self) -> Dict[str, Path]:
        """Ensure all base taxonomy directories exist.

        Returns:
            Dict of category -> directory path
        """
        created = {}
        for category, rule in SEMANTIC_TAXONOMY.items():
            dest = self.root / rule["destination"]
            dest.mkdir(parents=True, exist_ok=True)
            created[category] = dest

        return created

    def summary(self) -> str:
        """Print the semantic file system taxonomy."""
        lines = [
            "=" * 60,
            "SEMANTIC FILE SYSTEM TAXONOMY",
            "=" * 60,
            "",
        ]

        for category, rule in SEMANTIC_TAXONOMY.items():
            lock = "🔒" if not rule["writable"] else "✏️"
            lines.append(f"  {lock} {category}")
            lines.append(f"     Pattern: {rule['pattern']}")
            lines.append(f"     Destination: {rule['destination']}")
            lines.append(f"     {rule['description']}")
            lines.append("")

        return "\n".join(lines)


def enforce_semantic_taxonomy(state: dict, *args, **kwargs) -> dict:
    """Interceptor: enforce semantic taxonomy on generated artifacts.

    Called as a post_execution hook. Checks if state contains generated
    file info and validates/enforces the taxonomy.
    """
    generated_file = state.get("generated_file", "")
    if not generated_file:
        return state

    project_root = _find_project_root()
    enforcer = SemanticFilesystemEnforcer(project_root)

    try:
        category, destination = enforcer.classify_file(generated_file)
        state["file_taxonomy_category"] = category
        state["file_taxonomy_destination"] = destination

        if SEMANTIC_TAXONOMY.get(category, {}).get("writable") is False:
            state["taxonomy_violation"] = True
            state["taxonomy_violation_reason"] = (
                f"Cannot write '{generated_file}' to '{destination}' — "
                f"AI cannot modify {category}"
            )
            logger.error("Taxonomy violation: %s", state["taxonomy_violation_reason"])
        else:
            state["taxonomy_violation"] = False
    except Exception as e:
        state["taxonomy_error"] = str(e)

    return state


def _find_project_root() -> Path:
    p = Path.cwd()
    for _ in range(10):
        if (p / ".research").exists():
            return p
        if p.parent == p:
            break
        p = p.parent
    return Path.cwd()
