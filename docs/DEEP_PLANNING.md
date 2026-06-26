# Deep iterative planning → roadmap → autonomous build

This is the workflow for a researcher who wants to think a project through
*deeply*, capture it as a durable plan, and then let the AI (Hermes or any MCP
client) build toward that plan — re-planning from results, branching the
analysis where the evidence forks, and never losing the thread back to the
goal.

It is built from three protocols that chain together. None of them is a script;
each is a reasoning scaffold (see [PROTOCOL_DOCTRINE.md](PROTOCOL_DOCTRINE.md)).
The AI is the brain — the protocols name the questions, the artefacts, and the
gates, and leave the method, tools, and thresholds to be decided per project
from the literature.

## The three protocols

| Protocol | Role | Routes from |
|---|---|---|
| `methodology/deep_planning` | Build a rigorous, **branchable** roadmap step by step | "plan this deeply", "make a roadmap", "think through the whole project" |
| `guidance/roadmap_execution` | The **autonomous build loop** that executes the roadmap and re-plans | "build toward this autonomously", "execute the roadmap", "run the plan" |
| `guidance/analysis_paths` | When + how to **branch** the analysis, compare branches, merge or abandon | "branch the analysis", "fork an alternative approach", "compare these paths" |

They chain: `deep_planning → roadmap_execution → (loops, calling analysis_paths
when a fork opens) → synthesis / dead_end_routing`.

## The single thread: `inputs/research_plan.md`

Everything hangs off one living document — `inputs/research_plan.md`. Deep
planning writes it; roadmap execution reads it, executes against it, and keeps
it in sync; analysis paths records branch outcomes in it. It carries an
**append-only iteration log** so the plan's history is never lost — a fresh AI
can pick up the project cold and know what to build next and why.

The roadmap is a scaffold, not a frozen spec. It names the goal, the
milestones, the decision points + branches, the load-bearing assumptions, and
the sequence. It does **not** pin the method, library, or threshold for a
milestone that hasn't run yet — those are chosen when the milestone executes,
from the literature.

## Stage 1 — Deep planning (`methodology/deep_planning`)

The AI helps the researcher turn an ambitious goal into a branchable roadmap:

1. **Orient + frame** — restate the goal as a researchable *question* with
   observable success criteria and constraints.
2. **Decompose** — break the goal into milestones (question / produces /
   depends-on / rough size) at the altitude the researcher reasons over.
3. **Mark uncertainty** — for each milestone, surface the assumptions it rests
   on, what would falsify them, and how much each could move the plan.
   Load-bearing assumptions get registered as tracked hypotheses.
4. **Identify branch points** — find the decision points where a result will
   select among genuinely different next moves, and name the branches + what
   decides each.
5. **Sequence** — order the work so the highest-uncertainty,
   highest-consequence questions resolve early.
6. **Capture the roadmap** — write it all to `inputs/research_plan.md` with an
   iteration-log section.
7. **Set the iteration contract** — make explicit that the plan is revisited
   after each milestone, and state when the AI will re-plan *with* the
   researcher vs. autonomously.

The plan is **iterative by design**: re-enter this protocol any time results
demand a reshape. Re-planning appends to the iteration log, never overwrites.

## Stage 2 — Autonomous build (`guidance/roadmap_execution`)

Given the roadmap, the AI runs an outer loop toward the goal:

1. **Load the thread** — `sys_boot` + the roadmap + path state + tracked
   hypotheses; reconstruct exactly where the project stands.
2. **Select the next milestone** whose dependencies are met (or follow the
   branch a resolved decision point just selected).
3. **Execute the milestone** by handing it to `guidance/analysis_plan` (the
   per-step loop that grounds the method, writes scripts, produces artefacts).
   Long milestones run as background tasks so the loop can checkpoint + resume.
4. **Record the result as evidence** — what it showed, which assumptions it
   moved, which decision point it resolved; finalize the step + checkpoint.
5. **Re-plan from the evidence** — routine result → continue; resolved decision
   point → close ruled-out branches; strained/falsified assumption → reshape
   downstream milestones; genuine fork → consult `analysis_paths`. Every
   reshape appends to the iteration log.
6. **Pause or proceed** — judged from reversibility + cost, not a step count.
   The loop pauses for the researcher when the goal's framing or a core
   assumption is in question.
7. **Loop or converge** — back to step 2 until the success criteria are met,
   then close out and route to synthesis (or dead-end routing).

### Autonomy + floor gates

The loop respects `interaction.autonomy_level`:

- **manual / supervised** — present the result + roadmap diff + proposed next
  milestone and wait every loop.
- **adaptive (default)** — flow on cheap, reversible moves; pause on the
  consequential ones.
- **autopilot** — flow through milestones, *except* the floor gates.

**Floor gates page even on autopilot** (mirroring `guidance/autopilot`'s
enforced floors): the final deliverable compile, declaring a milestone/path a
dead end (`sys_path operation='abandon'`), package installs, spending real
money, and large background jobs.

## Stage 3 — Branching the analysis (`guidance/analysis_paths`)

When a result opens two rival next moves worth pursuing in parallel, this
protocol keeps the multi-path exploration legible:

- **Decide whether to branch at all** — branch only when staying single-track
  would lose information (rival methods worth comparing; the evidence must
  decide; a split that would contaminate the main analysis). A minor tweak is a
  script version-bump, not a branch.
- **Name the branches** by the axis that distinguishes them
  (`cox_ph_complete_case` vs `cox_ph_imputed`), created with
  `sys_path operation='create' branch_of=<parent>` so the lineage is recorded.
- **Hold them comparable** — same input data, same question, same metric;
  differ on exactly one axis; set the comparison criterion *before* seeing
  results.
- **Compare + decide** — merge the winner, abandon a loser (preserved, never
  deleted), or keep both when the comparison itself is the finding.
- **Merge** = commit the project's direction to the winner and record it in the
  roadmap; **abandon** = `sys_path operation='abandon'` (a floor gate) +
  capture the lesson, then route via `guidance/dead_end_routing`.

## How this relates to the lighter planning protocols

- `guidance/iterative_planning` answers **"what's the single best next step?"**
  per turn. Use it when the researcher wants the AI to propose moves
  one-at-a-time without committing to a whole roadmap.
- `methodology/deep_planning` builds the **whole branchable roadmap** up front.
  Use it for an ambitious goal too large for a single next-step decision.
- `guidance/analysis_plan` is the **per-step execution loop** both of the above
  drive into; `roadmap_execution` is the outer loop that calls it repeatedly.

## Quick start for a researcher

> "Plan this deeply: I want to know whether <X> drives <Y>, controlling for
> the obvious confounds, ending in a paper-ready figure."

The AI routes to `methodology/deep_planning`, builds the roadmap with you, and
writes it to `inputs/research_plan.md`. Then:

> "Build toward this autonomously — page me before anything irreversible."

The AI routes to `guidance/roadmap_execution` and runs the loop at your
autonomy level, branching the analysis via `guidance/analysis_paths` wherever
the evidence forks, and keeping the roadmap in sync the whole way.
