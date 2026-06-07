"""Tool definitions for the research domain."""
from __future__ import annotations

from typing import Any


RESEARCH_TOOL_DEFINITIONS: dict[str, dict[str, Any]] = {
    "tool_web_scrape": {
        "short": "Scrape a webpage and return markdown content. Use when fetching one URL as text.",
        "description": "Scrape a webpage and return markdown content.",
        "category": "search",
        "inputSchema": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    },
    "tool_literature_download": {
        "short": "Download a paper PDF + .meta.yaml sidecar. Use when grabbing a specific reference.",
        "description": "Download a paper PDF. Default scope is inputs/literature/ (project-wide). Pass step_id='NN_<slug>' to save it under workspace/<step>/literature/ instead. Writes a .meta.yaml sidecar with title/authors/year/doi if provided so synthesis can cite it correctly.",
        "category": "search",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "filename": {"type": "string"},
                "step_id": {
                    "type": "string",
                    "description": "Optional: NN_<slug> to scope the download to that experiment step's literature folder.",
                },
                "metadata": {
                    "type": "object",
                    "description": "Citation metadata to embed in the sidecar (title, authors, year, doi, venue, source).",
                },
                "skip_unpaywall": {"type": "boolean"},
            },
            "required": ["url", "filename"],
        },
    },
    "tool_literature_search_and_save": {
        "short": "Search provider + download top-N PDFs with metadata. Use when sourcing literature for a step.",
        "description": "Search a provider, download the top-N PDFs into the chosen scope (project or step), preserve citation metadata. One-shot 'find + save' for literature you want backing a specific analysis step.",
        "category": "search",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "source": {
                    "type": "string",
                    "description": "semantic_scholar | crossref | pubmed | arxiv (default semantic_scholar)",
                },
                "step_id": {"type": "string"},
                "limit": {"type": "number", "description": "Hits to consider (default 5)."},
                "download_top": {"type": "number", "description": "Top-N to actually download (default 3)."},
            },
            "required": ["query"],
        },
    },
    "tool_step_literature_list": {
        "short": "List PDFs in a step's literature/ (or all steps). Use when auditing per-step references.",
        "description": "List PDFs in a specific experiment step's literature/ folder, OR across every step when no step_id is given.",
        "category": "search",
        "inputSchema": {
            "type": "object",
            "properties": {
                "step_id": {"type": "string"},
            },
        },
    },
    "tool_python_exec": {
        "short": "Execute a workspace Python script (host permissions). Use when running .py analysis.",
        "description": "Execute a Python script located in the workspace. Runs with host permissions — do NOT execute untrusted code.",
        "category": "execution",
        "inputSchema": {
            "type": "object",
            "properties": {
                "script_path": {"type": "string"},
                "timeout": {"type": "number"},
            },
            "required": ["script_path"],
        },
    },
    "tool_r_exec": {
        "short": "Execute a workspace R script. Use when running .R analysis.",
        "description": "Execute an R script located in the workspace.",
        "category": "execution",
        "inputSchema": {
            "type": "object",
            "properties": {
                "script_path": {"type": "string"},
                "timeout": {"type": "number"},
            },
            "required": ["script_path"],
        },
    },
    "tool_julia_exec": {
        "short": "Execute a workspace Julia script. Use when running .jl analysis.",
        "description": "Execute a Julia script located in the workspace.",
        "category": "execution",
        "inputSchema": {
            "type": "object",
            "properties": {
                "script_path": {"type": "string"},
                "timeout": {"type": "number"},
            },
            "required": ["script_path"],
        },
    },
    "tool_bash_exec": {
        "short": "Execute a workspace Bash script. Use when running .sh utilities.",
        "description": "Execute a Bash script located in the workspace.",
        "category": "execution",
        "inputSchema": {
            "type": "object",
            "properties": {
                "script_path": {"type": "string"},
                "timeout": {"type": "number"},
            },
            "required": ["script_path"],
        },
    },
    "tool_package_install": {
        "short": "Install Python packages + append to environment/requirements.txt. Use when adding deps.",
        "description": "Install Python packages and append them to environment/requirements.txt. In autopilot mode, requires confirmed=true (server-enforced autopilot floor gate — see guidance/autopilot.yaml).",
        "category": "execution",
        "inputSchema": {
            "type": "object",
            "properties": {
                "packages": {"type": "array", "items": {"type": "string"}},
                "confirmed": {"type": "boolean", "description": "Required in autopilot mode. Researcher consent."},
            },
            "required": ["packages"],
        },
    },
    "tool_data": {
        "short": "Unified data tool. operation=sample|profile|convert.",
        "description": "Unified data-inspection / conversion dispatcher. operation='sample' returns N rows from a tabular dataset (CSV, Parquet, Feather, JSON, Excel) via head|random|tail strategy. operation='profile' returns schema, dtypes, missingness, descriptive stats, and suggested next steps for a tabular dataset. operation='convert' converts a dataset between CSV / Parquet / Feather / RDS. Every legacy tool_data_sample / tool_data_profile / tool_data_convert name aliases to this entry point with operation injected via _ALIAS_PARAM_INJECTION so callers using the older per-operation names keep working unchanged.",
        "category": "data",
        "inputSchema": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["sample", "profile", "convert"],
                    "description": "Which data sub-operation to invoke.",
                },
                "filepath": {
                    "type": "string",
                    "description": "Path to the dataset file. Required for every operation.",
                },
                # operation='sample' kwargs
                "n_rows": {
                    "type": "number",
                    "description": "operation='sample' — REQUIRED. Number of rows to sample.",
                },
                "strategy": {
                    "type": "string",
                    "description": "operation='sample' — head | random | tail (default: head).",
                },
                # operation='convert' kwargs
                "output_format": {
                    "type": "string",
                    "description": "operation='convert' — REQUIRED. Target format (csv | parquet | feather | rds).",
                },
            },
            "required": ["operation", "filepath"],
        },
    },
    "tool_slurm_submit": {
        "short": "Submit a SLURM job from researcher_config.runtime.cluster_defaults.",
        "description": "Generates an sbatch script (cpus, mem, time, partition, gpus, array, dependency, modules, conda env), submits it, records job_id + script in .os_state/cluster/jobs/<job_id>.json. All optional params default to runtime.cluster_defaults; typical call is just (step_id, cmd).",
        "category": "exec",
        "inputSchema": {
            "type": "object",
            "properties": {
                "step_id": {"type": "string"},
                "cmd": {"type": "string"},
                "job_name": {"type": "string"},
                "cpus": {"type": "number"},
                "mem": {"type": "string"},
                "time_limit": {"type": "string"},
                "partition": {"type": "string"},
                "gpus": {"type": "number"},
                "array": {"type": "string", "description": "e.g. '1-100%10' for 100 tasks, 10 concurrent."},
                "dependency": {"type": "string", "description": "e.g. 'afterok:12345'."},
                "modules": {"type": "array", "items": {"type": "string"}},
                "conda_env": {"type": "string"},
                "extra_sbatch": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["cmd"],
        },
    },
    "tool_slurm_status": {
        "short": "Live status via squeue + finished status via sacct for one or all project jobs.",
        "description": "When job_id is given, returns a single record (live + finished state, elapsed, max RSS, exit code). Without job_id, returns every job submitted from this project.",
        "category": "exec",
        "inputSchema": {
            "type": "object",
            "properties": {"job_id": {"type": "string"}},
        },
    },
    "tool_slurm_fetch": {
        "short": "Block until a SLURM job finishes; return stdout / stderr paths.",
        "description": "Polls squeue every poll_interval seconds until the job is no longer queued / running, then collects the log files under the recorded log_dir.",
        "category": "exec",
        "inputSchema": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string"},
                "poll_interval": {"type": "number"},
                "max_wait": {"type": "number"},
            },
            "required": ["job_id"],
        },
    },
    "tool_slurm_list": {
        "short": "List every SLURM job submitted from this project.",
        "description": "Reads .os_state/cluster/jobs/*.json. No external calls.",
        "category": "exec",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "tool_research_method": {
        "short": "Gather 5-10 sources + write a method report. Use BEFORE choosing any statistical/computational method.",
        "description": "Gather 5-10 academic + web sources about a method, dedupe, write a structured report. Use BEFORE choosing any statistical/computational method.",
        "category": "research",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Method name + context, e.g. 'logistic regression with imbalanced classes'."},
                "limit": {"type": "number"},
            },
            "required": ["query"],
        },
    },
    "tool_research_tool": {
        "short": "Find tagged candidate libs / CLIs / websites. Use when picking a tool for a task.",
        "description": "Find candidate libraries / CLIs / websites for a task. Tags each candidate as installable | api_available | external_tool | paid_or_licensed. Use when picking a tool. In autopilot mode, calls with source='paid' or paid=true require confirmed=true (server-enforced autopilot floor gate — see guidance/autopilot.yaml).",
        "category": "research",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task": {"type": "string"},
                "language": {"type": "string", "description": "any | python | r | julia | bash"},
                "source": {"type": "string", "description": "Optional source tag. 'paid' triggers the autopilot floor gate."},
                "paid": {"type": "boolean", "description": "Optional. Set true to flag a paid_or_licensed candidate; triggers the autopilot floor gate."},
                "confirmed": {"type": "boolean", "description": "Required in autopilot mode when source is paid. Researcher consent."},
            },
            "required": ["task"],
        },
    },
    "tool_external_tool_instructions": {
        "short": "Write WORKSHEET.md for an external website / GUI / paid service. Use when handing off to humans.",
        "description": "When the chosen tool is external (website, GUI, paid service), write a WORKSHEET.md telling the researcher how to use it and where to drop the outputs.",
        "category": "research",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tool_name": {"type": "string"},
                "purpose": {"type": "string"},
                "url": {"type": "string"},
                "steps": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["tool_name", "purpose", "url"],
        },
    },
    "tool_alternative_path_propose": {
        "short": "Confidence-gated alt-pipeline scan + recommendation. Use BEFORE committing to a method.",
        "description": (
            "Confidence-gated alternative-pipeline scan. Pulls literature on "
            "the user's chosen method AND on alternatives framed for the "
            "specific data shape, counts comparative-evidence signals, and "
            "returns a recommendation: `commit_user_method` (stay quiet — "
            "default) OR `branch_to_alternative` (surface the alternative to "
            "the researcher ONCE and, on confirmation, call `sys_path("
            "operation='create', branch_of=<current>)` to create an `NN_<slug>_alt_path_<k>` fork "
            "alongside the primary). Writes "
            "`outputs/reports/alternative_path_<slug>.md` with the cited "
            "evidence. Use BEFORE committing a methodology when you suspect a "
            "subfield-canonical alternative could materially out-perform the "
            "researcher's first instinct — but DO NOT call repeatedly for "
            "the same step (proposing weak alternatives erodes trust)."
        ),
        "category": "research",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "What the step is trying to do, e.g. 'differential expression on bulk RNA-seq with paired samples'.",
                },
                "user_method": {
                    "type": "string",
                    "description": "The method the user proposed (or the AI's default), e.g. 'DESeq2 with ~condition design'.",
                },
                "data_summary": {
                    "type": "string",
                    "description": "Short data-shape note that helps the literature scan (sample size, paired-ness, sparsity, etc.). Optional but recommended.",
                },
                "limit": {"type": "number"},
            },
            "required": ["task", "user_method"],
        },
    },
    "tool_intake_autofill": {
        "short": "Propose project metadata from inputs/ + fill researcher_config blanks. Use during onboarding.",
        "description": "Read inputs/ (data + literature + context notes) and propose project metadata (research question, domain, hypotheses). Fills blanks in researcher_config.yaml and rewrites inputs/intake.md.",
        "category": "intake",
        "inputSchema": {
            "type": "object",
            "properties": {
                "overwrite": {
                    "type": "boolean",
                    "description": "If true, overwrite even non-blank config fields (default false).",
                }
            },
        },
    },
    "tool_task": {
        "short": "Unified background task tool. operation=run|status|list|kill.",
        "description": "Unified background-subprocess (Popen) dispatcher. operation='run' spawns a real background subprocess and returns task_id immediately (use for any command expected to run longer than runtime.long_running_threshold_seconds; REQUIRES command; accepts optional cwd + description). operation='status' checks a task's status + tail of its log (REQUIRES task_id; accepts optional tail_lines, default 50). operation='list' lists all known background tasks with live status. operation='kill' kills a task (SIGTERM by default; REQUIRES task_id; accepts optional signal_name ∈ TERM|KILL|INT). Every legacy tool_task_run / tool_task_status / tool_task_list / tool_task_kill name aliases to this entry point with operation injected via _ALIAS_PARAM_INJECTION so callers using the older per-operation names keep working unchanged.",
        "category": "tasks",
        "inputSchema": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["run", "status", "list", "kill"],
                    "description": "Which task sub-operation to invoke.",
                },
                # operation='run' kwargs
                "command": {
                    "type": "string",
                    "description": "operation='run' — REQUIRED. Shell-tokenised command, or a list.",
                },
                "cwd": {
                    "type": "string",
                    "description": "operation='run' — Optional working directory relative to project root.",
                },
                "description": {
                    "type": "string",
                    "description": "operation='run' — Optional human-readable description.",
                },
                # operation='status'|'kill' kwargs
                "task_id": {
                    "type": "string",
                    "description": "operation='status'|'kill' — REQUIRED. Identifier returned by operation='run'.",
                },
                "tail_lines": {
                    "type": "number",
                    "description": "operation='status' — Tail length to return (default 50).",
                },
                "signal_name": {
                    "type": "string",
                    "description": "operation='kill' — Signal to send: TERM | KILL | INT (default TERM).",
                },
                "confirmed": {
                    "type": "boolean",
                    "description": "Required in autopilot mode for operation='run' (expensive background jobs). Researcher consent.",
                },
            },
            "required": ["operation"],
        },
    },
    "tool_notebook_exec": {
        "short": "Execute a Jupyter notebook (papermill-aware with provenance sidecar).",
        "description": "Executes a .ipynb. When papermill is installed AND parameters is given, runs the notebook with parameter injection — output lands at notebook/runs/<stem>_<param-hash>.ipynb with a .prov.json sidecar capturing the input notebook + parameters + RNG seed + wall time. When papermill is absent, falls back to `jupyter nbconvert --execute --inplace` (parameters dict is ignored with a warning). Pass output_path to override the default runs/ location.",
        "category": "execution",
        "inputSchema": {
            "type": "object",
            "properties": {
                "notebook_path": {"type": "string"},
                "timeout": {"type": "number"},
                "kernel": {"type": "string"},
                "parameters": {"type": "object",
                               "description": "Injected into the `parameters`-tagged cell (papermill only)."},
                "output_path": {"type": "string"},
            },
            "required": ["notebook_path"],
        },
    },
    "tool_rmarkdown_render": {
        "short": "Render an .Rmd or .qmd doc (rmarkdown OR quarto). Use when knitting R/Quarto reports.",
        "description": "Render an .Rmd or .qmd document (rmarkdown::render OR quarto render).",
        "category": "execution",
        "inputSchema": {
            "type": "object",
            "properties": {
                "doc_path": {"type": "string"},
                "output_format": {"type": "string"},
                "timeout": {"type": "number"},
            },
            "required": ["doc_path"],
        },
    },
    "tool_scratch": {
        "short": "Unified scratch sandbox. operation=write|run|list|clear.",
        "description": "Unified scratch-sandbox dispatcher for workspace/scratch/ — gitignored, no provenance — use for syntax checks, smoke tests, parameter sweeps. operation='write' writes a quick-test file (REQUIRES filename + content). operation='run' executes a script there with language inferred from extension (.py | .R | .jl | .sh) (REQUIRES filename; accepts optional timeout). operation='list' returns the current files. operation='clear' wipes the directory (keeps .gitignore and README). Anything important must be moved out into a proper experiment (e.g. via tool_promote_to_step). Every legacy tool_scratch_write / tool_scratch_run / tool_scratch_list / tool_scratch_clear name aliases to this entry point with operation injected via _ALIAS_PARAM_INJECTION so callers using the older per-operation names keep working unchanged.",
        "category": "scratch",
        "inputSchema": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["write", "run", "list", "clear"],
                    "description": "Which scratch sub-operation to invoke.",
                },
                # operation='write' kwargs
                "filename": {
                    "type": "string",
                    "description": "operation='write'|'run' — REQUIRED. File name under workspace/scratch/.",
                },
                "content": {
                    "type": "string",
                    "description": "operation='write' — REQUIRED. File contents to write.",
                },
                # operation='run' kwargs
                "timeout": {
                    "type": "number",
                    "description": "operation='run' — Optional execution timeout in seconds (default 60).",
                },
            },
            "required": ["operation"],
        },
    },
    "tool_workspace_repair": {
        "short": "Detect + heal missing dirs / corrupted state (never deletes). Use when workspace looks broken.",
        "description": "Detect missing directories / corrupted state / stale paths and (optionally) heal them. NEVER deletes files.",
        "category": "state",
        "inputSchema": {
            "type": "object",
            "properties": {"dry_run": {"type": "boolean"}},
        },
    },
    "tool_context_intake": {
        "short": "Route stray files into inputs/ subfolders (logs moves, never overwrites). Use after dropping files.",
        "description": "Detect new files dropped anywhere in the project and route each into the right inputs/ subfolder (literature / raw_data / context). Logs every move; never overwrites.",
        "category": "intake",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source_dir": {"type": "string"},
                "dry_run": {"type": "boolean"},
                "also_autofill": {"type": "boolean"},
            },
        },
    },
    "tool_citations_verify": {
        "short": "Verify citation_keys against Crossref (flags hallucinations). Use before submitting.",
        "description": "Verify every citation_key in workspace/citations.md by hitting Crossref. Reports verified vs unverified (possibly hallucinated) entries.",
        "category": "synthesis",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "tool_search": {
        "short": "Unified literature/web search. Replaces tool_search_{semantic_scholar,pubmed,crossref,arxiv,web} via source=… or auto.",
        "description": "One search tool, five providers + auto-routing. Pass source='semantic_scholar'|'pubmed'|'crossref'|'arxiv'|'web' to pin a provider, or source='auto' (default) to let Research-OS pick based on the query's domain (biomedical → semantic_scholar+pubmed; ML/methods → semantic_scholar+arxiv; social/behavioral → crossref+semantic_scholar; geoscience → crossref+arxiv; generic → web). The pre-consolidation per-provider names still work as deprecated aliases (logged for usage audit).",
        "category": "search",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "source": {
                    "type": "string",
                    "enum": ["auto", "semantic_scholar", "pubmed", "crossref", "arxiv", "web"],
                },
                "limit": {"type": "integer"},
            },
            "required": ["query"],
        },
    },
}
