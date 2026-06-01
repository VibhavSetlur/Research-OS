# Cheatsheet — every Research OS command worth knowing

One page. Print it. Pin it.

---

## CLI (two commands total)

```bash
research-os init                          # scaffold THIS folder
research-os init my-project --name "X"    # scaffold ./my-project
research-os init . --force                # re-scaffold (preserves data + config)
research-os init --ide cursor,claude      # only those two IDEs
research-os start                         # run the MCP server (global)
```

Your IDE auto-launches `research-os start` per project. You rarely run
it by hand.

---

## Project-setup prompts (researcher-facing)

```
fill out the intake
look at my data
read the files i just dropped
i'm bringing this into research-os, we've been working on it for months
we already analysed this, just write it up
```

## Run analyses

```
run a baseline EDA
fit a logistic regression and check assumptions
do real EDA — i don't have a hypothesis yet
benchmark random forest vs xgboost head-to-head
data quality audit on this csv
power analysis for the IRB
design the evaluation strategy
design the sweep, equal budgets
freeze the analysis plan
this isn't working — abandon it and try X
what should i do next?
```

## Read / understand

```
review this paper
tear apart this paper as a tough reviewer
journal club on these three papers
explain mixed-effects models to me
teach me propensity scores before i use them
reproduce this paper
find me papers about X
do a systematic review of X
data ethics review on this dataset
```

## Visualization

```
make me a figure from this CSV
polish my figures for the talk
build a figure deck for the paper
critique this figure
remake this chart for the dashboard
make figure 2 with panels A B C D
order my figures for the paper
check colour accessibility on my figures
```

## Writing + synthesis

```
workshop the title
draft the methods
draft the results
draft the discussion
tighten the limitations
draft the cover letter
draft the end matter (data avail / CRediT / etc.)

draft the paper for a journal submission
draft an NIH R01 narrative
make a dashboard for executives
build a poster for the conference
build a slide deck for my defense
build slides for a 12-minute talk
make a one-pager for the poster session
write a lay summary for the public
press release on this finding
weekly update for my PI
status update for my advisor
```

## Audit + ship

```
check reproducibility
audit my workspace for issues
is this ready to submit
fix my workspace
```

## Session control

```
wrap up the session
pick up where we left off
hand off to a collaborator
switch to autopilot mode
switch to manual mode
push back if you disagree with my plan
```

---

## Routing primitives (the AI calls these — you don't)

`sys_boot` — one-call session start
`tool_route(prompt)` — picks the right protocol from your message
`sys_protocol_get format='summary'` — load step headings (~300 tokens)
`sys_active_tools(protocol)` — tool shortlist per protocol
`sys_help` — AI orientation block (which protocol does what)
`sys_active_project` — which project did the global server resolve

---

## Where files go

```
inputs/raw_data/      ← your data (immutable — RO blocks writes)
inputs/literature/    ← your PDFs (immutable — RO blocks writes)
inputs/context/       ← your notes / drafts / past reports
docs/                 ← research question, domain, glossary
workspace/            ← AI lives here; numbered experiment folders
workspace/scratch/    ← AI sandbox (gitignored)
synthesis/            ← final outputs (only created when you ask)
.os_state/            ← internal — do NOT edit by hand
```

---

## Autonomy slider (set in `inputs/researcher_config.yaml`)

```
manual      → asks before every tool call (learning / watching)
supervised  → reads + searches freely; asks for big steps (default)
autopilot   → runs end-to-end; asks only before final synthesis
```

Switch mid-session: "switch to manual mode" / "switch to autopilot".

---

## When something is wrong

```
the AI is making bad choices  → "switch to manual mode"
the workspace looks broken    → "fix the workspace"
the AI seems to forget        → "show me sys_help"
the chat is too long          → "hand off the session"
something deleted by mistake  → "list checkpoints" → "rollback to <id>"
```

---

## Docs (start with the first one that fits)

| File | Read when |
|---|---|
| `FIRST_HOUR.md` | First time, top to bottom |
| `QUICKSTART.md` | You want the dense version |
| `USE_CASES.md` | Pick the right protocol by role × goal × output |
| `RESEARCHER_GUIDE.md` | Full non-technical walkthrough |
| `PROTOCOLS.md` | Catalogue of all 82 protocols |
| `TOOLS.md` | Catalogue of all 140 MCP tools |
| `AI_GUIDE.md` | If you want to know what the AI is doing |
| `FAQ.md` | When something is weird |
