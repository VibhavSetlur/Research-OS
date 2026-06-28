# Sharing a workspace or output

**What this is for.** Concrete ways to hand this project — or just one
piece of it — to someone else: a collaborator, your PI / advisor, an
Argonne or partner team, or the next stage's owner in a pipeline. Each
path is safe by default: none of them leak AI-internal config or drag
along large raw data unless you ask.

Pick the path that matches *what* you're handing off:

| You want to hand off… | Use | Best when |
|---|---|---|
| The **whole project**, as a file | [Share archive](#1-share-archive--a-zip-you-can-send-anywhere) (`sys_export_share_archive`) | email / upload, no git needed |
| The **whole project**, citable + archival | [RO-Crate](#2-ro-crate--citable-archival-quality) (`sys_export_ro_crate`) | deposit, DOI, long-term preservation |
| The **whole project**, for a team to pull + contribute | [GitHub repo](#3-github-repo) | ongoing collaboration |
| **One folder's output + a contract** to the next actor | [Pipeline stage handoff](#4-pipeline-stage-handoff) (`program/pipeline_stage_handoff`) | a pipeline where someone else owns the next stage |
| The **exact environment** a result ran in | [Docker image by digest](#5-share-a-docker-image-by-digest) | "it works on my machine" must become "it works everywhere" |

A note on what's stripped, once, that applies to the archive and RO-Crate
paths: both **exclude** `.os_state/`, the IDE MCP configs, `AGENTS.md`,
and `CLAUDE.md` by default — so what your collaborator opens looks like a
finished research workspace, not an in-progress AI session.

---

## 1. Share archive — a zip you can send anywhere

The simplest path. In your AI client, ask:

> "export a share archive of this project"

The AI calls **`sys_export_share_archive`** (see [`TOOLS.md`](TOOLS.md)),
which writes `workspace/exports/<timestamp>.zip` in the project root. No
git knowledge required — email it, drop it in shared storage, upload it
anywhere.

**What's included:** `inputs/` (minus raw data unless you ask the AI to
include raw inputs), `workspace/`, `synthesis/`, `docs/`, `environment/`,
and a top-level `README.md` if present.

**What's excluded (always):** `AGENTS.md`, `CLAUDE.md`,
`GETTING_STARTED.md`, `.os_state/`, `.claude/`, `.cursor/`, `.vscode/`,
`.antigravity/`, `.opencode/`, MCP configs, `__pycache__/`, virtualenvs,
`node_modules/`.

To include the raw data too (e.g. handing the project to someone who must
re-run from scratch), say so explicitly — *"export a share archive
**including raw inputs**"* — and confirm there's nothing sensitive in
`inputs/raw_data/` first.

---

## 2. RO-Crate — citable, archival-quality

When the bundle needs to be **citable** and **preservation-grade** — a
data deposit, a DOI-backed supplement, a long-term archive — ask:

> "export an RO-Crate of this project"

The AI calls **`sys_export_ro_crate`**. An [RO-Crate](https://www.researchobject.org/ro-crate/)
is a standard, machine-readable research-object package: it wraps the same
clean workspace as the share archive but adds a `ro-crate-metadata.json`
manifest describing every file (what it is, what produced it),
**checksums** for integrity, and the structured metadata a repository or
DOI minter expects. The result is a bundle a data repository can ingest
and a reviewer can verify byte-for-byte — not just a zip.

Use the share archive for "send it to a colleague today"; use the
RO-Crate for "deposit it so it can be cited in five years".

---

## 3. GitHub repo

For a team that will pull, contribute, and follow history, use the
[GitHub CLI](https://cli.github.com/) directly. From the project root:

```sh
gh repo create $(basename "$PWD") --private --source=. --push
```

That one command initialises git if needed, creates the GitHub repo named
after the current folder, sets it as `origin`, and pushes the first
commit.

**Security note.** Default to `--private`. Only flip to `--public` after
confirming `inputs/` contains no sensitive data (PHI, embargoed results,
unpublished collaborator data, API keys). See the `confidentiality_level`
field documented for the project audit metadata before publishing.

Requires `gh auth login` once. Before running the command, review your
`.gitignore` to make sure AI-internal files (`.os_state/`, `.claude/`, MCP
configs) are excluded — the `init` wizard adds these by default.

---

## 4. Pipeline stage handoff

Sometimes you don't hand off the whole project — you hand off **one
stage's output plus the contract** for what the next person should do with
it. This is the normal case in a multi-stage pipeline where different
people (or different labs) own different stages: you finish "stage 2:
alignment", and stage 3's owner needs the aligned output *and* an explicit
statement of what it is, how it was produced, and what they're expected to
do next.

Ask the AI to **hand off a stage**, and it runs
**`program/pipeline_stage_handoff`**. The protocol packages a folder's
output together with a **`HANDOFF.md` contract** — the document that turns
"here's a folder" into "here's a folder *and the agreement around it*". A
`HANDOFF.md` states:

- **What this folder contains** — the output artefacts, named, with their
  shapes / schemas.
- **How it was produced** — the command / stage that made it, the inputs
  it consumed, the environment (and, if it ran as a tracked daemon job,
  the run id and provenance so it's traceable). For containerised stages,
  the **image + digest** so the next actor can reproduce the exact
  environment (see [§5](#5-share-a-docker-image-by-digest)).
- **The I/O contract for the next stage** — what the next actor receives,
  what they're expected to produce, and the acceptance criteria that say
  their stage is done.
- **Caveats** — known limitations, what's *not* in scope, anything they
  must not assume.

This is the same I/O-contract discipline that `build/pipeline_construction`
uses to organize stages inside a `tool_build` project (see
[TOOL_BUILDER.md](TOOL_BUILDER.md#3-pipeline-shaped-tools-buildpipeline_construction)) —
here it's pointed *outward*, to a human or team taking the next stage.

For handing the **whole project** to a human collaborator (not just one
stage), the broader `guidance/collaboration_handoff` protocol packages the
project with the context a new owner needs to pick it up — ask the AI to
"hand this project off to a collaborator".

---

## 5. Share a Docker image by digest

When the thing that matters is the **exact environment** a result ran in —
"reproduce my benchmark", "run my pipeline stage on your data" — share the
container image **by digest**, not by tag. A tag (`myimg:latest`) can be
re-pushed to point at different bits tomorrow; a **digest** is the
immutable content hash, so the recipient runs the *identical* image you
did.

If you ran the work as a tracked container job, the digest is already
recorded for you. The daemon's `DockerRunner` records the image **and its
content digest** on every `daemon docker` run, so you can read it back off
the run record rather than chasing it down:

```bash
research-os daemon docker myimg:tag -- python run.py   # the run records image + digest
research-os daemon logs <run_id>                       # shows the recorded image + digest
```

To share that image:

```bash
# get the immutable digest of the image you ran
docker inspect --format='{{index .RepoDigests 0}}' myimg:tag
# → myregistry/myimg@sha256:abc123…

# push it to a registry the recipient can reach
docker push myregistry/myimg:tag
```

The recipient then pulls and runs **by digest** — guaranteeing identical
bits:

```bash
docker pull myregistry/myimg@sha256:abc123…
research-os daemon docker myregistry/myimg@sha256:abc123… -- python run.py
```

Pair the digest with the [stage handoff](#4-pipeline-stage-handoff)
above: the `HANDOFF.md` names the digest, so "what you received", "how it
was produced", and "the environment to reproduce it in" all travel
together. See [DAEMON.md](DAEMON.md#the-three-ways-to-run-a-long-job) for
how containerised runs are recorded.

---

## What collaborators get

From the share archive, RO-Crate, or GitHub repo, a collaborator opens a
clean research workspace they can read without any Research-OS context:

* `synthesis/dashboard.html` — the polished single-file dashboard (open in
  any browser; self-contained).
* `synthesis/figures/` — every curated figure with its caption sidecar.
* `synthesis/REPORT.md` / `synthesis/paper.typ` — the narrative deliverable.
* `workspace/NN_*/conclusions.md` — the per-step reasoning chain.
* `workspace/NN_*/scripts/` — the actual analysis code (reproducible).
* `workspace/NN_*/data/next_step_output/` — derived artefacts each step
  persisted.
* `docs/` — research question, glossary, workflow diagram.

For a **tool_build** project, the share also surfaces the governance
layer — `spec/` (including the architecture diagram in
`spec/architecture.md`), `decisions/` (the ADRs), `eval/` (with each
result's conditions sidecar), and the inner `project/` repo — so the
recipient understands not just *what* the tool is but *why* it's shaped
that way. See [TOOL_BUILDER.md](TOOL_BUILDER.md).

The AI-side configuration is intentionally excluded, so the share reads as
a finished research project, not an in-progress AI workspace.
