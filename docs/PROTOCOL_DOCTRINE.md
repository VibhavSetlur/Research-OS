# Protocol doctrine — scaffold, not script

A Research OS protocol gives the AI a **scaffold for reasoning**, not
a **script to execute**. This is the single most important rule for
anyone editing a protocol or adding a new one. If you internalise
nothing else from this file, internalise that.

## The principle

A scaffold names:
1. The **questions** worth asking about a project
2. The **dimensions** worth reasoning over
3. The **grounding** the answer must cite
4. The **artefacts** that record the reasoning

A scaffold does NOT name:
1. The specific method
2. The specific tool / library / CLI
3. The specific threshold / cutoff / hyperparameter
4. The specific step sequence

The AI fills in the specifics per project, from the literature, never
from training memory or from a table in the protocol.

## Why

Three reasons.

**Reasoning generalises; recipes don't.** A protocol that says "use
DESeq2 with ~condition design" is correct for one decade in one
subfield and silently wrong everywhere else. A protocol that says
"reason about the outcome's distributional family + the dependency
structure + the field's current best-practice estimator" is correct
in every era of every field.

**Prescription erodes the AI's reasoning surface.** When a protocol
hands the AI an answer, the AI stops looking — even when the answer
is wrong for the current project. Scaffolds force the AI to *justify*
each commitment, which surfaces the cases where the default would
have been wrong.

**Maintenance debt.** A repository of 47 prescriptive protocols
becomes a repository of 47 things that go stale at different rates.
Scaffolds are stable across decades because the *questions* don't
change as fast as the *answers*.

## How to spot prescription in a protocol

A description that contains any of the below is suspect:

- A finite menu of methods mapped from data shape, like
  `Continuous · independent · low-D → OLS / Ridge / LASSO`. *(Real
  example, now removed.)*
- A named threshold without a citation, like `CFI ≥ 0.95`,
  `|SMD| > 0.10`, `I² > 75% = considerable`. The threshold may even
  be the field convention — but stating it without a source pushes
  the AI to copy it instead of looking it up for THIS field.
- A specific tool / library name as the default, like "use dowhy /
  econml / SHAP / MICE". The tool is fine to mention as an example;
  it is not fine to default-pick.
- A canned step sequence with no branch points, like
  "randomisation_check → ITT/PP → MICE → primary_analysis →
  safety → CONSORT". Each step might be reasonable; the
  fixed order asserts that this is the right shape for every project
  in the methodology, which it never is.
- A specific split ratio, sample-size cutoff, or count, like
  "70/15/15 split", "Aim for 30-100 codes", "minimum 10 studies".
  Numerical defaults masquerade as scaffolds; they're recipes.

## How to write scaffold language

Patterns that work:

- **Name the question, not the answer.** "What's the outcome's
  distributional family on this sample?" beats "Use a Poisson GLM for
  count data."
- **Name the dimension, not the value.** "Justify the split from the
  deployment regime" beats "Use a 70/15/15 split."
- **Demand grounding, not a tool.** "Surface the field's current
  best-practice estimator via `tool_research_method`" beats "Use
  DESeq2."
- **Frame thresholds as field-specific.** "Cite the source for
  whichever cutoff is used" beats "Use CFI ≥ 0.95."
- **State the failure mode, not the procedure.** "Treating clusters
  as fixed when they were fit on the same data inflates type-I error"
  beats "Run the test on a holdout sample."

## When prescription IS the right answer

Some commitments aren't optional and shouldn't be scaffolded around:

- **Reproducibility primitives.** "Set RNG seeds explicitly; print
  library versions" is prescription, but it's prescription about the
  *system*, not about the *science*. Keep it.
- **Mechanical conventions.** "Save figures to
  `outputs/figures/` at ≥300 DPI" is prescription. It's about file
  layout that downstream tooling depends on, not about the analysis.
  Keep it.
- **Universal failures of inference.** "Cluster-then-DE without
  pseudo-bulk aggregation is pseudo-replication" is a fact about
  inference, not a methodology choice. Stating the failure mode as a
  rule is fine.

The line: prescription about WHO uses what tool is bad; prescription
about HOW the system records the work is good.

## Reviewer's checklist

Before merging a protocol change, walk every step:

1. Could a researcher in a different field use this step? If the
   answer requires renaming the methodology, it's scaffolded; if it
   requires rewriting the step, it's prescribed.
2. Does the step name a tool or threshold? If yes, is it tagged as
   "the literature names" / "the field's reporting standard names" /
   "cite the source"? If not, rewrite.
3. If you removed every tool name, library name, and numerical
   threshold from the step description, would the step still tell
   the AI what to do? If yes, the step is a scaffold. If no, it was
   a recipe.
4. Does the step demand citation for every commitment? Reasoning
   without grounding is just opinion.

## Examples

Prescription:

```yaml
- id: factor_structure
  description: |
    EFA / CFA. Report:
      CFA → CFI, TLI (≥0.95), RMSEA (≤0.06), SRMR (≤0.08).
```

Scaffold:

```yaml
- id: factor_structure
  description: |
    Decide between exploratory and confirmatory factor analysis.
    Report whichever fit indices the field treats as canonical for
    this kind of model. Thresholds are field-specific — cite the
    source.
```

Prescription:

```yaml
- id: data_split
  description: |
    Stratified 70/15/15 split. Set random_state explicitly.
```

Scaffold:

```yaml
- id: evaluation_regime
  description: |
    The split mirrors the deployment regime. Time-forward
    deployment → time-forward split. Cross-institution deployment →
    leave-one-institution-out split. A random k-fold split requires
    a positive justification, not a default.
```

## Cross-referencing protocols (`see_also`, optional)

A growing protocol library is only useful if a researcher (or the AI
following a protocol) can find adjacent work without scanning every
file. The recommended convention for cross-references is a top-level
`see_also:` field carrying a short list of related protocol IDs.

```yaml
id: methodology/missing_data_strategy
name: "Missing-data strategy"
version: '1.9.3'
see_also:
  - methodology/multiple_comparisons     # both shape the analysis plan
  - audit/preregistration                # missingness assumptions belong in the prereg
  - methodology/sensitivity_analysis     # sensitivity sweep tests robustness
steps: ...
```

**When to populate `see_also`:**

- The reader of THIS protocol almost always needs ONE of those other
  protocols within the same session (sequential or branching).
- The protocols share a foundational artefact (a registered plan, a
  shared assumption log, a common output the reader will return to).
- The relationship is non-obvious — the trigger phrases of the related
  protocol wouldn't surface it via `tool_route` on their own.

**When NOT to add `see_also`:**

- The related protocol is already reachable via `next_protocol`
  (that's the linear successor; `see_also` is for lateral siblings).
- The relationship is "any audit protocol" or "any synthesis protocol"
  — too coarse to be actionable.
- You're padding to make a protocol look thorough. Empty / blank
  `see_also:` is a docs smell; better to omit the field.

**Status (v1.9.3):** the field is documented but not yet wired into
any tool or auto-rendered surface. A future release may surface
`see_also` in `sys_protocol_get format='summary'` and in the workflow
DAG. Adding `see_also` to your own protocols today is a low-risk
investment — the schema accepts the field; downstream tools will pick
it up when they're built.

## No version commentary in live bodies

Protocol bodies, MCP tool descriptions, and code docstrings/comments
must read as **timeless current doctrine**. They describe what the
system does NOW. They do not narrate which version added which rule
or which version fixed which bug.

**Where version history lives:**

| Surface | Carries |
|---|---|
| `CHANGELOG.md` | What changed in each release, with rationale |
| `git log` / `git blame` | Line-level provenance |
| `version:` (protocol YAML) | Which package release this protocol shipped with |
| `schema_version:` (protocol YAML) | Bumps only when prescriptive structure changes |
| `last_reviewed:` (protocol YAML) | When a maintainer last read this for staleness |

**What stays out of live bodies:**

- "`v1.4.0` added X" / "`v1.5.0` fixed Y" / "as of `v1.3.4` we …"
- "previously this clobbered, now we …"
- "promoted from WARN to BLOCK in `v1.5.0`"
- "the `v1.3.4` stress test caught this"
- "carried over from the `v1.5.1` stress audit"

**Why:** every load of a live doctrine surface pays the token cost.
A 13-protocol routing call that has 200 lines of version chatter
strung across the protocols burns ~3 KB of context on history the
reader can't act on. The CHANGELOG already carries the history;
readers who need it know where to find it.

**The rule for inline WHY comments.** Comments that explain a
*non-obvious mechanical reason* a piece of code looks the way it
does (a workaround, a subtle invariant, a hidden constraint) stay.
Comments that *narrate* the project history ("`v1.3.4` added this
because the `v1.3.3` stress test surfaced…") get stripped down to
the timeless WHY: "this matches `^##\s` not `^##` so that `###`
sub-headers don't truncate the parent section."

**Enforcement.** `scripts/lint_no_version_chatter.py` scans the live
surfaces (protocols/, server.py, tools/actions/, project_ops.py,
wizard.py) and flags `v\d+\.\d+(?:\.\d+)?` references plus the
common "previously this / was the bug / promoted from WARN to BLOCK
in vX" phrasings. Run with `--strict` to fail on any hit; run with
`--diff` to fail only on hits in files modified relative to HEAD.
Preflight invokes it in `--diff` mode so new commits can't introduce
new chatter without the maintainer noticing.

---

If you read a step in a protocol that fails the checklist above,
file the rewrite or do it yourself. The point of this file is that
the principle outlives any one person editing the codebase.
