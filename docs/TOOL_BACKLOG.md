# Tool backlog — enhancements surfaced during protocol work

Tool gaps noticed while authoring protocols. Each has a safe fallback today, so
these are enhancements, not blockers.

## 1. `tool_git` rollback operation — ✅ DONE

`tool_git` gained a `restore` operation:
`tool_git(operation='restore', name=<tag-or-commit>)` returns the inner repo's
working tree (or `paths=`) to a blessed version WITHOUT moving HEAD or losing
history (the reverted-from SHA is reported so it's fully recoverable). Path-
contained to the inner repo like every other `tool_git` op. The
`build/versioning_and_rollback` protocol uses it instead of a bash fallback.

## 2. `tool_sql_exec` (for methodology/polyglot_analysis) — open

Research OS runs Python / R / Julia / Bash via dedicated exec tools, but there
is no SQL / DuckDB executor. The polyglot protocol treats SQL as a first-class
research language (the right tool for set-based data work), so SQL is currently
only reachable via a Python/R DB client.

Requested: a `tool_sql_exec` that runs a `.sql` script / inline query against a
configured engine (DuckDB as the zero-config default for file-based analytics;
a connection string for a real warehouse), capturing provenance like the other
exec tools.

Fallback today: run SQL inside `tool_python_exec` via duckdb/sqlite3 — works,
just not first-class.
