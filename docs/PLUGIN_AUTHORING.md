# Authoring a Research-OS protocol pack

This guide is for third parties (research labs, domain communities,
methodology specialists) who want to ship their own protocol pack
without forking the Research-OS core repo.

A pack contributes some combination of:

* **Protocols** — YAML files under a `protocols/` subtree, addressable
  via the `<pack>/<category>/<name>` namespace.
* **Tools** — Python callables exposed through the MCP dispatcher
  as `tool_<pack>_<name>`.
* **Router entries** — trigger phrases + decompositions merged into
  the core router index so `tool_route` picks up the pack's
  protocols automatically.
* **Domain detector** — a function that scans a project's `inputs/`
  and returns a confidence score that the project belongs to your
  pack's domain (`tool_intake_autofill` consults this).

Five packs ship in-tree with the core wheel as worked examples:

* `src/research_os_humanities/` — close-reading, archival, theory pack.
* `src/research_os_qualitative/` — interview coding + thematic analysis.
* `src/research_os_theory_math/` — proof-shaped paper schema + lemma tracking.
* `src/research_os_wet_lab/` — bench protocols + sample tracking + assay QC.
* `src/research_os_engineering/` — benchmark runs + ablation matrices.

Six adapter packs ship in-tree too (`slurm`, `nextflow`, `snakemake`,
`cytoscape`, `redcap`, `synapse`) — read those to see how a pack
bridges Research OS to an external system. You can use any of the
above as a complete template.

## 1. Project layout

```
my-research-os-pack/
├── pyproject.toml
├── README.md
└── src/
    └── research_os_mypack/
        ├── __init__.py            # exposes register()
        ├── tools.py               # @register_tool-decorated handlers
        ├── detector.py            # detect_mypack(inputs_dir) -> dict
        ├── router_entries.py      # MYPACK_ROUTER_ENTRIES dict
        └── protocols/
            ├── <category>/
            │   └── <name>.yaml
            └── …
```

The Python package name must match the import path: `research_os_<pack>`.

## 2. Register the pack via an entry point

`pyproject.toml`:

```toml
[project]
name = "research-os-mypack"
version = "0.1.0"
dependencies = ["research-os>=1.7.0"]

[project.entry-points."research_os.protocol_pack"]
mypack = "research_os_mypack:register"
```

The `:register` part names the callable Research-OS will invoke at
server startup. It must return a `PackRegistration`.

## 3. The `register()` callable

```python
# src/research_os_mypack/__init__.py
from pathlib import Path

from research_os.plugins import PackRegistration, captured_tools
from research_os_mypack import tools as _tools  # noqa: F401 — load decorators
from research_os_mypack.detector import detect_mypack
from research_os_mypack.router_entries import MYPACK_ROUTER_ENTRIES

__version__ = "0.1.0"
_PROTOCOLS_DIR = Path(__file__).parent / "protocols"


def register() -> PackRegistration:
    return PackRegistration(
        name="mypack",                         # lowercase, alphanumeric + underscores
        version=__version__,
        protocols_dir=_PROTOCOLS_DIR,
        tools=captured_tools(_tools.__name__),
        router_entries=MYPACK_ROUTER_ENTRIES,
        domain_detector=detect_mypack,
        description="One-line summary shown in sys_packs_installed.",
    )
```

## 4. Authoring tools with `@register_tool`

```python
# src/research_os_mypack/tools.py
from research_os.plugins import register_tool

@register_tool(
    "tool_mypack_my_action",                   # MUST start with tool_<pack>_
    schema={
        "type": "object",
        "properties": {
            "subject": {"type": "string"},
            "depth":   {"type": "integer"},
        },
        "required": ["subject"],
    },
    description="One-paragraph human-readable description of what the tool does.",
)
def my_action(name, arguments, root):
    """The dispatcher passes (name, arguments, root) to your handler.

    `name` is the resolved tool name; `arguments` is the args dict
    from the MCP call; `root` is a Path to the project directory.

    Return a list[TextContent] (or anything `_text()` would have
    handled — your envelope must be `{"status": "success"|"error", ...}`).

    Preferred: build the envelope with the core helpers so it conforms
    to the v2.1.0 envelope (CONTRACT A.6.1) on the way out — every
    field (`payload`, `audit_findings`, `next_recommended_call`,
    `tier_transition`, `tokens_estimate`, `ro_version`) is populated
    for you:

        from research_os.server.envelopes import _success, _error, _text

        return _text(_success({"hello": "world"},
                              next_recommended_call="tool_x(args=...)"))

    Legacy `{"status": "success", "data": {...}}` returns still work —
    the dispatcher upgrades them via `_normalize_envelope` — but new
    code should call `_success` / `_error` directly.
    """
    ...
```

The decorator captures the tool in a module-level registry. The
pack's `register()` function pulls the captured tools via
`captured_tools(_tools.__name__)`.

## 5. Authoring protocols

Each YAML under `protocols/<category>/<name>.yaml` is loaded under
the fully-qualified name `<pack>/<category>/<name>`. Required fields
match the core protocol contract — see
[`docs/PROTOCOL_DOCTRINE.md`](PROTOCOL_DOCTRINE.md):

```yaml
id: my_protocol_id
name: Pack — Name (audience-tailored)
version: '0.1.0'
schema_version: '2.0'
last_reviewed: '2026-06-04'
description: |
  Multi-paragraph free-form description.
trigger: |
  Researcher says any of: "phrase 1", "phrase 2".
prerequisites:
  - At least one input file exists.
editorial_voice:
  mode: hybrid
  rules:
    - "Opinionated rule capturing the discipline's epistemic standard."
steps:
  - id: step_one
    name: Step name
    description: |
      Practical guidance; reference real Research-OS tool names.
expected_outputs:
  - workspace/output.md
next_protocol: null
on_failure: null
```

**Anti-patterns** (every protocol reviewer rejects on sight):

* Hardcoded thresholds with no justification.
* Canned step sequences with no branch points.
* "Pick from this menu" without naming the trade-offs of each option.
* Marketing language. AI-tone. Em dashes everywhere.

## 6. Router entries

```python
# src/research_os_mypack/router_entries.py
MYPACK_ROUTER_ENTRIES = {
    "mypack/<category>/<name>": {            # MUST start with mypack/
        "intent_class": "methodology",       # one of the core L1 classes
        "sub_intent": "method_pick",
        "summary": "One-line shown in alternatives.",
        "triggers": [
            "trigger phrase 1",
            "trigger phrase 2",
        ],
        "shortcut_tool": "tool_mypack_my_action",   # optional
        "token_estimate": 1500,
        "decomposition": [
            {"tool": "tool_mypack_my_action",
             "purpose": "Scaffold the deliverable."},
            {"protocol": "mypack/<category>/<name>",
             "purpose": "Walk the full loop."},
        ],
    },
}
```

The plugin loader merges these into the core router index at server
startup so `tool_route` picks up pack protocols by trigger phrase.

## 7. Domain detector (optional)

```python
# src/research_os_mypack/detector.py
from pathlib import Path

def detect_mypack(inputs_dir: Path) -> dict:
    """Inspect inputs/ for mypack signals; return confidence + signals."""
    if not inputs_dir.exists():
        return {"pack": "mypack", "confidence": 0.0, "signals": []}
    # ... scan files; collect signals ...
    score = 0.5  # in [0,1]
    return {
        "pack": "mypack",
        "confidence": round(score, 3),
        "signals": ["found X", "found Y"],
    }
```

`tool_intake_autofill` consults every installed pack's detector when
the core detector is uncertain about the project's domain.

## 8. Testing your pack

```python
def test_my_pack_registers():
    from research_os.plugins import discover_packs, installed_packs
    discover_packs(bundled=[("mypack", "research_os_mypack:register")])
    names = {p["name"] for p in installed_packs()}
    assert "mypack" in names

def test_my_pack_tool_dispatches(tmp_path):
    # Force a fresh server load so the dispatcher picks up your pack tools.
    import sys
    for m in list(sys.modules):
        if m.startswith("research_os"):
            del sys.modules[m]
    import research_os.server as srv
    r = srv._handle_tool_call("tool_mypack_my_action", {"subject": "x"}, tmp_path)
    ...
```

## 9. Namespace rules (enforced by the loader)

* Pack name: lowercase alphanumeric (underscores allowed); 2-32 chars.
* Tool names: must start with `tool_<pack>_`.
* Router entry keys: must start with `<pack>/`.
* Protocols: live under `protocols/<category>/<name>.yaml`; addressable as
  `<pack>/<category>/<name>`.
* Tool-name collisions with core (or another pack) cause registration to
  fail loudly — the loader writes the traceback to
  `workspace/logs/pack_errors.log` and skips your pack so others continue.

## 10. Releasing your pack

```bash
# Bump version in pyproject.toml + __init__.py
python -m build
twine upload dist/research_os_mypack-*.whl
```

End users:

```bash
pip install research-os research-os-mypack
research-os start
```

The MCP server discovers your pack via the `research_os.protocol_pack`
entry-point group on next start; no further configuration.

## 11. Reference

* [`pack_api.py`](https://github.com/VibhavSetlur/Research-OS/blob/main/src/research_os/plugins/pack_api.py)
  — `PackRegistration`, `register_tool`, `captured_tools`.
* [`loader.py`](https://github.com/VibhavSetlur/Research-OS/blob/main/src/research_os/plugins/loader.py)
  — discovery + namespace validation + merge.
* [`research_os_humanities/`](https://github.com/VibhavSetlur/Research-OS/tree/main/src/research_os_humanities)
  — full worked example: 8 protocols + 3 tools + detector + router entries.

## 12. Returning the v2.1.0 envelope

Every Research-OS tool — core, pack, or adapter — returns the v2.1.0
envelope (CONTRACT A.6.1). It has nine fields: `status`, `payload`,
`data` (deprecated v2.2.0+), `audit_findings`, `next_recommended_call`,
`tier_transition`, `tokens_estimate`, `ro_version`, and (on errors)
`error`. The `payload` is your tool's actual return value; everything
else is wiring the dispatcher uses to route the AI's next call.

Use `_success`, `_error`, and `RoError` from
`research_os.server.envelopes` and `research_os.server.errors` —
they auto-populate every field with safe defaults, so you don't have
to remember the shape.

```python
# src/research_os_mypack/tools.py
from research_os.plugins import register_tool
from research_os.server.envelopes import _success, _error, _text
from research_os.server.errors import RoError, did_you_mean


@register_tool(
    "tool_mypack_lookup",
    schema={
        "type": "object",
        "properties": {"subject_id": {"type": "string"}},
        "required": ["subject_id"],
    },
    description="Look up a subject by id; emits the v2.1.0 envelope.",
)
def lookup(name, arguments, root):
    subject_id = (arguments.get("subject_id") or "").strip()
    if not subject_id:
        # WHAT / WHY / NEXT — composed sentence + structured payload.
        return _text(_error(
            what="subject_id is required",
            why="the caller passed an empty string",
            next_action="re-call with a non-empty `subject_id` from `mem_subjects_list`",
        ))

    known = _load_known_subject_ids(root)
    if subject_id not in known:
        # Use RoError when an inner layer raises and an outer one
        # translates to an envelope. The dispatcher catches it
        # automatically; here we render it ourselves for clarity.
        suggestions = did_you_mean(subject_id, known)
        suggestion_text = (
            f"did you mean: {', '.join(suggestions)}?"
            if suggestions else "see `mem_subjects_list` for valid ids"
        )
        raise RoError(
            f"subject '{subject_id}' not found",
            why="no matching record in workspace/subjects/",
            next_action=suggestion_text,
        )

    record = _read_subject_record(root, subject_id)
    # `_success` auto-derives `tokens_estimate` from len(json.dumps(payload))//4,
    # fills `ro_version`, and defaults `audit_findings=[]`. Pass explicit
    # kwargs for `next_recommended_call` and `tier_transition` when relevant.
    return _text(_success(
        record,
        next_recommended_call=f"tool_mypack_annotate(subject_id='{subject_id}')",
        tier_transition="intake -> draft" if record["complete"] else None,
    ))
```

Notes:

* The dispatcher funnels every handler result through
  `_normalize_envelope`, so legacy `{"status": "success", "data": {...}}`
  returns still work — but new code should call `_success` / `_error`
  directly to get every envelope field populated.
* `next_recommended_call` should be a literal next-call string the AI
  can dispatch verbatim (e.g. `"tool_x(arg='value')"`) — the same
  contract `tool_route` uses for `recommended_action`.
* `tier_transition` is `"tier_a -> tier_b"` when your tool advanced
  the project across a pipeline boundary (intake → draft, draft →
  audit, audit → synthesis). Leave it `None` otherwise.
* `audit_findings` is a list of `{severity, code, message}` dicts.
  Emit BLOCKer-severity findings only when the tool genuinely failed
  a gate; CAUTION / CONSIDERATION are fine for soft warnings.

## 13. Authoring an infrastructure adapter

Adapters are pluggable detectors + provenance-extractors for infra
the research project uses **around** its code: HPC schedulers (Slurm,
PBS), workflow engines (Snakemake, Nextflow), analysis platforms
(Cytoscape), data systems (REDCap, Synapse). They live in a separate
entry-point group from protocol packs — `research_os.adapter` vs.
`research_os.protocol_pack` — so the two registries never
cross-contaminate.

Six adapters ship in-tree as worked examples:
`src/research_os_adapter_slurm/`, `…_nextflow/`, `…_snakemake/`,
`…_cytoscape/`, `…_redcap/`, `…_synapse/`. The Slurm adapter is the
worked example below.

### Layout

```
research-os-adapter-myinfra/
├── pyproject.toml
├── README.md
└── src/
    └── research_os_adapter_myinfra/
        └── __init__.py            # exposes register()
```

Single-file adapters are the norm — detect / extract / describe /
optional tools all fit in one module. Larger adapters can split
into `detector.py` / `extract.py` / `handlers/` as they grow.

### Entry-point group: `research_os.adapter`

`pyproject.toml`:

```toml
[project]
name = "research-os-adapter-myinfra"
version = "0.1.0"
dependencies = ["research-os>=1.8.0"]

[project.entry-points."research_os.adapter"]
myinfra = "research_os_adapter_myinfra:register"
```

The group name is **`research_os.adapter`** (singular) — distinct
from `research_os.protocol_pack`. The MCP server walks both groups
at startup via `discover_adapters()` / `discover_packs()`.

### `register_adapter` signature

`register()` returns an `AdapterRegistration`. The canonical way to
build one is `register_adapter(...)` — it validates the name,
compiles the regex patterns up-front, and rejects malformed tools
before the server starts.

```python
from research_os.adapters import (
    AdapterRegistration,
    AdapterTool,
    register_adapter,
)

def register() -> AdapterRegistration:
    return register_adapter(
        name="myinfra",                          # lowercase, [a-z][a-z0-9_]*
        version="0.1.0",
        description="One-line summary in sys_adapters_installed.",
        detect=detect,                           # (root) -> bool
        extract=extract,                         # (root, step_id=None) -> dict
        describe=describe,                       # () -> dict (optional)
        tools_md_patterns=_TOOLS_MD_PATTERNS,    # ((regex, template), ...)
        tools=(
            AdapterTool(
                name="tool_myinfra_status",      # MUST start with tool_myinfra_
                handler=_handle_status,
                schema={"type": "object", "properties": {...}},
            ),
        ),
    )
```

Validation enforces:

* `name` matches `^[a-z][a-z0-9_]{0,30}$`.
* `detect` and `extract` are callable.
* Every `tools_md_patterns` regex compiles.
* Every `AdapterTool.name` starts with `tool_<adapter>_`.

### `detect` / `extract` contract (Slurm example)

`detect(root: Path) -> bool` — fast filesystem scan, no network.
Return True if the project uses your infra. The Slurm adapter scans
`workspace/**.{sh,bash,slurm,sbatch}` for `#SBATCH` / `#PBS`
directives or inline `sbatch` / `qsub` invocations:

```python
def detect(root: Path) -> bool:
    for path in _candidate_scripts(root):
        head = path.read_text(errors="ignore")[:8192]
        if _SBATCH_RE.search(head) or _PBS_RE.search(head) or _INLINE_RE.search(head):
            return True
    return False
```

`extract(root: Path, step_id: str | None = None) -> dict` — reads the
filesystem and returns structured provenance. The pipeline runner
serialises the dict to YAML at
`workspace/<step>/provenance/<adapter>.yaml`. Slurm extracts per-job
scheduler / partition / walltime / nodes / cpus / memory / GPU
resources / output paths / dependencies / loaded modules:

```python
def extract(root: Path, step_id: str | None = None) -> dict:
    scripts = _candidate_scripts(root)
    if step_id:
        step_prefix = (root / "workspace" / step_id).resolve()
        scripts = [s for s in scripts if str(s.resolve()).startswith(str(step_prefix))]
    jobs = []
    for path in scripts:
        text = path.read_text(errors="ignore")
        sched, kv = _parse_directives(text)
        if sched == "unknown" and not _INLINE_RE.search(text[:8192]):
            continue
        jobs.append({
            "script": str(path.relative_to(root)),
            "scheduler": sched,
            "partition": kv.get("partition") or kv.get("queue"),
            "time": kv.get("time") or kv.get("walltime"),
            "nodes": kv.get("nodes") or kv.get("N"),
            # ... cpus, mem, gres, output, job_name, account, depends_on, ...
        })
    return {"scheduler": ..., "scripts_scanned": len(scripts), "jobs": jobs}
```

Keep `extract` cheap and idempotent — the runner may call it once
per step and on every audit pass. If a sub-pass needs network access
(e.g. `squeue --json` for live job status), expose it as an opt-in
tool instead (see below).

### `tools_md_patterns` format

The core tools.md extractor builds a multi-language manifest of
every tool / module / library / scheduler resource a step uses.
Adapters contribute regex → human-template pairs that get merged in
at scan time:

```python
_TOOLS_MD_PATTERNS = (
    (r"^\s*#\s*SBATCH\s+--partition=(\S+)", "Slurm partition: {0}"),
    (r"^\s*#\s*SBATCH\s+--gres=(\S+)",       "Slurm gres: {0}"),
    (r"^\s*#\s*PBS\s+-q\s+(\S+)",            "PBS queue: {0}"),
    (r"^\s*module\s+load\s+(\S+)",           "HPC module: {0}"),
)
```

Each pattern is `(regex_source, template)`. Capture groups land in
the template via `{0}`, `{1}`, etc. The patterns compile at
`register_adapter()` time, so a malformed regex fails the adapter
loudly at startup rather than silently at scan time.

### Optional tools

Adapters can ship opt-in tools alongside the detect/extract pair.
They're merged into the dispatcher's `TOOL_DEFINITIONS` + `_HANDLERS`
at startup. Each tool is an `AdapterTool(name, handler, schema)`.
The Slurm adapter ships two — `tool_slurm_job_status` (wraps
`squeue --json` / `qstat -f`) and `tool_slurm_estimate_cost`
(multiplies wall-time × nodes × $/node-hour):

```python
AdapterTool(
    name="tool_slurm_job_status",                # MUST start with tool_slurm_
    handler=_handle_job_status,
    schema={
        "type": "object",
        "properties": {"job_id": {"type": "string"}},
        "required": ["job_id"],
        "description": "Query Slurm/PBS for a job's status.",
    },
),
```

Tool handlers follow the same `(name, arguments, root)` signature
as pack tools and should return the v2.1.0 envelope via `_success`
/ `_error` / `_text` (see §12).

### Testing pattern

Mirror the pack test pattern — force a fresh server load so the
dispatcher picks up your adapter, then exercise `detect` /
`extract` / each tool:

```python
def test_myinfra_registers():
    from research_os.adapters import discover_adapters, installed_adapters
    discover_adapters(bundled=[("myinfra", "research_os_adapter_myinfra:register")])
    names = {a["name"] for a in installed_adapters()}
    assert "myinfra" in names

def test_myinfra_detect_and_extract(tmp_path):
    (tmp_path / "workspace").mkdir()
    (tmp_path / "workspace" / "run.sh").write_text("#!/bin/bash\n#SBATCH --partition=gpu\n")
    from research_os_adapter_myinfra import detect, extract
    assert detect(tmp_path) is True
    payload = extract(tmp_path)
    assert payload["jobs"][0]["partition"] == "gpu"

def test_myinfra_tool_dispatches(tmp_path):
    import sys
    for m in list(sys.modules):
        if m.startswith("research_os"):
            del sys.modules[m]
    import research_os.server as srv
    result = srv._handle_tool_call("tool_myinfra_status", {"job_id": "12345"}, tmp_path)
    # Envelope shape: every adapter tool returns the v2.1.0 envelope.
    import json
    env = json.loads(result[0].text)
    assert env["status"] in {"success", "warning", "error"}
    assert "ro_version" in env
```

End users install the adapter exactly like a pack:

```bash
pip install research-os research-os-adapter-myinfra
research-os start
```

The MCP server discovers it via the `research_os.adapter` entry-point
group on next start; no further configuration. `sys_adapters_installed`
returns the active adapter list for diagnostics.

---

## Security + known-caveats reading for pack authors

Two documents you should read before publishing a pack:

* [SECURITY.md](SECURITY.md) — the trust boundary. Adapter packs run
  inside the same OS-level boundary as the core; anything an attacker
  can do via `tool_python_exec` they can do via your adapter's tools.
  Design pack tools so they don't widen the attack surface (e.g. don't
  accept arbitrary shell-command strings as parameters).
* [FAQ.md — Known caveats in 2.2.x](FAQ.md#known-caveats-in-22x) —
  envelope-shape compatibility, path containment scope, autopilot gate
  granularity. Pack maintainers hit these before end users do.
