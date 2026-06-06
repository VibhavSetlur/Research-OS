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
