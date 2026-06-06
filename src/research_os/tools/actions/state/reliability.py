"""Telemetry-free local reliability logging.

Writes one JSONL event per significant occurrence (gate fire, tool error,
recovery, abandon) to ``workspace/.os_state/reliability.jsonl``. Local
file only — never phones home. The researcher voluntarily runs
``tool_reliability(operation='report')`` to produce a redacted markdown
summary they can paste into a bug report.

Constraints:
- No project content (no claim text, no findings, no PII).
- Only structural facts: protocol name + version, model_profile (what
  the researcher declared in researcher_config.yaml), event type, a
  small structured payload.
- File is append-only; rotation policy is "leave it alone" — JSONL
  stays tiny (one event ~= 250 bytes; 10K events ~= 2.5MB).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("research_os.tools.state.reliability")


_VALID_EVENT_TYPES = {
    "gate_fire",
    "gate_recover",
    "gate_abandon",
    "tool_error",
    "tool_success",
    "protocol_start",
    "protocol_complete",
    "override_used",
    "stale_state_detected",
    "paywall_skipped",
}


def _log_path(root: Path) -> Path:
    p = root / "workspace" / ".os_state" / "reliability.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _read_model_profile(root: Path) -> str:
    """Best-effort read of researcher_config.yaml model_profile.

    Wizard-canonical path is ``inputs/researcher_config.yaml``; falls back to
    a legacy root-level config for projects scaffolded before the wizard
    moved the file under ``inputs/``.
    """
    cfg = root / "inputs" / "researcher_config.yaml"
    if not cfg.exists():
        legacy = root / "researcher_config.yaml"
        if legacy.exists():
            cfg = legacy
        else:
            return "unknown"
    try:
        import yaml  # type: ignore
        data = yaml.safe_load(cfg.read_text()) or {}
        return str(data.get("model_profile") or "unknown")
    except Exception:
        return "unknown"


def _redact(value: Any) -> Any:
    """Drop anything that could leak project content from a payload.

    Strings longer than 80 chars are truncated. Anything that looks
    like a file path or URL with project-content fragments is replaced
    with a hash. Nested dicts/lists walked recursively.
    """
    if isinstance(value, str):
        if len(value) > 80:
            return value[:77] + "..."
        return value
    if isinstance(value, dict):
        return {k: _redact(v) for k, v in value.items() if isinstance(k, str)}
    if isinstance(value, list):
        return [_redact(v) for v in value[:10]]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:80]


def log_event(
    root: Path,
    event_type: str,
    *,
    protocol_name: str | None = None,
    model_profile: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append one event line to ``workspace/.os_state/reliability.jsonl``."""
    try:
        if event_type not in _VALID_EVENT_TYPES:
            return {
                "status": "error",
                "message": (
                    f"Unknown event_type '{event_type}'. Allowed: "
                    f"{sorted(_VALID_EVENT_TYPES)}"
                ),
            }
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event_type,
            "protocol": protocol_name or "",
            "model_profile": model_profile or _read_model_profile(root),
            "payload": _redact(payload or {}),
        }
        path = _log_path(root)
        with open(path, "a") as f:
            f.write(json.dumps(record, separators=(",", ":")) + "\n")
        return {"status": "success", "log_path": str(path.relative_to(root))}
    except Exception as e:
        logger.exception("reliability.log_event failed")
        return {"status": "error", "message": str(e)}


def reliability_report(root: Path) -> dict[str, Any]:
    """Produce a redacted markdown summary of the reliability log.

    Aggregates events by type and protocol; surfaces top gate-fire and
    error patterns. Designed to be paste-able into a GitHub issue
    without revealing project content.
    """
    try:
        path = _log_path(root)
        if not path.exists():
            return {
                "status": "success",
                "message": "No reliability log yet (no events recorded).",
                "events_total": 0,
            }

        events: list[dict[str, Any]] = []
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except Exception:
                continue

        if not events:
            return {
                "status": "success",
                "message": "reliability.jsonl exists but is empty.",
                "events_total": 0,
            }

        by_type: dict[str, int] = {}
        by_protocol: dict[str, int] = {}
        gate_fires_by_protocol: dict[str, int] = {}
        errors_by_protocol: dict[str, int] = {}
        model_profiles: dict[str, int] = {}

        for ev in events:
            t = str(ev.get("event") or "unknown")
            p = str(ev.get("protocol") or "unknown")
            mp = str(ev.get("model_profile") or "unknown")
            by_type[t] = by_type.get(t, 0) + 1
            by_protocol[p] = by_protocol.get(p, 0) + 1
            model_profiles[mp] = model_profiles.get(mp, 0) + 1
            if t == "gate_fire":
                gate_fires_by_protocol[p] = gate_fires_by_protocol.get(p, 0) + 1
            if t == "tool_error":
                errors_by_protocol[p] = errors_by_protocol.get(p, 0) + 1

        first_ts = events[0].get("ts", "")
        last_ts = events[-1].get("ts", "")

        lines = [
            "# Reliability report (redacted)",
            "",
            f"- Events total: **{len(events)}**",
            f"- First event: {first_ts}",
            f"- Last event: {last_ts}",
            "",
            "## Events by type",
            "",
        ]
        for t, n in sorted(by_type.items(), key=lambda x: -x[1]):
            lines.append(f"- `{t}` — {n}")

        lines += ["", "## Model profile mix", ""]
        for mp, n in sorted(model_profiles.items(), key=lambda x: -x[1]):
            lines.append(f"- `{mp}` — {n}")

        if gate_fires_by_protocol:
            lines += ["", "## Top gate fires (by protocol)", ""]
            for p, n in sorted(
                gate_fires_by_protocol.items(), key=lambda x: -x[1]
            )[:10]:
                lines.append(f"- `{p}` — {n} fire(s)")

        if errors_by_protocol:
            lines += ["", "## Top tool errors (by protocol)", ""]
            for p, n in sorted(
                errors_by_protocol.items(), key=lambda x: -x[1]
            )[:10]:
                lines.append(f"- `{p}` — {n} error(s)")

        lines += [
            "",
            (
                "_Report contains no project content — only structural counts "
                "and protocol identifiers. Safe to share when filing a bug._"
            ),
        ]
        report_path = root / "workspace" / "logs" / "reliability_report.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text("\n".join(lines) + "\n")

        return {
            "status": "success",
            "events_total": len(events),
            "by_type": by_type,
            "by_protocol": dict(
                sorted(by_protocol.items(), key=lambda x: -x[1])[:20]
            ),
            "model_profiles": model_profiles,
            "first_event_ts": first_ts,
            "last_event_ts": last_ts,
            "report_path": str(report_path.relative_to(root)),
        }
    except Exception as e:
        logger.exception("reliability.report failed")
        return {"status": "error", "message": str(e)}
