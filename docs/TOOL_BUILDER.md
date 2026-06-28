# Building a tool (tool_build mode)

Most of Research OS is built for **analysis** — data in, results out, a
paper at the end. But a lot of research work is *building the thing that
does the analysis*: a variant caller, a CLI, a small library, a
simulation engine, an internal service, a multi-stage data pipeline.
That work has a different shape. "Done" isn't a figure with grounded
conclusions — it's **tests, build, and eval passing**. The unit of
progress isn't a numbered experiment — it's a **commit in a repo**.

`tool_build` mode reshapes the whole workspace around that reality.
Research OS stops trying to *be* the project and becomes the **governance
layer above** it: it holds the spec, the architecture, the design
decisions, and the eval harness that defines success, while the actual
tool lives in its own git repo underneath.

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
| Building / iterating on software (a tool, library, CLI, service, pipeline) | **tool_build** | **a commit** in the inner repo | **tests + build + eval pass** |
| Building a tool *and* the analysis that uses it | **hybrid** | an analysis spine + a `tool/` half | analysis grounded **and** the tool tested |
| Poking around, no committed direction yet | **exploration** | a throw-away probe in `workspace/scratch/` | you learned what you needed |
| Working interactively in Jupyter | **notebook** | a notebook cell run | the notebook reproduces clean |
| Running a program of several sub-studies | **multi_study** | a registered study under `studies/` | each study done + cross-study synthesis |

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
my-tool/                   ← Research OS governance workspace
├── spec/                    what we're building
│   ├── requirements.md        what the tool must do (functional + non-functional)
│   ├── design.md              how it's built (modules, data flow, trade-offs)
│   └── architecture.md        the architecture DIAGRAM + component contracts
├── decisions/               ADRs — WHY the tool is shaped this way (0001-*.md, …)
├── eval/                    the harness that defines "done" (tests / build / benchmarks)
│   └── <eval>/conditions.json    the recorded conditions sidecar for each eval result
├── milestones.md            roadmap of shippable increments (acceptance = a passing check, not a date)
├── governance.md            how the whole thing fits together
├── CHANGELOG.md             what changed, milestone by milestone
├── inputs/                  source-of-truth: raw_data/ + literature/ soft-guarded; context/ + config AI-maintained
├── workspace/scratch/       AI sandbox for throw-away probes
└── project/                ← THE ACTUAL TOOL — its own git repo (name = inner_repo)
```

Two layers, two jobs:

* **The governance layer** (outer workspace) keeps the build honest
  against intent. The spec says what success looks like; `architecture.md`
  shows how the pieces fit and what contracts they hold each other to;
  the ADRs record the load-bearing choices so a future contributor — or a
  fresh AI session — understands *why*, not just *how*; the eval harness
  decides whether the tool actually meets the spec.
* **The inner repo** (`project/` by default) is where code is written and
  committed. It's a normal git repository — clone it, ship it, hand it
  off on its own.

The full layout reference lives in the `GETTING_STARTED.md` and
`governance.md` that the scaffold writes into your project.

---

## The build arc, end to end

`tool_route` understands build phrasing ("build a tool", "spec it out",
"implement this", "wire up the pipeline", "write a benchmark", "cut a
release") and routes to the `build/*` protocols. These are scaffolds for
reasoning, not scripts — they name the questions a serious builder
answers and force you to justify your own answers for *this* tool. They
never pick a language, framework, or architecture for you.

You don't call protocols by name; you talk, and the router picks. The
canonical arc, with what each phase pins down:

| Phase | Protocol | What it pins down |
|---|---|---|
| **Design** | `build/spec_and_design` | The consumer, the acceptance criteria, the interface contract; **an architecture diagram** (`architecture.md`); load-bearing decisions recorded as ADRs. The opening move — before any code. |
| **Build (loop)** | `build/implement_iteration` | Scope one increment → implement it in the inner repo → prove it with a test → run the checks → **commit** against the objective. **Loops per commit.** |
| **Build (pipeline)** | `build/pipeline_construction` | For pipeline-shaped tools: organize the tool as ordered **stages**, each with an explicit **I/O contract**; executing the pipeline is a tracked **run**. |
| **Verify** | `build/test_strategy` | Turn the acceptance criteria into a real test regime (units, integration, edge cases, what *not* to test). |
| **Verify** | `build/tool_evaluation_loop` | The evidence-driven evaluate → improve heartbeat; every eval **result carries a recorded conditions sidecar** so a number is reproducible, not just quoted. |
| **Verify** | `build/benchmark_vs_baseline` | Measure against a baseline with a fair, repeatable harness when the tool's value is "faster / better / more accurate". |
| **Ship** | `build/release_and_changelog` | Cut a coherent, shippable increment: version, changelog entry, the release checks; **the README must carry the architecture diagram**. |

Say *"spec out a fast FASTQ deduplicator"* and you land in
`build/spec_and_design`; say *"implement the next feature"* and you're in
the `build/implement_iteration` loop; say *"turn this into a 4-stage
pipeline"* and you're in `build/pipeline_construction`.

---

## 1. Spec + architecture diagram (`build/spec_and_design`)

The opening move, before a line of code. It produces the `spec/` triad:

* **`requirements.md`** — what the tool must do. Functional (the
  behaviours) *and* non-functional (speed, memory, portability, the
  platforms it must run on). This is the contract with the consumer.
* **`design.md`** — how it's built: the modules, the data flow between
  them, the trade-offs you chose and rejected.
* **`architecture.md`** — the **architecture diagram**. `spec_and_design`
  includes an `architecture_map` step whose job is exactly this: a
  rendered diagram (Mermaid) of the components and how they connect, plus
  the contract each boundary holds (what crosses it, in what shape). This
  is the picture a new contributor or a fresh AI session reads first to
  understand the shape of the thing.

Load-bearing choices made here — "why a streaming parser, not load-all",
"why Rust for the hot loop" — are written as **ADRs** under `decisions/`
(`0001-streaming-parser.md`, …). An ADR records the decision, the
context, the alternatives, and the consequence, so the *why* survives the
people who made it.

> Grounding still applies. A library or method you pull in is a
> decision — run `tool_research_tool` first and log the choice with
> `mem_log` so the ADR trail is intact.

---

## 2. The implement_iteration loop — the unit is a COMMIT

This is the heartbeat of tool_build, the analog of the analysis-mode
per-step loop. The key difference: **the unit of progress is a commit in
the inner repo, not a numbered step.** One trip through the loop = one
coherent commit.

```
scope one increment   →  the smallest shippable behaviour, tied to a milestone
        ↓
implement in project/ →  write the code in the inner repo
        ↓
prove it with a test  →  a failing test that now passes; never "looks right"
        ↓
run the checks        →  tool_build(operation='build'|'test'|'lint')  must be green
        ↓
commit                →  tool_git commit, message tied to the objective
        ↓
(loop to the next increment)
```

Concretely, in a session:

* **`tool_git`** drives the inner repo's own history — `status`, `diff`,
  `branch`, `commit`. You stay inside the governed workspace; the inner
  repo keeps its own clean commit log.
* **`tool_build`** runs your configured `workspace.commands` with the
  inner repo as the working directory:
  `operation='build' | 'test' | 'lint'`, each reporting pass/fail.
* **`tool_bash_exec`** handles anything the two above don't (scaffold a
  file, run a one-off script). For a long build or test suite, wrap it in
  `tool_task` and poll — never block the session on a long job (see
  [DAEMON.md](DAEMON.md) for backgrounding long work).

A commit is not "done" because the code looks finished. It's done when
the increment it implements has a test that passes and the build/lint are
green. That is what the loop enforces.

---

## 3. Pipeline-shaped tools (`build/pipeline_construction`)

Some tools aren't one program — they're an ordered **pipeline**: stage 1
ingests, stage 2 aligns, stage 3 calls, stage 4 reports. For these, the
unit of design is not a commit but a **STAGE plus its I/O contract**, and
`build/pipeline_construction` is the protocol that organizes them.

It pins down, per stage:

* **The I/O contract** — exactly what the stage consumes (shape, schema,
  files) and exactly what it emits, so stages compose without surprises
  and a downstream stage can be developed against a fixed input shape.
* **The order + the seams** — which stages depend on which, where a stage
  can be swapped, where intermediate artefacts land.

Once the pipeline exists, **running it is a tracked run** — journaled and
provenanced exactly like any other Research OS run (see
[DAEMON.md](DAEMON.md)). That means a pipeline execution records its
inputs, the command, and its outputs, and shows up in the run lineage —
so when an input changes, the daemon can tell you which stages went
stale. The architecture diagram from `spec_and_design` is the natural
home for the stage graph; keep them consistent.

---

## 4. The evaluation loop with eval provenance (`build/tool_evaluation_loop`)

When the tool's value is a *measured* property — accuracy, recall, speed,
F1 against a gold set — `eval/` is what decides "done", and
`build/tool_evaluation_loop` is the evidence-driven heartbeat that runs
it: **build → evaluate → read the result → improve → re-evaluate.**

The non-negotiable rule here is **eval provenance**: every eval result
must carry a **recorded conditions sidecar** — the exact conditions under
which that number was produced (the inputs/dataset version, the
parameters, the commit of the tool under test, the environment, the
seed). A bare "F1 = 0.91" is not admissible; "F1 = 0.91 *under these
recorded conditions*" is.

```
eval/
├── accuracy_v2/
│   ├── result.json           the measured numbers
│   └── conditions.json       ← the recorded conditions sidecar (inputs, params, commit, env, seed)
└── throughput/
    ├── result.json
    └── conditions.json
```

Why it matters: a number you can't reproduce can't gate a release, can't
be compared across commits, and can't be cited in the README or a paper.
The sidecar is what turns "it got faster" into "it got 2.3× faster on
*this* dataset at *this* commit with *these* params" — a claim a reviewer
can re-run. When you regress, the loop compares the new conditions
against the old to tell you what actually changed.

---

## 5. Running builds, tests, and evals

The governance gate that makes *"done = tests + build + eval pass"*
enforceable rather than aspirational:

* **`tool_build(operation='build'|'test'|'lint')`** — runs the matching
  configured command in the inner repo and reports pass/fail. This is
  what you run in the loop.
* **`tool_audit(scope='tool', dimension='build' | 'tests')`** — the
  governance gate. It runs the configured build / test commands and
  *gates* on them, the same way analysis mode gates on grounded figures.
* The daemon's mode-aware self-check additionally watches that `eval/`
  defines "done", `spec/` says what's being built, `decisions/` records
  ADRs, and the inner `project/` repo has tests once it has code — these
  surface in `daemon_notes` so the AI course-corrects early.

For anything long (a full suite, a big benchmark, a pipeline run), hand
it to the daemon as a tracked job (`research-os daemon run`, `daemon
docker`, or `daemon submit` for SLURM) so it's journaled, provenanced,
and doesn't block the chat. See [DAEMON.md](DAEMON.md).

---

## 6. Release: the README carries the architecture diagram (`build/release_and_changelog`)

Cutting a release turns a set of committed increments into something a
consumer can adopt: a version, a changelog entry, the release checks.

One requirement specific to tool_build: **the README must carry the
architecture diagram.** A consumer landing on the repo should see, at the
top, the same component/stage picture from `spec/architecture.md` — so
the first thing they understand is the *shape* of the tool, not a wall of
install instructions. `release_and_changelog` checks for it. Keep the
README's diagram in sync with `spec/architecture.md`; they are the same
picture, surfaced in two places.

After a release, `build/package_and_publish` handles distribution (wheel,
crate, container, registry) when you're ready to ship it outward.

---

## Done = tests + build + eval pass (not figures)

This is the line that separates tool_build from analysis. In analysis
mode, the AI must read every figure it produced and ground every number
before a step is "done". In tool_build mode the equivalent bar is
mechanical and unambiguous:

> A milestone is done when its acceptance check — a passing eval (with
> its conditions sidecar), a green test suite, a clean build — passes.
> Not when the code "looks finished", and not when there's a nice figure.

So the loop is always: implement → prove it with a test →
`tool_build` / `tool_audit(scope='tool')` → commit; and for measured
properties, evaluate with a recorded conditions sidecar. A milestone in
`milestones.md` carries its acceptance bar in the table; the eval harness
in `eval/` is what actually decides. **Figures are not the deliverable; a
working, tested, evaluated, shippable tool is.**

| | analysis mode | tool_build mode |
|---|---|---|
| Unit of work | a numbered step `workspace/NN_*` | **a commit** in the inner repo |
| "Done" | figures + tables + grounded conclusions | **tests + build + eval pass** |
| The artefact of record | `conclusions.md` per step | a green check + an eval result with its conditions sidecar |
| The picture | figures in `synthesis/` | the **architecture diagram** in `spec/architecture.md` + the README |
| The deliverable | a paper / report | a working tool other people run |

---

## See also

* [START.md](START.md) — install + first project (analysis on-ramp).
* [RESEARCHER_GUIDE.md](RESEARCHER_GUIDE.md) — the full workflow guide;
  modes are covered in the mental-model section.
* [HYBRID_ARCHITECTURE.md](HYBRID_ARCHITECTURE.md) — when you're building
  a tool *and* the analysis that uses it (`hybrid` mode), with
  `hybrid/tool_to_analysis_handoff`.
* [DAEMON.md](DAEMON.md) — running long builds, tests, pipeline runs, and
  evals as tracked, provenanced jobs (native / Docker / SLURM).
* [SHARING.md](SHARING.md) — handing a tool, a pipeline stage's output,
  or a built Docker image off to the next person.
* [PROTOCOLS.md](PROTOCOLS.md) — the live `build/*` protocol catalogue
  (run `tool_protocols_list` for the exact set in your install).
* [PROTOCOL_DOCTRINE.md](PROTOCOL_DOCTRINE.md) — why the `build/*`
  protocols are scaffolds, not scripts.
* `governance.md` + `GETTING_STARTED.md` — written into your tool_build
  workspace at `init`; the on-the-ground reference for your project.
