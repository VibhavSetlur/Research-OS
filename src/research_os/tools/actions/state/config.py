"""Researcher config — read/write/validate ``inputs/researcher_config.yaml``.

This file is the source of truth for who the AI is working with + how it
should behave in the workspace. Domain / research question / hypotheses
do NOT live here — they're inferred from inputs/ by ``tool_intake_autofill``
and written to ``inputs/intake.md`` + ``docs/research_overview.md``.

The config is created on init via ``init_config`` and edited by the
researcher (or by the AI on the researcher's behalf via ``sys_config_set``).
"""

from __future__ import annotations

import copy
import logging
import os
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger("research_os.tools.config")


# Prefer ruamel.yaml for round-trip writes so the rich inline help
# comments in CONFIG_TEMPLATE survive every override. Falls back to
# PyYAML when ruamel.yaml isn't installed — the structure is preserved
# either way, only the comments are lost on the fallback path.
try:
    from ruamel.yaml import YAML as _RuamelYAML  # type: ignore
    _ruamel = _RuamelYAML()
    _ruamel.preserve_quotes = True
    _ruamel.indent(mapping=2, sequence=4, offset=2)
    _ruamel.width = 4096  # don't reflow long strings
    _RUAMEL_AVAILABLE = True
except ImportError:
    _ruamel = None
    _RUAMEL_AVAILABLE = False


def _load_config_roundtrip(path: Path):
    """Load YAML preserving comments + format if ruamel.yaml is present."""
    txt = path.read_text()
    if _RUAMEL_AVAILABLE:
        return _ruamel.load(txt)
    return yaml.safe_load(txt) or {}


def _dump_config_roundtrip(path: Path, data) -> None:
    """Dump YAML preserving comments + format if ruamel.yaml is present;
    fall back to PyYAML otherwise (loses comments — log once)."""
    if _RUAMEL_AVAILABLE:
        import io
        buf = io.StringIO()
        _ruamel.dump(data, buf)
        path.write_text(buf.getvalue())
    else:
        path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))
        logger.info(
            "ruamel.yaml not installed — researcher_config.yaml comments will "
            "be stripped on this override write. `pip install ruamel.yaml` to "
            "preserve them."
        )


# ---------------------------------------------------------------------------
# CONFIG_TEMPLATE — single source of truth for the per-project schema.
#
# The canonical schema is documented in ``templates/researcher_config.yaml``
# (source-tree copy). This in-code constant MUST stay byte-for-byte
# synchronised with that file except for the leading ``project_name: ""``
# line, which is replaced with the ``project_name: "{project_name}"``
# placeholder so init_config can stamp the directory name on first write.
# The ``test_config_template_matches_file`` test
# (tests/unit/test_config_template_matches_file.py) asserts the sync.
#
# When updating the schema, edit ``templates/researcher_config.yaml`` first
# and then mirror the change here. The wizard reads from this template via
# init_config, so both consumers see the same shape.
# ---------------------------------------------------------------------------

CONFIG_TEMPLATE = """# Research OS — Researcher Configuration
#
# Tells the AI who it's working with and how you want it to behave.
# Research OS does NOT manage LLM providers — your AI client (Claude Code /
# OpenCode / Antigravity / Cursor / Claude / VS Code) handles model access.
#
# EVERY field is OPTIONAL, but the more you fill in here, the better the
# AI orients. Domain / research question / hypotheses are NOT in this file
# — drop data + notes into inputs/ and say "fill out the intake" to the
# AI; it writes those to inputs/intake.md and docs/research_overview.md.

# ── Who you are ─────────────────────────────────────────────────────────
researcher:
  name: ""
  institution: ""
  orcid: ""
  email: ""

# ── Open-science licensing (RO-Crate + CodeMeta + CITATION.cff) ────────
# Used when sys_export_ro_crate / sys_export_share_archive emit
# ro-crate-metadata.json + codemeta.json. data = applies to outputs +
# the dataset description; code = applies to scripts. SPDX identifiers.
licenses:
  data: "CC-BY-4.0"
  code: "MIT"

# ── This project ────────────────────────────────────────────────────────
project_name: "{project_name}"

# ── Workspace mode — what kind of work is this? ─────────────────────────
# Changes the scaffold, which protocols route, and which audits apply.
#   analysis    → linear numbered analysis steps (default; classic Research OS)
#   tool_build  → building software / a tool you iterate on. Research OS
#                 governs from above (spec + decisions + milestones + eval
#                 harness); the tool itself lives in an inner git repo.
#   exploration → scratch-first quick probes, light gates, promote-to-step.
#   notebook    → Jupyter-first; a notebook / cell is the unit of work.
#   multi_study → a portfolio of sub-studies with a shared codebook + roll-up.
workspace:
  mode: "analysis"        # analysis | tool_build | exploration | notebook | multi_study
  inner_repo: ""          # tool_build only: inner project dir (blank → "project")
  # tool_build only: the shell commands that define "done" for the inner
  # repo. tool_build(operation=build|test|lint) runs these (cwd = inner
  # repo) and tool_audit(scope='tool', dimension='build'|'tests') gates on
  # them. Blank = the command isn't configured; that gate reports a clear
  # "configure workspace.commands.<op>" message instead of running.
  commands:
    build: ""             # e.g. "make" | "cargo build" | "npm run build"
    test: ""              # e.g. "pytest -q" | "cargo test" | "npm test"
    lint: ""              # e.g. "ruff check ." | "cargo clippy" | "eslint ."

# ── What you want to produce (blank = AI suggests; start exploratory) ───
research_goal:
  output_types: []               # paper | abstract | poster | dashboard | report | exploratory
  target_venue: ""               # journal | conference | preprint | dissertation | report
  poster_dimensions: "36x48"

# ── How the AI should behave ────────────────────────────────────────────
interaction:
  autonomy_level: "supervised"   # manual | supervised | autopilot | coaching
  # coaching → AI doesn't auto-execute; surfaces pedagogical preludes,
  #            explains WHY each gate exists, asks the researcher to draft
  #            then critiques. Great for graduate students / new PIs
  #            learning how to use a methodology rigorously. Pair with
  #            tool_lessons(operation='mistake_replay') each session for
  #            self-coaching across recurring patterns the researcher keeps
  #            tripping.

  # Quality-gate posture (the AI NEVER bypasses on its own).
  #   enforce        → refuse bypass without an explicit researcher ask
  #   allow_override → allow override_completeness_gate=true on request,
  #                    rationale logged to workspace/logs/override_log.md
  #   warn_only      → treat gate blockers as warnings (sandbox use only)
  quality_gate_policy: "enforce"

  # Ambiguity posture
  #   ask_when_uncertain → default; AI asks a one-line follow-up
  #   take_best_default  → AI proceeds, surfaces the chosen default for review
  ambiguity_posture: "ask_when_uncertain"

# ── Audit strictness ───────────────────────────────────────────────────
# How hard audits enforce gates. "light" downgrades most blockers to
# notes; "strict" keeps every gate at full enforcement; "normal" is the
# baseline. "auto" follows tool_rigor_signals_scan — a project with
# substantive methods.md + citations + git + preregistration scores
# high and gets "light"; a sketch scores low and gets "strict".
gate_strictness: "auto"               # light | normal | strict | auto

# ── Project tier ───────────────────────────────────────────────────────
# Sets the default audit strictness across the whole project.
#   throwaway → light  (sandbox / exploratory; no publication intent)
#   sketch    → normal (working draft; may or may not publish)
#   production → strict (active path to submission / hand-off)
project_tier: "production"            # throwaway | sketch | production

# ── Match the AI model class running in your IDE ────────────────────────
#
# The single most important knob if you're NOT on a frontier model.
# Tells Research OS how to batch steps, load protocols, and what to skip.
#
#   small  → 1 step/turn, summary-only protocol loads, skip optional
#            sub-sections, prefer shortcut_tool over decomposition.
#            Pick for: Claude Haiku 4.5, GPT-4o-mini, Gemini 2.5 Flash,
#            Llama 3.3-70B, Mistral, Phi-4, any local model.
#   medium → 3 steps/turn, summary loads with on-demand drill-down.
#            Pick for: Claude Sonnet 4.5/4.6, GPT-4o / GPT-4.1, Gemini
#            2.5 Pro, Llama 4 Maverick.
#   large  → 6 steps/turn, full protocol loads when useful, deeper
#            multi-step reasoning chains.
#            Pick for: Claude Opus 4.x, GPT-5 / o-series, Gemini 3 Pro.
model_profile: "medium"

# ── Writing preferences ─────────────────────────────────────────────────
writing_preferences:
  # Citation style. Pick the convention your field expects:
  #   STEM / biomedical / quantitative social science
  #     apa                 → APA 7 (author-date); psychology, education, much
  #                           of the social sciences.
  #     vancouver           → Vancouver (numeric); biomedical journals.
  #     acm                 → ACM (numeric); computer science conferences.
  #     ieee                → IEEE (numeric); engineering, signal processing.
  #     nature              → Nature superscript-numeric.
  #   Humanities / theory
  #     mla                 → MLA 9 (author-page); literature, modern
  #                           languages, cultural studies.
  #     chicago_author_date → Chicago 17 author-date; history, social
  #                           sciences that prefer Chicago over APA.
  #     chicago_notes_bib   → Chicago 17 notes + bibliography; literary
  #                           studies, theology, art history (footnotes).
  #     amsplain            → AMS plain (numeric, alpha-keyed bib);
  #                           pure mathematics + theoretical CS.
  #     siam                → SIAM (numeric); applied math, scientific
  #                           computing.
  citation_style: "apa"
  language: "en-US"
  # Typst venue template the AI imports when authoring synthesis/paper.typ.
  # One of:
  #   nature | science | nejm | cell | ieee_conf | neurips | acl
  #   plos  | generic_two_column | generic_thesis
  #   humanities_essay      → single-column, footnote-friendly, MLA/Chicago.
  #   chicago_thesis        → Chicago notes+bibliography thesis layout.
  venue_template: "generic_two_column"
  # PDF engine. "typst" is the recommended default (fast, single-binary,
  # modern type-safe macros). Use "latex" when a journal requires .tex
  # submission — author synthesis/paper.tex by hand and call
  # tool_latex_compile.
  pdf_compile_engine: "typst"    # typst | latex | both

# ── AI client knobs (paired with model_profile above) ──────────────────
# Optional. When present, the ai.* block overrides the legacy top-level
# `model_profile`. Lets you tune how much context the AI gets at boot +
# how big a default protocol load it requests, independent of which
# model class is running.
#
#   ai.context_class:
#     short → sys_boot returns the lean ~450-token state summary
#             (default; right for most chat / IDE sessions).
#     long  → sys_boot returns ~10000 tokens of project history and
#             sys_protocol_get defaults to format='full'.
#             Pick for long-context models that benefit from the full
#             arc in working memory (Opus/Gemini/o-series with big
#             windows).
#   ai.model_profile:
#     small → sys_protocol_get defaults to format='lean' (cap 3 steps,
#             short descriptions); shortcut tools preferred over full
#             decomposition. Mirrors the top-level model_profile=small
#             defaults — included here so ai.* is a single point of truth.
#     medium / large → use the format defaults above (summary / context-driven).
ai:
  context_class: "short"          # short | long
  model_profile: "medium"         # small | medium | large

# ── Compute environment ─────────────────────────────────────────────────
runtime:
  shared_server: false           # set true on HPC / shared boxes
  long_running_threshold_seconds: 60

# ── Figure defaults ────────────────────────────────────────────────────
# What companions the AI ships with every figure. SVG companions double
# disk and audit noise. The opinionated default is: one .png + one
# .prov.json + one .caption.md, with the plain-English interpretation
# integrated into conclusions.md next to the embed. Opt in below per
# project when the editorial pipeline actually consumes the extras.
figures:
  svg_allowed: false             # ship .svg next to .png? off by default
  interactive_html_allowed: true # interactive .html companions allowed for networks / multi-panels

# ── Synthesis ──────────────────────────────────────────────────────────
# No knobs. The AI authors synthesis files directly (paper.typ,
# slides.typ, poster.typ, essay.typ, dashboard.html). The tools that
# support that workflow are configuration-free:
# tool_synthesize_plan inspects what's ready, tool_synthesis_scaffold
# seeds a tiny starter, tool_synthesis_check validates the AI's draft,
# tool_typst_compile renders the PDF.

# ── API keys (optional; public endpoints work without keys) ─────────────
# NO LLM PROVIDER KEYS HERE — Research OS does not call any model.
api_keys:
  semantic_scholar: ""
  pubmed: ""
  crossref: ""
  firecrawl: ""
  serpapi: ""
"""


def _config_path(root: Path) -> Path:
    root = Path(root)
    return root / "inputs" / "researcher_config.yaml"


# ---------------------------------------------------------------------------
# Cross-project profile
# ---------------------------------------------------------------------------
#
# Researchers run `research-os init` repeatedly — once per project. Re-typing
# name / email / ORCID / institution / API keys + writing_preferences for
# every fresh project is friction worth removing. The cross-project profile
# at ``$XDG_CONFIG_HOME/research-os/profile.yaml`` (default
# ``~/.config/research-os/profile.yaml``) holds the researcher's defaults;
# the wizard reads it as initial values, and writes it back when the
# researcher opts in ("save my profile for future projects").
#
# Per-project ``inputs/researcher_config.yaml`` ALWAYS wins on conflict —
# the profile is a starting point, not an override.


def profile_path() -> Path:
    """Return the cross-project profile path (XDG-compliant; default ~/.config)."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else (Path.home() / ".config")
    return base / "research-os" / "profile.yaml"


def load_profile() -> dict[str, Any]:
    """Load the cross-project profile, or {} if absent / unreadable."""
    p = profile_path()
    if not p.exists():
        return {}
    try:
        data = yaml.safe_load(p.read_text()) or {}
        return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.warning("Cross-project profile at %s unreadable: %s", p, e)
        return {}


def save_profile(profile: dict[str, Any]) -> dict[str, Any]:
    """Persist the cross-project profile (chmod 600 — keys may be present)."""
    p = profile_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "# Research OS — cross-project researcher profile.\n"
        "# Read by `research-os init` as default values for every new\n"
        "# project. Per-project inputs/researcher_config.yaml ALWAYS wins\n"
        "# on conflict — this file is a starting point.\n"
        "#\n"
        "# Edit by hand, or run `research-os init` and answer 'yes' when\n"
        "# the wizard asks whether to save your answers as defaults.\n\n"
        + yaml.dump(profile, default_flow_style=False, sort_keys=False)
    )
    if os.name != "nt":
        try:
            os.chmod(p, 0o600)
        except Exception:
            pass
    return {"status": "success", "profile_path": str(p)}


VALID_GATE_POLICIES = ("enforce", "allow_override", "warn_only")
VALID_AMBIGUITY_POSTURES = ("ask_when_uncertain", "take_best_default")

# ``coaching`` is a pedagogical surface (extra preludes, no auto-execute) but
# carries no scheduling difference vs ``supervised``; the actual code branches
# that gate on autonomy treat it as supervised. Keeping the alias here so the
# display value (``"coaching"``) survives in get_config / sys_help output while
# scheduling code only sees the three executable modes.
_AUTONOMY_ALIASES = {"coaching": "supervised"}


def normalize_autonomy_level(value: Any, *, default: str = "supervised") -> str:
    """Return one of ``manual | supervised | autopilot`` for the executable
    scheduler. ``coaching`` aliases to ``supervised``. Unknown / blank values
    fall back to ``default``.
    """
    if not isinstance(value, str):
        return default
    v = value.strip()
    if v in {"manual", "supervised", "autopilot"}:
        return v
    return _AUTONOMY_ALIASES.get(v, default)


def get_interaction_policy(root: Path) -> dict[str, str]:
    """Return ``{quality_gate_policy, ambiguity_posture}`` from the config.

    Falls back to the documented defaults when the file or the
    ``interaction:`` block is absent or contains an unknown value.
    Callers use this to decide whether to enforce, soft-override, or
    warn-only on quality-gate blockers; and whether to ask the
    researcher or pick a best-default on ambiguity.
    """
    root = Path(root)
    defaults = {
        "quality_gate_policy": "enforce",
        "ambiguity_posture": "ask_when_uncertain",
    }
    try:
        cfg_path = _config_path(root)
        if not cfg_path.exists():
            return defaults
        cfg = yaml.safe_load(cfg_path.read_text()) or {}
        interaction = cfg.get("interaction") or {}
        out = dict(defaults)
        pol = interaction.get("quality_gate_policy")
        if pol in VALID_GATE_POLICIES:
            out["quality_gate_policy"] = pol
        amb = interaction.get("ambiguity_posture")
        if amb in VALID_AMBIGUITY_POSTURES:
            out["ambiguity_posture"] = amb
        return out
    except Exception:
        return defaults


VALID_WORKSPACE_MODES = (
    "analysis", "tool_build", "exploration", "notebook", "multi_study",
)


def get_workspace_mode(root: Path) -> str:
    """Return the workspace mode from the config (``analysis`` default).

    The mode picks the scaffold profile + (later slices) which protocols
    route and which audits apply. Falls back to ``analysis`` whenever the
    config is missing, the ``workspace:`` block is absent, or the value
    is unknown — so an old / malformed config behaves exactly like the
    classic linear-analysis workspace. Never raises.
    """
    root = Path(root)
    try:
        cfg_path = _config_path(root)
        if not cfg_path.exists():
            return "analysis"
        cfg = yaml.safe_load(cfg_path.read_text()) or {}
        workspace = cfg.get("workspace") or {}
        mode = workspace.get("mode") if isinstance(workspace, dict) else None
        if mode in VALID_WORKSPACE_MODES:
            return mode
        return "analysis"
    except Exception:
        return "analysis"


def get_inner_repo_dir(root: Path) -> str:
    """Return the tool_build inner project dir name (blank → ``project``).

    Only meaningful for ``workspace.mode == 'tool_build'``. The inner
    directory is where the actual tool lives + gets its own ``git init``;
    Research OS governs it from above. Always returns a usable, traversal-
    safe single path segment.
    """
    root = Path(root)
    try:
        cfg_path = _config_path(root)
        if not cfg_path.exists():
            return "project"
        cfg = yaml.safe_load(cfg_path.read_text()) or {}
        workspace = cfg.get("workspace") or {}
        raw = workspace.get("inner_repo") if isinstance(workspace, dict) else None
    except Exception:
        raw = None
    name = (raw or "").strip().strip("/").replace("..", "").strip()
    # Collapse to a single safe segment — never a nested / traversing path.
    name = name.split("/")[0] if name else ""
    return name or "project"


def _mask_api_keys(config: dict[str, Any]) -> dict[str, Any]:
    safe = copy.deepcopy(config)
    keys = safe.get("api_keys")
    if isinstance(keys, dict):
        for k, v in keys.items():
            if not isinstance(v, str) or not v:
                continue
            if len(v) > 8:
                safe["api_keys"][k] = f"{v[:4]}…{v[-4:]}"
            else:
                safe["api_keys"][k] = "***"
    return safe


def get_config(root: Path) -> dict[str, Any]:
    try:
        cfg_path = _config_path(root)
        if not cfg_path.exists():
            return {"status": "error", "message": "researcher_config.yaml not found — run `research-os init`."}

        warning = None
        if os.name != "nt":
            try:
                mode = os.stat(cfg_path).st_mode
                if mode & 0o004:
                    warning = (
                        "WARNING: inputs/researcher_config.yaml is world-readable. "
                        "Run `chmod 600 inputs/researcher_config.yaml` to protect API keys."
                    )
            except Exception:
                pass

        config = yaml.safe_load(cfg_path.read_text()) or {}
        safe = _mask_api_keys(config)

        result: dict[str, Any] = {"status": "success", "config": safe}
        if warning:
            result["warning"] = warning
        return result
    except Exception as e:
        logger.exception("get_config failed")
        return {"status": "error", "message": str(e)}


def get_research_config(root: Path) -> dict[str, Any]:
    """Return the raw researcher_config.yaml dict (no masking, no envelope).

    Compatibility shim — synthesis modules (typst.py, preview.py,
    figure_auto_embed.py, poster_typst handler) call this helper to
    read venue / synthesis preferences directly without wading through
    the get_config() success envelope. Returns an empty dict when the
    file is missing or unparseable so callers can chain ``.get(...)``
    against it safely.
    """
    try:
        cfg_path = _config_path(root)
        if not cfg_path.exists():
            return {}
        return yaml.safe_load(cfg_path.read_text()) or {}
    except Exception:
        return {}


def set_config(key: str, value: Any, root: Path) -> dict[str, Any]:
    """Set a single config value with dot notation (e.g. researcher.name)."""
    try:
        cfg_path = _config_path(root)
        config = yaml.safe_load(cfg_path.read_text()) if cfg_path.exists() else {}
        config = config or {}

        parts = key.split(".")
        cursor = config
        for part in parts[:-1]:
            if part not in cursor or not isinstance(cursor[part], dict):
                cursor[part] = {}
            cursor = cursor[part]
        cursor[parts[-1]] = value

        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        cfg_path.write_text(yaml.dump(config, default_flow_style=False, sort_keys=False))
        return {"status": "success", "key": key, "value": value}
    except Exception as e:
        logger.exception("set_config failed")
        return {"status": "error", "message": str(e)}


def init_config(root: Path, overrides: dict | None = None) -> dict[str, Any]:
    """Create ``inputs/researcher_config.yaml`` if missing, then merge overrides.

    Domain / research question / hypotheses are NOT persisted here — the
    caller (``scaffold_minimal_workspace`` → ``regenerate_intake``) writes
    those to ``inputs/intake.md`` instead.

    The cross-project profile at ``~/.config/research-os/profile.yaml``
    is loaded as the starting point — researcher.name / email / orcid /
    institution / api_keys / writing_preferences seeded from there if
    present. Per-project overrides still win on conflict.
    """
    root = Path(root)
    overrides = overrides or {}
    cfg_path = _config_path(root)
    already_exists = cfg_path.exists()
    profile = load_profile()
    if not already_exists:
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        cfg_path.write_text(
            CONFIG_TEMPLATE.format(
                project_name=overrides.get("project_name", ""),
            )
        )
        # Seed researcher fields + api_keys + writing_preferences from the
        # cross-project profile so a fresh init doesn't ask for the same
        # things every time.
        if profile:
            try:
                config = _load_config_roundtrip(cfg_path)
                for top_key in ("researcher", "api_keys", "writing_preferences"):
                    profile_block = profile.get(top_key)
                    if isinstance(profile_block, dict):
                        config_block = config.get(top_key) or {}
                        for k, v in profile_block.items():
                            if isinstance(v, str) and v.strip() and not (config_block.get(k) or "").strip():
                                config_block[k] = v
                        config[top_key] = config_block
                if isinstance(profile.get("model_profile"), str):
                    config["model_profile"] = profile["model_profile"]
                _dump_config_roundtrip(cfg_path, config)
            except Exception as e:
                logger.warning("Failed to apply cross-project profile: %s", e)

    if overrides:
        try:
            config = _load_config_roundtrip(cfg_path)
            if overrides.get("project_name"):
                config["project_name"] = overrides["project_name"]
            # Multi-researcher: append authors to a top-level list, deduplicated.
            if overrides.get("authors"):
                existing = config.get("authors") or []
                if not isinstance(existing, list):
                    existing = []
                seen = {(a.get("name"), a.get("email")) for a in existing
                        if isinstance(a, dict)}
                for a in overrides["authors"]:
                    if not isinstance(a, dict):
                        continue
                    key = (a.get("name"), a.get("email"))
                    if key in seen:
                        continue
                    existing.append(a)
                    seen.add(key)
                config["authors"] = existing
            if overrides.get("depth"):
                config.setdefault("research_goal", {})["target_venue"] = overrides["depth"]
            # Workspace mode (analysis | tool_build | exploration) + the
            # tool_build inner-repo dir. Only non-default values are written;
            # the template already ships mode: "analysis".
            ws_in = overrides.get("workspace")
            if isinstance(ws_in, dict):
                ws_block = config.setdefault("workspace", {})
                mode_in = ws_in.get("mode")
                if mode_in in VALID_WORKSPACE_MODES:
                    ws_block["mode"] = mode_in
                inner_in = ws_in.get("inner_repo")
                if isinstance(inner_in, str) and inner_in.strip():
                    ws_block["inner_repo"] = inner_in.strip()
            if overrides.get("model_profile") in ("small", "medium", "large"):
                config["model_profile"] = overrides["model_profile"]
            # API keys: merge non-empty values into the api_keys: block.
            if overrides.get("api_keys"):
                api_keys_in = overrides["api_keys"]
                if isinstance(api_keys_in, dict):
                    for k, v in api_keys_in.items():
                        if isinstance(v, str) and v.strip():
                            config.setdefault("api_keys", {})[k] = v.strip()
            # Researcher identity (name / email / institution / orcid).
            if overrides.get("researcher"):
                r_in = overrides["researcher"]
                if isinstance(r_in, dict):
                    r_block = config.setdefault("researcher", {})
                    for k, v in r_in.items():
                        if isinstance(v, str) and v.strip():
                            r_block[k] = v.strip()
            _dump_config_roundtrip(cfg_path, config)
        except Exception as e:
            logger.warning(f"Failed to apply config overrides: {e}")

    if os.name != "nt":
        try:
            os.chmod(cfg_path, 0o600)
        except Exception:
            pass

    gitignore = root / ".gitignore"
    if gitignore.exists():
        content = gitignore.read_text()
        if "inputs/researcher_config.yaml" not in content:
            with open(gitignore, "a") as f:
                f.write("\n# secrets\ninputs/researcher_config.yaml\n")

    if already_exists:
        return {"status": "success", "message": "Config already exists; overrides applied."}
    return {
        "status": "success",
        "message": "Initialised researcher_config.yaml and locked permissions to 600.",
    }


# ---------------------------------------------------------------------------
# API-key management (CLI: research-os api-key add|list|rotate|remove|test)
# ---------------------------------------------------------------------------
#
# Stored in the api_keys: block of inputs/researcher_config.yaml. Every
# write re-applies chmod 600 because the file may have been touched by
# something that doesn't know about the secret. _mask_api_keys above
# is used to redact previews on list.


def add_api_key(root: Path, provider: str, value: str) -> dict[str, Any]:
    """Add (or overwrite) ``api_keys.<provider>`` and chmod 600 the file.

    Returns ``{"status": "success", "provider": provider, "rotated": bool}``
    where ``rotated`` is True if an existing value was overwritten.
    """
    root = Path(root)
    if not provider or not isinstance(provider, str):
        return {"status": "error", "message": "provider name must be a non-empty string"}
    if not isinstance(value, str) or not value.strip():
        return {"status": "error", "message": "value must be a non-empty string"}
    cfg_path = _config_path(root)
    if not cfg_path.exists():
        init_config(root)
    try:
        config = _load_config_roundtrip(cfg_path)
        api_keys = config.get("api_keys") or {}
        if not isinstance(api_keys, dict):
            api_keys = {}
        rotated = bool(api_keys.get(provider))
        api_keys[provider] = value.strip()
        config["api_keys"] = api_keys
        _dump_config_roundtrip(cfg_path, config)
        if os.name != "nt":
            try:
                os.chmod(cfg_path, 0o600)
            except Exception:
                pass
        return {"status": "success", "provider": provider, "rotated": rotated}
    except Exception as e:
        logger.exception("add_api_key failed")
        return {"status": "error", "message": str(e)}


def remove_api_key(root: Path, provider: str) -> dict[str, Any]:
    """Clear ``api_keys.<provider>`` (set to empty string)."""
    root = Path(root)
    cfg_path = _config_path(root)
    if not cfg_path.exists():
        return {"status": "error", "message": "researcher_config.yaml not found"}
    try:
        config = _load_config_roundtrip(cfg_path)
        api_keys = config.get("api_keys") or {}
        if not isinstance(api_keys, dict) or not api_keys.get(provider):
            return {"status": "noop", "message": f"{provider}: no key to remove"}
        api_keys[provider] = ""
        config["api_keys"] = api_keys
        _dump_config_roundtrip(cfg_path, config)
        if os.name != "nt":
            try:
                os.chmod(cfg_path, 0o600)
            except Exception:
                pass
        return {"status": "success", "provider": provider}
    except Exception as e:
        logger.exception("remove_api_key failed")
        return {"status": "error", "message": str(e)}


def list_api_keys(root: Path) -> dict[str, Any]:
    """Return the masked api_keys block (preview-only)."""
    root = Path(root)
    cfg_path = _config_path(root)
    if not cfg_path.exists():
        return {"status": "error", "message": "researcher_config.yaml not found"}
    try:
        config = yaml.safe_load(cfg_path.read_text()) or {}
        masked = _mask_api_keys(config)
        return {"status": "success", "api_keys": masked.get("api_keys") or {}}
    except Exception as e:
        logger.exception("list_api_keys failed")
        return {"status": "error", "message": str(e)}


# Free-tier endpoints we can hit with the configured key to confirm it
# works. Each entry: (URL template, headers builder). We keep this tiny —
# 1 token round-trip per provider, never enough payload to incur a meaningful
# rate-limit hit. Adding a provider here = adding it to the `test` action.
_API_KEY_TEST_ENDPOINTS: dict[str, dict[str, Any]] = {
    "semantic_scholar": {
        "url": "https://api.semanticscholar.org/graph/v1/paper/search?query=test&limit=1",
        "headers_builder": lambda v: {"x-api-key": v} if v else {},
        "needs_key": False,  # endpoint works keyless; key just lifts rate-limit
    },
    "pubmed": {
        # eutils returns an XML/JSON ping regardless of API key; api_key just
        # raises the per-IP rate-limit. We hit a trivial einfo query.
        "url": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/einfo.fcgi?retmode=json",
        "headers_builder": lambda v: {},
        "needs_key": False,
    },
    "crossref": {
        # Crossref expects a 'mailto:' user-agent for the polite pool, not a
        # secret key; we just verify connectivity.
        "url": "https://api.crossref.org/works?rows=1",
        "headers_builder": lambda v: {"User-Agent": f"research-os/test ({v or 'anonymous'})"},
        "needs_key": False,
    },
}


def check_api_key(root: Path, provider: str) -> dict[str, Any]:
    """Do a 1-token round-trip against the provider to verify the key works.

    Returns ``{"status": "ok"|"fail", "provider": ..., "detail": "..."}``.
    Never raises — network errors / 4xx / 5xx all map to status='fail'.

    (Function is named ``check_api_key`` rather than ``test_api_key`` so
    pytest doesn't try to collect it as a test case.)
    """
    root = Path(root)
    info = _API_KEY_TEST_ENDPOINTS.get(provider)
    if not info:
        return {
            "status": "fail",
            "provider": provider,
            "detail": f"no test endpoint registered for {provider!r}; "
                      f"known: {sorted(_API_KEY_TEST_ENDPOINTS)}",
        }
    cfg_path = _config_path(root)
    key_value = ""
    if cfg_path.exists():
        try:
            cfg = yaml.safe_load(cfg_path.read_text()) or {}
            key_value = (cfg.get("api_keys") or {}).get(provider) or ""
        except Exception:
            key_value = ""
    if info.get("needs_key", True) and not key_value:
        return {"status": "fail", "provider": provider,
                "detail": "no key configured (add with `research-os api-key add ...`)"}
    try:
        # Local import — urllib is stdlib, no dependency footprint.
        from urllib import error, request
        url = info["url"]
        headers = info["headers_builder"](key_value) or {}
        req = request.Request(url, headers=headers)
        with request.urlopen(req, timeout=10) as resp:  # noqa: S310
            status_code = resp.getcode()
            if 200 <= status_code < 300:
                return {"status": "ok", "provider": provider,
                        "detail": f"HTTP {status_code}"}
            return {"status": "fail", "provider": provider,
                    "detail": f"HTTP {status_code}"}
    except error.HTTPError as e:  # type: ignore[name-defined]
        return {"status": "fail", "provider": provider,
                "detail": f"HTTP {e.code}"}
    except Exception as e:
        return {"status": "fail", "provider": provider, "detail": str(e)}


# Enum-membership contracts for fields whose template documents a
# closed set. validate_config flags off-enum values so a typo (e.g.
# ``gate_strictness: lite``) surfaces at validate time instead of
# being silently treated as the documented default.
_ENUM_FIELDS: dict[str, tuple[str, ...]] = {
    "interaction.autonomy_level": (
        "manual", "supervised", "autopilot", "coaching",
    ),
    "interaction.quality_gate_policy": VALID_GATE_POLICIES,
    "interaction.ambiguity_posture": VALID_AMBIGUITY_POSTURES,
    "gate_strictness": ("light", "normal", "strict", "auto"),
    "project_tier": ("throwaway", "sketch", "production"),
    "workspace.mode": VALID_WORKSPACE_MODES,
    "model_profile": ("small", "medium", "large"),
    # AI-side knobs (paired model_profile + context_class). The ai.*
    # path takes precedence when present; legacy top-level model_profile
    # is still honoured for back-compat.
    "ai.model_profile": ("small", "medium", "large"),
    "ai.context_class": ("short", "long"),
    "writing_preferences.pdf_compile_engine": ("typst", "latex", "both"),
    "writing_preferences.citation_style": (
        # STEM / biomedical / quantitative
        "apa", "vancouver", "acm", "ieee", "nature",
        # Humanities / theory
        "mla", "chicago_author_date", "chicago_notes_bib",
        # Mathematical sciences
        "amsplain", "siam",
    ),
    # Synthesis knobs intentionally absent — the AI authors synthesis
    # files directly, so there's nothing to validate.
}

# No bool fields today. Retained for future use.
_BOOL_FIELDS: tuple[str, ...] = ()

# No numeric synthesis-tier fields today.
_NUMERIC_FIELDS: tuple[tuple[str, str, float, float], ...] = ()


def _dotted_get(cfg: dict[str, Any], path: str) -> Any:
    cursor: Any = cfg
    for part in path.split("."):
        if not isinstance(cursor, dict):
            return None
        cursor = cursor.get(part)
    return cursor


def validate_config(root: Path) -> dict[str, Any]:
    """Report which keys are present + whether API keys are configured.

    Also validates enum-membership for fields whose template documents a
    closed set (autonomy_level, gate_strictness, project_tier, etc.).
    A field set to an off-enum value (typo, stale alias) is surfaced in
    ``enum_violations`` and counts toward the human-readable message.
    """
    res = get_config(root)
    if res.get("status") != "success":
        return res
    config = res.get("config", {}) or {}

    required_paths = [
        ("project_name", config.get("project_name")),
        ("researcher.name", (config.get("researcher") or {}).get("name")),
        ("interaction.autonomy_level", (config.get("interaction") or {}).get("autonomy_level")),
        ("model_profile", config.get("model_profile")),
        ("research_goal.output_types", (config.get("research_goal") or {}).get("output_types")),
    ]

    missing = [k for k, v in required_paths if not v]

    enum_violations: list[dict[str, Any]] = []
    for field, allowed in _ENUM_FIELDS.items():
        value = _dotted_get(config, field)
        if value is None or value == "":
            continue
        if not isinstance(value, str) or value not in allowed:
            enum_violations.append({
                "field": field,
                "value": value,
                "allowed": list(allowed),
            })

    # Bool fields (synthesis toggles) — flag non-bool values. Blank /
    # absent is fine (template default applies); a string "true" or
    # int 1 is a typo worth surfacing.
    for field in _BOOL_FIELDS:
        value = _dotted_get(config, field)
        if value is None:
            continue
        if not isinstance(value, bool):
            enum_violations.append({
                "field": field,
                "value": value,
                "allowed": [True, False],
            })

    # Numeric fields (synthesis tier knobs) — type + range check.
    for field, kind, lo, hi in _NUMERIC_FIELDS:
        value = _dotted_get(config, field)
        if value is None:
            continue
        ok = False
        if kind == "int" and isinstance(value, int) and not isinstance(value, bool):
            ok = lo <= value <= hi
        elif kind == "float" and isinstance(value, (int, float)) and not isinstance(value, bool):
            ok = lo <= float(value) <= hi
        if not ok:
            enum_violations.append({
                "field": field,
                "value": value,
                "allowed": [f"{kind} in [{lo}, {hi}]"],
            })

    api_keys = config.get("api_keys") or {}
    keys_present = sorted(k for k, v in api_keys.items() if v and v != "***" and not str(v).endswith("…"))
    keys_missing = sorted(k for k, v in api_keys.items() if not v)

    if missing and enum_violations:
        message = (
            f"Missing required fields: {', '.join(missing)}; "
            f"off-enum values: {', '.join(v['field'] for v in enum_violations)}"
        )
    elif missing:
        message = f"Missing required fields: {', '.join(missing)}"
    elif enum_violations:
        message = (
            "Off-enum values: "
            + ", ".join(f"{v['field']}={v['value']!r}" for v in enum_violations)
        )
    else:
        message = "Config OK."

    return {
        "status": "success",
        "required_fields_missing": missing,
        "enum_violations": enum_violations,
        "api_keys_configured": keys_present,
        "api_keys_blank": keys_missing,
        "message": message,
    }
