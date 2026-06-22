# File & output versioning (research projects)

> This is the convention for files **inside a research project** scaffolded by
> Research OS. For versioning *the Research OS package itself*, see
> [RELEASING.md](RELEASING.md).

Research is iterative: you re-run a step, a figure improves, a draft gets
rewritten. The question is always *"do I overwrite or keep a copy?"* This is
the one rule, so the AI and the researcher never guess.

## The rule

| Artifact | Convention | Why |
|---|---|---|
| **Analysis scripts** you iterate on | `*_v1.py`, `*_v2.py` … keep prior versions | A failed/abandoned approach is evidence; the diff is the story |
| **Figures / tables / captions** | overwrite in place (`fig_1.png`) | The *script* that produces them is versioned; the image is derived |
| **Synthesis deliverables** (paper / poster / slides / dashboard PDFs) | overwrite the live file; the previous good render is auto-archived to `synthesis/archive/<name>_<timestamp>.<ext>` on recompile | You want one canonical `paper.pdf`, but never silently lose a good render |
| **Data you produced** (`outputs/*.csv`, processed datasets) | overwrite in place; the producing script is versioned | Reproducible from the versioned script |
| **`inputs/raw_data/` + `inputs/literature/`** | source-of-truth; soft-guarded (`force=true` + your OK to overwrite) | Your original data + papers — the AI shouldn't silently rewrite them |
| **Rest of `inputs/`** (`context/`, `intake.md`, `researcher_config.yaml`) | the AI maintains these for you | Intake + context can come from files you drop OR from what you tell the AI in chat |

**One canonical name, versioned history where it matters.** Don't create
`paper_final_v3_REAL.typ`. The live file keeps its plain name; history lives in
`synthesis/archive/` (deliverables) or in `_vN` script suffixes (analysis code).

## "Did the work actually land?" — the existence gate

Every protocol declares `expected_outputs`. At the end of a protocol the
injected completion step calls **`tool_verify(scope='outputs')`**, which checks
each declared output against the filesystem and reports it as:

- **present** — exists and is non-empty ✅
- **empty** — exists but has no real content → regenerate it
- **missing** — was never created → re-run the step that produces it

If anything is missing or empty, **do not log the protocol `completed`** —
regenerate the gap (bump a `_vN` if a prior good copy exists), then re-verify.
This is the "go back and create it / make a new version" loop: the system
refuses to call thin air "done".

```
tool_verify(scope='outputs')                  # the active protocol's outputs
tool_verify(scope='outputs', all_protocols=true)   # sweep the whole project
tool_verify(scope='outputs', min_bytes=200)        # stricter "non-empty" bar
```

`sys_protocol_validate` gives the same existence picture for a single named
protocol (now also reporting `non_empty` per output and an `empty_count`).
