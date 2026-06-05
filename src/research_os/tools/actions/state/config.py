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

# ── This project ────────────────────────────────────────────────────────
project_name: "{project_name}"

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
  #            tool_mistake_replay each session for self-coaching across
  #            recurring patterns the researcher keeps tripping.

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
  # Typst venue template for tool_paper_compile_typst. One of:
  #   nature | science | nejm | cell | ieee_conf | neurips | acl
  #   plos  | generic_two_column | generic_thesis
  #   humanities_essay      → single-column, footnote-friendly, MLA/Chicago.
  #   chicago_thesis        → Chicago notes+bibliography thesis layout.
  venue_template: "generic_two_column"
  # PDF engine for the synthesis pipeline. "typst" is the recommended
  # default (fast, single-binary install, modern type-safe macros).
  # Use "latex" when a journal requires .tex submission.
  pdf_compile_engine: "typst"    # typst | latex | both

# ── Compute environment ─────────────────────────────────────────────────
runtime:
  shared_server: false           # set true on HPC / shared boxes
  long_running_threshold_seconds: 60
  default_n_for_sampling: 1000

# ── Language + tool-stack preferences ──────────────────────────────────
# Read by `methodology/pick_tool_stack`. AI uses these as hints (NOT
# hard constraints); field-practice for a given method still wins.
tool_stack:
  preferred_languages: ["python", "R"]   # order = tie-breaker; empty = no preference
  allow_mixed_language_steps: true        # false → split mixed work into separate steps
  field_practice_overrides_preference: true   # true → R Bioconductor wins for DE even if Python listed first
  cite_field_practice_when_choosing: true     # require literature citation per language choice

# ── Synthesis pipeline ─────────────────────────────────────────────────
# Controls how tool_synthesize / tool_slides_compile_reveal /
# tool_poster_compile_typst assemble the final artefacts. Defaults are
# safe: figures auto-embed into their owning step's section, slides
# render with reveal.js + a 15-minute conference template, posters
# render with Typst at 36x48 (academic).
synthesis:
  # Figures: auto-embed step output figures into their owning section
  # of the paper body during tool_synthesize. Off = caller hand-places.
  figures_auto_embed: true
  # How auto-embed places figures.
  #   append_to_section → drop at end of the step's owning section
  #   inline_at_xref    → place at the first ![fig:id] reference site
  #   end_of_results    → cluster all figures at end of Results
  figures_auto_embed_mode: "append_to_section"
  # Rewrite bare [fig:id] tokens in step conclusions to ![…](…) refs
  # that resolve against the embedded figure registry.
  figure_xref_rewrite: true

  # Slide deck (tool_slides_compile_reveal).
  #   reveal   → reveal.js HTML deck (default; works in any browser)
  #   marp     → Marp markdown → PDF/HTML
  #   beamer   → LaTeX Beamer (when a venue requires .tex)
  slide_engine: "reveal"
  # Slide template (matches deck length + section shape).
  #   conference_15min | conference_30min | lab_meeting | thesis_defense
  slide_template: "conference_15min"
  # Visual theme; "" → reveal default. Examples: black, white, league,
  # beige, sky, night, serif, simple, solarized.
  slide_theme: ""
  # Generate speaker-notes panel from step conclusions.
  slide_speaker_notes_enabled: true
  # Also emit a 1-up print handout PDF alongside the deck.
  slide_print_handout: true

  # Poster (tool_poster_compile_typst).
  #   typst    → recommended (single-binary install, fast)
  #   latex    → Beamer poster (legacy)
  poster_engine: "typst"
  # Poster template (matches dimensions + density).
  #   academic_36x48 | academic_48x36 | academic_a0_portrait
  #   | academic_a1_landscape | public_24x36
  poster_template: "academic_36x48"
  # Visual theme. light | dark | institution_branded
  poster_theme: "light"
  # Optional QR URL printed bottom-right (project page / preprint).
  poster_qr_url: ""
  # Emit a US-letter handout PDF alongside the poster.
  poster_handout_pdf: true

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
    "model_profile": ("small", "medium", "large"),
    "writing_preferences.pdf_compile_engine": ("typst", "latex", "both"),
    "writing_preferences.citation_style": (
        # STEM / biomedical / quantitative
        "apa", "vancouver", "acm", "ieee", "nature",
        # Humanities / theory
        "mla", "chicago_author_date", "chicago_notes_bib",
        # Mathematical sciences
        "amsplain", "siam",
    ),
    # ── Synthesis pipeline ────────────────────────────────────────────
    "synthesis.figures_auto_embed_mode": (
        "append_to_section", "inline_at_xref", "end_of_results",
    ),
    "synthesis.slide_engine": ("reveal", "marp", "beamer"),
    "synthesis.slide_template": (
        "conference_15min", "conference_30min", "lab_meeting", "thesis_defense",
    ),
    "synthesis.poster_engine": ("typst", "latex"),
    "synthesis.poster_template": (
        "academic_36x48", "academic_48x36",
        "academic_a0_portrait", "academic_a1_landscape",
        "public_24x36",
    ),
    "synthesis.poster_theme": ("light", "dark", "institution_branded"),
}

# Fields whose template default is bool. validate_config flags non-bool
# values so a typo (e.g. ``figures_auto_embed: "yes"``) is surfaced.
_BOOL_FIELDS: tuple[str, ...] = (
    "synthesis.figures_auto_embed",
    "synthesis.figure_xref_rewrite",
    "synthesis.slide_speaker_notes_enabled",
    "synthesis.slide_print_handout",
    "synthesis.poster_handout_pdf",
)


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
