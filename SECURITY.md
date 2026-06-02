# Security Policy

## Supported versions

Research OS follows [SemVer](https://semver.org). Security fixes target
the latest minor release; older minors receive critical fixes for 6
months after the next minor lands.

| Version | Supported          |
| ------- | ------------------ |
| 1.1.x   | ✅ active           |
| 1.0.x   | ✅ until 2026-12-02 |
| < 1.0   | ❌ pre-release      |

## Reporting a vulnerability

**Please do NOT open a public GitHub issue for a security vulnerability.**

Instead, use one of:

1. **GitHub private vulnerability reporting** (preferred) —
   <https://github.com/VibhavSetlur/Research-OS/security/advisories/new>
2. **Email** — `vibhav.setlur@gmail.com` with subject prefix
   `[research-os security]`. PGP key available on request.

Include:

- the version (`pip show research-os`)
- the OS + Python version
- a minimal reproducer (a private gist is fine if it contains anything sensitive)
- the impact you observed
- whether you've already disclosed it elsewhere

You'll get a first response within **5 business days**. If we accept
the report, expect a fix within **30 days** for high-severity issues,
**90 days** for medium-severity, and a credited mention in the
[CHANGELOG](CHANGELOG.md) unless you ask for anonymity.

## Scope

In scope:

- The `research-os` Python package (the MCP server, CLI, protocol loader, router).
- Any code that ships in the wheel under `src/research_os/`.
- Scaffolded files written by `research-os init` (templates under `templates/`).

Out of scope:

- The LLM provider itself (Anthropic / OpenAI / etc.) — Research OS does
  not manage provider keys.
- The AI IDE wrapping Research OS (Claude Code, Cursor, …) — report to
  their security teams.
- Optional dependencies pulled in by `research-os[all]` — report
  upstream; we'll bump the pin once they fix it.
- Vulnerabilities that require an attacker who already has write access
  to your `workspace/` (that's already a full local compromise).

## What we treat as in-scope and serious

- Tool calls that exfiltrate data outside the project root.
- Tool calls that write to `inputs/raw_data/` or `inputs/literature/`
  (those are immutable by design — a bypass is a bug).
- Path-traversal in `sys_file_*` tools.
- Credential leakage in logs, audit reports, or share-safe zips.
- Bypass of the quality-gate / override audit trail.

Thanks for keeping the project trustworthy.
