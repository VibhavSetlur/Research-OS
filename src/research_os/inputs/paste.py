"""Save freeform paste blobs into ``inputs/context/`` as Markdown files.

Researchers often arrive with notes from a Slack thread, a forwarded
email from their PI, a chunk of meeting transcript, or a draft README.
This helper normalises whatever they paste into a clean Markdown file
with a meaningful filename and a short YAML front-matter block so the
AI (and downstream provenance tooling) can tell where it came from.

We detect a handful of common shapes:

* **Slack thread** — ``User\\nTimestamp\\nMessage`` repeated, sometimes
  with reactions and "view in channel" cruft. We collapse to
  ``**User** _(timestamp)_:`` for each post.
* **Email** — leading headers (``From:``, ``To:``, ``Subject:``,
  ``Date:``) → emit as a fenced ``email`` block at the top.
* **Plain notes / meeting transcript** — pass through with the original
  line breaks preserved.

If the format can't be classified we save it verbatim — the goal is
"never lose what the researcher pasted", not "guess at all costs".
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from research_os.errors import check_write_permitted

_SLACK_TIMESTAMP_RE = re.compile(
    r"^\s*(\d{1,2}:\d{2}\s?(?:AM|PM)?|\d{1,2}/\d{1,2}/\d{2,4}.*|"
    r"(?:Today|Yesterday|Mon|Tue|Wed|Thu|Fri|Sat|Sun)\b.*)\s*$",
    re.IGNORECASE,
)
_EMAIL_HEADER_RE = re.compile(r"^(From|To|Cc|Bcc|Subject|Date|Reply-To):\s*",
                              re.IGNORECASE)


@dataclass
class PasteResult:
    path: Path
    kind: str            # "slack" | "email" | "notes" | "verbatim"
    line_count: int
    bytes_written: int


# ---------------------------------------------------------------------------
# Detectors
# ---------------------------------------------------------------------------


def detect_kind(blob: str) -> str:
    if not blob.strip():
        return "verbatim"
    lines = blob.strip().splitlines()
    head = lines[: min(10, len(lines))]
    # Email — three or more leading header-shaped lines.
    header_hits = sum(1 for line in head if _EMAIL_HEADER_RE.match(line))
    if header_hits >= 2:
        return "email"
    # Slack — alternating short name + timestamp + body.
    ts_hits = sum(1 for line in lines if _SLACK_TIMESTAMP_RE.match(line))
    if ts_hits >= 2 and len(lines) >= 5:
        return "slack"
    return "notes"


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------


def _format_slack(blob: str) -> str:
    """Best-effort Slack normaliser.

    Heuristic: a Slack message paste looks like
        Vibhav Setlur
        10:42 AM
        actual body line 1
        actual body line 2
        (reactions)
        Joe Researcher
        10:51 AM
        reply body
    We collapse every ``Name\\nTimestamp\\nBody...`` triple into
    ``**Name** _(timestamp)_  Body`` with the body preserved verbatim.
    Lines that don't fit the pattern are emitted as-is.
    """
    raw_lines = [l.rstrip() for l in blob.splitlines()]  # noqa: E741
    out: list[str] = []
    i = 0
    n = len(raw_lines)
    while i < n:
        line = raw_lines[i].strip()
        if not line:
            out.append("")
            i += 1
            continue
        # A short, capitalised, single-line name followed by a timestamp.
        is_name = bool(line) and len(line) <= 60 and not line.startswith("**")
        next_line = raw_lines[i + 1].strip() if i + 1 < n else ""
        if is_name and _SLACK_TIMESTAMP_RE.match(next_line):
            user = line
            ts = next_line
            body: list[str] = []
            j = i + 2
            while j < n:
                bl = raw_lines[j].strip()
                # Next post boundary: a name + timestamp pair.
                bln = raw_lines[j + 1].strip() if j + 1 < n else ""
                if (bl and len(bl) <= 60 and not bl.startswith("**")
                        and _SLACK_TIMESTAMP_RE.match(bln)):
                    break
                body.append(raw_lines[j])
                j += 1
            out.append(f"**{user}** _{ts}_")
            for bl in body:
                out.append(bl)
            out.append("")
            i = j
            continue
        out.append(raw_lines[i])
        i += 1
    return "\n".join(out).strip() + "\n"


def _format_email(blob: str) -> str:
    """Split off the header block + render it in a fenced ``email`` chunk."""
    lines = blob.splitlines()
    head: list[str] = []
    rest: list[str] = []
    in_body = False
    for line in lines:
        if not in_body and _EMAIL_HEADER_RE.match(line):
            head.append(line)
        elif not in_body and line.strip() == "":
            in_body = True
        else:
            rest.append(line)
    fenced = "\n".join(head)
    body = "\n".join(rest).strip()
    return f"```email\n{fenced}\n```\n\n{body}\n"


def _format_notes(blob: str) -> str:
    """Pass-through, but normalise CRLF and trim trailing whitespace."""
    return "\n".join(line.rstrip() for line in blob.splitlines()).strip() + "\n"


# ---------------------------------------------------------------------------
# Public entry
# ---------------------------------------------------------------------------


def save(
    blob: str,
    dest_dir: Path,
    source_hint: str = "",
    kind: str | None = None,
) -> PasteResult:
    """Save a pasted blob into ``dest_dir`` as a self-describing markdown file.

    ``source_hint`` (e.g. ``"PI slack message"``) becomes part of the
    filename + frontmatter so it's grep-able later. If ``kind`` is None
    we auto-detect via :func:`detect_kind`.
    """
    if not blob:
        raise ValueError("blob is empty")
    detected_kind = kind or detect_kind(blob)
    if detected_kind == "slack":
        body = _format_slack(blob)
    elif detected_kind == "email":
        body = _format_email(blob)
    elif detected_kind == "notes":
        body = _format_notes(blob)
    else:
        body = blob if blob.endswith("\n") else blob + "\n"

    dest_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y%m%d_%H%M%S")
    hint_slug = re.sub(r"[^a-zA-Z0-9_-]+", "_",
                       source_hint.lower())[:30].strip("_") or "note"
    fname = f"{stamp}_{detected_kind}_{hint_slug}.md"
    target = dest_dir / fname

    # Enforce input-tree write protection if we're inside a workspace
    # (heuristic: walk up looking for ``.os_state``). When found, ask the
    # central guard to vet the destination; raise on protection violation so
    # the caller (the init wizard) can warn and skip without aborting.
    root = dest_dir.resolve()
    workspace_root: Path | None = None
    for candidate in (root, *root.parents):
        if (candidate / ".os_state").exists():
            workspace_root = candidate
            break
    if workspace_root is not None:
        try:
            rel = target.resolve().relative_to(workspace_root)
        except ValueError:
            rel = target
        check_write_permitted(str(rel))

    frontmatter = (
        "---\n"
        f"captured_at: {now.isoformat()}\n"
        f"source_kind: {detected_kind}\n"
        f"source_hint: {source_hint or '(unspecified)'}\n"
        f"captured_via: research-os init wizard\n"
        "---\n\n"
    )
    target.write_text(frontmatter + body)
    return PasteResult(
        path=target,
        kind=detected_kind,
        line_count=body.count("\n"),
        bytes_written=target.stat().st_size,
    )
