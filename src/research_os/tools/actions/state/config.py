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


# v1.3.2: prefer ruamel.yaml for round-trip writes so the rich inline
# help comments in CONFIG_TEMPLATE survive every override. Falls back
# to PyYAML when ruamel.yaml isn't installed — the structure is
# preserved either way, only the comments are lost on the fallback path.
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


CONFIG_TEMPLATE = """# Research OS — Researcher Configuration
#
# Tells the AI who it's working with and how you want it to behave.
# Research OS does NOT manage LLM providers — your AI client (Claude Code /
# OpenCode / Antigravity / Cursor / Claude / VS Code) handles model access.
#
# EVERY field below is OPTIONAL, but the more you fill in here, the better
# the AI orients. Domain / research question / hypotheses are NOT in this
# file — drop data + notes into inputs/ and say "fill out the intake" to
# the AI; it writes those to inputs/intake.md and docs/research_overview.md.

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
  output_types: []               # any of: paper | abstract | poster | dashboard | report | exploratory
  target_venue: ""               # journal | conference | preprint | dissertation | report
  poster_dimensions: "36x48"

# ── How the AI should behave ────────────────────────────────────────────
interaction:
  autonomy_level: "supervised"   # manual | supervised | autopilot
  # manual     → ask before every tool call.
  # supervised → ask before path creation, synthesis, destructive writes.
  # autopilot  → run autonomously; ask only before synthesis / very long jobs.

  # Quality-gate posture. The AI NEVER bypasses a gate on its own; this
  # only sets the friction level when the researcher asks to bypass.
  #   enforce        → AI refuses to bypass without an explicit researcher
  #                    instruction in the current message.
  #   allow_override → AI may pass override_completeness_gate=true when
  #                    the researcher asks, but must record the rationale.
  #   warn_only      → Treat blockers as warnings (still logged); deliverables
  #                    proceed. Use only for sandbox / exploratory projects.
  quality_gate_policy: "enforce"

  # Whether the AI should ask follow-ups vs. take a reasonable default
  # when a protocol step is ambiguous.
  #   ask_when_uncertain → default. Surfaces ask_user from tool_route.
  #   take_best_default  → AI proceeds with the most defensible choice
  #                        and surfaces it in the conclusion for review.
  ambiguity_posture: "ask_when_uncertain"

# ── Match the AI model class running in your IDE ────────────────────────
#
# The single most important knob if you're not on a frontier model.
#   small  → 1 step/turn, summary-only protocol loads, skip optional
#            sub-sections. Pick for: Claude Haiku 4.5, GPT-4o-mini,
#            Gemini 2.5 Flash, Llama 3.3, Mistral, Phi-4, local models.
#   medium → 3 steps/turn, summary loads with on-demand drill-down.
#            Pick for: Claude Sonnet 4.5/4.6, GPT-4o/4.1, Gemini 2.5 Pro,
#            Llama 4 Maverick.
#   large  → 6 steps/turn, full protocol loads when useful, deeper plans.
#            Pick for: Claude Opus 4.x, GPT-5/o-series, Gemini 3 Pro.
model_profile: "medium"          # small | medium | large

# ── Writing preferences ─────────────────────────────────────────────────
writing_preferences:
  citation_style: "apa"          # apa | vancouver | acm | ieee | nature
  language: "en-US"

# ── Compute environment ─────────────────────────────────────────────────
runtime:
  shared_server: false           # true → AI uses background tasks for long jobs,
                                 #        and warns before heavy memory/CPU bursts.
  long_running_threshold_seconds: 60   # jobs longer than this prefer background.
  default_n_for_sampling: 1000   # default head-sample for tabular exploration.

# ── API keys (optional; public endpoints work without keys) ─────────────
# NO LLM PROVIDER KEYS HERE — Research OS does not call any model.
# These are for literature search and web scraping only.
api_keys:
  semantic_scholar: ""           # https://www.semanticscholar.org/product/api
  pubmed: ""                     # https://www.ncbi.nlm.nih.gov/account/
  crossref: ""                   # https://www.crossref.org  (rarely needed)
  firecrawl: ""                  # https://firecrawl.io  — web search + scrape
  serpapi: ""                    # https://serpapi.com   — fallback web search
"""


def _config_path(root: Path) -> Path:
    return root / "inputs" / "researcher_config.yaml"


# ---------------------------------------------------------------------------
# Cross-project profile (v1.3.0)
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


def get_interaction_policy(root: Path) -> dict[str, str]:
    """Return ``{quality_gate_policy, ambiguity_posture}`` from the config.

    Falls back to the documented defaults when the file or the
    ``interaction:`` block is absent or contains an unknown value.
    Callers use this to decide whether to enforce, soft-override, or
    warn-only on quality-gate blockers; and whether to ask the
    researcher or pick a best-default on ambiguity.
    """
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

    v1.3.0: cross-project profile at ``~/.config/research-os/profile.yaml``
    is loaded as the starting point — researcher.name / email / orcid /
    institution / api_keys / writing_preferences seeded from there if
    present. Per-project overrides still win on conflict.
    """
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
            # v1.3.0: researcher identity (name / email / institution / orcid).
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


def validate_config(root: Path) -> dict[str, Any]:
    """Report which keys are present + whether API keys are configured."""
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

    api_keys = config.get("api_keys") or {}
    keys_present = sorted(k for k, v in api_keys.items() if v and v != "***" and not str(v).endswith("…"))
    keys_missing = sorted(k for k, v in api_keys.items() if not v)

    return {
        "status": "success",
        "required_fields_missing": missing,
        "api_keys_configured": keys_present,
        "api_keys_blank": keys_missing,
        "message": (
            "Config OK." if not missing else f"Missing required fields: {', '.join(missing)}"
        ),
    }
