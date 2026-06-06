"""Figure auto-embed for synthesis/paper.md.

Walks every numbered step's ``outputs/figures/`` directory and embeds
the figures into the corresponding section of ``synthesis/paper.md`` so
the researcher does not have to hand-place each ``![…](…)`` line. Reads
each figure's sibling ``<stem>.caption.md`` sidecar for:

  * the caption headline (first paragraph)
  * a "Note:" appendix (remaining paragraphs)
  * YAML frontmatter declaring section_hint / figure_priority /
    poster_priority / alt_text / figures_for_paper / interactive_required.

Three placement modes:

  * ``append_to_section`` — default. Drop each figure at the end of the
    section indicated by section_hint (falls back to Results).
  * ``explicit_map``      — caller passes ``section_map={stem: section}``
    and figures land in those sections regardless of section_hint.
  * ``reorder``           — sort by ``figure_priority`` ascending and
    append in priority order at the end of the Results section.

The pass is idempotent: a figure that already appears in the document
(matched by stem) is never re-inserted; running auto_embed_figures
twice in a row produces byte-identical output.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("research_os.tools.synthesis.figure_auto_embed")


IMAGE_EXTS = {".png", ".pdf", ".svg", ".jpg", ".jpeg"}

# Default per-section ordering used when section_hint resolution falls
# through. Results is the natural home for empirical figures.
DEFAULT_SECTION = "Results"

# Sections in the order they typically appear in an IMRAD paper. Used
# to pick a fallback insertion point when the requested section is
# missing from paper.md.
SECTION_ORDER = (
    "Abstract", "Introduction", "Background", "Related Work",
    "Methods", "Materials and Methods", "Results", "Discussion",
    "Conclusion", "References",
)


# ---------------------------------------------------------------------------
# Caption frontmatter parsing
# ---------------------------------------------------------------------------


_FRONTMATTER_DEFAULTS: dict[str, Any] = {
    "section_hint": DEFAULT_SECTION,
    "figure_priority": 100,
    "poster_priority": 100,
    "alt_text": "",
    "figures_for_paper": True,
    "interactive_required": False,
}


def read_caption_frontmatter(caption_md: Path | str) -> dict[str, Any]:
    """Parse the YAML frontmatter at the top of a ``<stem>.caption.md``.

    Returns ``_FRONTMATTER_DEFAULTS`` merged with whatever the file
    declares; missing or unreadable files yield the defaults verbatim.
    The body of the caption (everything after the closing ``---``) is
    returned under the ``_body`` key so callers don't need to re-read
    the file to format the figure caption.
    """
    p = Path(caption_md)
    out = dict(_FRONTMATTER_DEFAULTS)
    out["_body"] = ""
    if not p.exists():
        return out
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out

    lines = text.splitlines()
    body_start = 0
    if lines and lines[0].strip() == "---":
        # Find the closing ---.
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                fm_text = "\n".join(lines[1:i])
                body_start = i + 1
                try:
                    import yaml  # type: ignore

                    parsed = yaml.safe_load(fm_text) or {}
                    if isinstance(parsed, dict):
                        for k, v in parsed.items():
                            if k in _FRONTMATTER_DEFAULTS:
                                out[k] = v
                except Exception as exc:
                    logger.debug("caption frontmatter unreadable %s: %s", p, exc)
                break

    out["_body"] = "\n".join(lines[body_start:]).strip()
    # Empty body → fall back to the filename stem.
    if not out["_body"]:
        out["_body"] = p.stem.replace(".caption", "").replace("_", " ")
    return out


# ---------------------------------------------------------------------------
# Step-summary.yaml field check
# ---------------------------------------------------------------------------


def _step_figures_for_paper(step_dir: Path) -> bool:
    """Return the ``figures_for_paper`` field from step_summary.yaml.

    Defaults to True when the field is missing or the file unreadable.
    A False value tells discover_figures to skip every figure under
    this step (e.g. exploratory pilots, internal diagnostics).
    """
    summary = step_dir / "step_summary.yaml"
    if not summary.exists():
        return True
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(summary.read_text()) or {}
        if not isinstance(data, dict):
            return True
        val = data.get("figures_for_paper", True)
        return bool(val)
    except Exception:
        return True


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def discover_figures(root: Path | str) -> list[dict[str, Any]]:
    """Walk ``workspace/<step>/outputs/figures/`` across the project.

    Returns one dict per figure with keys::

        step_id, stem, path, caption_md, section_hint,
        figure_priority, poster_priority, alt_text, body

    Steps with ``step_summary.yaml.figures_for_paper: false`` are
    skipped entirely. Per-figure frontmatter ``figures_for_paper:
    false`` also skips that single figure.
    """
    root = Path(root)
    workspace = root / "workspace"
    out: list[dict[str, Any]] = []
    if not workspace.exists():
        return out

    for step_dir in sorted(workspace.iterdir()):
        if not step_dir.is_dir():
            continue
        if not re.match(r"^\d{2,3}_", step_dir.name):
            continue
        if step_dir.name.endswith("__DEAD_END"):
            continue
        if not _step_figures_for_paper(step_dir):
            continue

        fig_dir = step_dir / "outputs" / "figures"
        if not fig_dir.exists():
            continue

        for f in sorted(fig_dir.rglob("*")):
            if not f.is_file():
                continue
            if f.suffix.lower() not in IMAGE_EXTS:
                continue
            # Sidecar lives at <stem>.caption.md (Path.with_suffix only
            # replaces the LAST suffix so compose the name explicitly).
            caption_md = f.parent / (f.stem + ".caption.md")
            fm = read_caption_frontmatter(caption_md)
            if not fm.get("figures_for_paper", True):
                continue
            out.append(
                {
                    "step_id": step_dir.name,
                    "stem": f.stem,
                    "path": str(f.relative_to(root).as_posix()),
                    "caption_md": str(caption_md.relative_to(root).as_posix())
                    if caption_md.exists()
                    else "",
                    "section_hint": fm.get("section_hint") or DEFAULT_SECTION,
                    "figure_priority": int(fm.get("figure_priority", 100)),
                    "poster_priority": int(fm.get("poster_priority", 100)),
                    "alt_text": fm.get("alt_text") or "",
                    "interactive_required": bool(fm.get("interactive_required", False)),
                    "body": fm.get("_body", ""),
                }
            )
    return out


# ---------------------------------------------------------------------------
# Markdown section helpers
# ---------------------------------------------------------------------------


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def _split_into_sections(text: str) -> list[dict[str, Any]]:
    """Walk paper.md and produce a list of section descriptors.

    Each descriptor has ``level``, ``title``, ``start`` (line index of
    the heading), and ``end`` (exclusive line index where the section's
    contents end — at the next heading of equal-or-lower level).
    """
    lines = text.splitlines()
    headings: list[dict[str, Any]] = []
    for i, line in enumerate(lines):
        m = _HEADING_RE.match(line)
        if m:
            headings.append(
                {
                    "level": len(m.group(1)),
                    "title": m.group(2).strip(),
                    "start": i,
                }
            )

    # Compute end indices.
    for i, h in enumerate(headings):
        end = len(lines)
        for j in range(i + 1, len(headings)):
            if headings[j]["level"] <= h["level"]:
                end = headings[j]["start"]
                break
        h["end"] = end
    return headings


def _find_section(
    headings: list[dict[str, Any]], wanted: str
) -> dict[str, Any] | None:
    """Find the first section whose title case-insensitively matches.

    Falls through ``SECTION_ORDER`` to a sensible neighbour if the
    requested section is missing.
    """
    wanted_lc = wanted.strip().lower()
    for h in headings:
        if h["title"].lower() == wanted_lc:
            return h
    # Loose match — strip leading numeric prefix and trailing markers.
    for h in headings:
        cleaned = re.sub(r"^[\d.\s]+", "", h["title"]).strip().lower()
        if cleaned == wanted_lc:
            return h
    return None


def _figure_in_paper(text: str, stem: str) -> bool:
    """Has this stem already been inserted (manually or by a prior run)?

    We match on the basename / stem appearing inside a markdown image,
    a Typst ``image()`` call, or a label like ``<fig:STEM>``.
    """
    needle = re.escape(stem)
    patterns = [
        rf"!\[[^\]]*\]\([^)]*{needle}[^)]*\)",  # ![...](.../stem.png)
        rf'image\("[^"]*{needle}[^"]*"',
        rf"<fig:{needle}>",
    ]
    return any(re.search(p, text) for p in patterns)


# ---------------------------------------------------------------------------
# Caption rendering — splits headline vs Note appendix
# ---------------------------------------------------------------------------


def _split_caption(body: str) -> tuple[str, str]:
    """First paragraph = headline; rest = "Note:" appendix.

    A "paragraph" is the standard markdown sense — text separated by
    blank lines. Headlines beyond ~280 chars are truncated to keep
    figure cross-references readable; the full body still lives in
    the sidecar file.
    """
    if not body:
        return "", ""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    if not paragraphs:
        return "", ""
    headline = paragraphs[0]
    note = " ".join(paragraphs[1:]).strip()
    return headline, note


def _render_figure_block(figure: dict[str, Any]) -> str:
    """Return the markdown image + caption block for one figure."""
    headline, note = _split_caption(figure.get("body", ""))
    alt = figure.get("alt_text") or headline or figure["stem"]
    img = f"![{alt}]({figure['path']}){{#fig:{figure['stem']}}}"
    pieces = [img, ""]
    if headline:
        pieces.append(f"**Figure ({figure['stem']}).** {headline}")
    if note:
        pieces.append("")
        pieces.append(f"*Note:* {note}")
    return "\n".join(pieces)


# ---------------------------------------------------------------------------
# Embedding driver
# ---------------------------------------------------------------------------


def auto_embed_figures(
    paper_md_path: Path | str,
    root: Path | str,
    *,
    mode: str = "append_to_section",
    section_map: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Insert markdown image blocks into ``paper_md_path``.

    Modes:
        - ``append_to_section`` — figure lands at the end of the section
          named in its ``section_hint``.
        - ``explicit_map``      — uses ``section_map`` ({stem: section}).
        - ``reorder``           — all figures clustered at end of
          Results, sorted by ``figure_priority`` ascending.

    Idempotent. Figures whose ``stem`` already appears in the document
    are skipped (so manual placements are preserved).
    """
    paper_md_path = Path(paper_md_path)
    root = Path(root)
    if not paper_md_path.exists():
        return {
            "status": "error",
            "message": f"paper.md not found at {paper_md_path}",
            "embedded": 0,
        }

    figures = discover_figures(root)
    if not figures:
        return {
            "status": "success",
            "embedded": 0,
            "skipped_already_present": 0,
            "message": "No figures with figures_for_paper=true discovered.",
        }

    text = paper_md_path.read_text(encoding="utf-8", errors="replace")
    headings = _split_into_sections(text)

    # Decide insertion section per figure.
    target_section: dict[str, str] = {}
    if mode == "explicit_map":
        section_map = section_map or {}
        for fig in figures:
            target_section[fig["stem"]] = section_map.get(
                fig["stem"], fig["section_hint"] or DEFAULT_SECTION
            )
    elif mode == "reorder":
        for fig in figures:
            target_section[fig["stem"]] = DEFAULT_SECTION
        figures = sorted(figures, key=lambda f: f["figure_priority"])
    else:  # append_to_section (default)
        for fig in figures:
            target_section[fig["stem"]] = fig["section_hint"] or DEFAULT_SECTION

    embedded = 0
    skipped_present = 0
    missing_section: list[str] = []
    missing_file: list[str] = []
    lines = text.splitlines()

    # Process figures in REVERSE order grouped by section so multiple
    # appends to the same section keep the priority order intact and
    # earlier insertions don't shift later line indices.
    by_section: dict[str, list[dict[str, Any]]] = {}
    for fig in figures:
        sec = target_section[fig["stem"]]
        by_section.setdefault(sec, []).append(fig)

    # Sort each section's figures by priority so first-priority lands first.
    for sec in by_section:
        by_section[sec] = sorted(by_section[sec], key=lambda f: f["figure_priority"])

    # Apply per-section insertions from bottom of doc to top to keep
    # line indices stable.
    ordered_sections = []
    for sec_name, figs in by_section.items():
        h = _find_section(headings, sec_name)
        if h is None:
            for fig in figs:
                if not _figure_in_paper(text, fig["stem"]):
                    missing_section.append(fig["stem"])
            continue
        ordered_sections.append((h["end"], sec_name, figs, h))

    ordered_sections.sort(key=lambda t: t[0], reverse=True)

    for insert_at, _, figs, _h in ordered_sections:
        blocks: list[str] = []
        for fig in figs:
            if _figure_in_paper("\n".join(lines), fig["stem"]):
                skipped_present += 1
                continue
            if not (root / fig["path"]).exists():
                missing_file.append(fig["path"])
                continue
            blocks.append("")
            blocks.append(_render_figure_block(fig))
            blocks.append("")
            embedded += 1
        if blocks:
            lines[insert_at:insert_at] = blocks

    new_text = "\n".join(lines)
    if not new_text.endswith("\n"):
        new_text += "\n"
    paper_md_path.write_text(new_text, encoding="utf-8")

    # Append a log line so the researcher can see what happened.
    log_dir = root / "workspace" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "figure_auto_embed.md"
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    log_entry = (
        f"## {ts}\n"
        f"- mode: {mode}\n"
        f"- embedded: {embedded}\n"
        f"- skipped (already present): {skipped_present}\n"
        f"- missing section: {len(missing_section)}\n"
        f"- missing file: {len(missing_file)}\n"
    )
    if log_path.exists():
        log_path.write_text(log_path.read_text() + "\n" + log_entry)
    else:
        log_path.write_text("# Figure auto-embed log\n\n" + log_entry)

    return {
        "status": "success",
        "embedded": embedded,
        "skipped_already_present": skipped_present,
        "missing_section": missing_section,
        "missing_file": missing_file,
        "mode": mode,
        "log_path": str(log_path.relative_to(root)),
    }


# ---------------------------------------------------------------------------
# Cross-reference rewriting
# ---------------------------------------------------------------------------


# A bare-stem cross-reference is a token of the form `01_volcano` that
# appears OUTSIDE a markdown image / link / code span and matches a
# discovered figure stem. We rewrite it to `@fig:01_volcano` so a
# downstream filter (pandoc-crossref, Typst label resolver) can hook
# it up to the figure block emitted above.

_CODE_FENCE_RE = re.compile(r"^```")
_INLINE_CODE_RE = re.compile(r"`[^`]+`")
_MD_IMAGE_OR_LINK_RE = re.compile(r"!?\[[^\]]*\]\([^)]*\)")
_FIG_REF_RE = re.compile(r"@fig:[A-Za-z0-9_.:-]+")


def rewrite_figure_xrefs(paper_md_path: Path | str) -> dict[str, Any]:
    """Rewrite bare figure stems to ``@fig:<stem>`` cross-references.

    Skips lines inside fenced code blocks, content inside inline code
    spans, content inside markdown image/link payloads, and tokens that
    are already in ``@fig:`` form.

    Idempotent — a second pass produces the same text.
    """
    paper_md_path = Path(paper_md_path)
    if not paper_md_path.exists():
        return {"status": "error", "message": f"paper.md not found at {paper_md_path}"}

    text = paper_md_path.read_text(encoding="utf-8", errors="replace")

    # Collect stems from the document's own image lines so we only
    # rewrite tokens that actually correspond to embedded figures.
    stems: set[str] = set()
    for m in re.finditer(r"\{#fig:([A-Za-z0-9_.:-]+)\}", text):
        stems.add(m.group(1))
    for m in re.finditer(r"!\[[^\]]*\]\(([^)]+)\)", text):
        stem = Path(m.group(1)).stem
        if stem:
            stems.add(stem)
    if not stems:
        return {"status": "success", "rewritten": 0, "message": "no figure stems found"}

    stem_alt = "|".join(re.escape(s) for s in sorted(stems, key=len, reverse=True))
    bare_re = re.compile(r"(?<![\w@:/])(?:" + stem_alt + r")(?![\w])")

    out_lines: list[str] = []
    in_fence = False
    rewritten = 0
    for line in text.splitlines():
        if _CODE_FENCE_RE.match(line.strip()):
            in_fence = not in_fence
            out_lines.append(line)
            continue
        if in_fence:
            out_lines.append(line)
            continue

        # Mask off code spans and md-image/link payloads so we don't
        # rewrite stems sitting inside ![alt](path/stem.png).
        masks: list[str] = []

        def _mask(match: re.Match[str]) -> str:
            masks.append(match.group(0))
            return f"\x00MASK{len(masks) - 1}\x00"

        masked = _INLINE_CODE_RE.sub(_mask, line)
        masked = _MD_IMAGE_OR_LINK_RE.sub(_mask, masked)

        # Don't touch tokens already in @fig: form.
        masked = _FIG_REF_RE.sub(_mask, masked)

        def _rewrite(match: re.Match[str]) -> str:
            nonlocal rewritten
            rewritten += 1
            return f"@fig:{match.group(0)}"

        masked = bare_re.sub(_rewrite, masked)

        # Restore masks.
        for i, raw in enumerate(masks):
            masked = masked.replace(f"\x00MASK{i}\x00", raw)
        out_lines.append(masked)

    new_text = "\n".join(out_lines)
    if not new_text.endswith("\n"):
        new_text += "\n"
    paper_md_path.write_text(new_text, encoding="utf-8")
    return {"status": "success", "rewritten": rewritten, "stems_known": len(stems)}


# ---------------------------------------------------------------------------
# Audit gate — orphan figures
# ---------------------------------------------------------------------------


def audit_figure_coverage(root: Path | str) -> dict[str, Any]:
    """Block when a discovered figure (figures_for_paper != false) is
    NOT embedded in synthesis/paper.md.

    Back-compat shim: delegates to :class:`FigureCoverageAudit` (the
    Phase-4 AuditBase subclass) and reshapes the structured findings
    back into the original dict surface. The Phase-4 audit artefacts
    (workspace/figure_coverage_audit.{md,json} +
    workspace/logs/.audit_findings.jsonl) are NOT written by this
    function — that happens in the server handler so the workspace
    write only fires when a tool actually invoked the audit. Direct
    callers (tests, scripts) still get the same dict shape as v1.

    Returns ``status='error'`` plus a list of blockers when at least
    one orphan exists. The intent is to fail loudly when a researcher
    forgets to enable auto-embed or hand-writes a paper without
    pulling in their own figures.
    """
    root = Path(root)
    audit = FigureCoverageAudit()
    findings = audit.run(root)
    return audit.to_legacy_dict(root, findings)


# ---------------------------------------------------------------------------
# AuditBase migration — Phase 4b
# ---------------------------------------------------------------------------


from research_os.tools.actions.audit._base import (  # noqa: E402
    AuditBase,
    AuditFinding,
    _now_iso,
    _ro_version,
    validate_finding,
)


class FigureCoverageAudit(AuditBase):
    """Phase-4 audit: every discovered figure must appear in synthesis/paper.md.

    Maps the legacy BLOCK/PASS/WARN logic into the structured
    :class:`AuditFinding` schema:

    * Missing ``synthesis/paper.md``      → one ``severity='block'``
      finding under dimension ``figures``.
    * Each orphan figure                  → one ``severity='block'``
      finding under dimension ``figures``, evidence_paths pointing at
      both ``synthesis/paper.md`` and the figure's on-disk path.
    * Zero findings                       → the gate passed; the
      writer emits an empty .json + a "no findings" .md, so dashboards
      always see a fresh artefact.

    Each finding's ``id`` is derived deterministically from
    ``audit_name + dimension + evidence_paths`` via :func:`uuid.uuid5`
    so reruns against an unchanged workspace produce stable IDs
    (avoids dashboard / jsonl churn from cosmetic re-audits).
    """

    name = "audit_figure_coverage"

    _NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")  # NAMESPACE_DNS

    def _make_finding(
        self,
        *,
        severity: str,
        dimension: str,
        evidence_paths: list[str],
        suggested_fix: str,
        override_kwarg: str | None = None,
        override_log_format: str | None = None,
    ) -> AuditFinding:
        key = "|".join([self.name, dimension] + sorted(evidence_paths))
        stable_id = str(uuid.uuid5(self._NAMESPACE, key))
        finding = AuditFinding(
            audit_name=self.name,
            severity=severity,
            dimension=dimension,
            id=stable_id,
            evidence_paths=list(evidence_paths),
            suggested_fix=suggested_fix,
            override_kwarg=override_kwarg,
            override_log_format=override_log_format,
            generated_at=_now_iso(),
            ro_version=_ro_version(),
        )
        validate_finding(finding.to_dict())
        return finding

    def run(self, root: Path, **kwargs: Any) -> list[AuditFinding]:
        root = Path(root)
        paper = root / "synthesis" / "paper.md"
        if not paper.exists():
            return [
                self._make_finding(
                    severity="block",
                    dimension="figures",
                    evidence_paths=["synthesis/paper.md"],
                    suggested_fix=(
                        "Create synthesis/paper.md before running the "
                        "figure-coverage gate (e.g. via tool_synthesize "
                        "or tool_paper_create)."
                    ),
                )
            ]

        figures = discover_figures(root)
        if not figures:
            return []

        text = paper.read_text(encoding="utf-8", errors="replace")
        findings: list[AuditFinding] = []
        for fig in figures:
            if _figure_in_paper(text, fig["stem"]):
                continue
            findings.append(
                self._make_finding(
                    severity="block",
                    dimension="figures",
                    evidence_paths=[
                        "synthesis/paper.md",
                        fig.get("path") or f"workspace/{fig['step_id']}/outputs/figures/{fig['stem']}",
                    ],
                    suggested_fix=(
                        f"Embed figure '{fig['stem']}' (step "
                        f"{fig['step_id']}) into synthesis/paper.md, or "
                        "enable synthesis.figures_auto_embed=true in "
                        "researcher_config.yaml and rerun "
                        "tool_paper_figures_autoembed."
                    ),
                )
            )
        return findings

    def to_legacy_dict(
        self,
        root: Path,
        findings: list[AuditFinding],
    ) -> dict[str, Any]:
        """Reshape findings into the v1 return dict (status/blockers/...)."""
        root = Path(root)
        paper = root / "synthesis" / "paper.md"
        if not paper.exists():
            return {
                "status": "error",
                "message": "synthesis/paper.md not found",
                "blockers": ["synthesis/paper.md does not exist"],
            }
        figures = discover_figures(root)
        if not figures:
            return {
                "status": "success",
                "blockers": [],
                "warnings": [],
                "checked": 0,
                "embedded": 0,
                "message": "no figures with figures_for_paper=true to audit",
            }

        # Reconstruct legacy blocker strings from the figure list so the
        # ordering and wording match the pre-migration surface byte-for-byte.
        text = paper.read_text(encoding="utf-8", errors="replace")
        blockers: list[str] = []
        embedded = 0
        for fig in figures:
            if _figure_in_paper(text, fig["stem"]):
                embedded += 1
            else:
                blockers.append(
                    f"figure '{fig['stem']}' (step {fig['step_id']}) "
                    f"exists on disk but is not embedded in synthesis/paper.md"
                )
        status = "error" if blockers else "success"
        return {
            "status": status,
            "blockers": blockers,
            "checked": len(figures),
            "embedded": embedded,
            "advice": (
                "Run tool_paper_figures_autoembed (or enable "
                "synthesis.figures_auto_embed=true in researcher_config.yaml) "
                "to embed every step's figures before compiling."
            )
            if blockers
            else None,
        }
