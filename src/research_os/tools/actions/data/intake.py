"""Intake auto-fill — read inputs/ and propose the project metadata.

The most accessible workflow is: the researcher drops files into inputs/
(data, PDFs, notes, drafts) and says "fill out the intake". This tool
inspects everything and writes:
  - inputs/intake.md (with proposed research question + domain + key files)
  - docs/research_overview.md   (if currently blank/placeholder)
  - state.json gains inferred domain / research_question / hypotheses so
    later regenerations of intake.md preserve them. The researcher_config
    is intentionally NOT touched here — it's reserved for fields a
    researcher actively chooses (identity, autonomy, model_profile, …).
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from pathlib import Path
from typing import Any

logger = logging.getLogger("research_os.tools.intake")


# Heuristic mappings — keep small and easy to audit.
DOMAIN_HINTS = {
    "clinical": {
        "exts": [".dcm", ".nii"],
        "cols": ["patient_id", "diagnosis", "treatment", "icd", "trial"],
        "keywords": ["patient", "treatment", "clinical", "outcome", "diagnosis"],
    },
    "epidemiology": {
        "exts": [".sav", ".dta", ".csv"],
        "cols": ["exposure", "cohort", "incidence", "prevalence", "follow_up"],
        "keywords": ["incidence", "cohort", "epidemio", "exposure"],
    },
    "genomics": {
        "exts": [".fasta", ".fastq", ".bam", ".vcf", ".gtf", ".gff"],
        "cols": ["gene_id", "log2fc", "padj", "chromosome"],
        "keywords": ["rna-seq", "genome", "gene expression", "variant", "alignment"],
    },
    "biology_ecology": {
        "exts": [".csv", ".tsv"],
        "cols": [
            "species", "sex", "island", "habitat", "site", "taxon",
            "bill_length_mm", "bill_depth_mm", "flipper_length_mm",
            "body_mass_g", "wing_chord", "tarsus", "morphotype",
        ],
        "keywords": [
            "species", "ecology", "biology", "morphology", "morphometric",
            "dimorphism", "allometric", "phenotype", "population", "fauna",
            "flora", "wildlife", "field study", "pygoscelis", "passerine",
            "vertebrate", "invertebrate",
        ],
    },
    "nlp": {
        "exts": [".jsonl", ".txt", ".arrow"],
        "cols": ["text", "label", "tokens"],
        "keywords": ["nlp", "language model", "tokenis", "transformer", "embedding"],
    },
    "finance": {
        "exts": [".csv", ".xlsx"],
        "cols": ["ticker", "price", "volume", "yield", "pe_ratio"],
        "keywords": ["return", "portfolio", "alpha", "market", "stock"],
    },
    "economics": {
        "exts": [".dta", ".csv", ".xlsx"],
        "cols": ["country", "gdp", "inflation", "unemployment"],
        "keywords": ["panel", "macro", "monetary", "gdp", "labor"],
    },
    "geospatial": {
        "exts": [".shp", ".tiff", ".geojson", ".nc"],
        "cols": ["latitude", "longitude", "elevation"],
        "keywords": ["satellite", "remote sensing", "raster", "spatial"],
    },
    "social_sciences": {
        "exts": [".sav", ".csv"],
        "cols": ["respondent", "likert", "demographic"],
        "keywords": ["survey", "questionnaire", "respondent"],
    },
    "ml_benchmark": {
        "exts": [".csv", ".parquet", ".arrow"],
        "cols": ["target", "features", "split"],
        "keywords": ["benchmark", "baseline", "accuracy", "auroc"],
    },
}


def _classify_domain(files: list[Path], context_text: str) -> tuple[str, list[str]]:
    """Score each domain by signals; return the winner + a short rationale."""
    ctx = context_text.lower()
    scores: Counter[str] = Counter()
    rationales: dict[str, list[str]] = {d: [] for d in DOMAIN_HINTS}

    ext_set = {p.suffix.lower() for p in files}
    column_set: set[str] = set()
    for p in files:
        if p.suffix.lower() in {".csv", ".tsv"}:
            try:
                header = p.read_text(errors="replace").splitlines()[:1]
                if header:
                    sep = "," if p.suffix.lower() == ".csv" else "\t"
                    for col in header[0].split(sep):
                        column_set.add(col.strip().strip('"').lower())
            except Exception:
                pass

    for domain, hints in DOMAIN_HINTS.items():
        for ext in hints.get("exts", []):
            if ext in ext_set:
                scores[domain] += 2
                rationales[domain].append(f"file extension {ext}")
        for col in hints.get("cols", []):
            if col in column_set:
                scores[domain] += 3
                rationales[domain].append(f"column `{col}`")
        for kw in hints.get("keywords", []):
            if kw in ctx:
                scores[domain] += 2
                rationales[domain].append(f"keyword '{kw}' in context notes")

    if not scores:
        return ("general", ["no specific signals detected"])
    winner, _ = scores.most_common(1)[0]
    return (winner, rationales[winner][:5])


def _propose_question(context_text: str, raw_files: list[Path]) -> str:
    """Pull the first plausible research question from context notes."""
    if context_text:
        # Look for explicit research-question patterns.
        patterns = [
            r"(?im)^research\s*question[:\-]\s*(.+)$",
            r"(?im)^rq[:\-]\s*(.+)$",
            r"(?im)^aim[:\-]\s*(.+)$",
            r"(?im)^objective[:\-]\s*(.+)$",
        ]
        for pat in patterns:
            m = re.search(pat, context_text)
            if m:
                return m.group(1).strip()
        # Fallback: the first sentence ending in "?" if any.
        m = re.search(r"([A-Z][^?]{15,200}\?)", context_text)
        if m:
            return m.group(1).strip()

    # Fallback when no notes — say so.
    if raw_files:
        return (
            f"What patterns / relationships can we identify across the "
            f"{len(raw_files)} input file(s)?  *(AI-proposed placeholder — refine.)*"
        )
    return "*(no research question proposed — add context to inputs/context/)*"


def _propose_hypotheses(context_text: str) -> list[str]:
    """Pick out any H1/H2/H3 style hypotheses from context notes.

    Handles common styles:
      H1: text
      Hypothesis 1: text
      - H1 — text
      - **H1** — text             (markdown bold)
      * H1: text                  (bullet)
      1. **Hypothesis** — text
    """
    if not context_text:
        return []
    hits: list[str] = []
    # Pattern 1: explicit "H<n>" or "Hypothesis <n>" labels, optionally
    # wrapped in markdown bullets / bold / hashes. Separator can be
    # ":", "-", "—", "–".
    pat = re.compile(
        r"""(?ixm)
        ^\s*                       # leading whitespace
        (?:[-*+]\s+|\d+[.)]\s+)?   # optional list marker
        (?:[*_]{1,2})?             # optional opening bold/italic
        (?:hypothesis|h)           # word "hypothesis" or letter H
        (?:[*_]{1,2})?             # optional close of bold around the word
        \s*(\d+)\b                 # the index (mandatory — we need H1 vs noise)
        (?:[*_]{1,2})?             # optional close after number
        \s*[:\-–—]\s*    # separator
        (.{15,400}?)               # the hypothesis text
        \s*$
        """
    )
    for m in pat.finditer(context_text):
        text = re.sub(r"^[*_]+|[*_]+$", "", m.group(2)).strip()
        if text:
            hits.append(text)
    return hits[:6]


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def intake_autofill(root: Path, *, overwrite: bool = False) -> dict[str, Any]:
    """Read inputs/, infer project metadata, and populate intake + config."""
    try:
        from research_os.project_ops import (
            compute_file_hash,
            load_state,
            now_iso,
            regenerate_intake,
            save_state,
        )

        inputs_dir = root / "inputs"
        if not inputs_dir.exists():
            return {"status": "error", "message": "inputs/ not found"}

        # Collect files
        raw_files = sorted(
            f for f in (inputs_dir / "raw_data").rglob("*")
            if f.is_file() and not f.name.startswith(".") and f.name != ".gitkeep"
        ) if (inputs_dir / "raw_data").exists() else []
        literature_files = sorted(
            f for f in (inputs_dir / "literature").rglob("*")
            if f.is_file() and f.suffix.lower() in {".pdf", ".epub"}
        ) if (inputs_dir / "literature").exists() else []
        context_files = sorted(
            f for f in (inputs_dir / "context").rglob("*")
            if f.is_file() and not f.name.startswith(".") and f.name != ".gitkeep"
        ) if (inputs_dir / "context").exists() else []

        context_text_parts: list[str] = []
        for cf in context_files:
            if cf.suffix.lower() in {".md", ".txt", ".rst", ".org"}:
                try:
                    context_text_parts.append(cf.read_text(errors="replace"))
                except Exception:
                    pass
        context_text = "\n\n".join(context_text_parts)

        # Classify + propose. Respect existing state when already set —
        # init's --domain / --question flags land in state before this
        # tool runs, and rewriting them here was overwriting the
        # researcher's deliberate input with weaker auto-inferences.
        state_pre = load_state(root)
        existing_domain = (state_pre.get("domain") or "").strip()
        existing_question = (state_pre.get("research_question") or "").strip()
        domain_auto, domain_why = _classify_domain(raw_files, context_text)
        domain = existing_domain or domain_auto
        if existing_domain:
            domain_why = [f"preserved from state.domain = {existing_domain!r}"]
        question_auto = _propose_question(context_text, raw_files)
        # Keep state's question unless it was the placeholder.
        question = (
            existing_question if existing_question
            and "*(AI-proposed placeholder" not in existing_question
            else question_auto
        )
        hypotheses = _propose_hypotheses(context_text)

        # NOTE: researcher_config.yaml is no longer touched here. Domain /
        # research_question / hypotheses are written to state (below) and
        # to inputs/intake.md (via regenerate_intake at the end of this
        # function). The config is reserved for fields a researcher
        # actively chooses.

        # Create / update docs/research_overview.md. Scaffold no longer
        # pre-creates this file (the placeholder text was unnecessary
        # boilerplate), so intake_autofill is the canonical writer.
        rq_path = root / "docs" / "research_overview.md"
        rq_path.parent.mkdir(parents=True, exist_ok=True)
        rq_changed = False
        write = True
        if rq_path.exists():
            current = rq_path.read_text()
            placeholders = ("(blank", "(to be", "*(blank", "*(to be", "to be filled")
            is_placeholder = any(m in current.lower() for m in placeholders)
            write = overwrite or is_placeholder or len(current.strip()) < 60
        if write:
            rq_body = (
                f"# Research Question\n\n"
                f"{question}\n\n"
            )
            if hypotheses:
                rq_body += "## Hypotheses (inferred from inputs/context)\n\n"
                for i, h in enumerate(hypotheses, 1):
                    rq_body += f"- H{i}: {h}\n"
                rq_body += "\n"
            rq_body += (
                "## Last updated\n\n"
                f"{now_iso()} — populated by `tool_intake_autofill`.\n"
            )
            rq_path.write_text(rq_body)
            rq_changed = True

        # Persist intake findings to state so later intake regenerations
        # (which run without explicit overrides) keep the inferred values.
        state = load_state(root)
        state_dirty = False
        if domain and (overwrite or not state.get("domain")):
            state["domain"] = domain
            state_dirty = True
        if question and (overwrite or not state.get("research_question")):
            state["research_question"] = question
            state_dirty = True
        if hypotheses:
            existing = state.setdefault("active_hypotheses", [])
            existing_ids = {h.get("id") for h in existing if isinstance(h, dict)}
            for i, h_text in enumerate(hypotheses, 1):
                hid = f"H{i}"
                if hid not in existing_ids:
                    existing.append({"id": hid, "statement": h_text, "status": "testing"})
                    state_dirty = True
        if state_dirty:
            save_state(root, state)

        # Regenerate intake.md with fresh hashes + the proposed content
        intake_path = regenerate_intake(
            root,
            project_name=state.get("project_name") or "Research Project",
            config_overrides={
                "research_question": question,
                "domain": domain,
                "keywords": hypotheses[:5],
            },
        )

        # Build the autofill report
        summary = {
            "status": "success",
            "files_seen": {
                "raw_data": len(raw_files),
                "literature": len(literature_files),
                "context": len(context_files),
            },
            "proposed_domain": domain,
            "domain_rationale": domain_why,
            "proposed_research_question": question,
            "proposed_hypotheses": hypotheses,
            "state_fields_updated": [
                k for k in ("domain", "research_question", "active_hypotheses")
                if state.get(k)
            ],
            "research_question_md_updated": rq_changed,
            "intake_path": intake_path,
            "message": (
                "Intake autofilled. The AI should review with the researcher: "
                "'I read your inputs. I propose domain=<X>, question=<Y>. Approve?'"
            ),
        }
        return summary
    except Exception as e:
        logger.exception("intake_autofill failed")
        return {"status": "error", "message": str(e)}
