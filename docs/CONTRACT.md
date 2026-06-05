# Research OS — Public Contract (v2)

This is the **integrator contract**. It pins which parts of Research OS
are stable across releases, which can move under SemVer-MINOR, and
which are internal. If you wrap, embed, or build on top of Research OS
(another MCP client, a CI bot, a lab IDE, a hosted service), read this
before pinning to a version.

The contract is **part of the public API** — changes to this file are
themselves SemVer-gated. A change to the STABLE section here is a
MAJOR-bump signal.

Versioning rules (see also [RELEASING.md](RELEASING.md)):

| Bump | Means |
|---|---|
| MAJOR (`1.x → 2.0.0`) | Anything in section A changed in a way that breaks an existing well-behaved client. |
| MINOR (`1.1.0 → 1.2.0`) | Section B changed — surface grew, no rename, no removal. |
| PATCH (`1.1.0 → 1.1.1`) | Section C changed — internals only. |

---

## A. STABLE surface (MAJOR-bump required to change)

If you depend on any of the below, you can pin a `~=X.Y` range and
trust nothing here moves under you.

### A.1 Public tool names + input schemas

Three name prefixes are public:

* `sys_*` — system / state / config / packs / files / help / boot.
  Examples: `sys_boot`, `sys_state_get`, `sys_protocol_get`,
  `sys_tool_describe`, `sys_packs_installed`, `sys_help`.
* `tool_*` — workflow tools (routing, audits, synthesis, viz, search,
  exec, pack-contributed). Examples: `tool_route`, `tool_synthesize`,
  `tool_audit_full`, `tool_plan_turn`, `tool_data_profile`,
  `tool_<pack>_*` for pack-contributed tools.
* `mem_*` — memory / log writers. Examples: `mem_analysis_log`,
  `mem_decision_log`, `mem_intake_capture`.

Stability guarantee: a tool that ships in `vX.0` is callable by the
same name with the same required input schema for the rest of the
`vX` line. New optional kwargs may appear (MINOR). Renames or
required-field changes are MAJOR. Deprecated names live on as
aliases for one MAJOR line.

The canonical, machine-readable list is whatever
`sys_tool_describe` and the MCP `tools/list` handshake return for
the running server.

### A.2 Audit-finding JSON schema

`src/research_os/schemas/audit_finding.schema.json` (JSON Schema
draft-07). Every audit emits a list of objects validated against
this schema. Required fields — `id`, `audit_name`, `severity`,
`dimension`, `generated_at`, `ro_version` — are part of the stable
contract; adding a new optional field is MINOR, renaming or removing
any of the above is MAJOR. `severity` enum is fixed at
`block | warn | info`.

### A.3 `researcher_config.yaml` field names

The canonical schema lives in
`templates/researcher_config.yaml`. The following top-level
sections are stable in v2:

* `researcher`
* `project_name`
* `research_goal`
* `interaction`
* `gate_strictness`
* `project_tier`
* `model_profile`
* `writing_preferences`
* `runtime`
* `tool_stack`
* `synthesis`
* `api_keys`

Adding a new top-level section or a new key under an existing one is
**MINOR**. Renaming or removing any of the above is **MAJOR**.
Enums on `gate_strictness` (`light | normal | strict | auto`),
`project_tier` (`throwaway | sketch | production`), and
`model_profile` (`small | medium | large`) are stable.

### A.4 Workspace directory layout

Every project on disk has a fixed shape. Integrations may read or
write any of these paths.

```
<project>/
├── inputs/                      # immutable inputs
│   ├── raw_data/                # NEVER written to after intake
│   ├── literature/              # NEVER written to after intake
│   ├── researcher_config.yaml   # see A.3
│   ├── intake.md                # filled by tool_intake_autofill
│   └── …
├── workspace/                   # all derived work
│   ├── 00_<step>/               # per-step subdirs
│   ├── methods.md
│   ├── analysis.md
│   ├── logs/                    # override_log.md, drafter_loops/, etc.
│   └── …
├── docs/
│   └── research_overview.md
└── .os_state/                   # private engine state — do not hand-edit
    ├── state.json
    ├── manifest.json
    ├── protocol_execution_log.jsonl
    ├── active_plan.json
    └── …
```

Renaming or relocating any of these directories is MAJOR. Adding a
new sibling directory or a new file inside `.os_state/` is MINOR.

### A.5 Protocol routing `intent_class` enum

`tool_route` resolves a researcher prompt down to one of ten L1
intent classes. The enum is fixed in v2:

```
session | discover | plan | execute | synthesize | audit_wrap |
methodology | literature | memory | review
```

Adding a new value is MAJOR (existing dispatch tables would not
handle it). Renaming or removing one is MAJOR. The `sub_intent` L2
vocabulary is intent-class-scoped and additions there are MINOR.

---

## B. MINOR-changeable (additions OK; renames PATCH)

Anything in this section may grow without warning between MINOR
releases. Wrap defensively if you care.

* **Tool argument optional kwargs.** New optional kwargs may appear
  on any public tool. Default values are picked to preserve prior
  behaviour. Renaming an existing optional kwarg is **PATCH** during
  a pre-release window and **MAJOR** after one full MINOR line.
* **Audit prose wording.** The free-text `message` and
  `suggested_fix` fields on `AuditFinding` are MINOR-mutable. Don't
  parse them with regex; group on the stable `audit_name` +
  `dimension` + `severity` tuple instead.
* **Protocol body prose.** The `description`, `editorial_voice`, and
  step-`description` fields inside protocol YAMLs are MINOR-mutable.
  Stable: the protocol's `id`, `name`, fully-qualified address
  (`<category>/<name>`), step `id`s, and `expected_outputs` paths.
* **New protocols + new tools.** Always MINOR. The router may pick a
  new protocol for a phrase your client previously saw routed to an
  older one — that's expected. Pin on tool names + the router's
  returned `primary_protocol` if you need determinism.

## C. PATCH-changeable / internal

Anything below may move at any time, including within a PATCH bump.
Do not depend on it.

* **Internal module structure.** Imports from
  `research_os.tools.actions.*`, `research_os.project_ops`, helper
  classes inside `research_os.utils.*`. Re-exports from
  `research_os.plugins` (the names listed in `__all__`) are stable.
* **Test fixtures, dev scripts.** Anything under `tests/`,
  `scripts/`, `tools/dev/` is dev-only and may be reorganised
  without notice. CI scripts under `.github/workflows/` are
  maintainer-owned.
* **Embeddings cache + on-disk index formats.** Files like
  `_embeddings.npz`, `.os_state/route_cache.sqlite`, plan-state
  internals — rebuilt on first server start of a new version.
* **CLI sub-command flags marked `(deprecated)`** — the wizard's
  `--workspace`, `--legacy-prompt`, etc.

---

## D. OUT-OF-SCOPE (Research OS will NOT do)

These are non-goals. Don't file issues asking for them; build them
as adapter packs or external services that talk to Research OS.

* **LLM provider management.** Research OS never holds an Anthropic /
  OpenAI / Google / vLLM API key, never makes an inference call, and
  never streams a chat completion. The IDE owns model access.
* **Cloud infrastructure provisioning.** No Terraform, no Helm, no
  Pulumi, no "spin up an EC2 box for me." Use your infra tools.
* **Long-running compute scheduling.** Research OS will not run a
  three-day GPU job inside its own process. Use the `slurm`,
  `nextflow`, or `snakemake` adapter pack to dispatch + poll; the
  adapter speaks the contract on both ends.
* **Live collaboration.** No CRDTs, no presence, no real-time
  document editing. Two researchers should each operate their own
  Research OS workspace and merge via git.

---

## Reporting a contract violation

If a release breaks something in section A without a MAJOR bump,
that's a release-process bug. Open an issue tagged `contract` with:

1. The version that broke it.
2. The previous version that worked.
3. The exact failing tool call / config field / path.
4. A minimal repro (a YAML or a `tool_*` invocation).

The maintainer will yank the broken version and re-release with the
correct bump.
