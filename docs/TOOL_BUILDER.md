# Building a tool (tool_build mode)

Most of Research OS is built for **analysis** — data in, results out, a
paper at the end. But a lot of research work is *building the thing that
does the analysis*: a variant caller, a CLI, a small library, a
simulation engine, an internal service. That work has a different shape.
"Done" isn't a figure with grounded conclusions — it's **tests, build,
and eval passing**. The unit of progress isn't a numbered experiment —
it's a **commit in a repo**.

`tool_build` mode reshapes the whole workspace around that reality.
Research OS stops trying to be the project and becomes the **governance
layer above** it: it holds the spec, the design decisions, and the eval
harness that defines success, while the actual tool lives in its own git
repo underneath.

If you're doing data analysis, you want [START.md](START.md) and the
[Researcher Guide](RESEARCHER_GUIDE.md) — not this page. If you're not
sure which you're doing, see [Which mode?](#which-mode) below.

---

## Which mode?

Set the mode once, at `research-os init`. It shapes the scaffold and how
the AI works.

| You're mostly… | Mode | "A unit of work" is… | "Done" means… |
|---|---|---|---|
| Turning data into results + a write-up | **analysis** *(default)* | a numbered experiment step under `workspace/NN_*` | figures + tables + grounded conclusions |
| Building / iterating on software (a tool, library, CLI, service) | **tool_build** | a commit / iteration in the inner repo | tests + build + eval pass |
| Poking around, no committed direction yet | **exploration** | a throw-away probe in `workspace/scratch/` | you learned what you needed |

Pick **tool_build** when the deliverable is *code other people will run*,
the success criterion is *it works / it's fast enough / it passes the
benchmark*, and you'll be committing iteratively. Pick **analysis** when
the deliverable is *a finding* backed by figures and prose. You can
transition mode later (ask the AI to "switch modes" → it runs
`sys_workspace_mode`, which builds the new surface), but it's cheapest to
choose up front.

---

## Start a tool_build project

```bash
mkdir my-tool && cd my-tool
research-os init --workspace-mode tool_build
```

…or run the plain wizard and answer **"A tool / software I iterate on"**
at the *"What are you building?"* step. Either way the scaffold seeds the
governance surface and an inner project repo, and writes a tuned
`GETTING_STARTED.md` you should read first inside the new folder.

You can also flip an existing workspace by editing
`inputs/researcher_config.yaml`:

```yaml
workspace:
  mode: tool_build
  inner_repo: ""        # the inner project dir (blank → "project")
  commands:
    build: ""           # e.g. "make" | "cargo build" | "npm run build"
    test: ""            # e.g. "pytest -q" | "cargo test" | "npm test"
    lint: ""            # e.g. "ruff check ." | "cargo clippy" | "eslint ."
```

The `commands` are what *"done"* runs against. Fill them in early — the
build / test / lint audit gate uses them, and reports a clear
"configure `workspace.commands.<op>`" message until you do.

---

## The governance model

Research OS does **not** contain the tool. It governs the build from
above. The actual tool lives in its own git repository underneath the
workspace, with its own history independent of the governance layer.

```
my-tool/                  ← Research OS governance workspace
├── spec/                   what we're building
│   ├── requirements.md       what the tool must do (functional + non-functional)
│   └── design.md             how it's built (architecture, modules, trade-offs)
├── decisions/              ADRs — WHY the tool is shaped this way (0001-*.md, …)
├── eval/                   the harness that defines "done" (tests / build / benchmarks)
├── milestones.md           roadmap of shippable increments (acceptance = a passing check, not a date)
├── governance.md           how the whole thing fits together
├── CHANGELOG.md            what changed, milestone by milestone
├── inputs/                 source-of-truth: raw_data/ + literature/ soft-guarded; context/ + config AI-maintained
├── workspace/scratch/      AI sandbox for throw-away probes
└── project/               ← THE ACTUAL TOOL — its own git repo (name = inner_repo)
```

Two layers, two jobs:

* **The governance layer** (outer workspace) keeps the build honest
  against intent. The spec says what success looks like; the ADRs record
  the load-bearing choices so a future contributor — or a fresh AI
  session — understands *why*, not just *how*; the eval harness decides
  whether the tool actually meets the spec.
* **The inner repo** (`project/` by default) is where code is written and
  committed. It's a normal git repository — clone it, ship it, hand it
  off on its own.

The full layout reference lives in the `GETTING_STARTED.md` and
`governance.md` that the scaffold writes into your project.

---

## The build arc

`tool_route` understands build phrasing ("build a tool", "spec it out",
"implement this", "write a benchmark", "cut a release") and routes to the
`build/*` protocols. The canonical arc:

| Phase | Protocol | What it pins down |
|---|---|---|
| Design | `build/spec_and_design` | The consumer, the acceptance criteria, the interface contract; load-bearing decisions recorded as ADRs. The opening move — before any code. |
| Build (loop) | `build/implement_iteration` | Scope one increment → implement it in the inner repo → prove it with a test → run the checks → commit against the objective. **Loops per increment.** |
| Verify | `build/test_strategy` | Turn the acceptance criteria into a real test regime (units, integration, edge cases, what *not* to test). |
| Verify | `build/benchmark_vs_baseline` | Measure against a baseline with a fair, repeatable harness when the tool's value is "faster / better / more accurate". |
| Ship | `build/release_and_changelog` | Cut a coherent, shippable increment: version, changelog entry, the release checks. |

These are scaffolds for reasoning, not scripts — they name the questions
a serious builder answers and force you to justify your own answers for
*this* tool. They never pick a language, framework, or architecture for
you.

You don't call protocols by name; you talk, and the router picks. Say
*"spec out a fast FASTQ deduplicator"* and you land in
`build/spec_and_design`; say *"implement the next feature"* and you're in
the `build/implement_iteration` loop.

---

## The build tools + audits

`tool_build` mode is git- and shell-driven, because building software is:

* **`tool_git`** — run git operations against the inner repo (status,
  diff, branch, commit). The inner repo has its own history; this is how
  you drive it without leaving the governed workspace.
* **`tool_build`** — runs the configured `workspace.commands` with the
  inner repo as the working dir. `operation='build' | 'test' | 'lint'`
  each runs the matching command and reports pass/fail.
* **`tool_bash_exec`** — for anything the two above don't cover (scaffold
  a file, run a one-off script). For long builds or test suites, wrap it
  in `tool_task` and poll — never block the session on a long job.
* **`tool_audit(scope='tool', dimension='build' | 'tests')`** — the
  governance gate. It runs the configured build / test commands and gates
  on them, the same way analysis mode gates on grounded figures. This is
  what makes *"done = tests + build pass"* enforceable rather than
  aspirational.

Grounding still applies: a library or method you pull in is a decision —
run `tool_research_tool` first and log the choice with `mem_log` so the
ADR trail is intact.

---

## Done = tests + build pass

In analysis mode, the AI must read every figure it produced and ground
every number before a step is "done". In tool_build mode the equivalent
bar is mechanical and unambiguous:

> A milestone is done when its acceptance check — a passing eval, a green
> test suite, a clean build — passes. Not when the code "looks finished".

So the loop is always: implement → prove it with a test → run
`tool_build`/`tool_audit(scope='tool')` → commit. A milestone in
`milestones.md` carries its acceptance bar in the table; the eval harness
in `eval/` is what actually decides. Figures are not the deliverable; a
working, tested, shippable tool is.

---

## See also

* [START.md](START.md) — install + first project (analysis on-ramp).
* [RESEARCHER_GUIDE.md](RESEARCHER_GUIDE.md) — the full workflow guide;
  modes are covered in the mental-model section.
* [USE_CASES.md](USE_CASES.md) — role × goal × output, including a
  tool_build example.
* [PROTOCOL_DOCTRINE.md](PROTOCOL_DOCTRINE.md) — why the `build/*`
  protocols are scaffolds, not scripts.
* `governance.md` + `GETTING_STARTED.md` — written into your tool_build
  workspace at `init`; the on-the-ground reference for your project.
