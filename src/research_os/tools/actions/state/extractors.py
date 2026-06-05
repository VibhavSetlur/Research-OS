"""Multi-language tools.md extractors.

Each per-language extractor returns a list of (kind, name, version_or_loc)
tuples. Kinds: 'python_import', 'r_library', 'r_bioc_install',
'r_renv', 'r_description', 'bash_module', 'bash_env', 'node_dep',
'node_import', 'rust_dep', 'rust_use', 'julia_dep', 'julia_using',
'adapter_pattern'.

The dispatcher extract_from_file(path) picks the right extractor by
file suffix; the bulk extract_from_tree(root, step_id) walks a step
tree and returns all extractions deduplicated.

Adapter contributions: active_adapter_extractors() returns
{adapter_name: ((regex_source, template), ...)} from registered
adapters; their patterns get applied to every text file as
('adapter_pattern', adapter_name, formatted_template) tuples.
"""
from __future__ import annotations

import json
import logging
import pathlib
import re

logger = logging.getLogger("research_os.extractors")


# ── Type alias for clarity ───────────────────────────────────────────
# Each extraction is (kind, name, version_or_loc) where the third
# element is None when no version / location applies.
Extraction = tuple[str, str, str | None]


# ── Python ───────────────────────────────────────────────────────────
# Anchor at line start with NO leading non-whitespace; module name must
# be ≥ 1 char but we drop tiny single-letter modules at the dispatcher
# level only where it matters (here we capture all, dedup later).
_PY_IMPORT_RE = re.compile(
    r"^\s*(?:from|import)\s+([a-zA-Z_][\w.]*)",
    re.MULTILINE,
)


def extract_python(text: str) -> list[Extraction]:
    """Parse ``import X`` / ``from X import Y`` → ``('python_import', X, None)``.

    Only the top-level package (before the first dot) is returned so
    ``import numpy.linalg`` and ``import numpy`` collapse to one entry.
    """
    out: list[Extraction] = []
    seen: set[str] = set()
    for m in _PY_IMPORT_RE.finditer(text):
        top = m.group(1).split(".", 1)[0]
        if top and top not in seen:
            seen.add(top)
            out.append(("python_import", top, None))
    return out


# ── R (scripts) ──────────────────────────────────────────────────────
# library(X), require(X), requireNamespace("X"), p_load(a, b, c),
# BiocManager::install("X" or c("a", "b"))
_R_LIBRARY_RE = re.compile(
    r"\blibrary\s*\(\s*['\"]?([a-zA-Z][\w.]*)['\"]?\s*[\),]",
)
_R_REQUIRE_RE = re.compile(
    r"\brequire\s*\(\s*['\"]?([a-zA-Z][\w.]*)['\"]?\s*[\),]",
)
_R_REQUIRENS_RE = re.compile(
    r"\brequireNamespace\s*\(\s*['\"]([a-zA-Z][\w.]*)['\"]",
)
_R_PLOAD_RE = re.compile(
    r"\bp_load\s*\(([^)]*)\)",
)
_R_BIOC_RE = re.compile(
    r"\bBiocManager::install\s*\(\s*(?:c\s*\(\s*)?([^)]+?)\)",
)
_R_NAME_TOKEN_RE = re.compile(r"['\"]?([a-zA-Z][\w.]*)['\"]?")


def extract_r(text: str) -> list[Extraction]:
    """Parse ``library(X)`` / ``require(X)`` / ``p_load(...)`` etc.

    BiocManager::install(...) entries are tagged ``r_bioc_install``;
    everything else is ``r_library``.
    """
    out: list[Extraction] = []
    seen: set[tuple[str, str]] = set()

    def _add(kind: str, name: str) -> None:
        key = (kind, name)
        if name and key not in seen:
            seen.add(key)
            out.append((kind, name, None))

    for m in _R_LIBRARY_RE.finditer(text):
        _add("r_library", m.group(1))
    for m in _R_REQUIRE_RE.finditer(text):
        _add("r_library", m.group(1))
    for m in _R_REQUIRENS_RE.finditer(text):
        _add("r_library", m.group(1))
    # p_load takes a comma-separated bag of bare names (pacman convention).
    for m in _R_PLOAD_RE.finditer(text):
        bag = m.group(1)
        for tok in re.split(r"[,\s]+", bag):
            tok = tok.strip().strip("'\"")
            if tok and re.match(r"^[a-zA-Z][\w.]*$", tok):
                _add("r_library", tok)
    # BiocManager::install("X") or BiocManager::install(c("a", "b")).
    for m in _R_BIOC_RE.finditer(text):
        bag = m.group(1)
        for tm in _R_NAME_TOKEN_RE.finditer(bag):
            name = tm.group(1)
            if name and name != "c":
                _add("r_bioc_install", name)
    return out


# ── R DESCRIPTION file ───────────────────────────────────────────────
# Imports / Depends / Suggests / LinkingTo blocks may span multiple
# lines; entries are comma-separated and may carry version specs in
# parens, e.g. ``ggplot2 (>= 3.4.0)``.
_R_DESC_BLOCK_RE = re.compile(
    r"^(Imports|Depends|Suggests|LinkingTo)\s*:\s*(.+?)(?=^[A-Z][\w-]*\s*:|\Z)",
    re.MULTILINE | re.DOTALL,
)
_R_DESC_ENTRY_RE = re.compile(
    r"([a-zA-Z][\w.]*)\s*(?:\(([^)]*)\))?",
)


def extract_r_description(text: str) -> list[Extraction]:
    """Parse an R DESCRIPTION file's Imports/Depends/Suggests/LinkingTo.

    Returns ``('r_description', name, version_spec)`` tuples (the
    version spec is ``None`` when absent).
    """
    out: list[Extraction] = []
    seen: set[tuple[str, str | None]] = set()
    for block in _R_DESC_BLOCK_RE.finditer(text):
        body = block.group(2)
        # Split on commas after collapsing the block's continuation
        # lines (DESCRIPTION uses leading-whitespace continuation).
        body_flat = re.sub(r"\s+", " ", body)
        for entry in body_flat.split(","):
            entry = entry.strip()
            if not entry:
                continue
            m = _R_DESC_ENTRY_RE.match(entry)
            if not m:
                continue
            name = m.group(1)
            ver = (m.group(2) or "").strip() or None
            # R-base / methods etc. are real entries; keep them — the
            # filter is best left to the caller / renderer.
            key = (name, ver)
            if key in seen:
                continue
            seen.add(key)
            out.append(("r_description", name, ver))
    return out


# ── renv.lock (JSON) ─────────────────────────────────────────────────
def extract_r_renv_lock(text: str) -> list[Extraction]:
    """Walk an ``renv.lock`` JSON file's ``Packages.*`` entries.

    Returns ``('r_renv', name, Version)`` tuples.
    """
    out: list[Extraction] = []
    try:
        data = json.loads(text)
    except (ValueError, TypeError) as e:
        logger.debug("renv.lock JSON parse failed: %s", e)
        return out
    packages = (data or {}).get("Packages") or {}
    if not isinstance(packages, dict):
        return out
    seen: set[tuple[str, str | None]] = set()
    for name, info in packages.items():
        if not isinstance(name, str) or not name:
            continue
        version: str | None = None
        if isinstance(info, dict):
            v = info.get("Version")
            if isinstance(v, str) and v:
                version = v
        key = (name, version)
        if key in seen:
            continue
        seen.add(key)
        out.append(("r_renv", name, version))
    return out


# ── Bash / shell ─────────────────────────────────────────────────────
# `module load X/Y/Z` (one or more modules per line, space-separated).
_BASH_MODULE_RE = re.compile(
    r"^\s*module\s+(?:load|add)\s+(.+?)\s*(?:#.*)?$",
    re.MULTILINE,
)
_BASH_CONDA_RE = re.compile(
    r"\bconda\s+activate\s+([\w./\-]+)",
)
_BASH_VENV_RE = re.compile(
    r"\bsource\s+([\w./\-]+?)/bin/activate\b",
)


def extract_bash_modules(text: str) -> list[Extraction]:
    """Parse HPC ``module load`` lines + conda/venv activation commands.

    ``module load gcc/11.2 cuda/12.1`` → two ``bash_module`` entries.
    ``conda activate my-env``         → ``('bash_env', 'conda:my-env', None)``.
    ``source ~/venvs/x/bin/activate`` → ``('bash_env', 'venv:~/venvs/x', None)``.
    """
    out: list[Extraction] = []
    seen: set[tuple[str, str]] = set()

    def _add(kind: str, name: str) -> None:
        key = (kind, name)
        if name and key not in seen:
            seen.add(key)
            out.append((kind, name, None))

    for m in _BASH_MODULE_RE.finditer(text):
        rest = m.group(1).strip()
        # Trailing inline comments already stripped by the regex; split
        # remaining tokens on whitespace so multi-module loads work.
        for tok in rest.split():
            tok = tok.strip()
            if not tok or tok.startswith("-"):
                continue
            _add("bash_module", tok)
    for m in _BASH_CONDA_RE.finditer(text):
        env_name = m.group(1).strip()
        _add("bash_env", f"conda:{env_name}")
    for m in _BASH_VENV_RE.finditer(text):
        venv_path = m.group(1).strip()
        _add("bash_env", f"venv:{venv_path}")
    return out


# ── Node / JS / TS ───────────────────────────────────────────────────
_NODE_IMPORT_RE = re.compile(
    r"""
    (?:^|\s)
    (?:
        import\s+(?:[^'"]+?\s+from\s+)?['"]([^'"]+)['"]
      | require\s*\(\s*['"]([^'"]+)['"]\s*\)
    )
    """,
    re.VERBOSE | re.MULTILINE,
)


def _node_top_pkg(spec: str) -> str | None:
    """Reduce an import specifier to the npm package name.

    ``@scope/pkg/sub`` → ``@scope/pkg``; ``react-dom/server`` → ``react-dom``;
    relative imports (``./foo``, ``../bar``, ``/abs``) → ``None``.
    """
    if not spec or spec.startswith(".") or spec.startswith("/"):
        return None
    if spec.startswith("@"):
        parts = spec.split("/", 2)
        if len(parts) >= 2:
            return "/".join(parts[:2])
        return None
    return spec.split("/", 1)[0]


def extract_node(text: str, *, is_package_json: bool = False) -> list[Extraction]:
    """Parse Node imports or a ``package.json`` dependency map.

    * ``is_package_json=True``: ``('node_dep', name, version_spec)``.
    * Otherwise: ``import``/``require`` statements → ``('node_import', name, None)``.
    """
    out: list[Extraction] = []
    if is_package_json:
        try:
            data = json.loads(text)
        except (ValueError, TypeError) as e:
            logger.debug("package.json parse failed: %s", e)
            return out
        seen: set[tuple[str, str | None]] = set()
        for field in ("dependencies", "devDependencies",
                      "peerDependencies", "optionalDependencies"):
            block = (data or {}).get(field) or {}
            if not isinstance(block, dict):
                continue
            for name, ver in block.items():
                if not isinstance(name, str) or not name:
                    continue
                ver_s = ver if isinstance(ver, str) else None
                key = (name, ver_s)
                if key in seen:
                    continue
                seen.add(key)
                out.append(("node_dep", name, ver_s))
        return out

    seen_im: set[str] = set()
    for m in _NODE_IMPORT_RE.finditer(text):
        spec = m.group(1) or m.group(2) or ""
        pkg = _node_top_pkg(spec)
        if pkg and pkg not in seen_im:
            seen_im.add(pkg)
            out.append(("node_import", pkg, None))
    return out


# ── Rust ──────────────────────────────────────────────────────────────
# Cargo.toml [dependencies] block — entries look like:
#   serde = "1.0"
#   tokio = { version = "1", features = ["full"] }
#   anyhow.workspace = true
_RUST_SECTION_RE = re.compile(
    r"^\s*\[(?P<section>[\w.-]+)\]\s*$",
    re.MULTILINE,
)
_RUST_DEP_LINE_RE = re.compile(
    r"^\s*(?P<name>[a-zA-Z_][\w-]*)\s*=\s*(?P<rest>.+?)\s*$",
    re.MULTILINE,
)
_RUST_USE_RE = re.compile(
    r"^\s*(?:pub\s+)?use\s+([a-zA-Z_][\w]*)",
    re.MULTILINE,
)


def _rust_version_from_value(value: str) -> str | None:
    """Pull a version string out of a Cargo.toml RHS.

    Handles ``"1.2"``, ``{ version = "1.2", ... }``, and table forms;
    returns None when no version literal is present (workspace = true,
    git = "...", path = "...", etc.).
    """
    value = value.strip()
    # Plain string literal: serde = "1.0"
    m = re.fullmatch(r'["\']([^"\']+)["\']', value)
    if m:
        return m.group(1)
    # Inline table: { version = "1.2", features = [...] }
    if value.startswith("{"):
        vm = re.search(r'version\s*=\s*["\']([^"\']+)["\']', value)
        if vm:
            return vm.group(1)
    return None


def extract_rust(text: str, *, is_cargo_toml: bool = False) -> list[Extraction]:
    """Parse Cargo.toml dependencies or ``use`` statements in ``.rs`` files.

    * ``is_cargo_toml=True``: scans ``[dependencies]`` / ``[dev-dependencies]``
      / ``[build-dependencies]`` blocks → ``('rust_dep', name, version_spec)``.
    * Otherwise: top-level ``use`` statements → ``('rust_use', crate_root, None)``.
    """
    out: list[Extraction] = []
    if is_cargo_toml:
        # Walk section markers and capture dep lines under any of the
        # canonical dependency sections.
        dep_sections = {
            "dependencies", "dev-dependencies", "build-dependencies",
        }
        # Find every section header and its byte span.
        headers: list[tuple[str, int, int]] = []
        matches = list(_RUST_SECTION_RE.finditer(text))
        for i, m in enumerate(matches):
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            headers.append((m.group("section"), start, end))
        seen: set[tuple[str, str | None]] = set()
        for section, start, end in headers:
            # Allow sub-sections like [dependencies.foo] = treat the
            # foo as a dep with no captured version (the table sets it).
            if section in dep_sections:
                block = text[start:end]
                for dm in _RUST_DEP_LINE_RE.finditer(block):
                    name = dm.group("name")
                    rest = dm.group("rest")
                    if not name or name.startswith("#"):
                        continue
                    ver = _rust_version_from_value(rest)
                    key = (name, ver)
                    if key in seen:
                        continue
                    seen.add(key)
                    out.append(("rust_dep", name, ver))
            elif section.startswith(
                ("dependencies.", "dev-dependencies.", "build-dependencies."),
            ):
                # [dependencies.serde] subtable form.
                name = section.split(".", 1)[1]
                # Pull a version out of the subtable if present.
                ver = None
                vm = re.search(
                    r'^\s*version\s*=\s*["\']([^"\']+)["\']',
                    text[start:end], re.MULTILINE,
                )
                if vm:
                    ver = vm.group(1)
                key = (name, ver)
                if name and key not in seen:
                    seen.add(key)
                    out.append(("rust_dep", name, ver))
        return out

    seen_u: set[str] = set()
    for m in _RUST_USE_RE.finditer(text):
        crate = m.group(1)
        # Skip language keywords that look like crate roots in `use`.
        if crate in {"crate", "self", "super"}:
            continue
        if crate and crate not in seen_u:
            seen_u.add(crate)
            out.append(("rust_use", crate, None))
    return out


# ── Julia ─────────────────────────────────────────────────────────────
# Project.toml [deps] is a flat name → uuid map. [compat] gives version
# bounds; we attach those when present, else fall back to the uuid so
# callers always have something in the third slot.
_JULIA_SECTION_RE = re.compile(
    r"^\s*\[(?P<section>[\w-]+)\]\s*$",
    re.MULTILINE,
)
_JULIA_KV_RE = re.compile(
    r"""^\s*(?P<name>[a-zA-Z_][\w]*)\s*=\s*["']([^"']*)["']""",
    re.MULTILINE,
)
_JULIA_USING_RE = re.compile(
    r"^\s*(?:using|import)\s+([a-zA-Z_][\w]*)",
    re.MULTILINE,
)


def extract_julia(text: str, *, is_project_toml: bool = False) -> list[Extraction]:
    """Parse a Project.toml ``[deps]`` table or ``using``/``import`` statements.

    * ``is_project_toml=True``: ``('julia_dep', name, uuid_or_version)``.
    * Otherwise: ``using X`` / ``import X`` → ``('julia_using', name, None)``.
    """
    out: list[Extraction] = []
    if is_project_toml:
        # Find section spans.
        headers: list[tuple[str, int, int]] = []
        matches = list(_JULIA_SECTION_RE.finditer(text))
        for i, m in enumerate(matches):
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            headers.append((m.group("section"), start, end))
        deps: dict[str, str | None] = {}
        compats: dict[str, str] = {}
        for section, start, end in headers:
            block = text[start:end]
            if section == "deps":
                for km in _JULIA_KV_RE.finditer(block):
                    deps[km.group("name")] = km.group(2) or None
            elif section == "compat":
                for km in _JULIA_KV_RE.finditer(block):
                    compats[km.group("name")] = km.group(2)
        seen: set[tuple[str, str | None]] = set()
        for name, uuid in deps.items():
            ver = compats.get(name) or uuid
            key = (name, ver)
            if key in seen:
                continue
            seen.add(key)
            out.append(("julia_dep", name, ver))
        return out

    seen_u: set[str] = set()
    for m in _JULIA_USING_RE.finditer(text):
        name = m.group(1)
        if name and name not in seen_u:
            seen_u.add(name)
            out.append(("julia_using", name, None))
    return out


# ── Adapter-contributed patterns ─────────────────────────────────────
def extract_adapter_patterns(text: str) -> list[Extraction]:
    """Apply every active adapter's tools_md regex patterns to ``text``.

    Each registered ``(regex_source, template)`` pair from
    :func:`research_os.adapters.loader.active_adapter_extractors` is
    applied; matches yield ``('adapter_pattern', adapter_name, formatted_template)``
    tuples. The template may reference capture groups via ``{0}``, ``{1}``, …
    """
    out: list[Extraction] = []
    try:
        from research_os.adapters.loader import active_adapter_extractors
    except Exception as e:
        logger.debug("adapter loader unavailable: %s", e)
        return out
    try:
        adapter_map = active_adapter_extractors()
    except Exception as e:
        logger.debug("active_adapter_extractors() failed: %s", e)
        return out
    seen: set[tuple[str, str, str]] = set()
    for adapter_name, patterns in (adapter_map or {}).items():
        for pat_source, template in patterns or ():
            try:
                regex = re.compile(pat_source)
            except re.error as e:
                logger.debug(
                    "adapter %s: bad regex %r: %s", adapter_name, pat_source, e,
                )
                continue
            for m in regex.finditer(text):
                groups = m.groups()
                try:
                    formatted = template.format(*groups, **(m.groupdict() or {}))
                except (IndexError, KeyError) as e:
                    logger.debug(
                        "adapter %s: template %r format failed: %s",
                        adapter_name, template, e,
                    )
                    formatted = template
                key = ("adapter_pattern", adapter_name, formatted)
                if key in seen:
                    continue
                seen.add(key)
                out.append(("adapter_pattern", adapter_name, formatted))
    return out


# ── Per-file dispatch ────────────────────────────────────────────────
# Suffix lookups are lower-cased; bare names (DESCRIPTION, Cargo.toml,
# Project.toml, renv.lock, package.json) are matched by exact basename.
_SUFFIX_DISPATCH: dict[str, str] = {
    ".py": "python",
    ".r": "r",
    ".sh": "bash",
    ".bash": "bash",
    ".js": "node",
    ".ts": "node",
    ".mjs": "node",
    ".cjs": "node",
    ".tsx": "node",
    ".jsx": "node",
    ".rs": "rust",
    ".jl": "julia",
}

# Filenames (case-sensitive matches against `path.name`) that pin a
# specific extractor regardless of suffix.
_FILENAME_DISPATCH: dict[str, str] = {
    "DESCRIPTION": "r_description",
    "renv.lock": "r_renv_lock",
    "package.json": "package_json",
    "Cargo.toml": "cargo_toml",
    "Project.toml": "project_toml",
}


def _safe_read_text(path: pathlib.Path) -> str | None:
    """Read ``path`` defensively — never raise."""
    try:
        return path.read_text(errors="ignore")
    except (OSError, UnicodeError) as e:
        logger.debug("read failed for %s: %s", path, e)
        return None


def extract_from_file(path: pathlib.Path) -> list[Extraction]:
    """Pick the right extractor(s) by suffix / filename and run them.

    Adapter regex patterns are ALWAYS applied on top of any language
    extraction so HPC ``module load`` patterns (or any adapter custom
    matcher) catch hits in mixed-content files like shell scripts.
    """
    out: list[Extraction] = []
    if path is None:
        return out
    try:
        if not path.is_file():
            return out
    except OSError as e:
        logger.debug("is_file() failed for %s: %s", path, e)
        return out

    text = _safe_read_text(path)
    if text is None:
        return out

    # Filename-based dispatch wins over suffix (Cargo.toml, etc.).
    extractor_key: str | None = _FILENAME_DISPATCH.get(path.name)
    if extractor_key is None:
        # Special-case .DESCRIPTION (some repos use a dotted extension).
        suffix = path.suffix.lower()
        if path.name == ".DESCRIPTION":
            extractor_key = "r_description"
        else:
            extractor_key = _SUFFIX_DISPATCH.get(suffix)

    try:
        if extractor_key == "python":
            out.extend(extract_python(text))
        elif extractor_key == "r":
            out.extend(extract_r(text))
        elif extractor_key == "r_description":
            out.extend(extract_r_description(text))
        elif extractor_key == "r_renv_lock":
            out.extend(extract_r_renv_lock(text))
        elif extractor_key == "bash":
            out.extend(extract_bash_modules(text))
        elif extractor_key == "node":
            out.extend(extract_node(text))
        elif extractor_key == "package_json":
            out.extend(extract_node(text, is_package_json=True))
        elif extractor_key == "cargo_toml":
            out.extend(extract_rust(text, is_cargo_toml=True))
        elif extractor_key == "rust" or path.suffix.lower() == ".rs":
            out.extend(extract_rust(text))
        elif extractor_key == "project_toml":
            out.extend(extract_julia(text, is_project_toml=True))
        elif extractor_key == "julia":
            out.extend(extract_julia(text))
    except Exception as e:
        logger.debug(
            "language extractor %s failed on %s: %s",
            extractor_key, path, e,
        )

    # Adapter patterns are applied on EVERY text file we managed to read.
    try:
        out.extend(extract_adapter_patterns(text))
    except Exception as e:
        logger.debug("adapter patterns failed on %s: %s", path, e)

    return out


# ── Tree walk ────────────────────────────────────────────────────────
# Directory names we never recurse into — caches, vendored junk, and
# generated artefacts that would otherwise drown the signal.
_SKIP_DIRS = {
    ".git", ".hg", ".svn",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "node_modules", ".venv", "venv", "env", ".tox",
    "target", "build", "dist", ".cargo",
    ".ipynb_checkpoints",
}


def extract_from_tree(
    root: pathlib.Path,
    step_id: str | None = None,
) -> list[Extraction]:
    """Walk ``workspace/<step_id>/`` (or all of ``workspace/`` if ``step_id``
    is None) and aggregate extractions across every supported file.

    The result is deduplicated on the full ``(kind, name, version)``
    tuple and returned sorted for stable output.
    """
    out: list[Extraction] = []
    if root is None:
        return out

    workspace = root / "workspace" if (root / "workspace").exists() else root
    target: pathlib.Path
    if step_id:
        target = workspace / step_id
        if not target.exists() or not target.is_dir():
            logger.debug("extract_from_tree: %s not a directory", target)
            return out
    else:
        target = workspace
        if not target.exists() or not target.is_dir():
            logger.debug("extract_from_tree: %s not a directory", target)
            return out

    seen: set[Extraction] = set()
    try:
        walker = _iter_files(target)
    except Exception as e:
        logger.debug("tree walk failed for %s: %s", target, e)
        return out

    for f in walker:
        try:
            for hit in extract_from_file(f):
                if hit not in seen:
                    seen.add(hit)
                    out.append(hit)
        except Exception as e:
            logger.debug("extract_from_file failed on %s: %s", f, e)

    # Stable order: by kind, then name, then version (None sorts first).
    out.sort(key=lambda t: (t[0], t[1], t[2] or ""))
    return out


def _iter_files(root: pathlib.Path):
    """Yield every regular file under ``root``, skipping noisy dirs."""
    stack: list[pathlib.Path] = [root]
    while stack:
        d = stack.pop()
        try:
            children = list(d.iterdir())
        except OSError as e:
            logger.debug("iterdir failed for %s: %s", d, e)
            continue
        for child in children:
            try:
                if child.is_symlink():
                    # Don't follow symlinks — they may point outside the
                    # tree and create cycles.
                    continue
                if child.is_dir():
                    if child.name in _SKIP_DIRS or child.name.startswith("."):
                        # Hidden + caches are pruned. (We allow hidden
                        # files at any level, just not hidden dirs.)
                        if child.name in _SKIP_DIRS:
                            continue
                        # Permit dotted dirs that are NOT in skip list.
                        if child.name.startswith(".") and child.name not in _SKIP_DIRS:
                            # Still skip — too noisy and rarely useful.
                            continue
                    stack.append(child)
                elif child.is_file():
                    yield child
            except OSError as e:
                logger.debug("stat failed for %s: %s", child, e)
                continue
