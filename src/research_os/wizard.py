"""Interactive scaffolding wizard for ``research-os init``.

Walks researchers through a 7-step setup in under a minute: project
location, name, optional research metadata, AI IDE wiring, an *optional*
"bring in your inputs" loop (paste a Slack message, drop in paper URLs,
attach screenshots, symlink existing data), an *optional* API-keys
collection step, and a post-scaffold verification pass.

Arrow-key navigation, multi-select with Space, Tab path completion, and
paper URL auto-download. Pure stdlib + ``requests`` (already a dep).
Falls back to line-based prompts when stdin/stdout isn't a TTY, so
``--yes`` and CI keep working.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

from research_os import __version__, logo, tui
from research_os.tui import _C  # noqa  (re-exported for cli.py's status lines)

# ---------------------------------------------------------------------------
# IDE registry — single source of truth, mirrored from project_ops
# ---------------------------------------------------------------------------

IDE_CHOICES: list[tuple[str, str, str]] = [
    ("claude",      "Claude Code / Claude Desktop", "Anthropic's CLI + desktop app"),
    ("cursor",      "Cursor",                       "AI-first VS Code fork"),
    ("vscode",      "VS Code (+ MCP extension)",    "Standard VS Code with MCP enabled"),
    ("antigravity", "Antigravity",                  "Google's agentic IDE"),
    ("opencode",    "OpenCode",                     "Open-source AI coding CLI"),
    ("windsurf",    "Windsurf",                     "Codeium's agentic IDE"),
    ("continue",    "Continue",                     "Open-source IDE assistant"),
    ("aider",       "Aider",                        "AI pair-programming CLI"),
]
VALID_IDES = tuple(k for k, _, _ in IDE_CHOICES)

# Single-select domain menu. The wizard appends "Other (type my own)" and
# "Skip" at the end. Keep the visible list short — researchers can always
# type a custom one.
DOMAIN_MENU: list[tuple[str, str]] = [
    ("clinical",        "Clinical / health"),
    ("genomics",        "Genomics / bioinformatics"),
    ("neuroscience",    "Neuroscience"),
    ("physics",         "Physics"),
    ("chemistry",       "Chemistry"),
    ("materials",       "Materials science"),
    ("climate",         "Climate / environmental"),
    ("nlp",             "NLP / language"),
    ("computer_vision", "Computer vision"),
    ("finance",         "Finance / economics"),
    ("social_science",  "Social science"),
    ("ml",              "ML / AI methodology"),
    ("robotics",        "Robotics"),
]


# ---------------------------------------------------------------------------
# Status-line helpers (cli.py imports several of these)
# ---------------------------------------------------------------------------


def disable_color() -> None:
    tui.disable_color()


def _hr(ch: str = "─") -> str:
    try:
        w = max(50, shutil.get_terminal_size((80, 24)).columns - 2)
    except OSError:
        w = 68
    return ch * min(68, w)


def ok(msg: str, detail: str = "") -> None:
    suf = f"  {_C.GREY}{detail}{_C.RESET}" if detail else ""
    print(f"  [{_C.GREEN}✓{_C.RESET}] {msg}{suf}")


def warn(msg: str, detail: str = "") -> None:
    suf = f"  {_C.GREY}{detail}{_C.RESET}" if detail else ""
    print(f"  [{_C.YELLOW}!{_C.RESET}] {msg}{suf}")


def fail(msg: str, detail: str = "") -> None:
    suf = f"  {_C.GREY}{detail}{_C.RESET}" if detail else ""
    print(f"  [{_C.RED}✗{_C.RESET}] {msg}{suf}")


def info(msg: str) -> None:
    print(f"  {_C.BLUE}›{_C.RESET} {msg}")


def section(num: int, total: int, title: str, blurb: str = "") -> None:
    print()
    head = f"  {_C.MAGENTA}{_C.BOLD}Step {num}/{total}{_C.RESET}  {_C.BOLD}{title}{_C.RESET}"
    print(head)
    print(f"  {_C.GREY}{_hr()}{_C.RESET}")
    if blurb:
        print(f"  {_C.DIM}{blurb}{_C.RESET}")
    print()


def slugify(value: str, fallback: str = "research-project") -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]", "-", value.replace(" ", "-")).lower().strip("-")
    return slug or fallback


# ---------------------------------------------------------------------------
# Resolved-choices data class
# ---------------------------------------------------------------------------


@dataclass
class WizardResult:
    target_dir: Path
    project_name: str
    domain: str
    question: str                      # primary question (back-compat)
    questions: list[str]               # full list — written to researcher_config
    ides: list[str]
    force: bool
    run_verify: bool
    start_server: bool
    create_dir_needed: bool
    detected_inputs: list[Path] = field(default_factory=list)
    pending_notes: list[tuple[str, str]] = field(default_factory=list)
    pending_papers: list[str] = field(default_factory=list)
    # New in this revision — files the user wants copied/symlinked.
    pending_attachments: list[Path] = field(default_factory=list)
    # API keys captured in Step 6 — written to inputs/researcher_config.yaml.
    api_keys: dict[str, str] = field(default_factory=dict)
    # Model tier — written into researcher_config.yaml as model_profile.
    model_profile: str = "medium"
    # Workspace mode — written into researcher_config.yaml as workspace.mode.
    #   analysis (default) | hybrid | tool_build | exploration | notebook | multi_study
    workspace_mode: str = "analysis"
    # MCP registration scope: workspace (per-project files, default) or
    # global (also print the user-scope install command).
    mcp_scope: str = "workspace"
    # Researcher identity, written into researcher_config.yaml AND
    # (when researcher opts in) ~/.config/research-os/profile.yaml so
    # the next `research-os init` pre-fills these without asking.
    researcher_name: str = ""
    researcher_email: str = ""
    researcher_institution: str = ""
    researcher_orcid: str = ""
    save_as_profile: bool = False


# ---------------------------------------------------------------------------
# Predicate: should we run the wizard?
# ---------------------------------------------------------------------------


# Lightweight format checks for identity fields — re-prompt on obvious typos
# rather than silently writing a malformed email / ORCID into the config.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_ORCID_RE = re.compile(r"^\d{4}-\d{4}-\d{4}-\d{3}[\dXx]$")


def _prompt_validated(label: str, pattern: re.Pattern, example: str) -> str:
    """Prompt for an optional value; re-ask on an obviously-malformed entry.

    Blank always accepts (the field is optional). A non-blank value that fails
    ``pattern`` triggers a one-line warning + re-prompt.
    """
    while True:
        val = tui.text(label, default="", allow_empty=True).strip()
        if not val or pattern.match(val):
            return val
        warn(
            f"That doesn't look like a valid {label.split(' (')[0].lower()}",
            f"expected e.g. {example} — re-enter or leave blank to skip",
        )


def should_run_wizard(args) -> bool:
    if getattr(args, "yes", False):
        return False
    if getattr(args, "no_interactive", False):
        return False
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return False
    return True


# ---------------------------------------------------------------------------
# The wizard
# ---------------------------------------------------------------------------


def run_wizard(args) -> WizardResult:
    """Drive the interactive prompts. Honors any flag already passed on
    the command line by skipping the matching question."""
    print(logo.render(width=68, version=__version__))

    total = 7

    # ── Step 1: Location ────────────────────────────────────────────────
    section(1, total, "Project location",
            "Where should your research workspace live?")
    cwd = Path.cwd().resolve()
    if args.directory:
        target_dir = Path(os.path.expanduser(args.directory)).resolve()
        create_dir_needed = not target_dir.exists()
        ok(f"Location: {target_dir}",
           "(will create)" if create_dir_needed else "(already exists)")
    else:
        choice = tui.select_one(
            "Pick one:",
            [
                ("here",   f"Use current directory  {_C.GREY}({cwd}){_C.RESET}"),
                ("new",    "Create a new folder here"),
                ("custom", "Use a specific path"),
            ],
            default_index=0,
        )
        if choice == "here":
            target_dir = cwd
            create_dir_needed = False
        elif choice == "new":
            sub = tui.text("Folder name",
                           placeholder="e.g. cohort-2024-eda",
                           allow_empty=False)
            target_dir = (cwd / slugify(sub)).resolve()
            create_dir_needed = not target_dir.exists()
        else:
            raw = tui.text("Absolute or relative path",
                           placeholder="Tab to autocomplete",
                           completer=tui.path_completer,
                           allow_empty=False)
            target_dir = Path(os.path.expanduser(raw)).resolve()
            create_dir_needed = not target_dir.exists()
        ok(f"Target: {target_dir}",
           "(will create)" if create_dir_needed else "(already exists)")

    # Bail out NOW if the workspace already exists — BEFORE asking the rest of
    # the wizard, so the researcher never fills everything out only to hit
    # "already exists" at the end.
    if (target_dir / ".os_state").exists() and not getattr(args, "force", False):
        print()
        fail(f"Workspace already exists: {target_dir}",
             "Pass --force to re-scaffold (your data + config are preserved), "
             "or choose a different location.")
        raise SystemExit(1)

    # ── Step 2: Project name ────────────────────────────────────────────
    section(2, total, "Project name",
            "A human-readable title. Used in docs/intake.md and dashboards.")
    if args.name:
        project_name = args.name
        ok(f"Name: {project_name}")
    else:
        default_name = target_dir.name.replace("-", " ").replace("_", " ").title()
        project_name = tui.text("Project name", default=default_name)
        ok(f"Name: {project_name}")

    # ── What are you building? (workspace mode) ─────────────────────────
    # Set early — it shapes the whole scaffold. Honors --workspace-mode if
    # already passed on the command line; mixed/unsure → analysis.
    workspace_mode = _ask_workspace_mode(getattr(args, "workspace_mode", None))
    ok({
        "analysis":    "Mode: analysis (linear analysis steps)",
        "hybrid":      "Mode: hybrid (research + software component)",
        "tool_build":  "Mode: tool_build (governed software build)",
        "exploration": "Mode: exploration (scratch-first probes)",
        "notebook":    "Mode: notebook (Jupyter-first)",
        "multi_study": "Mode: multi_study (program / portfolio)",
    }.get(workspace_mode, f"Mode: {workspace_mode}"))

    # ── Step 3: Research details (optional, menu-driven) ────────────────
    section(3, total, "Research details (optional)",
            "Helps the AI orient. Skip anything you're not sure about — "
            "the AI infers what's missing from your data and notes.")
    domain = args.domain or _ask_domain()
    questions = list(args.questions or [])
    if args.question and args.question not in questions:
        questions.insert(0, args.question)
    if not questions:
        questions = _ask_questions()
    primary_question = questions[0] if questions else ""

    if domain:
        ok(f"Domain: {domain}")
    if questions:
        ok(f"Research question(s): {len(questions)}")
        for q in questions:
            print(f"      {_C.DIM}· {q[:90]}{'…' if len(q) > 90 else ''}{_C.RESET}")
    if not domain and not questions:
        ok("Skipped — AI will infer from inputs/.")

    # ── Step 4: AI IDE wiring ───────────────────────────────────────────
    section(4, total, "AI IDE wiring",
            "Pick only the IDE(s) you actually use. Add more later with "
            "`research-os ide add <name>`.")
    if args.ide and args.ide != "all":
        ides = [p.strip() for p in args.ide.split(",") if p.strip() in VALID_IDES]
        if not ides:
            ides = ["claude"]
        ok(f"IDEs (from --ide): {', '.join(ides)}")
    else:
        preselected = ["claude"]  # The sensible single default.
        ides = tui.select_many(
            "Wire up these IDEs:",
            IDE_CHOICES,
            preselected=preselected,
            help_line="Space to toggle · 'a' for all · 'n' for none · Enter to confirm",
        )
        if not ides:
            warn("No IDE selected — wiring Claude Code by default.")
            ides = ["claude"]

    # Model-profile selector — tunes how the AI batches steps, loads
    # protocols, and how aggressive optional audits are. Single most
    # important knob if not on a frontier model.
    print()
    model_profile_choices = [
        ("medium", "medium  — Sonnet 4.5/4.6, GPT-4o/4.1, Gemini 2.5 Pro (default)"),
        ("large",  "large   — Opus 4.x, GPT-5/o-series, Gemini 3 Pro"),
        ("small",  "small   — Haiku 4.5, GPT-4o-mini, Gemini 2.5 Flash, Llama 3.3, local"),
    ]
    model_profile = tui.select_one(
        "Which AI model class are you using in your IDE?",
        model_profile_choices,
        default_index=0,
        help_line="Sets `model_profile` in researcher_config.yaml. Change anytime later.",
    )

    # ── Step 5: Bring in your inputs ────────────────────────────────────
    section(5, total, "Bring in your inputs (optional)",
            "Add any data, papers, notes, or images you already have.")
    pending_notes, pending_papers, detected_inputs, pending_attachments = \
        _collect_inputs(target_dir)

    # ── Step 6: API keys (optional) ─────────────────────────────────────
    section(6, total, "API keys (optional)",
            "Used only for literature search + web scraping. NO LLM keys — "
            "your AI IDE owns model access. Skip to fill in later via "
            "inputs/researcher_config.yaml (chmod 600).")
    api_keys = _collect_api_keys()

    # ── Step 6b: Researcher identity (defaults from cross-project profile)─
    from research_os.tools.actions.state.config import load_profile
    profile = load_profile()
    profile_researcher = profile.get("researcher") if isinstance(profile.get("researcher"), dict) else {}
    if profile_researcher and any(profile_researcher.values()):
        ok("Using your saved profile for name / email / institution / ORCID")
        researcher_name = profile_researcher.get("name", "") or ""
        researcher_email = profile_researcher.get("email", "") or ""
        researcher_institution = profile_researcher.get("institution", "") or ""
        researcher_orcid = profile_researcher.get("orcid", "") or ""
        save_as_profile = False
    else:
        print()
        skip_id = tui.confirm(
            f"Set your researcher identity? "
            f"{_C.GREY}(name / email / institution / ORCID — used in citations + sharing){_C.RESET}",
            default=False,
        )
        if skip_id:
            researcher_name = tui.text("Name", default="", allow_empty=True)
            researcher_email = _prompt_validated(
                "Email", _EMAIL_RE, "you@university.edu",
            )
            researcher_institution = tui.text("Institution", default="", allow_empty=True)
            researcher_orcid = _prompt_validated(
                "ORCID (optional)", _ORCID_RE, "0000-0002-1825-0097",
            )
            save_as_profile = tui.confirm(
                "Save these as defaults for future `research-os init` runs? "
                f"{_C.GREY}(stored at ~/.config/research-os/profile.yaml chmod 600){_C.RESET}",
                default=True,
            )
        else:
            researcher_name = researcher_email = researcher_institution = researcher_orcid = ""
            save_as_profile = False

    # ── Step 7: Post-init actions ───────────────────────────────────────
    section(7, total, "After scaffolding",
            "Final touches. Defaults are safe — Enter to accept.")
    run_verify = tui.confirm("Run a smoke check on the new workspace?", default=True)
    start_server = tui.confirm(
        f"Start the MCP server now? {_C.GREY}(usually no — IDE auto-launches){_C.RESET}",
        default=False,
    )

    return WizardResult(
        target_dir=target_dir,
        project_name=project_name,
        domain=domain,
        question=primary_question,
        questions=questions,
        ides=ides,
        force=args.force,
        run_verify=run_verify,
        start_server=start_server,
        create_dir_needed=create_dir_needed,
        detected_inputs=detected_inputs,
        pending_notes=pending_notes,
        pending_papers=pending_papers,
        pending_attachments=pending_attachments,
        api_keys=api_keys,
        model_profile=model_profile,
        workspace_mode=workspace_mode,
        mcp_scope=(getattr(args, "mcp_scope", None) or "workspace"),
        researcher_name=researcher_name,
        researcher_email=researcher_email,
        researcher_institution=researcher_institution,
        researcher_orcid=researcher_orcid,
        save_as_profile=save_as_profile,
    )


# ---------------------------------------------------------------------------
# Step 3 helpers
# ---------------------------------------------------------------------------


VALID_WORKSPACE_MODES = (
    "analysis", "tool_build", "exploration", "notebook", "multi_study",
    "hybrid",
)


def _ask_workspace_mode(preset: str | None = None) -> str:
    """Ask 'What are you building?' → workspace mode.

    Honors a value already passed on the command line (``--workspace-mode``).
    Mixed / unsure maps implicitly to ``analysis``. Returns one of
    ``analysis | tool_build | exploration | notebook | multi_study``.
    """
    if isinstance(preset, str) and preset.strip() in VALID_WORKSPACE_MODES:
        return preset.strip()
    pick = tui.select_one(
        "What are you building?",
        [
            ("analysis",    "Analysis pipeline (data → results → paper)"),
            ("hybrid",      "Research + software (analysis steps + a code component)"),
            ("tool_build",  "A tool / software I iterate on"),
            ("exploration", "Quick exploration (scratch-first probes)"),
            ("notebook",    "A Jupyter notebook project"),
            ("multi_study", "A multi-study program (portfolio + meta-analysis)"),
        ],
        default_index=0,
        help_line="Shapes the scaffold + how the AI works. Change later in "
                  "researcher_config.yaml (workspace.mode).",
    )
    return pick if pick in VALID_WORKSPACE_MODES else "analysis"


def _ask_domain() -> str:
    """Single-select menu over common domains + Other + Skip."""
    opts = [(k, label) for k, label in DOMAIN_MENU]
    opts.append(("__other__", "Other (type my own)"))
    opts.append(("__skip__",  f"Skip — let AI infer from data {_C.GREY}(default){_C.RESET}"))
    pick = tui.select_one(
        "Primary domain:",
        opts,
        default_index=len(opts) - 1,
    )
    if pick == "__skip__":
        return ""
    if pick == "__other__":
        return tui.text("Custom domain", placeholder="one word, e.g. astrophysics",
                        allow_empty=True)
    return pick


def _ask_questions() -> list[str]:
    """Loop: add a question OR finish. Returns the collected list."""
    qs: list[str] = []
    while True:
        if qs:
            label = f"Add another? {_C.GREY}({len(qs)} so far){_C.RESET}"
            opts = [
                ("add",  "Add another research question"),
                ("done", f"{_C.BOLD}Done with questions{_C.RESET}"),
            ]
            default_index = 1
        else:
            label = "Research question(s):"
            opts = [
                ("add",  "Type a research question now"),
                ("done", f"Skip — fill in {_C.BOLD}inputs/researcher_config.yaml{_C.RESET} later"),
            ]
            default_index = 0
        pick = tui.select_one(label, opts, default_index=default_index)
        if pick == "done":
            return qs
        q = tui.text("Question",
                     placeholder="e.g. 'Does X predict Y in cohort Z?'",
                     allow_empty=True)
        if q.strip():
            qs.append(q.strip())


# ---------------------------------------------------------------------------
# Step 5 helpers
# ---------------------------------------------------------------------------

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif",
                    ".tiff", ".svg", ".heic"}


def _collect_inputs(target_dir: Path) -> tuple[
        list[tuple[str, str]], list[str], list[Path], list[Path]]:
    """Loop over the input-helper submenu until the user picks 'done'.

    Returns ``(notes, papers, detected_data, attachments)`` — all applied
    AFTER the scaffold exists.
    """
    notes: list[tuple[str, str]] = []
    papers: list[str] = []
    attachments: list[Path] = []

    detected: list[Path] = []
    if target_dir.exists():
        for pat in ("*.csv", "*.tsv", "*.json", "*.jsonl", "*.xlsx", "*.xls",
                    "*.parquet", "*.feather", "*.pdf"):
            detected.extend(p for p in list(target_dir.glob(pat))[:10]
                            if not p.is_symlink())
    link_data = False

    while True:
        summary_bits = []
        if notes:
            summary_bits.append(f"{len(notes)} note(s)")
        if papers:
            summary_bits.append(f"{len(papers)} paper ref(s)")
        if attachments:
            summary_bits.append(f"{len(attachments)} file(s)")
        if detected and link_data:
            summary_bits.append(f"{len(detected)} data file(s)")
        summary = ("  " + _C.GREY + "(" + ", ".join(summary_bits) + " queued)" + _C.RESET
                   if summary_bits else "")

        opts = [
            ("note",   "Paste a note / Slack thread / email  →  inputs/context/"),
            ("paper",  "Add paper(s) by URL · DOI · arXiv ID  →  inputs/literature/"),
            ("file",   "Attach an image / screenshot / file   →  inputs/context/"),
        ]
        if detected:
            label = f"Symlink {len(detected)} existing data file(s)  →  inputs/raw_data/"
            if link_data:
                label = f"{_C.GREEN}✓{_C.RESET} {label}  (queued)"
            opts.append(("data", label))
        opts.append(("done", f"{_C.BOLD}I'm done with inputs{_C.RESET}{summary}"))

        choice = tui.select_one(
            "What would you like to add?",
            opts,
            default_index=len(opts) - 1,
            help_line="Add as many as you like — pick 'done' to move on.",
        )

        if choice == "done":
            break

        if choice == "note":
            _capture_note(notes)
        elif choice == "paper":
            _capture_paper_refs(papers)
        elif choice == "file":
            _capture_attachment(attachments)
        elif choice == "data":
            link_data = not link_data
            if link_data:
                ok(f"Will link {len(detected)} data file(s)", "into inputs/raw_data/")
            else:
                warn("Cancelled — data files left where they are.")

    return notes, papers, (detected if link_data else []), attachments


def _capture_note(notes: list[tuple[str, str]]) -> None:
    kind = tui.select_one(
        "What kind of note?",
        [
            ("auto",     f"Auto-detect {_C.GREY}(recommended){_C.RESET}"),
            ("slack",    "Slack message / thread"),
            ("email",    "Email (with headers)"),
            ("notes",    "Plain notes / meeting transcript"),
        ],
        default_index=0,
    )
    source_hint = tui.text(
        "One-line source label",
        placeholder="e.g. 'PI on Cohort 2024 cleanup'",
        allow_empty=True,
    ) or (kind if kind != "auto" else "note")
    blob = tui.multiline("Paste your text below:", sentinel="END")
    if blob.strip():
        notes.append((source_hint, blob))
        meta = f"{_C.GREEN}✓{_C.RESET} Queued — saves to inputs/context/ after scaffold."
        if kind != "auto":
            meta += f"  {_C.GREY}(kind: {kind}){_C.RESET}"
        print(f"  {meta}")
    else:
        warn("Empty paste — skipped.")


def _capture_paper_refs(papers: list[str]) -> None:
    print(f"  {_C.DIM}Accepted formats — one per line, space-, or comma-separated:{_C.RESET}")
    print(f"    {_C.GREY}• arXiv ID            2401.12345 / arxiv:2310.06825{_C.RESET}")
    print(f"    {_C.GREY}• arXiv URL           https://arxiv.org/abs/2401.12345{_C.RESET}")
    print(f"    {_C.GREY}• DOI                 10.1038/nature12373{_C.RESET}")
    print(f"    {_C.GREY}• DOI URL             https://doi.org/10.1038/nature12373{_C.RESET}")
    print(f"    {_C.GREY}• Direct PDF URL      https://example.com/paper.pdf{_C.RESET}")
    print()
    blob = tui.multiline("Paste paper IDs / URLs:", sentinel="END")
    from research_os.inputs.papers import parse_tokens
    tokens = parse_tokens(blob)
    if not tokens:
        warn("No recognisable tokens — skipped.")
    else:
        papers.extend(tokens)
        ok(f"Queued {len(tokens)} paper reference(s)",
           "downloads kick off after scaffold completes")


def _capture_attachment(attachments: list[Path]) -> None:
    """Accept one or many filesystem paths to copy into inputs/context/
    (or inputs/literature/ for PDFs). Paths support ``~`` and Tab
    autocomplete; users can paste multiple paths separated by newlines."""
    print(f"  {_C.DIM}One path per line. Tab to autocomplete. PDFs route to "
          f"inputs/literature/, everything else to inputs/context/.{_C.RESET}")
    raw = tui.multiline("Path(s) to file(s):", sentinel="END")
    if not raw.strip():
        # Allow single-line input via the standard text prompt too.
        single = tui.text("Or one path", placeholder="Tab to autocomplete",
                          completer=tui.path_completer, allow_empty=True)
        raw = single or ""
    candidates = [p.strip() for p in raw.splitlines() if p.strip()]
    if not candidates:
        warn("No paths given — skipped.")
        return
    accepted: list[Path] = []
    rejected: list[tuple[str, str]] = []
    for c in candidates:
        p = Path(os.path.expanduser(c)).expanduser().resolve()
        if not p.exists():
            rejected.append((c, "does not exist"))
        elif not p.is_file():
            rejected.append((c, "not a file"))
        else:
            accepted.append(p)
    for c, why in rejected:
        warn(f"Skipped: {c}", why)
    if accepted:
        attachments.extend(accepted)
        ok(f"Queued {len(accepted)} file(s)",
           "copies happen after scaffold completes")


# ---------------------------------------------------------------------------
# Step 6 helpers — API keys
# ---------------------------------------------------------------------------

# (slug, human label, one-line description / signup URL)
API_KEY_SPECS: list[tuple[str, str, str]] = [
    ("semantic_scholar", "Semantic Scholar",
     "https://www.semanticscholar.org/product/api"),
    ("pubmed", "PubMed (NCBI E-utilities)",
     "https://www.ncbi.nlm.nih.gov/account/"),
    ("crossref", "Crossref (polite pool email/token)",
     "https://www.crossref.org  (rarely needed — public endpoint works)"),
    ("firecrawl", "Firecrawl (web search + scrape)",
     "https://firecrawl.io"),
    ("serpapi", "SerpAPI (fallback web search)",
     "https://serpapi.com"),
]


def _collect_api_keys() -> dict[str, str]:
    """Optionally collect API keys. Returns dict of only non-empty keys.

    Never echoes the values back to the user — only the count.
    """
    pick = tui.select_one(
        "Add API keys now?",
        [
            ("yes",  "Yes — I have some keys handy"),
            ("skip", f"Skip — leave blank or fill later in "
                     f"{_C.BOLD}inputs/researcher_config.yaml{_C.RESET} "
                     f"{_C.GREY}(default){_C.RESET}"),
        ],
        default_index=1,
    )
    if pick != "yes":
        ok("Skipped — fill in inputs/researcher_config.yaml later (chmod 600).")
        return {}

    keys: dict[str, str] = {}
    for slug, label, descr in API_KEY_SPECS:
        # tui.secret masks the pasted key so it never echoes to the
        # terminal; the captured value is still merged into
        # inputs/researcher_config.yaml (which init_config chmod's to 600).
        prompt = f"{label} — {descr} (input hidden; Enter to skip)"
        value = tui.secret(prompt, allow_empty=True)
        if value and value.strip():
            keys[slug] = value.strip()

    if keys:
        # SECURITY: report count only, never echo values.
        ok(f"Captured {len(keys)} API key(s)",
           "stored in inputs/researcher_config.yaml (chmod 600)")
    else:
        ok("No keys entered — leaving all blank.")
    return keys


# ---------------------------------------------------------------------------
# Confirmation + done card
# ---------------------------------------------------------------------------


def show_summary_and_confirm(r: WizardResult) -> bool:
    print()
    print(f"  {_C.GREY}{_hr('━')}{_C.RESET}")
    print(f"  {_C.BOLD}Ready to scaffold{_C.RESET}")
    print(f"  {_C.GREY}{_hr('━')}{_C.RESET}")
    pad = 13
    rows = [
        ("Project",  r.project_name),
        ("Location", str(r.target_dir) + (f"  {_C.YELLOW}(new){_C.RESET}"
                                          if r.create_dir_needed else "")),
        ("Domain",   r.domain or _C.GREY + "(blank — AI will infer)" + _C.RESET),
        ("Questions", (f"{len(r.questions)} queued" if r.questions
                       else _C.GREY + "(blank — fill later in researcher_config.yaml)" + _C.RESET)),
        ("IDEs",     ", ".join(r.ides)),
    ]
    if r.pending_notes:
        rows.append(("Notes",       f"{len(r.pending_notes)} pasted blob(s) → inputs/context/"))
    if r.pending_papers:
        rows.append(("Papers",      f"{len(r.pending_papers)} URL(s) → inputs/literature/"))
    if r.pending_attachments:
        rows.append(("Attachments", f"{len(r.pending_attachments)} file(s) → inputs/context|literature/"))
    if r.detected_inputs:
        rows.append(("Link data",   f"{len(r.detected_inputs)} file(s) → inputs/raw_data/"))
    if r.api_keys:
        rows.append(("API keys",
                     f"{len(r.api_keys)} key(s) set — stored in researcher_config.yaml (chmod 600)"))
    rows.extend([
        ("Verify",   "yes" if r.run_verify else "no"),
        ("Server",   "start now" if r.start_server else "later (your IDE will launch it)"),
    ])
    for label, value in rows:
        print(f"  {_C.DIM}{label.ljust(pad)}{_C.RESET}{value}")
    print(f"  {_C.GREY}{_hr('━')}{_C.RESET}")
    print()
    return tui.confirm("Proceed?", default=True)


def show_done_card(r: WizardResult, scaffold_stats: dict, verify_summary: str | None,
                   note_results=None, paper_results=None,
                   attachment_results=None, author=None) -> None:
    print()
    print(f"  {_C.GREEN}{_hr('═')}{_C.RESET}")
    print(f"  {_C.GREEN}{_C.BOLD}  Workspace ready{_C.RESET}")
    print(f"  {_C.GREEN}{_hr('═')}{_C.RESET}")
    print()
    ok("Workspace scaffolded",
       f"{scaffold_stats.get('files', '?')} files · {scaffold_stats.get('dirs', '?')} directories")
    if r.ides:
        ok(f"Wired {len(r.ides)} AI IDE config(s)", ", ".join(r.ides))
    if r.detected_inputs:
        ok(f"Linked {len(r.detected_inputs)} existing data file(s)",
           "→ inputs/raw_data/")
    if attachment_results:
        ok(f"Copied {len(attachment_results)} attachment(s)",
           f"→ inputs/context|literature/ "
           f"({', '.join(p.name for p in attachment_results[:3])}"
           f"{'…' if len(attachment_results) > 3 else ''})")
    if note_results:
        ok(f"Saved {len(note_results)} note(s)", "→ inputs/context/")
    if paper_results:
        succ = sum(1 for p in paper_results if p.ok)
        if succ == len(paper_results):
            ok(f"Downloaded {succ} paper(s)", "→ inputs/literature/")
        else:
            warn(f"Downloaded {succ}/{len(paper_results)} paper(s)",
                 f"{len(paper_results) - succ} failed — see report below")
            for p in paper_results:
                if not p.ok:
                    suffix = f"  {_C.GREY}manual: {p.manual_url}{_C.RESET}" if p.manual_url else ""
                    print(f"        {_C.YELLOW}✗{_C.RESET} {p.token}  "
                          f"{_C.GREY}— {p.error}{_C.RESET}{suffix}")
    if verify_summary:
        ok("Smoke check passed", verify_summary)
    print()
    _next_steps(r)


def _next_steps(r: WizardResult) -> None:
    print(f"  {_C.BOLD}Next steps{_C.RESET}")
    print(f"  {_C.GREY}{_hr()}{_C.RESET}")
    n = 1
    cwd = Path.cwd().resolve()
    if r.target_dir != cwd:
        print(f"  {_C.CYAN}{n}.{_C.RESET}  cd {_C.BOLD}{r.target_dir}{_C.RESET}")
        n += 1
    print(f"  {_C.CYAN}{n}.{_C.RESET}  Drop more files into:")
    print(f"        {_C.DIM}inputs/raw_data/{_C.RESET}     data (CSV / Parquet / FASTQ / NIfTI / ...)")
    print(f"        {_C.DIM}inputs/literature/{_C.RESET}   PDFs of papers")
    print(f"        {_C.DIM}inputs/context/{_C.RESET}      notes, drafts, screenshots, prior reports")
    n += 1
    print(f"  {_C.CYAN}{n}.{_C.RESET}  Open your AI IDE on this folder — the MCP server auto-launches.")
    print(f"        {_C.BOLD}⚠ Already have it open? RESTART the IDE / reload the window{_C.RESET}")
    print(f"        {_C.DIM}so the research-os MCP tools load — they won't appear until you do.{_C.RESET}")
    if getattr(r, "mcp_scope", "workspace") == "global":
        try:
            from research_os.project_ops import mcp_global_install_hint
            for line in mcp_global_install_hint(r.ides).splitlines():
                print(f"        {_C.DIM}{line}{_C.RESET}")
        except Exception:
            pass
    n += 1
    print(f"  {_C.CYAN}{n}.{_C.RESET}  Start chatting. Try:")
    for line in [
        '"fill out the intake"           — AI reads inputs/, drafts question + hypotheses',
        '"what should I do next?"         — iterative planning',
        '"run a baseline EDA"             — creates workspace/01_*, scripts + figures',
        '"write the paper for a journal"  — verified citations only',
        '"what domain packs are available?" — wet_lab / humanities / qualitative / theory_math / engineering',
    ]:
        print(f"        {_C.DIM}{line}{_C.RESET}")
    print()
    print(f"  {_C.GREY}Read first:{_C.RESET}  {r.target_dir / 'GETTING_STARTED.md'}")
    print(f"  {_C.GREY}AI rules :{_C.RESET}   {r.target_dir / 'AGENTS.md'}")
    print(f"  {_C.GREY}Config   :{_C.RESET}   {r.target_dir / 'inputs' / 'researcher_config.yaml'}")
    print(f"  {_C.GREY}Add an IDE:{_C.RESET} research-os ide add <claude|cursor|vscode|…>")
    print()
