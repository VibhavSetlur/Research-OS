# How Research OS actually works (and why your results hold up)

Most docs show you the *commands*. This one shows you the **work** — how a
real project actually unfolds over days and sessions, where the messy parts
go, and how the system quietly turns that mess into something a reviewer (or
future-you) can trust. Read this once before your first real project; it's the
difference between "I pointed an AI at my data" and "I have a result I can
defend."

If you only remember one thing: **Research OS does not make research faster by
skipping the slow parts. It makes the slow parts — planning, iterating,
checking, citing — leave a trail, so you never have to redo them to prove they
happened.**

---

## Part 1 — Research is not linear, and neither is this

The quickstart shows a clean line: set up → EDA → model → paper. Real projects
don't go like that, and Research OS isn't built to pretend they do. Here is
what actually happens, and what the system does at each turn.

### You spend a whole session on the plan before touching the data

That's normal and correct. You don't have to "produce" anything the first day.

> **You:** Before any analysis, let's think through the whole approach. Here's
> what I'm worried about confounding, here's the population, here's what the
> reviewers at this venue always push back on.
>
> **AI:** *(loads the planning protocol)* Here's a draft research plan with the
> decision points called out — what we'll test, where the branch points are,
> what would make us change course. I've written it to
> `inputs/research_plan.md` — the durable, branchable roadmap. No numbered step
> exists yet; this is the plan we iterate on first.
>
> **You:** The matching strategy is wrong for this design. And add a
> sensitivity analysis for the dropout assumption.
>
> **AI:** Updated `inputs/research_plan.md` and appended the change to its
> iteration log. Want me to keep iterating, or are we ready to open the first
> step?

Nothing here creates a numbered step or a result. The plan lives in
`inputs/research_plan.md` — the single living roadmap, reshaped as you go, with
an append-only iteration log that preserves its history — until *you* decide
it's solid. You might do this over **three sessions across a week**, re-reading
literature between them. That is a feature: the plan firms up before any
analysis locks in, and when you finally open step `01`, the reasoning behind it
is already on disk. (Each numbered step then gets its OWN `plan.md` — see below
— for the planning that step needs before it runs.)

**Why this matters for trust:** a plan that was argued over and revised — with
the alternatives you rejected written down — is far more defensible than one
that was implied by whatever the AI did first.

### Planning doesn't only happen at the start — each step plans itself first

The whole-project roadmap (`inputs/research_plan.md`) is the arc. But planning
also happens *inside* the work. Say you've finished steps `01`–`05` and step
`06` is a real fork in the road — a modelling choice you want to think through
before any code runs. Each numbered step gets its **own** `workspace/<NN>/plan.md`,
and it is a living draft you iterate on the same way:

> **You:** *(on step 06)* Before we run anything, let's plan this step. I'm torn
> between a mixed-effects model and a GEE here.
>
> **AI:** I've drafted `workspace/06_*/plan.md` — where we are coming out of
> step 05, what this step will do, the two candidate approaches, and the open
> questions. Read it and push back.
>
> **You:** Go with mixed-effects, but add the GEE as a sensitivity check. And
> note we're assuming the random-slope structure converges.
>
> **AI:** Updated `plan.md`, and synced the change back to
> `inputs/research_plan.md`'s iteration log so the roadmap stays current.

You can go back and forth on `plan.md` for as long as you want — nothing runs
until you're ready. When the step finishes, `plan.md` ends as a true record of
what the step actually did vs. what was planned, so a reader sees the reasoning,
not just the result. The two plans stay in sync: `inputs/research_plan.md` is
the project arc; `workspace/<NN>/plan.md` is how one step on that arc was
thought through.

### You do literature work until something solidifies — not in one shot

Literature isn't a checkbox at the start. You circle it.

> **You:** Pull recent work on this estimator and tell me where the field
> actually disagrees.
>
> **AI:** *(searches, verifies each hit against Crossref / Semantic Scholar so
> nothing is hallucinated)* Here are 14 real papers, grouped by the three
> positions in the debate, with the two that directly threaten our approach
> flagged.
>
> **You:** *(next session)* I read those. Two of them change my hypothesis.
> Here are four more PDFs my advisor sent.

You drop the PDFs in `inputs/literature/`. They are **immutable** — the server
blocks writes to them, so your evidence base can't be silently edited. The
bibliography (`workspace/citations.md`) is regenerated from what's actually
there, and every citation is verified against a real record, not invented.
You repeat this loop until the framing stops moving. Only then do you commit
to a question and hypotheses.

### New literature shows up in the MIDDLE of an analysis step — here's exactly where it goes

This is the case the quickstart never shows, and it's the one people hit most.
You're three scripts into step `04_survival_model` and a paper lands that
changes how you should specify the model.

Two homes, and the distinction is the whole point:

- **`inputs/literature/`** — the paper is relevant to the *whole project*
  (it reframes the question, adds a citation you'll use in the paper). Drop it
  here. It joins the verified bibliography and is available to every step.
- **`workspace/04_survival_model/literature/`** — the paper only matters to
  *this step* (a specific method tweak, a parameter choice you're justifying
  right here). Put it in the step's own `literature/` folder so the reason for
  the change lives next to the change.

> **You:** This new paper says we should be using a competing-risks model, not
> plain Cox. Bring it into the current step and let's reconsider.
>
> **AI:** Saved it to `workspace/04_survival_model/literature/` (it's specific
> to this step's method choice). I'm bumping the script to `_v3` to add the
> competing-risks specification, and I'll record in `conclusions.md` that the
> change was prompted by this paper — so anyone reading the step sees *why*
> v3 exists, not just that it does.

What the system does for you here:
- the script bumps `_v2 → _v3`; **`_v2` stays on disk** — you can always show
  what the result looked like before the new evidence;
- the new output gets a fresh provenance sidecar recording it was built from
  the new inputs;
- `conclusions.md` records the literature-driven reason for the revision;
- if any downstream step was built on the old `_v2` output, the
  **provenance-integrity check flags it as stale** — you won't accidentally
  ship a figure built on the superseded version.

### A single step takes several iterations — and that's recorded, not hidden

Real analysis steps rarely work the first time. You'll go `_v1 → _v2 → _v3`,
sometimes over days.

```
workspace/04_survival_model/scripts/
  04_fit_model_v1.py      ← first attempt; assumption check failed
  04_fit_model_v2.py      ← fixed the time-scale; reviewer-style robustness added
  04_fit_model_v3.py      ← competing-risks, after the new paper
```

The **iteration ledger** versions these for you; old versions never disappear.
When you finally finish the step, the trail shows the path you took — which is
exactly what a methods section and a skeptical reviewer want.

### You do NOT call something "done" prematurely — the system helps you resist

The most common way research goes wrong is declaring a step finished before
it's actually sound. Research OS pushes back:

> **You:** OK, mark the model step complete.
>
> **AI:** Before I do — the completeness check flags two things: the
> assumption diagnostics for the new specification haven't been run, and one
> output figure was built from an input that changed after the figure was made
> (it's stale). I'd re-run the figure and add the diagnostics first. Want me
> to?

You can override, but you do it **knowingly**, and the override is recorded.
"Done" means *checked*, not *typed*.

---

## Part 2 — The true power: provenance, accuracy, organization

These are the three things that make the difference between output you trust
and output you hope is right. Here's what each one actually is, and how to get
the most out of it.

### Provenance — every result can prove where it came from

Every figure, table, and dataset the AI produces gets a `.prov.json` sidecar
recording: the exact inputs (by content hash), the script that made it, the
parameters, the random seed, the software versions, and the git commit. This
isn't bookkeeping for its own sake — it's what lets you answer, months later,
"how exactly did I get this number?" without re-deriving it from memory.

**How to get the most out of it:**
- Let the AI run analysis through steps and scripts rather than improvising
  one-off computations in chat — only the former leaves a sidecar.
- When an input changes, re-run the step. The **provenance-integrity check**
  re-hashes recorded inputs and flags any result whose input drifted since it
  was built (a *stale* result). Run it before any milestone:
  *"check provenance integrity across the project."*
- Before you submit or share, ask for a provenance pass. A result with a clean
  sidecar and a non-stale verdict is one you can defend line by line.

### Accuracy — numbers and citations are verified, not trusted

Two specific guards against the two most common AI failures:

- **Hallucinated numbers.** When you write up results, **claim grounding**
  extracts every quantitative claim in the prose and checks each one traces to
  a real artifact (a table cell, a figure's data, a recorded statistic).
  A number that can't be traced gets flagged before a reviewer sees it. Ask:
  *"ground every claim in the results section."*
- **Hallucinated citations.** Every citation is checked against Crossref /
  Semantic Scholar / PubMed. Invented references — the classic LLM failure —
  don't survive the bibliography step.

**How to get the most out of it:** write the prose *from* the artifacts, then
run grounding; don't paste in numbers from memory and hope. The system can
only verify a claim against a result that actually exists on disk.

### Organization — the structure is the safety net

The numbered-step layout (`workspace/NN_slug/` with `scripts/`, `data/`,
`outputs/`, `conclusions.md`) isn't bureaucracy — it's what makes a project
resumable, auditable, and handoff-ready. Each step declares what it hands the
next one (`data/next_step_output/`) and what it received
(`data/past_step_input/`), so the data lineage across steps is explicit.

**How to get the most out of it:**
- One question per step. Resist cramming three analyses into `01`.
- Let `conclusions.md` capture not just *what* you found but *why you moved on*
  — that's the connective tissue a paper is built from.
- Use the script-naming convention (`<NN>_<name>_v<k>`) the system enforces;
  it's what makes the iteration history readable a year later.
- Hand off with the session-handoff summary; the next session (or the next
  person) resumes from a real state snapshot, not your memory.

---

## Part 2b — Where the field-specific know-how comes from (skills)

Research OS makes sure your research is *done right*. It doesn't, by itself,
know how to run every field's methods — that capability comes from **skills**,
on-demand know-how documents the AI loads when it needs them (the open
agentskills.io standard). Your AI can pull from three sources, all through one
index:

- its **own skills** (the agent's bundled + learned library);
- the **K-Dense science pack** — a large library of deep science skills
  (bulk-RNA-seq, experimental design, literature review, cheminformatics, ...);
  install once with `research-os skills add-science-pack`;
- any other **Agent Skills** library you point it at.

On a fresh project, `sys_boot` tells the AI which skills match your domain and
mode, and it loads them before starting — so it runs *your field's* methods
with validated parameters instead of guessing. And it gets better over time:
RO distills the lessons from your projects into new skills and promotes the
durable ones into the agent's library, so it learns *your* way of working. The
division never changes: **skills = how to do this field's methods; Research OS =
how to do research right.** See [BEST_SETUP.md](BEST_SETUP.md) for setup.

## Part 3 — How the daemon watches over the work (optional but powerful)

For long or high-stakes projects, the optional daemon adds a layer that
*actively watches* rather than waits to be asked:

- it re-checks the project on a schedule, so problems it finds an hour into a
  long run actually reach the AI on its next turn;
- it surfaces **stale results**, **drift off-protocol**, **conclusions written
  with no audit**, and **stuck loops** — the failure modes you wouldn't catch
  yourself until too late;
- it turns soft "should" gates into hard, human-approved checkpoints for the
  steps that really matter.

Quick projects don't need it. Anything you'll defend — a submission, a
dissertation chapter, a result others will build on — benefits from it.
Start it with `research-os daemon start`; see [DAEMON.md](DAEMON.md).

---

## Part 4 — Long, reproducible, shareable work

Real research isn't only quick scripts. When the work is heavy or has to be
*exactly* reproducible, the daemon runs it as a tracked job and keeps the proof.

- **Long runs that don't freeze your chat.** `research-os daemon run "<cmd>"`
  runs a command as a tracked job — journaled, with its inputs, environment, and
  git commit recorded. `research-os daemon submit "<cmd>"` hands a job to SLURM
  and polls it to completion, surviving a login-node reboot.
- **Bit-for-bit reproducibility with containers.** If your pipeline ships as a
  Docker (or Podman) image, run it through the daemon:
  `research-os daemon docker myimage:1.0 -- python run.py`. The run records the
  **image and its content digest**, so "which exact image produced this output?"
  always has an answer. Add `--gpus all` for GPU work. (Kubernetes works via a
  thin wrapper — same contract.)
- **Sharing what you made.** Hand a finished workspace to a collaborator with a
  share archive, hand one *stage's* output to the next person with a contract
  (`program/pipeline_stage_handoff` writes a `HANDOFF.md` describing exactly what
  they get and owe back), or share the Docker image by digest so they run the
  identical pipeline. See [SHARING.md](SHARING.md).

The throughline of Parts 1–4 is one idea: **soft, trusted prose becomes hard,
verified structure** — a plan becomes numbered steps, a number becomes a grounded
claim, a run becomes a provenance record, a folder becomes a contracted handoff.
That's what lets the work hold up.

---

## Where to go next

- [START.md](START.md) — install + your first project.
- [SETUP_PROMPT.md](SETUP_PROMPT.md) — the one prompt that sets everything up.
- [RESEARCHER_GUIDE.md](RESEARCHER_GUIDE.md) — the full reference: every
  protocol, config knob, and power-user pattern.
- [SCENARIOS.md](SCENARIOS.md) — two worked projects end to end (a basic one and
  a deep PI-level program touching every capability).
- [PROJECT_LAYOUT.md](PROJECT_LAYOUT.md) — exactly what lives where.
