# Use Cases — which protocol for which researcher, which moment

Research OS is designed for the **full** research life-cycle, not just the
linear data → publication path. This document is a role × goal map: pick
your role, find your situation, see the protocol the AI will route to.

You don't need to memorise this. Just talk in plain English; `tool_route`
picks the protocol. This page exists so you know what's possible.

---

## By role

### The graduate student / postdoc running their own analyses

| You want to… | Say something like… | Protocol |
|---|---|---|
| Set up a new project from data + papers | "fill the intake" | `guidance/project_startup` |
| Run the next experiment | "run an EDA", "fit a logistic regression" | `guidance/analysis_plan` |
| Decide what to do next | "what should I do next" | `guidance/iterative_planning` |
| Sandbox-explore without paperwork | "just poke at this", "sanity check" | `guidance/casual_exploration` |
| Generate hypotheses from data | "do real EDA — no hypothesis yet" | `methodology/exploratory_data_analysis` |
| Compare two methods head-to-head | "benchmark RF vs XGB on this" | `methodology/method_comparison` |
| Write the paper | "draft the manuscript for a journal" | `synthesis/synthesis_paper` |
| Make a poster | "make me a conference poster" | `synthesis/synthesis_poster` |
| Make a dashboard | "build a dashboard" | `synthesis/synthesis_dashboard` |
| Wrap up a working session | "wrap up", "going to lunch" | `guidance/chat_handoff` |
| Come back next day | "pick up where we left off" | `guidance/session_resume` |

### The principal investigator / lab leader

| You want to… | Say something like… | Protocol |
|---|---|---|
| Read a draft paper for a journal club | "review this paper" | `guidance/quick_paper_review` |
| Compare 3-5 papers on a related-work search | "compare these papers", "journal club on these" | `literature/comparative_paper_review` |
| Get a weekly update for a meeting | "weekly update", "milestone update" | `synthesis/synthesis_progress_update` |
| Draft an NIH R01 | "draft an R01 grant" | `synthesis/synthesis_grant` |
| Draft the funder lay-summary section | "lay summary for the grant" | `synthesis/synthesis_lay_summary` |
| Vet a collaborator's analysis script | "review this code" | `guidance/code_review` |
| Respond to peer review on your paper | "draft a rebuttal" | `guidance/peer_review_response` |
| Package a finished project for a new lab | "send to a collaborator", "package for handoff" | `guidance/collaboration_handoff` |

### The methodologist / statistical consultant

| You want to… | Say something like… | Protocol |
|---|---|---|
| Teach a method to a consult-er | "explain mixed-effects models" | `methodology/methodological_consultation` |
| Justify a power calc for an upcoming RCT | "power analysis", "sample size" | `methodology/power_analysis` |
| Audit a dataset before recommending methods | "data quality audit" | `methodology/data_quality_audit` |
| Walk through methodology pick for a project | "which method should I use" | `methodology/methodology_selection` |
| Build the canonical pipeline for a subfield | "best-practice pipeline for snRNA-seq" | `methodology/deep_domain_research` |
| Pre-register the SAP | "freeze the analysis plan" | `methodology/preregistration` |
| Set up a simulation study (ADEMP) | "run a simulation study" | `methodology/simulation_studies` |

### The reviewer / journal-club host / reading-group leader

| You want to… | Say something like… | Protocol |
|---|---|---|
| Quick 30-min critique of a paper | "tear apart this paper" | `guidance/quick_paper_review` |
| Compare-and-contrast 3-5 papers | "journal club on these" | `literature/comparative_paper_review` |
| Critique a single figure from a paper | "critique Figure 2 of this paper" | `visualization/figure_critique` |
| Attempt to reproduce a published analysis | "reproduce this paper" | `methodology/reproduction_attempt` |
| Run a full systematic review (PRISMA) | "systematic review of X" | `literature/systematic_review` |
| Grade a body of evidence (GRADE) | "grade the evidence on X" | `literature/evidence_synthesis` |

### The communicator / outreach lead / press office

| You want to… | Say something like… | Protocol |
|---|---|---|
| Press release on a finding | "press release" | `synthesis/synthesis_lay_summary` (audience: press_release) |
| Patient-facing newsletter blurb | "patient newsletter explainer" | `synthesis/synthesis_lay_summary` (audience: patient_or_participant) |
| Twitter / Mastodon / Bluesky thread | "twitter thread on this paper" | `synthesis/synthesis_lay_summary` (audience: social_thread) |
| Lab blog post | "blog post about the project" | `synthesis/synthesis_lay_summary` (audience: blog_post) |
| Lay-summary box for an NIH grant | "funder lay-summary section" | `synthesis/synthesis_lay_summary` (audience: funder_lay_section) |

### The teacher / course instructor

| You want to… | Say something like… | Protocol |
|---|---|---|
| Build a lecture slide deck on a project | "build a teaching deck" | `synthesis/synthesis_slides` (audience: teaching) |
| Build a dashboard for a class | "teaching dashboard" | `synthesis/synthesis_dashboard` (audience: teaching) |
| Walk students through a method | "explain ANCOVA to me" | `methodology/methodological_consultation` |
| Have students reproduce a paper as an exercise | "reproduce this paper as a class exercise" | `methodology/reproduction_attempt` (audience: course_or_teaching) |

### The presenter / talk-giver

| You want to… | Say something like… | Protocol |
|---|---|---|
| Lab meeting slides | "lab meeting deck" | `synthesis/synthesis_slides` (audience: lab_meeting) |
| 12-minute conference talk | "conference slides, 12 min" | `synthesis/synthesis_slides` (audience: conference_talk_short) |
| Defense talk | "defense slides" | `synthesis/synthesis_slides` (audience: defense) |
| Invited seminar / job talk | "invited seminar deck" | `synthesis/synthesis_slides` (audience: invited_seminar) |
| Conference poster | "make a poster" | `synthesis/synthesis_poster` |

### The "I'm starting in the middle" researcher

You already have data + analyses + figures from before RO was set up. You
don't want to redo the intake.

| You want to… | Say something like… | Protocol |
|---|---|---|
| Plug an in-progress project into RO | "bringing this into Research-OS" | `guidance/mid_pipeline_entry` |
| Synthesize from results you computed elsewhere | "we already analysed this, just write it up" | `synthesis/synthesis_from_inputs` |
| Polish figures you already have | "polish my figures" | `visualization/visualization_workflow` |
| Critique a figure you already drafted | "critique this figure" | `visualization/figure_critique` |
| Resume a paused RO project | "pick up where we left off" | `guidance/session_resume` |

### The "I just want a viz" researcher

| You want to… | Say something like… | Protocol |
|---|---|---|
| Build a figure deck from a results table | "build me figures from this CSV" | `visualization/visualization_workflow` |
| Polish a single figure | "polish my figure" | `visualization/visualization_workflow` |
| Critique a figure | "critique this figure" | `visualization/figure_critique` |
| Just learn the figure conventions | "what's the figure style guide" | `visualization/figure_guidelines` |

### The "no project yet, just thinking" researcher

| You want to… | Say something like… | Protocol |
|---|---|---|
| Learn / compare methods before committing | "teach me about propensity scores" | `methodology/methodological_consultation` |
| Compare candidate papers in your area | "compare these foundational papers" | `literature/comparative_paper_review` |
| Power-justify an upcoming study | "how many subjects do I need" | `methodology/power_analysis` |
| Pre-register before data lands | "freeze the analysis plan" | `methodology/preregistration` |
| Choose a study design | "design the study" | `domain/research_design` |

---

## By depth of analysis

| Depth | When | Protocol |
|---|---|---|
| 5-minute napkin | "just poke at this", "sanity check" | `guidance/casual_exploration` |
| 30-minute appraisal | "review this paper" | `guidance/quick_paper_review` |
| Real EDA, hypothesis generation | "explore the data, find a hypothesis" | `methodology/exploratory_data_analysis` |
| Full per-step pipeline | "run the next experiment" | `guidance/analysis_plan` |
| Multi-method benchmark | "head-to-head comparison" | `methodology/method_comparison` |
| Subfield-grounded pipeline | "best-practice pipeline for X" | `methodology/deep_domain_research` |
| Full systematic synthesis | "systematic review on Y" | `literature/systematic_review` |
| Publication-grade synthesis | "draft the paper" | `synthesis/synthesis_paper` |

---

## By output type

| Want this output | Protocol |
|---|---|
| Polished single figure | `visualization/visualization_workflow` |
| Figure deck | `visualization/visualization_workflow` |
| Paper (IMRAD) | `synthesis/synthesis_paper` |
| Abstract | `synthesis/synthesis_abstract` |
| Poster | `synthesis/synthesis_poster` |
| Dashboard (offline HTML) | `synthesis/synthesis_dashboard` |
| Slides (lab / conference / defense / etc.) | `synthesis/synthesis_slides` |
| Internal / technical report | `synthesis/synthesis_report` |
| Grant narrative | `synthesis/synthesis_grant` |
| Lay summary / press release / blog | `synthesis/synthesis_lay_summary` |
| PI / advisor / weekly update | `synthesis/synthesis_progress_update` |
| Null-findings companion | `synthesis/synthesis_null_findings` |
| Critique brief (single paper) | `guidance/quick_paper_review` |
| Critique brief (single figure) | `visualization/figure_critique` |
| Comparative review brief (N papers) | `literature/comparative_paper_review` |
| Reproduction report | `methodology/reproduction_attempt` |
| Power justification paragraph | `methodology/power_analysis` |
| Data-quality audit report | `methodology/data_quality_audit` |
| Methodological consultation notes (optional) | `methodology/methodological_consultation` |

---

## You don't have to choose

`tool_route` picks the right protocol from a plain-English prompt. The
table above exists so you can see what's available and confirm the AI's
choice. If the wrong protocol gets picked, just say "actually I meant
X" — the AI re-routes without re-loading the workspace.

When you genuinely don't know what you want, say so:
> "I have some data and some ideas — help me figure out where to start."

The AI will ask a clarifying question. The router treats ambiguity as a
1-sentence follow-up cost, not as a wrong guess.
