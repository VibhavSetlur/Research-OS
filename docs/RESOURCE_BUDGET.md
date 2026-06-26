# Resource budget — turn "stay within budget" prose into enforced rlimits

## The pain (concrete, named)

Vibhav works on a shared HPC node. The autopilot protocol says, in prose,
to "page before a run whose estimated compute / memory / disk cost is
large relative to the project's budget." But there IS no budget the system
holds, and the prose is advisory — so:

1. A long job uses the daemon sandbox's GENERIC defaults (4 GB AS, 900s
   CPU, 2 GB file). On a shared node those are either too loose (a runaway
   job hogs the box and gets the user yelled at / OOM-killed by the
   scheduler) or irrelevant (the real budget is "don't exceed 16 GB and
   2 h because that's my fair share").
2. The researcher has no single place to declare "this project's runs may
   use up to X memory / Y wallclock / Z disk." So every run is a guess.

This is the same soft/hard gap the gate work closed, one layer down: a
limit the researcher cares about lives only as prose and generic defaults,
never as an enforced fact.

## The fix (one sentence)

Let the researcher declare a per-project resource budget once in
`researcher_config.yaml`, and have the daemon resolve it into the ACTUAL
`ResourceLimits` (rlimits + wallclock) applied to every submitted run — so
"stay within budget" becomes a hard, enforced bound, not a hope.

## Design

### One declaration, in the config the researcher already edits

```yaml
# inputs/researcher_config.yaml
resource_budget:
  memory_mb: 16384      # RLIMIT_AS  — virtual memory ceiling per run
  cpu_seconds: 7200     # RLIMIT_CPU — CPU-seconds (SIGXCPU then KILL)
  wall_seconds: 7200    # wallclock kill (the watchdog)
  file_size_mb: 51200   # RLIMIT_FSIZE — largest single file a run may write
  open_files: 4096      # RLIMIT_NOFILE
  # processes: 256      # RLIMIT_NPROC — OFF by default (shared-host footgun)
```

Every field is OPTIONAL. A field that is absent falls back to the sandbox
default (today's behaviour). A field set to `null` or `0` means "do not
cap this dimension" (unbounded — the researcher's explicit choice). So the
budget can both TIGHTEN (shared node) and LOOSEN (dedicated box, big fit)
relative to the generic defaults, deliberately.

### Resolution — one pure function, two consumers

`daemon/resource_budget.py`:

* `load_budget(root) -> dict` — read the `resource_budget:` block from the
  project config, coerce + validate, fail-safe to `{}` (no budget → today's
  defaults). stdlib + the one yaml dep already used by config.py.
* `apply_budget(limits, budget) -> ResourceLimits` — overlay the budget
  onto a base `ResourceLimits`, field by field, honouring the
  absent/null/0 semantics above. Pure, trivially testable.
* `resolve_run_limits(root, base=None) -> ResourceLimits` — the convenience
  the runner calls: base (or sandbox default) ← budget overlay.

The runner (`daemon/runners.py`, where today it does
`self.sandbox_limits or _sb.ResourceLimits()`) calls
`resolve_run_limits(root, base=self.sandbox_limits)` so an explicit
per-submit limit still wins, then the project budget fills the rest, then
the generic default backs everything. Precedence, tightest-intent-first:

    explicit per-run limit  >  project budget  >  sandbox default

### Surfaced, not silent

* The run's `_sandbox_meta["limits"]` already records the effective caps,
  so `daemon diff` / `/v1/runs` show exactly what bound the run. A run that
  was killed for exceeding budget is therefore explainable after the fact.
* `/v1/capabilities` and `daemon status` gain a `resource_budget` block so
  the researcher (and the AI) can SEE the active budget before submitting —
  closing the "page before spending, cite the budget you based it on"
  prose with a real number to cite.

### Why this is not over-reach

* It does NOT invent a cost ESTIMATOR (that would be doing the science /
  guessing). It enforces a ceiling the researcher declared. The autopilot
  `tool_task:run` gate still pages before a big run; the budget makes the
  "relative to budget" half of that prose concrete.
* No daemon, no budget block → identical to today (sandbox defaults). Pure
  opt-in. Existing projects unaffected.
* Reasoning side never touches this — it's a daemon execution concern. The
  AI just SEES the budget via capabilities (read by shape, like everything
  else) so it can reason about whether a planned run fits.

## Build order

1. This doc.
2. `daemon/resource_budget.py`: load_budget / apply_budget /
   resolve_run_limits (pure, stdlib).
3. Wire `daemon/runners.py` to resolve via the budget.
4. Surface the active budget in `/v1/capabilities` + `daemon status`.
5. Tests (load/coerce/fail-safe, overlay precedence incl. null=uncapped,
   runner integration) + live verify a budget actually bounds a run.
