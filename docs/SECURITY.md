# Security model

This document describes the Research-OS MCP server's trust boundary,
the threats it defends against, and the threats it explicitly does
not. Read this before deploying Research-OS on a machine that
contains code, data, or credentials you would not want a careless
(or adversarial) AI session to touch.

For day-to-day caveats and workarounds that are downstream of this
model, see the **Known caveats in 2.2.x** section of
[FAQ.md](FAQ.md).

---

## 1. The trust boundary in one sentence

> The Research-OS MCP server runs as **you**, the OS user that
> started it — and any tool the server exposes (notably
> `tool_python_exec` and `tool_bash_exec`) inherits every permission
> you have on that machine.

Concretely: if your shell can `rm -rf ~`, the AI driving the MCP
server can too. There is no sandbox layer between the server and the
operating system. Research-OS adds *workflow* guardrails (audits,
gates, override rationales) — it does not add an *OS* guardrail.

This is intentional. Research-OS is a research-workflow tool, not a
hosted agent. The trust boundary is the same as for any pip-installed
CLI you run locally.

---

## 2. What the workflow layer does enforce (post-2.2.x)

Inside the trust boundary, Research-OS has internal controls that
catch the most common foot-guns:

* **`sys_file_*` respects path containment** (new in 2.2.0). Reads
  and writes via `sys_file_read` / `sys_file_write` /
  `sys_file_list` reject paths that resolve outside the project
  root. This catches typos and a class of prompt-injection attempts
  that ask the AI to "save the report to `/etc/passwd`".
* **Autopilot enforces 8 floor gates** (new in 2.2.0). When
  `autonomy_level: autopilot`, every protocol step is checked
  against eight floor-gate audits before the next step runs. A
  blocking finding halts the protocol; the AI cannot silently
  continue past a failed gate.
* **`override_rationale` must be substantive** (new in 2.2.0). When
  the AI passes `override_unresolved_blocks=true`, the rationale
  string is checked for length and non-trivial content. A bare
  "needed to ship" is rejected. The rationale lands in
  `.os_state/overrides.log` for review.
* **`inputs/raw_data/` and `.os_state/` are write-protected.** The
  AI can read but not modify these directories via `sys_file_*`.
  Raw data is provenance; state is the source of truth for
  resumability. Both are append-only at the workflow layer.
* **Every audit emits a JSON companion** appended to
  `workspace/logs/.audit_findings.jsonl`. Query with
  `tool_audit_findings(operation='query', severity='block')` to
  spot patterns of overrides or repeated blocks.

These are *workflow* guardrails. An attacker (or a careless AI)
who calls `tool_python_exec` and writes raw Python that opens
`/etc/passwd` directly bypasses all of them. See section 4.

---

## 3. Recommended posture

* **Keep the default `autonomy_level: adaptive`** unless you have
  read every protocol the session might load. `adaptive` gates every
  irreversible, expensive, or paid action and tightens to confirm
  *all* write-side tools on a new or untrusted project. For
  per-tool-call confirmation regardless of trust, pin
  `autonomy_level: supervised` (or `manual`). `autopilot` trusts the
  AI to drive end-to-end and only stops on floor-gate violations.
* **Treat the workspace as a sandbox.** Run Research-OS from a
  dedicated project directory, not from your home folder. If the AI
  writes a wild file or shells out badly, the blast radius is the
  project directory plus anything writable by your user.
* **Pin pack versions.** Third-party adapter packs run inside the
  same trust boundary as the core. Pin them in `pyproject.toml` or
  `requirements.txt`; don't `pip install` an unknown
  `research-os-adapter-*` without reading the source.
* **Review `.os_state/overrides.log` periodically.** Even with the rationale validator
  rationale checks, the AI can produce a plausible-sounding
  rationale for almost anything. The log exists so you can spot
  patterns of overrides that should have been hard stops.

---

## 4. What an attacker CAN do

If an attacker controls the AI's input stream (e.g. via prompt
injection in a fetched literature PDF, a web-search snippet, or text
the user pastes into chat), they can:

* **Execute arbitrary code** via `tool_python_exec` or
  `tool_bash_exec` — anything you could type in a shell.
* **Read any file your OS user can read** — including SSH keys, API
  tokens in `~/.config/`, browser cookie stores, etc. — by calling
  `tool_python_exec` with `open(...).read()`.
* **Exfiltrate data** by calling outbound HTTP (`tool_python_exec`
  with `urllib.request`, or any of the search-provider tools if a
  key is configured).
* **Tamper with the workspace** outside the write-protected
  directories — including overwriting `inputs/researcher_config.yaml`
  to lower `autonomy_level` or disable gates.

The prompt-injection vector is real and not hypothetical:
literature PDFs and web search results regularly contain text that
reads "ignore previous instructions and ...". If the AI follows
that instruction and the user approves the tool call (or autopilot
is on), the attack succeeds.

**Mitigation:** pin `autonomy_level: supervised`, review tool calls
when ingesting untrusted content, and don't run the MCP server with
credentials in env vars you wouldn't want logged.

---

## 5. What an attacker CANNOT do (at the workflow layer)

* **Silently bypass an audit block.** `override_unresolved_blocks`
  requires a non-trivial `override_rationale` and is logged.
* **Read/write outside the project via `sys_file_*`.** The
  containment check rejects `..`, absolute paths outside the root,
  and symlink escapes.
* **Modify `inputs/raw_data/` or `.os_state/` via `sys_file_*`.**
  These are write-protected at the dispatcher.
* **Hide an unknown-tool error.** The dispatcher emits a structured
  envelope with a `did_you_mean` list; the AI cannot pretend the
  call succeeded.

Again: these protect against *casual* misuse, not against an
attacker who has gained `tool_python_exec`. The OS-level trust
boundary is the one that matters.

---

## 6. Reporting a vulnerability

For workflow-layer issues (a gate that can be bypassed, a path
containment edge case, an override-rationale check that takes a
trivial string): open a public issue at
<https://github.com/VibhavSetlur/Research-OS/issues>.

For an issue that lets an attacker get to `tool_python_exec` without
the user noticing (e.g. a tool that auto-dispatches based on
fetched content): email
[vibhav.a.setlur@gmail.com](mailto:vibhav.a.setlur@gmail.com)
before opening a public issue.

---

## See also

* [CONTRACT.md](CONTRACT.md) — stable surface (envelope shape,
  exception types) integrators can rely on.
* [PROTOCOL_DOCTRINE.md](PROTOCOL_DOCTRINE.md) — why protocols are
  scaffolds for reasoning, not scripts.
* [FAQ.md](FAQ.md) — "Known caveats in 2.2.x" section for
  workflow-level limitations.
* [AI_GUIDE.md](AI_GUIDE.md) — operating manual for the AI driving
  the server.
