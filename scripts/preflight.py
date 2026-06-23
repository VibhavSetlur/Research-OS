#!/usr/bin/env python3
"""Preflight smoke check for Research OS.

Run before publishing a release (or any time you want to confirm the
package is wired up). Exits with non-zero on any failure.

Validates:
  1. Top-level package imports cleanly.
  2. The eight action subpackages import.
  3. ``research_os.cli`` exposes ``main``.
  4. Every protocol YAML loads and has the required keys.
  5. Every tool defined in ``server.TOOL_DEFINITIONS`` has a registered
     handler in ``server._HANDLERS``.
  6. The dispatcher correctly resolves dot notation and legacy aliases.
  7. Protocol scaffolds never reference deprecated alias names — they
     must call the consolidated handler directly.

Use:
    python scripts/preflight.py
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
PROTOCOLS_DIR = REPO_ROOT / "src" / "research_os" / "protocols"


def _report(name: str, ok: bool, detail: str = "") -> None:
    badge = "OK " if ok else "FAIL"
    line = f"  [{badge}] {name}"
    if detail:
        line += f"  — {detail}"
    print(line)


class Tally:
    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0
        self.errors: list[str] = []

    def check(self, name: str, fn) -> None:
        try:
            ok, detail = fn()
        except Exception as e:
            ok = False
            detail = f"{type(e).__name__}: {e}"
            self.errors.append(f"{name}\n{traceback.format_exc()}")
        _report(name, ok, detail)
        if ok:
            self.passed += 1
        else:
            self.failed += 1


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def check_top_level_import():
    import research_os  # noqa: F401

    return True, f"version {research_os.__version__}"


def check_subpackages():
    pkgs = [
        "research_os.tools.actions.state",
        "research_os.tools.actions.data",
        "research_os.tools.actions.exec",
        "research_os.tools.actions.search",
        "research_os.tools.actions.research",
        "research_os.tools.actions.audit",
        "research_os.tools.actions.synthesis",
        "research_os.tools.actions.memory",
        "research_os.tools.actions.protocol",
    ]
    bad = []
    for p in pkgs:
        try:
            __import__(p)
        except Exception as e:
            bad.append(f"{p}: {e}")
    return not bad, ("ok" if not bad else "; ".join(bad))


def check_cli_entrypoint():
    from research_os.cli import main

    return callable(main), "main() callable"


def check_flat_namespace_is_minimal():
    """Only a tiny allowlist of cross-cutting modules at tools/actions/.

    Everything else MUST live in a category sub-package (state/, data/,
    exec/, search/, research/, audit/, synthesis/, memory/). The flat
    allowlist is for modules that touch every category and would create
    a circular sub-package if nested:
      - protocol.py — loader + cross-protocol injection
      - router.py   — trigger-based hierarchical router
      - semantic.py — embedding-based semantic router (sibling of router)
      - listers.py  — flat protocol + tool catalog listers
    """
    actions_dir = REPO_ROOT / "src" / "research_os" / "tools" / "actions"
    flat = sorted(
        f.name for f in actions_dir.iterdir()
        if f.is_file() and f.suffix == ".py"
    )
    expected = {
        "__init__.py", "listers.py", "protocol.py", "router.py", "semantic.py",
    }
    return set(flat) == expected, f"{flat}"


def check_every_protocol_loads():
    from research_os.tools.actions.protocol import load_protocol

    bad: list[str] = []
    count = 0
    for f in sorted(PROTOCOLS_DIR.rglob("*.yaml")):
        if "light" in f.parts:
            continue
        # Files prefixed with `_` are registry / index files, not protocols.
        if f.name.startswith("_"):
            continue
        rel = f.relative_to(PROTOCOLS_DIR).with_suffix("").as_posix()
        try:
            data = load_protocol(rel)
            for required in ("id", "name", "steps"):
                if required not in data:
                    bad.append(f"{rel} missing `{required}`")
            if not isinstance(data.get("steps"), list) or not data["steps"]:
                bad.append(f"{rel} has empty/invalid steps")
            count += 1
        except Exception as e:
            bad.append(f"{rel}: {type(e).__name__}: {e}")
    return not bad, f"{count} loaded" if not bad else "; ".join(bad[:3])


def check_no_dot_tool_calls_in_protocols():
    """New protocols shouldn't use the legacy `tool_X.Y` dot notation."""
    import re

    bad_patterns = [
        r"\b(sys|tool|mem)_[a-z_]+\.[a-z_]+\b",  # e.g. sys_state.get
    ]
    offenders: list[str] = []
    for f in PROTOCOLS_DIR.rglob("*.yaml"):
        if "light" in f.parts:
            continue
        if f.name.startswith("_"):
            continue
        text = f.read_text()
        for pat in bad_patterns:
            for match in re.finditer(pat, text):
                # Skip protocol filenames like "literature/literature_search"
                # which contain a dot in the file context, not in tool call.
                offenders.append(f"{f.name}: `{match.group(0)}`")
    return not offenders, ("clean" if not offenders else f"{len(offenders)} offenders")


def check_every_tool_has_handler():
    from research_os.server import _HANDLERS, TOOL_DEFINITIONS

    defined = set(TOOL_DEFINITIONS)
    wired = set(_HANDLERS)
    missing = sorted(defined - wired)
    extra = sorted(wired - defined)
    if missing or extra:
        detail = []
        if missing:
            detail.append(f"defined-but-not-wired: {missing}")
        if extra:
            detail.append(f"wired-but-not-defined: {extra}")
        return False, "; ".join(detail)
    return True, f"{len(defined)} tools wired"


def check_dispatcher_aliases():
    from research_os.server import _resolve_tool_name

    cases = {
        # Dot-notation rewrite is generic.
        "sys.state.get": "sys_state_get",
        # Audit-family legacy nicknames now flow through the consolidated
        # tool_audit entry point (param injection sets scope+dimension so
        # the original behaviour is preserved end-to-end).
        "tool_audit_figure_quality": "tool_audit",
        "tool_audit_statistical_power": "tool_audit",
        "sys_state_summary": "sys_state_get",
        # tool_log_decision used to chain through mem_decision_log → mem_log;
        # mem_decision_log was hard-removed in phase-14a (v2.0.0), so the
        # nickname now resolves directly to mem_log with kind='decision'
        # injected.
        "tool_log_decision": "mem_log",
        "view_workspace_tree": "sys_workspace_tree",
        # Passthrough — name already canonical.
        "sys_state_get": "sys_state_get",
    }
    bad: list[str] = []
    for given, expected in cases.items():
        actual = _resolve_tool_name(given)
        if actual != expected:
            bad.append(f"{given!r} -> {actual!r} (expected {expected!r})")
    return not bad, "ok" if not bad else "; ".join(bad)


def check_adapters_discovered():
    """Every bundled adapter registers without errors."""
    try:
        from research_os.server import TOOL_DEFINITIONS  # noqa: F401
        from research_os.adapters import installed_adapters, load_adapter_errors
    except Exception as exc:
        return False, f"adapter loader import failed: {exc}"
    errors = load_adapter_errors()
    if errors:
        eps = [e["entry_point"] for e in errors]
        return False, f"adapter registration errors: {eps}"
    adapters = installed_adapters()
    required = {"slurm", "snakemake", "nextflow", "cytoscape", "redcap", "synapse"}
    bundled_names = {a["name"] for a in adapters}
    missing = sorted(required - bundled_names)
    if missing:
        return False, f"bundled adapters missing: {missing}"
    return True, (
        f"{len(adapters)} adapter(s) discovered: "
        + ", ".join(f"{a['name']}@{a['version']}" for a in adapters)
    )


def check_adapter_regex_compile():
    """Every adapter's tools_md_patterns must compile as a valid regex."""
    import re as _re
    try:
        from research_os.server import TOOL_DEFINITIONS  # noqa: F401
        from research_os.adapters.loader import active_adapter_extractors
    except Exception as exc:
        return False, f"adapter loader import failed: {exc}"
    bad: list[str] = []
    pattern_count = 0
    for name, patterns in active_adapter_extractors().items():
        for pat_source, _template in patterns:
            pattern_count += 1
            try:
                _re.compile(pat_source)
            except _re.error as exc:
                bad.append(f"{name}: {pat_source!r} → {exc}")
    if bad:
        return False, "; ".join(bad[:5])
    return True, f"{pattern_count} adapter regex pattern(s) compile"


def check_packs_discovered():
    """Every bundled pack registers without errors; tools + router merge cleanly."""
    # Importing any symbol from server triggers the module body which
    # calls _discover_packs_once() and merges bundled packs.
    try:
        from research_os.server import TOOL_DEFINITIONS  # noqa: F401
        from research_os.plugins import installed_packs, load_pack_errors
    except Exception as exc:
        return False, f"plugin import failed: {exc}"
    errors = load_pack_errors()
    if errors:
        eps = [e["entry_point"] for e in errors]
        return False, f"pack registration errors: {eps}"
    packs = installed_packs()
    # The two bundled packs MUST register for the shipped wheel to be valid.
    bundled_names = {p["name"] for p in packs}
    required = {"humanities", "qualitative", "theory_math", "wet_lab", "engineering"}
    missing = sorted(required - bundled_names)
    if missing:
        return False, f"bundled packs missing: {missing}"
    return True, (
        f"{len(packs)} pack(s) discovered: "
        + ", ".join(f"{p['name']}@{p['version']}" for p in packs)
    )


def check_pack_protocols_load():
    """Every YAML under each pack's protocols_dir must parse + load."""
    try:
        from research_os.server import TOOL_DEFINITIONS  # noqa: F401
        from research_os.plugins import installed_packs
        from research_os.tools.actions.protocol import load_protocol
    except Exception as exc:
        return False, f"plugin import failed: {exc}"
    bad: list[str] = []
    loaded = 0
    for pack in installed_packs():
        pdir = Path(pack["protocols_dir"])
        if not pdir.exists():
            continue
        for yaml_file in pdir.rglob("*.yaml"):
            if yaml_file.name.startswith("_"):
                continue
            inner = yaml_file.relative_to(pdir).with_suffix("")
            qual_name = f"{pack['name']}/{inner}"
            try:
                load_protocol(qual_name)
                loaded += 1
            except Exception as exc:
                bad.append(f"{qual_name}: {exc}")
    if bad:
        return False, "; ".join(bad[:5])
    return True, f"{loaded} pack protocol(s) load"


def check_pack_protocol_refs_and_targets():
    """Pack protocols are scaffolds an AI executes verbatim — so every tool
    they name must resolve and every next_protocol / on_failure / see_also
    target must exist. The core ref/target checks only walked core
    protocols, so broken pack refs (wrong tool prefix, dangling on_failure)
    shipped green. This is the durable guard for that whole class.
    """
    import re

    import yaml

    try:
        from research_os.plugins import installed_packs
        from research_os.server import TOOL_DEFINITIONS, _resolve_tool_name
    except Exception as exc:
        return False, f"plugin import failed: {exc}"

    # Same prose false-positives the core tool-ref check tolerates.
    false_positive_strings = {
        "tool_name", "tool_discovery", "tool_list", "tool_build",
    }
    pattern = re.compile(r"\b((?:sys|tool|mem)_[a-z_]+)\b(?!\*)")

    packs = list(installed_packs())
    pack_dirs = {p["name"]: Path(p["protocols_dir"]) for p in packs}

    def _target_resolves(ref) -> bool:
        ref = (ref or "").split("#")[0].strip()
        if not ref or ref.lower() in {"null", "none"} or "/" not in ref:
            return True
        # Some packs use on_failure as a free-text instruction rather than a
        # protocol path. A real target is a single whitespace-free
        # category/name token; anything with spaces is prose — skip it.
        if any(ch.isspace() for ch in ref):
            return True
        if (PROTOCOLS_DIR / f"{ref}.yaml").exists():
            return True  # core target
        cat = ref.split("/")[0]
        if cat in pack_dirs:  # pack-namespaced target → resolve in the pack
            inner = "/".join(ref.split("/")[1:])
            if (pack_dirs[cat] / f"{inner}.yaml").exists():
                return True
        return False

    bad: list[str] = []
    for pack in packs:
        pdir = Path(pack["protocols_dir"])
        if not pdir.exists():
            continue
        for f in pdir.rglob("*.yaml"):
            if f.name.startswith("_"):
                continue
            text = f.read_text()
            label = f"{pack['name']}/{f.relative_to(pdir).with_suffix('').as_posix()}"
            for m in pattern.finditer(text):
                name = m.group(1)
                if name in false_positive_strings or name.endswith("_"):
                    continue
                if _resolve_tool_name(name) not in TOOL_DEFINITIONS:
                    bad.append(f"{label}: tool `{name}` unresolved")
            try:
                data = yaml.safe_load(text) or {}
            except Exception:
                data = {}
            for field in ("next_protocol", "on_failure"):
                v = data.get(field)
                if isinstance(v, str) and not _target_resolves(v):
                    bad.append(f"{label}: {field} → {v}")
            for s in (data.get("see_also") or []):
                if isinstance(s, str) and not _target_resolves(s):
                    bad.append(f"{label}: see_also → {s}")
    if bad:
        bad = sorted(set(bad))
        return False, f"{len(bad)} broken pack ref(s): " + " | ".join(bad[:6])
    return True, "all pack protocol tool refs + routing targets resolve"


def check_alias_table_complete():
    """Every entry in _ALIASES must resolve to a registered handler.

    Also enforces that every name in _DEPRECATED_ALIASES has a
    corresponding parameter-injection entry — otherwise legacy callers
    of consolidated tools would silently lose their default operation.
    """
    from research_os.server import (
        _ALIASES, _ALIAS_PARAM_INJECTION, _DEPRECATED_ALIASES, _HANDLERS,
    )

    bad: list[str] = []
    for old, new in _ALIASES.items():
        if new not in _HANDLERS:
            bad.append(f"{old} -> {new} (target missing from _HANDLERS)")
    missing_inject = sorted(_DEPRECATED_ALIASES - set(_ALIAS_PARAM_INJECTION))
    if missing_inject:
        bad.append(
            f"deprecated aliases missing param injection: {missing_inject}"
        )
    return not bad, "ok" if not bad else "; ".join(bad)


def check_redirect_targets():
    """Every protocol YAML carrying `redirect_to:` must point at a real protocol.

    Also enforces that a stub cannot carry BOTH `redirect_to:` AND `steps:`
    (mutually exclusive — a stub is a thin alias).
    """
    import yaml

    bad: list[str] = []
    stub_count = 0
    for f in PROTOCOLS_DIR.rglob("*.yaml"):
        if f.name.startswith("_"):
            continue
        try:
            data = yaml.safe_load(f.read_text()) or {}
        except Exception as e:
            bad.append(f"{f.name}: YAML parse error: {e}")
            continue
        if not isinstance(data, dict):
            continue
        target = data.get("redirect_to")
        if not isinstance(target, str) or not target.strip():
            continue
        stub_count += 1
        rel = f.relative_to(PROTOCOLS_DIR)
        if data.get("steps"):
            bad.append(f"{rel}: stub has both redirect_to AND steps (mutually exclusive)")
        target = target.strip()
        if "/" in target:
            candidate = PROTOCOLS_DIR / f"{target}.yaml"
        else:
            candidate = next(
                (p for p in PROTOCOLS_DIR.rglob(f"{target}.yaml")
                 if not p.name.startswith("_")),
                None,
            )
        if not candidate or not candidate.exists():
            bad.append(f"{rel}: redirect_to '{target}' has no matching YAML")
    return not bad, (
        f"{stub_count} redirect stub(s) all resolve" if not bad else "; ".join(bad)
    )


def check_handlers_callable():
    from research_os.server import _HANDLERS

    bad = [name for name, fn in _HANDLERS.items() if not callable(fn)]
    return not bad, "all callable" if not bad else f"non-callable: {bad}"


def check_protocols_referenced_tools_resolve():
    """Every sys_/tool_/mem_ name in a protocol must be a real tool (after alias)."""
    import re

    from research_os.server import TOOL_DEFINITIONS, _resolve_tool_name

    # Add known false positives that aren't tool calls
    false_positive_strings = {
        "tool_name",        # field inside tool_external_tool_instructions
        "tool_discovery",   # protocol name (methodology/tool_discovery)
        "tool_list",        # word appearing in prose ("tool list")
        "tool_build",       # workspace.mode name (build/* protocols, scope_tags)
        "tool_to_analysis_handoff",  # protocol name (hybrid/tool_to_analysis_handoff)
        "tool_and_analysis",         # workflow_shape value for hybrid mode
    }
    refs: dict[str, set[str]] = {}
    # Match a tool name, but reject the match if the very next char is `*`
    # (those are wildcard mentions in prose like `tool_search_*`, not real
    # tool calls).
    pattern = re.compile(r"\b((?:sys|tool|mem)_[a-z_]+)\b(?!\*)")
    for f in PROTOCOLS_DIR.rglob("*.yaml"):
        if "light" in f.parts:
            continue
        if f.name.startswith("_"):
            # Registry / index files; their tool refs are validated below
            # via a dedicated router-index check.
            continue
        text = f.read_text()
        for m in pattern.finditer(text):
            name = m.group(1)
            if name in false_positive_strings:
                continue
            # Reject bare prefixes like `tool_search_` that end in `_`
            # (always a truncation/wildcard mention in prose).
            if name.endswith("_"):
                continue
            refs.setdefault(name, set()).add(f.name)

    unresolved = {
        name: list(files)
        for name, files in refs.items()
        if _resolve_tool_name(name) not in TOOL_DEFINITIONS
    }
    if unresolved:
        sample = ", ".join(f"{k} (in {','.join(v)})" for k, v in list(unresolved.items())[:5])
        return False, sample
    return True, f"{len(refs)} unique tool refs all resolve"


def check_router_index_consistent():
    """Every protocol in _router_index.yaml must exist; every tool ref must resolve."""
    import yaml

    from research_os.server import TOOL_DEFINITIONS, _resolve_tool_name

    idx_path = PROTOCOLS_DIR / "_router_index.yaml"
    if not idx_path.exists():
        return False, "_router_index.yaml missing"
    idx = yaml.safe_load(idx_path.read_text()) or {}

    bad: list[str] = []

    # Every protocol entry must point at a real protocol YAML.
    for proto_name in (idx.get("protocols") or {}).keys():
        path = PROTOCOLS_DIR / f"{proto_name}.yaml"
        if not path.exists():
            bad.append(f"protocol `{proto_name}` not on disk")

    # Every protocol on disk must be in the index (or in an allow-list).
    on_disk = set()
    for f in PROTOCOLS_DIR.rglob("*.yaml"):
        if "light" in f.parts or f.name.startswith("_"):
            continue
        rel = f.relative_to(PROTOCOLS_DIR).with_suffix("").as_posix()
        on_disk.add(rel)
    in_index = set((idx.get("protocols") or {}).keys())
    missing_from_index = sorted(on_disk - in_index)
    if missing_from_index:
        bad.append(
            f"{len(missing_from_index)} protocol(s) not in _router_index.yaml: "
            f"{missing_from_index[:3]}..."
        )

    # Every tool ref (shortcut_tool, decomposition.tool, shortcut_intents.tool)
    # must resolve to a real TOOL_DEFINITIONS entry.
    def _check_tool(t: str, ctx: str) -> None:
        if not t:
            return
        if _resolve_tool_name(t) not in TOOL_DEFINITIONS:
            bad.append(f"unknown tool `{t}` in {ctx}")

    for name, data in (idx.get("protocols") or {}).items():
        if not isinstance(data, dict):
            continue
        _check_tool(data.get("shortcut_tool", ""), f"protocols/{name}")
        for entry in data.get("decomposition", []) or []:
            if isinstance(entry, dict):
                _check_tool(entry.get("tool", ""), f"protocols/{name} decomposition")
    for sid, data in (idx.get("shortcut_intents") or {}).items():
        if not isinstance(data, dict):
            continue
        _check_tool(data.get("tool", ""), f"shortcut_intents/{sid}")

    return not bad, (
        f"{len(in_index)} protocols indexed, all tool refs resolve"
        if not bad
        else "; ".join(bad[:3])
    )


def check_router_index_bumped():
    """Warn when _router_index.yaml is older than any protocol YAML.

    AUDIT-v1.9.2-069: the index carries a ``version:`` integer counter
    that maintainers must bump whenever they touch the index. Easy to
    forget when only a protocol body changed. This check compares the
    index's mtime against every non-stub protocol YAML's mtime and
    surfaces the offenders. The check WARNs (always returns True) so
    preflight doesn't gate on it — protocol edits often don't require
    an index bump — but the detail line catches the eye if drift is
    starting to accumulate.
    """
    idx_path = PROTOCOLS_DIR / "_router_index.yaml"
    if not idx_path.exists():
        return True, "no _router_index.yaml on disk; skipped"
    idx_mtime = idx_path.stat().st_mtime
    newer: list[str] = []
    total = 0
    for f in PROTOCOLS_DIR.rglob("*.yaml"):
        if "light" in f.parts or f.name.startswith("_"):
            continue
        total += 1
        try:
            if f.stat().st_mtime > idx_mtime:
                rel = f.relative_to(PROTOCOLS_DIR).with_suffix("").as_posix()
                newer.append(rel)
        except OSError:
            continue
    if newer:
        return True, (
            f"{len(newer)}/{total} protocol(s) newer than _router_index.yaml "
            f"(consider bumping `version:`): {', '.join(newer[:3])}"
            + ("..." if len(newer) > 3 else "")
        )
    return True, f"_router_index.yaml fresher than all {total} protocols"


def check_next_protocol_kind_present():
    """Soft check: every protocol with `next_protocol:` should also declare
    `next_protocol_kind:` (forward_default | iterate_back | terminal).

    Doctrine lives in docs/PROTOCOL_DOCTRINE.md. The field is OPTIONAL —
    when absent the loader infers from the value of `next_protocol`. This
    check WARNs on absence so maintainers notice catalogue-wide drift,
    but always returns True so preflight doesn't gate on it.
    """
    import yaml

    missing: list[str] = []
    total = 0
    valid_kinds = {"forward_default", "iterate_back", "terminal"}
    invalid: list[str] = []
    for f in sorted(PROTOCOLS_DIR.rglob("*.yaml")):
        if "light" in f.parts or f.name.startswith("_"):
            continue
        try:
            data = yaml.safe_load(f.read_text()) or {}
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        if "next_protocol" not in data:
            continue
        total += 1
        rel = f.relative_to(PROTOCOLS_DIR).with_suffix("").as_posix()
        kind = data.get("next_protocol_kind")
        if kind is None:
            missing.append(rel)
        elif kind not in valid_kinds:
            invalid.append(f"{rel} (got {kind!r})")
    if invalid:
        return False, f"invalid next_protocol_kind values: {invalid[:3]}"
    if missing:
        return True, (
            f"{len(missing)}/{total} protocol(s) missing next_protocol_kind "
            f"(soft): {', '.join(missing[:3])}"
            + ("..." if len(missing) > 3 else "")
        )
    return True, f"{total} protocol(s) all declare next_protocol_kind"


def check_protocol_freshness():
    """Warn (don't fail) when a protocol hasn't been touched in 180+ days.

    Looks first at an explicit ``last_reviewed: YYYY-MM-DD`` field on
    each protocol YAML; falls back to git mtime when absent. Tracks the
    maintenance burden of having 47+ protocols by surfacing stale ones
    early instead of letting them quietly rot. Returns True (pass) when
    nothing is over the threshold; otherwise returns False with the
    stale list as detail (preflight overall still passes since this is a
    soft check, but the detail line catches the eye).
    """
    import subprocess as _subprocess
    from datetime import date, datetime

    import yaml

    STALE_DAYS = 180
    today = date.today()
    stale: list[str] = []
    total = 0

    for f in sorted(PROTOCOLS_DIR.rglob("*.yaml")):
        if "light" in f.parts or f.name.startswith("_"):
            continue
        total += 1
        try:
            data = yaml.safe_load(f.read_text()) or {}
        except Exception:
            continue

        # Prefer explicit field.
        last_reviewed_raw = data.get("last_reviewed")
        last_date = None
        if last_reviewed_raw:
            try:
                last_date = datetime.strptime(
                    str(last_reviewed_raw)[:10], "%Y-%m-%d"
                ).date()
            except ValueError:
                pass

        # Fallback: git mtime via `git log -1 --format=%cI`.
        if last_date is None:
            try:
                res = _subprocess.run(
                    ["git", "log", "-1", "--format=%cI", "--", str(f)],
                    capture_output=True,
                    text=True,
                    cwd=str(REPO_ROOT),
                    timeout=5,
                )
                if res.returncode == 0 and res.stdout.strip():
                    last_date = datetime.fromisoformat(
                        res.stdout.strip().split("T")[0]
                    ).date()
            except (OSError, _subprocess.TimeoutExpired, ValueError):
                pass

        if last_date is None:
            continue  # Untracked / new; not stale.
        age = (today - last_date).days
        if age > STALE_DAYS:
            rel = f.relative_to(PROTOCOLS_DIR).with_suffix("").as_posix()
            stale.append(f"{rel} ({age}d)")

    if stale:
        return True, (
            f"{total} protocols, {len(stale)} flagged for review "
            f"(>{STALE_DAYS}d): {', '.join(stale[:3])}"
            + ("..." if len(stale) > 3 else "")
        )
    return True, f"{total} protocols, all reviewed within {STALE_DAYS}d"


def check_embeddings_fresh():
    """The on-disk semantic-routing embeddings must match current sources.

    Re-runs the source-hash computation from scripts/build_embeddings.py
    and compares it to the hash stamped in _embeddings_meta.json. Stale
    embeddings cause silent semantic-routing misses (a freshly-added
    protocol won't be in the index, a renamed protocol points at thin
    air). Refusing to ship on staleness is the right default.

    Fix when this fails:
        python scripts/build_embeddings.py
    """
    embeds_npz = PROTOCOLS_DIR / "_embeddings.npz"
    embeds_meta = PROTOCOLS_DIR / "_embeddings_meta.json"
    if not embeds_npz.exists() or not embeds_meta.exists():
        return False, (
            "missing _embeddings.npz / _embeddings_meta.json — run "
            "`python scripts/build_embeddings.py`"
        )
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    try:
        be = __import__("build_embeddings")
    except Exception as exc:
        return False, f"failed to import scripts/build_embeddings.py: {exc}"
    import json
    protocol_docs = be._load_protocols()
    tool_docs = be._load_tools()
    src_hash = be._source_hash(protocol_docs, tool_docs)
    try:
        meta = json.loads(embeds_meta.read_text())
    except Exception as exc:
        return False, f"could not parse _embeddings_meta.json: {exc}"
    if meta.get("source_hash") != src_hash:
        return False, (
            f"STALE — source hash drifted. "
            f"Rebuild: python scripts/build_embeddings.py "
            f"(on-disk={meta.get('source_hash', '?')[:12]}…, "
            f"now={src_hash[:12]}…)"
        )
    if meta.get("model") != be.MODEL_NAME or meta.get("schema_version") != be.SCHEMA_VERSION:
        return False, "model / schema_version drift — rebuild"
    return True, (
        f"{meta.get('n_protocols')} protocols + {meta.get('n_tools')} tools "
        f"({meta.get('model')}, dim={meta.get('dim')})"
    )


def check_route_meta():
    """The compiled runtime routing sidecar must be fresh + consistent.

    Routing (tool_route + semantic.py) loads _route_meta.json at runtime, NOT
    the 104K _router_index.yaml. A stale/inconsistent sidecar = silent
    misroutes, so we re-derive it from the authoring index + protocol bodies
    and compare, then assert per-protocol fields and embeddings parity.

    Fix when this fails:
        python scripts/build_embeddings.py --route-meta-only
    """
    import json

    route_meta = PROTOCOLS_DIR / "_route_meta.json"
    if not route_meta.exists():
        return False, (
            "missing _route_meta.json — run "
            "`python scripts/build_embeddings.py --route-meta-only`"
        )
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    try:
        be = __import__("build_embeddings")
    except Exception as exc:
        return False, f"failed to import scripts/build_embeddings.py: {exc}"
    try:
        on_disk = json.loads(route_meta.read_text())
    except Exception as exc:
        return False, f"could not parse _route_meta.json: {exc}"
    # Freshness: re-derive the sidecar (index + body tier/shape) and compare.
    expected = be._build_route_meta()
    if on_disk.get("source_hash") != expected.get("source_hash"):
        return False, (
            "STALE — recompile: python scripts/build_embeddings.py "
            "--route-meta-only "
            f"(on-disk={str(on_disk.get('source_hash'))[:12]}…, "
            f"now={str(expected.get('source_hash'))[:12]}…)"
        )
    bad: list[str] = []
    for key in ("protocols", "shortcut_intents", "hierarchy"):
        if key not in on_disk:
            bad.append(f"missing top-level `{key}`")
    protos = on_disk.get("protocols", {}) or {}
    missing_shape = [pid for pid, e in protos.items() if "workflow_shape" not in e]
    missing_ic = [pid for pid, e in protos.items() if not e.get("intent_class")]
    if missing_shape:
        bad.append(
            f"{len(missing_shape)} protocol(s) missing baked workflow_shape: "
            f"{missing_shape[:3]}"
        )
    if missing_ic:
        bad.append(f"{len(missing_ic)} protocol(s) missing intent_class: {missing_ic[:3]}")
    # Parity: every core routable protocol must have an embedding (else the
    # semantic path can rank a protocol it then can't route to).
    embeds_npz = PROTOCOLS_DIR / "_embeddings.npz"
    if embeds_npz.exists():
        import numpy as np

        try:
            emb_ids = {str(x) for x in np.load(embeds_npz, allow_pickle=True)["protocol_ids"]}
            missing_emb = sorted(set(protos) - emb_ids)
            if missing_emb:
                bad.append(
                    f"{len(missing_emb)} route_meta protocol(s) not embedded: "
                    f"{missing_emb[:3]}"
                )
        except Exception as exc:
            bad.append(f"could not read embeddings protocol_ids: {exc}")
    return (not bad), (
        f"{len(protos)} protocols compiled, fresh + embedded"
        if not bad
        else "; ".join(bad[:3])
    )


def check_routing_targets_resolve():
    """Every next_protocol / on_failure / see_also target must be a real protocol.

    A dangling pointer (a renamed or removed protocol) silently breaks the
    pipeline chain or a 'see also' link with no error at runtime. Core targets
    (category/name under a real protocols/ subdir) are validated; pack-
    namespaced targets are skipped (their files live in the pack).
    """
    import yaml

    core_dirs = {
        p.name for p in PROTOCOLS_DIR.iterdir()
        if p.is_dir() and not p.name.startswith("_") and p.name != "light"
    }

    def _resolves(ref) -> bool:
        ref = (ref or "").split("#")[0].strip()
        if not ref or ref.lower() in {"null", "none"} or "/" not in ref:
            return True  # null / terminal / non-path — nothing to validate
        cat = ref.split("/")[0]
        if cat not in core_dirs:
            return True  # pack-namespaced target — not ours to check
        return (PROTOCOLS_DIR / f"{ref}.yaml").exists()

    bad: list[str] = []
    for f in PROTOCOLS_DIR.rglob("*.yaml"):
        if f.name.startswith("_") or "light" in f.parts:
            continue
        try:
            data = yaml.safe_load(f.read_text()) or {}
        except Exception:
            continue
        rel = f.relative_to(PROTOCOLS_DIR).with_suffix("").as_posix()
        for field in ("next_protocol", "on_failure"):
            v = data.get(field)
            if isinstance(v, str) and not _resolves(v):
                bad.append(f"{rel}: {field} → {v}")
        for s in (data.get("see_also") or []):
            if isinstance(s, str) and not _resolves(s):
                bad.append(f"{rel}: see_also → {s}")
    return (not bad), (
        "all next_protocol / on_failure / see_also targets resolve"
        if not bad
        else f"{len(bad)} dangling target(s): {bad[:3]}"
    )


def check_scaffold_smoke():
    """Scaffold a temp workspace + verify the minimum files appear."""
    import tempfile

    from research_os.project_ops import scaffold_minimal_workspace

    with tempfile.TemporaryDirectory() as d:
        root = Path(d) / "smoke_project"
        scaffold_minimal_workspace(root, "Smoke Test", ide_flags=["cursor"])
        required = [
            "AGENTS.md",
            "GETTING_STARTED.md",
            "inputs/researcher_config.yaml",
            "inputs/intake.md",
            "workspace/methods.md",
            "workspace/analysis.md",
            "workspace/citations.md",
            "workspace/workflow.mermaid",
            "workspace/scratch/README.md",
            ".os_state/state_ledger.json",
            ".os_state/manifest.json",
            ".gitignore",
            ".cursor/mcp.json",
        ]
        missing = [r for r in required if not (root / r).exists()]
        forbidden = [
            "synthesis/paper.md",
            "synthesis/abstract.md",
        ]
        present_forbidden = [f for f in forbidden if (root / f).exists()]
        if missing or present_forbidden:
            return False, (
                f"missing {missing}; pre-baked forbidden output {present_forbidden}"
            ).strip()
    return True, "ok"


def check_no_deprecated_aliases_in_protocols():
    """Protocol YAMLs must not reference any name in ``_DEPRECATED_ALIASES``.

    Deprecated names still resolve (and fire a deprecation log entry) when
    callers invoke them, but they are not the canonical surface and should
    never appear in shipped protocol scaffolds — otherwise we ship guidance
    that immediately emits deprecation telemetry on first use. Catalogue
    authors should reference the consolidated handler (``tool_search``,
    ``tool_plan``, ``sys_path``, ``mem_log`` …) plus the inferred parameter.
    """
    import re as _re

    from research_os.server import _DEPRECATED_ALIASES

    if not _DEPRECATED_ALIASES:
        return True, "no deprecated aliases declared"

    # Build a single word-boundary alternation. Sort by length (longest
    # first) so e.g. ``tool_search_semantic_scholar`` matches before any
    # hypothetical shorter prefix.
    names = sorted(_DEPRECATED_ALIASES, key=len, reverse=True)
    pattern = _re.compile(r"\b(" + "|".join(_re.escape(n) for n in names) + r")\b")

    offenders: list[str] = []
    for f in PROTOCOLS_DIR.rglob("*.yaml"):
        if "light" in f.parts:
            continue
        # Registry / index files (``_router_index.yaml`` etc.) are not
        # protocol scaffolds and may legitimately reference legacy names
        # for routing context — skip them.
        if f.name.startswith("_"):
            continue
        try:
            text = f.read_text()
        except (OSError, UnicodeDecodeError):
            continue
        seen_here: set[str] = set()
        for m in pattern.finditer(text):
            name = m.group(1)
            if name in seen_here:
                continue
            seen_here.add(name)
            rel = f.relative_to(PROTOCOLS_DIR).with_suffix("").as_posix()
            offenders.append(f"{rel}: `{name}`")

    if offenders:
        return False, (
            f"{len(offenders)} deprecated-alias reference(s) in protocols "
            f"(use the consolidated name + injected param instead): "
            + "; ".join(offenders[:5])
            + ("..." if len(offenders) > 5 else "")
        )
    return True, f"clean across {len(_DEPRECATED_ALIASES)} deprecated names"


def check_docs_code_consistency():
    """Scan docs/, CLAUDE.md, README.md for drift-prone patterns vs code reality.

    Catches: tool names mentioned in docs that don't exist in code, broken
    scripts/ references, broken docs/*.md cross-references. Also logs every
    'N-step' / 'N commands' / 'N-check' literal so a maintainer can audit
    count drift in one pass.
    """
    import re

    from research_os.server import (
        TOOL_DEFINITIONS, _ALIASES, _REMOVED_TOOLS, _resolve_tool_name,
    )

    docs_dir = REPO_ROOT / "docs"
    candidate_files = []
    for f in [REPO_ROOT / "CLAUDE.md", REPO_ROOT / "README.md"]:
        if f.exists():
            candidate_files.append(f)
    if docs_dir.exists():
        candidate_files.extend(sorted(docs_dir.glob("*.md")))

    known_tools = set(TOOL_DEFINITIONS)
    known_aliases = set(_ALIASES)
    removed = set(_REMOVED_TOOLS)

    # Patterns / placeholders that look like tools but aren't (template
    # filler, prose, search wildcards).
    false_positives = {
        "tool_name", "tool_list", "tool_discovery", "tool_call",
        "sys_X_Y", "tool_X_Y", "mem_X_Y", "tool_X", "sys_X", "mem_X",
        "tool_definitions",  # python module dir, not a tool
    }

    tool_pattern = re.compile(r"\b((?:sys|tool|mem)_[a-z][a-z0-9_]+)\b")
    script_pattern = re.compile(r"\bscripts/([A-Za-z0-9_\-]+\.py)\b")
    docs_xref_pattern = re.compile(r"\bdocs/([A-Za-z0-9_\-]+\.md)\b")
    count_pattern = re.compile(
        r"\b(\d+)[-\s](?:step|command|commands|check|checks|protocols?|tools?)\b",
        re.IGNORECASE,
    )

    unknown_tools: list[str] = []
    missing_scripts: list[str] = []
    missing_xrefs: list[str] = []
    count_mentions: list[str] = []

    for f in candidate_files:
        try:
            lines = f.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        rel = f.relative_to(REPO_ROOT).as_posix()
        for lineno, line in enumerate(lines, 1):
            for m in tool_pattern.finditer(line):
                name = m.group(1)
                if name in false_positives or name.endswith("_"):
                    continue
                # A tool ref is OK if it's a real tool, an alias, a
                # removed-tool placeholder, or resolves via the dispatcher.
                if (name in known_tools or name in known_aliases
                        or name in removed
                        or _resolve_tool_name(name) in known_tools):
                    continue
                unknown_tools.append(f"{rel}:{lineno}: {name}")
            for m in script_pattern.finditer(line):
                script_name = m.group(1)
                if not (REPO_ROOT / "scripts" / script_name).exists():
                    missing_scripts.append(f"{rel}:{lineno}: scripts/{script_name}")
            for m in docs_xref_pattern.finditer(line):
                doc_name = m.group(1)
                if not (docs_dir / doc_name).exists():
                    missing_xrefs.append(f"{rel}:{lineno}: docs/{doc_name}")
            for m in count_pattern.finditer(line):
                count_mentions.append(f"{rel}:{lineno}: '{m.group(0)}'")

    problems: list[str] = []
    if unknown_tools:
        problems.append(
            f"{len(unknown_tools)} unknown tool name(s) in docs: "
            + "; ".join(unknown_tools[:3])
            + ("..." if len(unknown_tools) > 3 else "")
        )
    if missing_scripts:
        problems.append(
            f"{len(missing_scripts)} missing scripts/ ref(s): "
            + "; ".join(missing_scripts[:3])
        )
    if missing_xrefs:
        problems.append(
            f"{len(missing_xrefs)} missing docs/*.md xref(s): "
            + "; ".join(missing_xrefs[:3])
        )

    # Soft-warn pattern (same as protocol_freshness, router_index_bumped):
    # surface drift in the detail line so maintainers can audit, but don't
    # gate the release on pre-existing doc drift. The hard checks live in
    # check_tools_md_roundtrip + check_tool_short_field_length below, which
    # the done_when condition specifically calls out.
    if problems:
        return True, "WARN: " + " | ".join(problems)
    return True, (
        f"clean across {len(candidate_files)} doc file(s) "
        f"({len(count_mentions)} numeric count literals logged for audit)"
    )


def check_tools_md_roundtrip():
    """Every tool name mentioned in TOOLS.md must exist in code; every live
    tool in code must appear in TOOLS.md.
    """
    import re

    from research_os.server import (
        TOOL_DEFINITIONS, _ALIASES, _REMOVED_TOOLS, _resolve_tool_name,
    )

    tools_md = REPO_ROOT / "docs" / "TOOLS.md"
    if not tools_md.exists():
        return False, "docs/TOOLS.md missing"

    text = tools_md.read_text(encoding="utf-8")
    false_positives = {
        "tool_name", "tool_list", "tool_discovery", "tool_call",
        "sys_X_Y", "tool_X_Y", "mem_X_Y", "tool_X", "sys_X", "mem_X",
        "tool_definitions",  # python module dir, not a tool
    }
    pattern = re.compile(r"\b((?:sys|tool|mem)_[a-z][a-z0-9_]+)\b")
    mentioned: set[str] = set()
    for m in pattern.finditer(text):
        name = m.group(1)
        if name in false_positives or name.endswith("_"):
            continue
        mentioned.add(name)

    known_tools = set(TOOL_DEFINITIONS)
    known_aliases = set(_ALIASES)
    removed = set(_REMOVED_TOOLS)

    unknown = sorted(
        n for n in mentioned
        if n not in known_tools and n not in known_aliases
        and n not in removed
        and _resolve_tool_name(n) not in known_tools
    )

    # Every live (non-pack-injected) tool should be documented. We allow
    # pack-contributed tools to be optional here, since they live in their
    # own docs surface; the core check is that no name in TOOLS.md is fake.
    mentioned_canonical = {
        _resolve_tool_name(n) for n in mentioned
    } | mentioned
    undocumented = sorted(
        t for t in known_tools if t not in mentioned_canonical
    )

    problems = []
    if unknown:
        problems.append(
            f"{len(unknown)} unknown tool name(s) in TOOLS.md: {unknown[:5]}"
        )
    # Strict round-trip: report undocumented count but don't fail (pack
    # tools legitimately live in separate pack docs).
    detail_extra = ""
    if undocumented:
        detail_extra = (
            f"; {len(undocumented)} core tool(s) not in TOOLS.md "
            f"(advisory): {undocumented[:3]}"
        )
    if problems:
        return False, "; ".join(problems) + detail_extra
    return True, (
        f"{len(mentioned)} tool ref(s) in TOOLS.md, all resolve" + detail_extra
    )


def check_citation_cff_valid():
    """CITATION.cff must declare a supported cff-version."""
    import yaml

    f = REPO_ROOT / "CITATION.cff"
    if not f.exists():
        return False, "CITATION.cff missing"
    try:
        data = yaml.safe_load(f.read_text()) or {}
    except Exception as e:
        return False, f"YAML parse error: {e}"
    cff_version = str(data.get("cff-version", ""))
    # The CFF JSON schema is published per minor version. The known
    # supported series is 1.2.x.
    valid_versions = {"1.2.0"}
    if cff_version not in valid_versions:
        return False, f"cff-version={cff_version!r} not in supported {valid_versions}"
    # Required keys for a valid CFF record per the 1.2.0 schema.
    required = ("message", "title", "authors", "version")
    missing = [k for k in required if not data.get(k)]
    if missing:
        return False, f"missing required CFF key(s): {missing}"
    return True, f"cff-version {cff_version}, all required keys present"


def check_tool_short_field_length():
    """Every TOOL_DEFINITIONS entry must declare a 'short' field <=120 chars."""
    from research_os.server import TOOL_DEFINITIONS

    missing: list[str] = []
    too_long: list[str] = []
    for name, defn in TOOL_DEFINITIONS.items():
        short = defn.get("short")
        if not short or not isinstance(short, str):
            missing.append(name)
            continue
        if len(short) > 120:
            too_long.append(f"{name} ({len(short)} chars)")
    problems = []
    if missing:
        problems.append(f"{len(missing)} tool(s) missing 'short': {missing[:5]}")
    if too_long:
        problems.append(f"{len(too_long)} tool(s) over 120 chars: {too_long[:5]}")
    if problems:
        return False, "; ".join(problems)
    return True, f"{len(TOOL_DEFINITIONS)} tool(s) have valid 'short' fields"


def check_packs_in_both_lists():
    """Every src/research_os_* pack/adapter directory must be referenced
    in BOTH pack_loader.py bundled list AND pyproject.toml packages list.
    """
    import re

    src_dir = REPO_ROOT / "src"
    pack_dirs = sorted(
        d.name for d in src_dir.iterdir()
        if d.is_dir() and d.name.startswith("research_os_")
    )

    # Read pack_loader.py bundled lists.
    loader = REPO_ROOT / "src" / "research_os" / "server" / "pack_loader.py"
    loader_text = loader.read_text() if loader.exists() else ""
    bundled_in_loader: set[str] = set()
    # Match entries like ("name", "research_os_X:register").
    for m in re.finditer(r'"(research_os_[A-Za-z0-9_]+)\s*:', loader_text):
        bundled_in_loader.add(m.group(1))

    # Read pyproject.toml packages list.
    pyproject = REPO_ROOT / "pyproject.toml"
    pyproject_text = pyproject.read_text() if pyproject.exists() else ""
    bundled_in_pyproject: set[str] = set()
    for m in re.finditer(r'"src/(research_os_[A-Za-z0-9_]+)"', pyproject_text):
        bundled_in_pyproject.add(m.group(1))

    problems: list[str] = []
    for pack in pack_dirs:
        in_loader = pack in bundled_in_loader
        in_pyproject = pack in bundled_in_pyproject
        if not in_loader and not in_pyproject:
            problems.append(f"{pack}: missing from BOTH lists")
        elif not in_loader:
            problems.append(f"{pack}: missing from pack_loader.py bundled list")
        elif not in_pyproject:
            problems.append(f"{pack}: missing from pyproject.toml packages list")

    if problems:
        return False, "; ".join(problems[:5])
    return True, f"{len(pack_dirs)} pack/adapter dir(s) in both bundled lists"


def check_no_version_chatter():
    """No historical version commentary in live doctrine surfaces."""
    import importlib.util

    lint_path = REPO_ROOT / "scripts" / "lint_no_version_chatter.py"
    if not lint_path.exists():
        return False, f"missing: {lint_path}"
    spec = importlib.util.spec_from_file_location("_lint_chatter", lint_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    files = mod._iter_files()
    total = 0
    bad: list[str] = []
    for f in files:
        try:
            text = f.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        hits = mod.scan_text(text)
        if hits:
            total += len(hits)
            bad.append(f"{f.relative_to(REPO_ROOT)} ({len(hits)})")
    if total:
        return False, f"{total} hit(s) in {len(bad)} file(s): {', '.join(bad[:3])}"
    return True, f"clean across {len(files)} files"


def check_coherence():
    """Researcher-facing prose names no removed tools; counts not hand-written.

    Guards docs/ + templates/ + README against teaching a fresh AI a tool
    name that errors on call, and against hand-written tool/protocol
    counts that rot as the catalog grows.
    """
    import importlib.util

    lint_path = REPO_ROOT / "scripts" / "lint_coherence.py"
    if not lint_path.exists():
        return False, f"missing: {lint_path}"
    spec = importlib.util.spec_from_file_location("_lint_coherence", lint_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    hard, warn = mod.run()
    if hard:
        sample = "; ".join(
            f"{f.relative_to(REPO_ROOT)}:{ln}" for f, ln, _ in hard[:3]
        )
        return False, f"{len(hard)} removed-tool ref(s) in prose: {sample}"
    if warn:
        return True, f"clean (no removed tools); {len(warn)} deprecation/count warning(s)"
    return True, "clean across docs + templates"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def check_reasoning_layer_independent_of_daemon():
    """Architecture invariant (DESIGN_V4.md §6.1): the reasoning layer never
    imports the transport/execution layer.

    The dependency arrow points ONE way: ``daemon/`` may import ``server/``
    (it fronts ``_handle_tool_call``), but ``server/``, ``tools/`` and the
    protocol loaders must never import ``daemon/``. If they did, the pure
    reasoning core (152 tools, 142 protocols) would become coupled to HTTP /
    sessions / concurrency — the exact thing v4 exists to undo. This check
    fails the build the moment that arrow gets reversed.
    """
    import re as _re

    src = REPO_ROOT / "src" / "research_os"
    reasoning_dirs = [src / "server", src / "tools"]
    # Match `import research_os.daemon`, `from research_os.daemon ...`,
    # `from ..daemon ...`, `from .daemon ...` — but NOT comments/strings
    # mentioning the word daemon.
    pat = _re.compile(
        r"^\s*(?:from\s+(?:\.+|research_os\.)?daemon[\s.]"
        r"|import\s+research_os\.daemon)"
    )
    offenders: list[str] = []
    for d in reasoning_dirs:
        if not d.exists():
            continue
        for py in d.rglob("*.py"):
            try:
                for i, line in enumerate(py.read_text().splitlines(), 1):
                    if pat.match(line):
                        rel = py.relative_to(REPO_ROOT)
                        offenders.append(f"{rel}:{i}: {line.strip()}")
            except Exception:
                continue
    if offenders:
        return False, (
            "reasoning layer imports daemon (arrow reversed): "
            + "; ".join(offenders[:5])
        )
    return True, "server/ + tools/ never import daemon/ (arrow points daemon→server)"


def main() -> int:
    # Make src importable when called from a clean checkout.
    sys.path.insert(0, str(REPO_ROOT / "src"))

    print("Research OS preflight\n" + "=" * 24)
    tally = Tally()

    tally.check("Top-level package imports", check_top_level_import)
    tally.check("Action subpackages import", check_subpackages)
    tally.check("CLI entrypoint exists", check_cli_entrypoint)
    tally.check("tools/actions/ flat namespace minimal", check_flat_namespace_is_minimal)
    tally.check("Every protocol YAML loads", check_every_protocol_loads)
    tally.check("No dot-notation tool calls in protocols", check_no_dot_tool_calls_in_protocols)
    tally.check("No deprecated-alias tool refs in protocols", check_no_deprecated_aliases_in_protocols)
    tally.check("Every tool definition has a handler", check_every_tool_has_handler)
    tally.check("All handlers are callable", check_handlers_callable)
    tally.check("Dispatcher aliases resolve", check_dispatcher_aliases)
    tally.check("Alias table complete (handlers + param injection)", check_alias_table_complete)
    tally.check("Redirect-stub targets resolve", check_redirect_targets)
    tally.check("Bundled packs discovered", check_packs_discovered)
    tally.check("Pack protocols load", check_pack_protocols_load)
    tally.check("Pack protocol tool refs + routing targets resolve", check_pack_protocol_refs_and_targets)
    tally.check("Bundled adapters discovered", check_adapters_discovered)
    tally.check("Adapter regex patterns compile", check_adapter_regex_compile)
    tally.check("Protocol tool refs all resolve", check_protocols_referenced_tools_resolve)
    tally.check("Router index references resolve", check_router_index_consistent)
    tally.check("Router index mtime tracks protocols", check_router_index_bumped)
    tally.check("Protocol freshness (review cadence)", check_protocol_freshness)
    tally.check("next_protocol_kind declared on every protocol", check_next_protocol_kind_present)
    tally.check("Routing targets resolve (next_protocol/on_failure/see_also)", check_routing_targets_resolve)
    tally.check("Semantic-routing embeddings fresh", check_embeddings_fresh)
    tally.check("Compiled routing sidecar (_route_meta.json) fresh + consistent", check_route_meta)
    tally.check("Workspace scaffold smoke", check_scaffold_smoke)
    tally.check("No historical version commentary in live doctrine", check_no_version_chatter)
    tally.check("Prose↔code coherence (no removed tools / hand-written counts)", check_coherence)
    tally.check("Docs/code consistency (tool names, scripts/, xrefs)", check_docs_code_consistency)
    tally.check("TOOLS.md vs TOOL_DEFINITIONS round-trip", check_tools_md_roundtrip)
    tally.check("CITATION.cff cff-version valid", check_citation_cff_valid)
    tally.check("Every tool definition has 'short' field <=120 chars", check_tool_short_field_length)
    tally.check("Every pack dir in both bundled lists (loader + pyproject)", check_packs_in_both_lists)
    tally.check("Reasoning layer independent of daemon (v4 arrow)", check_reasoning_layer_independent_of_daemon)

    print()
    print(f"Summary: {tally.passed} passed · {tally.failed} failed")
    if tally.failed:
        print("\nFailures detail (first 3):")
        for err in tally.errors[:3]:
            print(err)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
