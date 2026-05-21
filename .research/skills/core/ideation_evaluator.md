---
skill_id: "ideation_evaluator"
version: "1.0.0"
description: "Triage random researcher thoughts into scratchpad notes, queued tasks, or isolated experiment branches before execution."
category: "core"
---

# Skill: Ideation Evaluator

Use this skill when the user introduces a random jump mid-workflow: a new robustness concern, a paper/link, a half-formed metric, a CSV, or a question like "did we check X?"

## Protocol

1. Do not immediately execute analysis code.
2. Capture the thought in `01_workspace/scratchpad/` when it came from an external note/file, or append it directly to `01_workspace/lab_notebook.md` when it came through chat.
3. Classify the thought:
   - `log_only`: contextual note that does not change current work.
   - `queue_later`: plausible follow-up, but not blocking the active experiment.
   - `branch_now`: a concrete hypothesis, robustness check, or method switch that could change results.
   - `intake_gap`: missing information that blocks interpretation.
4. Append a lab notebook entry with timestamp, source, classification, rationale, active experiment, and recommended action.
5. If classification is `branch_now`, propose a new experiment id using `exp_<next_number>_<short_slug>` and ask whether to pause the current experiment and branch.
6. If classification is `queue_later`, add a TODO-style item to `01_workspace/scratchpad/queued_ideas.md`.

## Branching Rule

Create an experiment branch only after the user approves or when the user explicitly asks to explore the idea now. The branch must live under:

```text
02_experiments/exp_<NNN>_<slug>/
  scripts/
  outputs/
    figures/
    tables/
    artifacts/
    analysis/
  decisions.yaml
```

The first decision in `decisions.yaml` must record the parent experiment and the reason for divergence.

## Response Template

When triaging a random jump, respond briefly:

```text
I logged this in `01_workspace/lab_notebook.md` as <classification>.
Recommendation: <branch now | queue | log only>, because <one-sentence rationale>.
Should I create `<experiment_id>` from `<active_experiment>`, or keep it queued?
```
