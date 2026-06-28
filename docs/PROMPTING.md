# Prompting Research OS — how to ask for what you want

Research OS does the bookkeeping, enforcement, and provenance for you. You drive
it in **plain language** — you don't call tools, you describe what you want and
your AI routes it through the right protocol. This guide is the practical
phrasebook: how to word a request to get a specific outcome, and **what happens
behind the scenes** when you do.

You never need the exact words below. The router matches intent, not keywords.
These are reliable phrasings plus a peek at the machinery so you can trust what
you get back.

---

## How a request flows (the 10-second model)

1. You type a message in your IDE/agent chat.
2. Your AI calls `tool_route` with your message. The router picks the protocol
   that fits, returns a plan, and — every time — a list of **capability skills
   to pull for this task**.
3. The AI loads those skills, does the work through Research OS tools (which
   record provenance, enforce gates, and keep the project organized), and
   reports back.
4. If a daemon is running, it watches the whole project in the background and
   flags anything that drifted (a step with no environment snapshot, a result
   built on changed data, conclusions left as a template) so the AI fixes it.

You can always ask **"what did you just do / what's the state?"** and the AI
will read it back from `sys_boot` + `STATE.md`.

---

## Recipes: say this → get that

Each recipe gives a **say it like this**, **what happens behind the scenes**,
and **how to verify** it actually happened.

### Pull papers into the project

> "Pull a few papers on <topic> into my inputs."
> "Find the key literature on <method> and add it to the project."
> "Ground this step in the literature — search for papers that support or
> challenge this result."

**Behind the scenes.** For project-wide reading, the AI searches (Crossref /
Semantic Scholar / PubMed / arXiv), downloads validated PDFs into
`inputs/literature/`, and refreshes `workspace/citations.md`. For a specific
step, it pulls papers **mid-step** into `workspace/<step>/literature/` and runs
the per-step grounding loop (each numeric claim gets a paper that agrees /
disagrees / is mixed). At step finalize, those papers are mirrored into the
project's root `literature/` corpus-of-record. The daemon watches whether the
root corpus has fallen behind and flags `literature_corpus_behind`.

**Verify.** `ls inputs/literature/` (or `workspace/<step>/literature/`), and
check `workspace/citations.md`. Ask "are any citations unverified?" — every
citation is resolved online before it can land in a paper.

**Tip.** "a few" / "the key ones" keeps it focused; "do a systematic review of
<topic>" triggers the heavier systematic-review protocol instead.

### Dockerize / containerize a step (reproducible, portable)

> "Dockerize this step."
> "Give me a container for this analysis so it runs on another machine."
> "Make step <NN> reproducible — pin its environment and write a Dockerfile."

**Behind the scenes.** The AI first snapshots the step's exact packages
(`sys_env(operation='snapshot', step_id='<NN_slug>')` → writes
`workspace/<NN_slug>/environment/requirements.txt`), then generates a
**step-scoped** `workspace/<NN_slug>/environment/Dockerfile` (+ `.dockerignore`)
built from *that step's own* requirements, with the build context set to the
step directory. The step's scripts, data, and pinned environment travel
together, so `docker build` from the step folder reproduces the step in
isolation — not the whole project, just that step.

**Verify.** `cat workspace/<NN>/environment/Dockerfile` — it should `COPY` the
step and `pip install -r environment/requirements.txt` from the step's own
pins. The header comment tells you the exact `docker build` command. A step
that ran scripts but has no per-step environment is flagged by the daemon
(`step_no_env_snapshot`), so ask "did every step that ran code get its own
environment?" before sharing.

**Tip.** Say "for the whole project" to get a project-level image at
`environment/Dockerfile` instead.

### Run something long without blocking the chat

> "Run this on the cluster / SLURM and let me know when it's done."
> "Kick this off in the background — I'll keep working."

**Behind the scenes.** With a daemon running, long work goes through a tracked
job (`tool_task` / SLURM submission). The job carries a full environment
snapshot automatically, records provenance, and notifies you on completion. You
won't sit blocked; ask "what's running?" any time (`sys_daemon`). Without a
daemon, the AI runs it foreground and you wait — so start the daemon for long /
HPC work (see [DAEMON.md](DAEMON.md)).

**Verify.** "Show me the running jobs and the resource budget."

### Build a shareable dashboard / slides / poster (for people who never saw your workspace)

> "Build a dashboard of the findings I can email my team."
> "Make a slide deck for the lab meeting."
> "I need a poster for the conference."

**Behind the scenes.** These route through the synthesis protocols, which all
delegate visual design to one shared design skill (`deliverable_design`). That
skill enforces, as a rubric:
- **Built for an external reader with no workspace** — *no step numbers, file
  paths, tool names, or raw column names ever surface*, in prose, captions, OR
  diagrams. A workflow/architecture diagram shows the **scientific/conceptual
  flow** (data → method → finding), never your folder structure (`01_canon →
  02_eda`).
- **Custom, designed to the argument** — sections are organized by *what was
  learned* ("Reranking lifted hits@10 by 5.9pp"), not by chronology or
  containers. One fixed template for every project is the "AI slop" this exists
  to prevent.
- Answer-first, restrained palette, every figure interpreted, accessible.

So the output captures *what you actually found and want to convey* — a
high-quality artefact a stranger understands in seconds, with none of the
behind-the-scenes mechanics leaking through.

**Verify.** Open the file. If you ever see "Step 03" or a filename in an
audience deliverable, say "this leaks workspace bookkeeping — rewrite it for an
external reader," and it will.

**Tip.** Say *who it's for and the one thing they must leave with* ("for my PI,
the headline is the 5.9pp lift") — that single sentence drives every design
choice. Research OS gives you the **structure**; the design and final wording
are tailored to your audience, not poured from a template.

### Test a tool on data — or make sample data when you have none

> "Test this tool on some data."
> "I don't have data yet — generate realistic sample data and run it."
> "Does it actually work on real input? Validate it on a dataset."

**Behind the scenes.** In a tool_build / hybrid project this routes to the
sample-data-and-validation protocol: it pins the tool's real input contract,
then either pulls a small representative real sample or **generates seeded,
re-runnable synthetic data** that matches the schema and includes the hard
cases (edge values, nulls, malformed rows). It runs the tool end-to-end and
validates the output is both **correct** (against ground truth — which synthetic
data gives you for free, since you made it) and **sensible** (ranges,
invariants). Failures feed the evaluate→improve loop. The data, its generator,
and the validation check are saved as a reusable fixture.

**Verify.** "Show me the sample data and the validation check." Synthetic data
is always labelled as synthetic so it's never mistaken for a real result.

### Plan iteratively (phases that can change as you learn)

> "Plan this as phases with decision gates."
> "Map out the project, but let the results reshape the later steps."

**Behind the scenes.** Deep planning writes a branchable roadmap to
`inputs/research_plan.md` and registers your load-bearing assumptions as tracked
hypotheses. Research is **not** a fixed pipeline: each step ends at a decision
gate (proceed / branch / dead-end) that can re-order, add, or drop later steps.
A path that doesn't pan out is preserved as a `__DEAD_END` (never deleted), so
the reasoning trail survives.

**Verify.** "Show me the plan and the open hypotheses." (`sys_boot` returns the
live plan; `inputs/research_plan.md` is the durable copy.)

### Branch, abandon, or revise a step

> "This direction isn't working — branch off step <NN> and try <alternative>."
> "Abandon this step but keep the files."

**Behind the scenes.** Branching forks a new path with a lineage tag; abandoning
renames to `__DEAD_END` (files preserved, never deleted). Nothing in
`workspace/` is ever hard-deleted.

### Ask what's happening / resume later

> "What's the state of the project?" · "Where did we leave off?"
> "Resume — what should I do next?"

**Behind the scenes.** The AI reads `sys_boot` (live state + next protocol +
any interrupted runs + daemon findings) and `STATE.md` (the human front page).
On a fresh chat it re-orients from these, so you can close the laptop mid-project
and pick up cleanly.

---

## What the daemon watches for you (so you don't have to)

If a daemon is running, it re-checks the project in the background and surfaces
issues the AI must address before building further. You'll see these come back
as the AI self-correcting mid-turn. The ones worth knowing:

| You might notice | What it means |
|---|---|
| "snapshotting the step environment first" | a step ran scripts but had no per-step env capture (`step_no_env_snapshot`) — needed for reproducibility/containers |
| "pulling literature for this claim" | a step made claims with no grounding (`step_ungrounded_no_literature`) |
| "updating the literature corpus" | root `literature/` fell behind a step or inputs (`literature_corpus_behind`) |
| "refreshing STATE.md" | the status file lagged the latest work (`state_md_stale`) |
| "logging this as a decision" | design choices weren't being recorded as ADRs (`decisions_not_logged`) |
| "this result is stale — re-running" | an output's input changed underneath it (staleness gate) |

You can always ask **"did the daemon flag anything?"** (`sys_daemon`).

---

## Framing tips that consistently help

- **Name the audience + the one takeaway** for any deliverable. "For a program
  officer; the takeaway is feasibility." It changes the whole design.
- **Say "structure, not design"** if you want an outline/skeleton you'll fill,
  vs. a finished artefact. Research OS provides the *shape*; you and the AI
  tailor the content + design.
- **Be explicit about scope**: "just this step" vs. "the whole project" for
  environment, docker, and audits.
- **Ask for verification**: "ground every number," "run the reproducibility
  audit," "check the citations resolve." These trigger the real gates.
- **Use "quick" / "throwaway" / "just sanity-check"** for exploratory work — it
  routes to scratch (no heavy audits) so you're not gated on a 2-minute probe.
- **You can override a gate** when you have a good reason: "skip the re-run
  audit, I accept the unverified state" — the AI logs the override + your
  rationale rather than silently passing.
- **When in doubt, just describe the goal.** You don't need to know the protocol
  or tool names; routing is the AI's job.

---

See also: [SCENARIOS.md](SCENARIOS.md) (two worked projects end to end),
[USE_CASES.md](USE_CASES.md) (outcome → which protocol fires),
[HOW_IT_WORKS.md](HOW_IT_WORKS.md) (why provenance/accuracy/organization hold up),
[RESEARCHER_GUIDE.md](RESEARCHER_GUIDE.md) (the full reference).
