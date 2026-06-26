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

import csv
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
                # Read ONLY the first line (O(one line) memory) instead of
                # read_text().splitlines(), which materialises the entire
                # (possibly multi-GB) file just to look at the header.
                with open(p, encoding="utf-8", errors="replace") as fh:
                    first = fh.readline()
                if first:
                    sep = "," if p.suffix.lower() == ".csv" else "\t"
                    for col in first.rstrip("\n").split(sep):
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
    """Pick out hypotheses from context notes.

    Handles common explicit styles AND falls back to natural-language
    extraction so PI briefs written in prose don't yield zero hypotheses.

    Explicit styles:
      H1: text
      Hypothesis 1: text
      - H1 — text
      - **H1** — text             (markdown bold)
      * H1: text                  (bullet)
      1. **Hypothesis** — text

    Natural-language fallback (only used when no explicit hypotheses found):
      - Sentences starting with "We hypothesise" / "We predict" / "We expect".
      - Sentences containing "is associated with" / "differs across" /
        "replicates the" / "is modulated by".
    """
    if not context_text:
        return []

    hits: list[str] = []
    # Pattern 1: explicit "H<n>" or "Hypothesis <n>" labels.
    pat = re.compile(
        r"""(?ixm)
        ^\s*                       # leading whitespace
        (?:[-*+]\s+|\d+[.)]\s+)?   # optional list marker
        (?:[*_]{1,2})?             # optional opening bold/italic
        (?:hypothesis|h)           # word "hypothesis" or letter H
        (?:[*_]{1,2})?             # optional close of bold around the word
        \s*(\d+)\b                 # the index
        (?:[*_]{1,2})?             # optional close after number
        \s*[:\-–—]\s*              # separator
        (.{15,400}?)               # the hypothesis text
        \s*$
        """
    )
    for m in pat.finditer(context_text):
        text = re.sub(r"^[*_]+|[*_]+$", "", m.group(2)).strip()
        if text:
            hits.append(text)

    if hits:
        return hits[:6]

    # Fallback: natural-language sentences that read like hypotheses.
    nl_pat = re.compile(
        r"""(?ix)
        ([A-Z][^.\n]{15,400}?
          \b(?:
              hypothesi[sz]e|hypothesi[sz]ed|
              predict|predicts|predicted|
              expect|expects|expected\s+to|
              is\s+associated\s+with|are\s+associated\s+with|
              differs?\s+(?:across|between|by)|
              replicates?\s+(?:the\s+)?|
              is\s+modulated\s+by
          )
          \b[^.\n]{5,300})
        \.
        """
    )
    for m in nl_pat.finditer(context_text):
        text = m.group(1).strip()
        if text and text not in hits:
            hits.append(text)

    return hits[:6]


def _extract_named_papers(context_text: str) -> list[str]:
    """Pull plausible paper references out of a PI brief.

    PI briefs typically say things like "Cite Himes et al 2014" or
    "Compare with the GTEx airway atlas" or "see Verhaak 2010". These
    are not formal citations the AI can resolve from a DOI — they're
    cues the AI should run a literature search for.

    Returns a deduplicated list of human-readable reference strings.
    """
    if not context_text:
        return []
    hits: list[str] = []
    # Pattern: "(Author) et al (YYYY)" or "Author YYYY" or "Author and
    # Author YYYY" — case-sensitive on first letter so we don't grab
    # random capitalised words. Excludes month names + common non-
    # author capitalised words via a stop-list (a regex can't easily
    # tell "Himes 2014" from "Nov 2014").
    NON_AUTHOR = {
        "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug",
        "Sep", "Oct", "Nov", "Dec",
        "January", "February", "March", "April", "May", "June", "July",
        "August", "September", "October", "November", "December",
        "Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
        "Saturday", "Sunday",
        "Biology", "Cell", "Nature", "Science", "PNAS", "Genet",
        "Genome", "Methods", "Genetics", "Lancet", "BMJ", "JAMA",
        "Cancer", "Brain", "Heart", "Kidney", "Blood",
    }
    patterns = [
        # "Himes BE, et al PLOS ONE 2014" or "Himes et al 2014" or
        # "Himes BE et al. 2014"
        re.compile(
            r"\b([A-Z][a-z]+(?:\s+[A-Z]{1,3},?)?(?:\s+and\s+[A-Z][a-z]+)?"
            r"\s*,?\s*et\s+al\.?(?:\s+[A-Za-z][\w]*){0,5}\s*\(?(\d{4})\)?)"
        ),
        # "Himes 2014" (bare surname + year)
        re.compile(r"\b([A-Z][a-z]+\s+\(?(\d{4})\)?)\b"),
        # "the GTEx atlas" / "the TCGA cohort"
        re.compile(r"\b(?:the\s+)?([A-Z][A-Z]{2,}\s+(?:atlas|dataset|cohort|database|consortium))",
                   re.IGNORECASE),
    ]
    def _is_author(ref: str) -> bool:
        first = ref.split()[0]
        return first not in NON_AUTHOR and not first.isdigit()
    for p in patterns:
        for m in p.finditer(context_text):
            ref = m.group(1).strip()
            if ref and ref not in hits and len(ref) < 80 and _is_author(ref):
                hits.append(ref)
    # De-dupe similar refs (e.g. "Himes 2014" + "Himes et al 2014")
    canonicalised: list[str] = []
    for ref in hits:
        key = re.sub(r"\s+et\s+al\.?", "", ref).lower()
        if not any(re.sub(r"\s+et\s+al\.?", "", c).lower() == key for c in canonicalised):
            canonicalised.append(ref)
    return canonicalised[:8]


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def intake_autofill(
    root: Path,
    *,
    overwrite: bool = False,
    question: str | None = None,
    domain: str | None = None,
    hypotheses: list[str] | None = None,
    context_note: str | None = None,
) -> dict[str, Any]:
    """Read inputs/, infer project metadata, and populate intake + config.

    The chat-first path: many researchers never edit inputs/ files — they
    just describe the project in chat ("my question is X, data's at /path,
    hypotheses H1/H2"). Pass what the researcher SAID via ``question`` /
    ``domain`` / ``hypotheses`` / ``context_note`` and those take precedence
    over file-inference, so a project with no context/*.md still gets a real
    intake. ``context_note`` is also folded into the corpus so the research
    overview captures the researcher's framing verbatim. With no explicit
    fields, behaviour is unchanged: infer everything from inputs/ files.
    """
    try:
        from research_os.project_ops import (
            load_state,
            now_iso,
            regenerate_intake,
            save_state,
        )

        # Capture the chat-provided hypotheses before the local `hypotheses`
        # var (file-inferred) shadows the parameter below.
        hyp_arg = [h.strip() for h in (hypotheses or []) if h and h.strip()]

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
        # Chat-provided framing joins the corpus so the research overview +
        # question/hypothesis inference see what the researcher SAID, even when
        # no context/*.md file exists.
        if context_note and context_note.strip():
            context_text = (
                (context_text + "\n\n" + context_note.strip()).strip()
                if context_text else context_note.strip()
            )

        # Classify + propose. Respect existing state when already set —
        # init's --domain / --question flags land in state before this
        # tool runs, and rewriting them here was overwriting the
        # researcher's deliberate input with weaker auto-inferences.
        state_pre = load_state(root)
        existing_domain = (state_pre.get("domain") or "").strip()
        existing_question = (state_pre.get("research_question") or "").strip()
        domain_auto, domain_why = _classify_domain(raw_files, context_text)
        # Precedence: explicit chat arg > deliberate existing state > inference.
        arg_domain = (domain or "").strip()
        domain = arg_domain or existing_domain or domain_auto
        if arg_domain:
            domain_why = [f"set by the researcher in chat = {arg_domain!r}"]
        elif existing_domain:
            domain_why = [f"preserved from state.domain = {existing_domain!r}"]
        question_auto = _propose_question(context_text, raw_files)
        arg_question = (question or "").strip()
        # Keep state's question unless it was the placeholder; a chat-provided
        # question always wins.
        question = (
            arg_question or (
                existing_question if existing_question
                and "*(AI-proposed placeholder" not in existing_question
                else question_auto
            )
        )
        hypotheses = _propose_hypotheses(context_text)
        # Chat-provided hypotheses take precedence over inference.
        if hyp_arg:
            hypotheses = hyp_arg
        # Fallback: if context yields zero hypotheses but we DO have a
        # research question (from --question flag or context inference),
        # at least register the question itself as the central testable
        # claim so downstream protocols have something to ground
        # against.
        #
        # A naive `"We test whether " + lowercased question` template
        # silently produces grammatically broken sentences when the
        # question contains "and" / "or" / commas — a trailing
        # conjunction leaves a dangling clause. So: detect compound
        # questions and either truncate at the first conjunction or
        # wrap the full question in parentheses as a quoted hypothesis
        # instead of a forced prose rewrite.
        if not hypotheses and question:
            q_stripped = question.rstrip("?").strip().rstrip(".,;: ")
            if len(q_stripped) >= 12:
                # Detect a compound question (contains ", and" / ", or"
                # / multiple "?"): use the QUOTE form so we don't try to
                # rewrite grammar we can't control.
                is_compound = (
                    ", and " in q_stripped.lower()
                    or ", or " in q_stripped.lower()
                    or q_stripped.count("?") >= 1
                    or len(q_stripped) > 160
                )
                # Detect an interrogative-led question. "We test whether " +
                # the lowercased question only reads grammatically when the
                # question is a *declarative* clause ("X reduces Y"). The most
                # common research-question forms instead open with an
                # auxiliary/modal verb ("Does X...", "Is Y...", "Can we...")
                # or a wh-word ("How does...", "What drives..."). Splicing
                # those after "We test whether" yields broken prose like
                # "We test whether does drug X reduce tumor size." — which the
                # researcher then has to trust as their central testable
                # claim. For those, fall back to the QUOTE form too.
                first_word = q_stripped.split(None, 1)[0].lower().strip(".,;:") if q_stripped.split() else ""
                _INTERROGATIVE_LEADS = {
                    # auxiliaries / modals
                    "do", "does", "did", "is", "are", "was", "were", "be",
                    "has", "have", "had", "can", "could", "will", "would",
                    "shall", "should", "may", "might", "must",
                    # wh-words
                    "how", "what", "why", "when", "where", "which", "who",
                    "whom", "whose",
                }
                is_interrogative = first_word in _INTERROGATIVE_LEADS
                if is_compound or is_interrogative:
                    hypotheses = [
                        f"Central question: \"{q_stripped}\""
                    ]
                else:
                    # Strip any trailing dangling conjunction.
                    for tail in (" and", " or", " but", " while", " yet"):
                        if q_stripped.lower().endswith(tail):
                            q_stripped = q_stripped[: -len(tail)].rstrip(",; ")
                    hypotheses = [
                        f"We test whether {q_stripped[0].lower()}{q_stripped[1:]}."
                    ]

        # Surface named-paper references (e.g. "Cite Himes 2014") as
        # explicit fetch suggestions so the AI knows to run a literature
        # search rather than silently hoping the PDF is already in
        # inputs/literature/.
        named_papers = _extract_named_papers(context_text)

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
            # Build a richer research_overview.md — background pulled
            # from inputs/context/*.md, sample-table inferred from a
            # quick CSV row-count, named-paper references surfaced as
            # a citations-to-find checklist, planned-analyses block so
            # a fresh PI / reviewer can read the file alone and know
            # what the project is about + where it's going.
            rq_body_parts = [
                f"# {state_pre.get('project_name') or 'Research Project'} — Overview",
                "",
                f"*Auto-populated by `tool_intake_autofill` at {now_iso()}.* "
                "*Edit freely; re-running intake will preserve your edits if the "
                "file is non-placeholder.*",
                "",
                "## Domain",
                "",
                f"**{domain or '_(not yet classified)_'}**",
            ]
            if domain_why:
                rq_body_parts.append("")
                rq_body_parts.append(
                    "_Why this domain:_ " + "; ".join(str(r) for r in domain_why)
                )
            rq_body_parts.extend([
                "",
                "## Research question",
                "",
                question or "_(not yet set)_",
                "",
                "## Background (auto-extracted from `inputs/context/*.md`)",
                "",
            ])
            if context_text.strip():
                # First ~600 chars of context, truncated cleanly at a paragraph.
                snippet = context_text.strip()[:600]
                if len(context_text.strip()) > 600:
                    snippet = snippet.rsplit("\n\n", 1)[0] + "\n\n_(truncated — see `inputs/context/` for the full PI brief / prior notes)_"
                rq_body_parts.append("> " + snippet.replace("\n", "\n> "))
            else:
                rq_body_parts.append(
                    "_(no context files present — drop a PI brief / prior report / lab notes into `inputs/context/` and re-run intake)_"
                )
            rq_body_parts.append("")
            rq_body_parts.append("## Hypotheses")
            rq_body_parts.append("")
            if hypotheses:
                for i, h in enumerate(hypotheses, 1):
                    rq_body_parts.append(f"- **H{i}**: {h}")
            else:
                rq_body_parts.append(
                    "_(none yet — refine the research question with the PI, then "
                    "re-run intake or call `mem_hypothesis_add` directly)_"
                )
            # Sample / data table — quick scan of raw_data
            rq_body_parts.extend(["", "## Input data (auto-inventoried)", ""])
            if raw_files:
                rq_body_parts.append("| File | Size | Rows (CSV/TSV only) |")
                rq_body_parts.append("|---|---|---|")
                for f in raw_files[:15]:
                    size_kb = f.stat().st_size / 1024
                    size_str = (f"{size_kb:.0f} KB" if size_kb < 1024
                                else f"{size_kb/1024:.1f} MB")
                    n_rows = ""
                    if f.suffix.lower() in {".csv", ".tsv"}:
                        # Stream with csv.reader so embedded newlines in
                        # quoted cells don't inflate the count, and clamp at
                        # 0 so a genuinely empty file shows 0 (not -1 from the
                        # naive `count - 1` header subtraction). newline="" is
                        # the documented csv-module requirement.
                        try:
                            sep = "," if f.suffix.lower() == ".csv" else "\t"
                            with open(
                                f, newline="", encoding="utf-8", errors="replace"
                            ) as fh:
                                n_rows = str(
                                    max(
                                        0,
                                        sum(1 for _ in csv.reader(fh, delimiter=sep))
                                        - 1,
                                    )
                                )
                        except (OSError, csv.Error):
                            n_rows = "?"
                    rq_body_parts.append(
                        f"| `{f.relative_to(root)}` | {size_str} | {n_rows} |"
                    )
                if len(raw_files) > 15:
                    rq_body_parts.append(f"| _… and {len(raw_files)-15} more_ | | |")
            else:
                rq_body_parts.append(
                    "_(no files in `inputs/raw_data/` yet — drop CSV / Parquet / "
                    "FASTQ / NIfTI / etc. and re-run intake)_"
                )

            # Planned analyses placeholder — the AI fills this in as it
            # walks through `methodology_selection` + `analysis_plan`.
            rq_body_parts.extend([
                "",
                "## Planned analyses (filled in as the project progresses)",
                "",
                "_(`workspace/analysis.md` is the canonical narrative log. "
                "This section is a high-level roadmap — link to the numbered "
                "step folders as they're created.)_",
                "",
            ])
            for i, p in enumerate((root / "workspace").iterdir() if (root / "workspace").exists() else [], 1):
                if p.is_dir() and p.name[:2].isdigit():
                    rq_body_parts.append(f"- `workspace/{p.name}/` — *(see step README)*")

            # Literature-to-find checklist
            rq_body_parts.extend(["", "## Literature to ground the work", ""])
            if named_papers:
                rq_body_parts.append(
                    "References named in `inputs/context/` — fetch + save to "
                    "`inputs/literature/`:"
                )
                rq_body_parts.append("")
                for ref in named_papers:
                    rq_body_parts.append(f"- [ ] {ref}")
            else:
                rq_body_parts.append(
                    "_(no named references found in context. The "
                    "`guidance/analysis_plan` ground_methods step will surface "
                    "candidate methods + their canonical citations once the AI "
                    "starts scoping the first analysis step.)_"
                )

            rq_body_parts.extend([
                "",
                "## Last updated",
                "",
                f"{now_iso()} — `tool_intake_autofill`.",
                "",
            ])
            rq_path.write_text("\n".join(rq_body_parts))
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
        next_actions = []
        if named_papers:
            already_have = {p.stem.lower() for p in literature_files}
            missing = [
                ref for ref in named_papers
                if not any(part.lower() in already_have for part in ref.split() if len(part) > 3)
            ]
            for ref in missing[:6]:
                next_actions.append(
                    f"Run tool_literature_search_and_save query=\"{ref}\" — "
                    "the PI brief names this reference but it's not in "
                    "inputs/literature/ yet."
                )
        if not hypotheses:
            next_actions.append(
                "No testable hypotheses inferable from inputs/context. Ask the "
                "researcher: 'What's the central claim you want this project "
                "to test? Phrasing it as H1 will sharpen everything downstream.'"
            )

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
            "named_paper_references": named_papers,
            "next_actions": next_actions,
            "state_fields_updated": [
                k for k in ("domain", "research_question", "active_hypotheses")
                if state.get(k)
            ],
            "research_question_md_updated": rq_changed,
            "intake_path": intake_path,
            "message": (
                "Intake autofilled. Review with the researcher: 'I read your "
                "inputs. I propose domain=<X>, question=<Y>, "
                f"{len(hypotheses)} hypotheses, {len(named_papers)} named "
                "paper references to fetch. Approve?'"
            ),
        }
        return summary
    except Exception as e:
        logger.exception("intake_autofill failed")
        return {"status": "error", "message": str(e)}
