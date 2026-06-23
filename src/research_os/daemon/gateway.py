"""OpenAI-compatible chat-completions gateway (Phase 2).

DESIGN_V4.md feature #2 — the keystone of the v4 re-architecture. It
turns the daemon from "a thing that serves data about runs" into "an AI
endpoint any OpenAI-compatible client can point at." A researcher sets
``base_url`` to the daemon and gets, for free, on every single turn:

  * **Protocol routing** — the daemon runs the prompt through the SAME
    hierarchical router the MCP server uses (``route_request``) and
    injects the chosen protocol's guidance as a system message. The LLM
    is steered toward the right research reasoning scaffold without the
    client knowing protocols exist.
  * **Field-awareness** — the project's detected research domain (Phase
    1.16) is injected, so a chemist and a historian get differently
    oriented assistance from the same endpoint.
  * **Freshness context** — if any result in the project is stale (Phase
    1.14), the LLM is told, so it won't reason over a figure that was
    built from data that has since changed.
  * **Tool access** — all 152 Research-OS tools are advertised to the LLM
    in OpenAI tool-schema form; when the model calls one, the gateway
    executes it through the single dispatch seam
    (``server.dispatch._handle_tool_call``) and feeds the result back,
    looping until the model produces a final answer.

ARCHITECTURE NOTE (strangler-fig, DESIGN_V4 #1). This module lives in
``daemon/`` and is the ONLY place that bridges a network transport to the
reasoning engine. It imports the engine's public seams (``route_request``,
``_handle_tool_call``, ``TOOL_DEFINITIONS``) but the engine never imports
it. Network I/O is injected via ``forward_fn`` so the entire routing +
tool-loop is unit-testable with zero network and zero API keys.

SECURITY. The gateway is a *mutating* surface (tools can write). It
requires a per-session bearer token (``gateway_token_env``) and binds
localhost-only by inheritance from the daemon. No token configured ->
the gateway refuses to assemble (caller returns 503).
"""
from __future__ import annotations

import json
import time
import uuid
from collections.abc import Callable, Iterator, Sequence
from typing import Any

# Type alias for the injected upstream forwarder. Given a fully-formed
# OpenAI chat-completions request body, return the parsed JSON response.
# Injected so tests pass a fake and production passes a urllib/httpx call.
ForwardFn = Callable[[dict, dict], dict]  # (body, headers) -> response_json


# ── context assembly (pure, no network) ──────────────────────────────


def _route_summary(route: dict) -> str:
    """One-paragraph human-readable summary of a route_request result."""
    if not route or route.get("status") != "success":
        return "No specific research protocol matched; proceed with general assistance."
    parts: list[str] = []
    proto = route.get("primary_protocol")
    intent = route.get("intent_class")
    sub = route.get("sub_intent")
    if proto:
        loc = f"{intent}/{sub}" if sub else (intent or "")
        parts.append(f"Matched protocol: {proto}" + (f" ({loc})" if loc else "") + ".")
    elif intent:
        parts.append(f"Matched intent class: {intent}.")
    advice = route.get("advice")
    if advice:
        parts.append(str(advice))
    ask = route.get("ask_user")
    if ask:
        parts.append(f"If ambiguous, ask the researcher: {ask}")
    decomposition = route.get("decomposition") or []
    if decomposition:
        steps = ", ".join(str(s) for s in decomposition[:8])
        parts.append(f"Suggested step sequence: {steps}.")
    return " ".join(parts)


def build_context_block(prompt: str, daemon: Any) -> dict[str, Any]:
    """Assemble the Research-OS system-context for a user prompt.

    Pure orchestration over the engine's public functions; no network.
    Returns a dict with:
      * ``system``      — the system-message text to prepend (str)
      * ``route``       — the raw route_request result (dict | None)
      * ``domain``      — detected domain id (str | None)
      * ``freshness``   — short freshness note (str | None)
      * ``available``   — whether a workspace was resolved (bool)

    Every section is best-effort: a failure in any one degrades to a note
    rather than breaking the completion. The gateway must never 500 on a
    context-assembly hiccup — a degraded answer beats no answer.
    """
    root = getattr(daemon, "root", None)
    lines: list[str] = [
        "You are operating through Research-OS, a research operating system. "
        "Use the provided protocol guidance to structure your reasoning, and "
        "call Research-OS tools when they help. Prefer rigor and provenance "
        "over speed.",
    ]
    out: dict[str, Any] = {
        "system": "",
        "route": None,
        "domain": None,
        "freshness": None,
        "available": root is not None,
    }

    # 1. Protocol routing — the core value-add.
    if root is not None and prompt and prompt.strip():
        try:
            from research_os.tools.actions.router import route_request

            # persist_plan=False: the gateway is stateless per request; it
            # must not write active_plan.json as a side effect of routing.
            route = route_request(prompt, root, persist_plan=False)
            out["route"] = route
            lines.append("PROTOCOL GUIDANCE: " + _route_summary(route))
        except Exception as exc:  # noqa: BLE001 - degrade, never break
            lines.append(f"(Protocol routing unavailable: {exc})")

    # 2. Domain / field-awareness.
    if root is not None:
        try:
            from .domains import detect

            dr = detect(root)
            out["domain"] = dr.profile.id
            lines.append(
                f"RESEARCH FIELD: {dr.profile.label} "
                f"(confidence {dr.confidence:.0%}). {dr.profile.notes}"
            )
        except Exception:  # noqa: BLE001
            pass

    # 3. Freshness — warn if results are stale.
    store = getattr(daemon, "runstore", None)
    if store is not None:
        try:
            from . import provenance as _prov
            from . import staleness as _stale

            manifests = store.recent_manifests(limit=200)
            if manifests:
                verdict = _stale.assess(manifests, _prov.hash_fn_for_root(root))
                n_stale = verdict["counts"]["stale"]
                if n_stale:
                    note = (
                        f"{n_stale} of {verdict['counts']['total']} recorded "
                        "results are STALE (built from inputs that have since "
                        "changed). Do not treat stale results as authoritative; "
                        "recommend 'research-os daemon rebuild' if relevant."
                    )
                    out["freshness"] = note
                    lines.append("FRESHNESS: " + note)
                else:
                    out["freshness"] = "all results fresh"
        except Exception:  # noqa: BLE001
            pass

    out["system"] = "\n\n".join(lines)
    return out


# ── tool schema bridge ───────────────────────────────────────────────


def _to_openai_tool(name: str, spec: dict) -> dict:
    """Convert a Research-OS TOOL_DEFINITIONS entry to OpenAI tool form."""
    desc = spec.get("short") or spec.get("description") or name
    schema = spec.get("inputSchema") or {"type": "object", "properties": {}}
    return {
        "type": "function",
        "function": {"name": name, "description": str(desc)[:1024], "parameters": schema},
    }


def research_os_tools(limit: int | None = None) -> list[dict]:
    """All Research-OS tools as OpenAI tool schemas.

    Lazy import of the registry keeps the daemon import graph light and
    preserves the invariant that ``daemon/`` reads engine seams, not the
    other way round.
    """
    from research_os.server.registry import TOOL_DEFINITIONS

    items = sorted(TOOL_DEFINITIONS.items())
    if limit is not None:
        items = items[:limit]
    return [_to_openai_tool(n, s) for n, s in items if isinstance(s, dict)]


def _tool_catalog() -> dict[str, Any]:
    """Categorized inventory of engine tools — counts + names by category.

    Lazy-imports the registry (preserves the daemon->server import arrow).
    Gives an agent a map of the toolbox without dumping 152 full schemas.
    """
    from research_os.server.registry import TOOL_DEFINITIONS

    by_cat: dict[str, list[str]] = {}
    for name, spec in sorted(TOOL_DEFINITIONS.items()):
        if not isinstance(spec, dict):
            continue
        cat = str(spec.get("category") or "uncategorized")
        by_cat.setdefault(cat, []).append(name)
    return {
        "total": sum(len(v) for v in by_cat.values()),
        "by_category": {k: len(v) for k, v in sorted(by_cat.items())},
        "names_by_category": by_cat,
    }


def build_capabilities(daemon: Any, *, include_tool_schemas: bool = False) -> dict[str, Any]:
    """The agent front door — one self-describing snapshot of Research-OS.

    Pure, read-only orchestration over engine + daemon public surfaces (no
    network, no mutation). Designed so any AI agent (Hermes, Claude Code,
    Cursor, a bare OpenAI client) can issue a SINGLE GET and learn:

      * **identity**   — what Research-OS is + version + the daemon endpoints.
      * **field**      — the project's detected research domain + how it was
        inferred (so the agent orients to chemistry vs. history vs. ML).
      * **tools**      — a categorized inventory (counts + names; full OpenAI
        schemas only when ``include_tool_schemas`` is set, to stay cheap).
      * **protocols**  — how many reasoning scaffolds exist + their categories.
      * **work_state** — freshness of recorded results + recent run count, so
        the agent knows whether it's walking into fresh or stale work.
      * **gateway**    — whether the chat endpoint is live + how to drive it.

    Every section is best-effort and degrades to ``null``/notes rather than
    raising — orientation must never 500.
    """
    from research_os import __version__

    root = getattr(daemon, "root", None)
    cfg = getattr(daemon, "config", None)
    out: dict[str, Any] = {
        "service": "research-os",
        "version": __version__,
        "root": str(root) if root else None,
        "available": root is not None,
        "tagline": (
            "A research operating system: protocol-guided reasoning, "
            "field-awareness, and provenance-tracked execution, callable "
            "by humans and AI agents over a single localhost daemon."
        ),
        "endpoints": {
            "capabilities": "GET /v1/capabilities",
            "chat": "POST /v1/chat/completions (OpenAI-compatible)",
            "state": "GET /v1/state",
            "domain": "GET /v1/domain",
            "runs": "GET /v1/runs",
            "lineage": "GET /v1/lineage",
            "staleness": "GET /v1/staleness",
            "rebuild_plan": "GET /v1/rebuild/plan",
        },
    }

    # 1. Field / domain.
    if root is not None:
        try:
            from .domains import detect

            dr = detect(root)
            out["field"] = {
                "id": dr.profile.id,
                "label": dr.profile.label,
                "confidence": round(dr.confidence, 3),
                "source": getattr(dr, "source", None),
                "languages": list(dr.profile.languages),
                "deliverables": list(dr.profile.artifacts),
            }
        except Exception:  # noqa: BLE001
            out["field"] = None

    # 2. Tools (categorized inventory; schemas optional).
    try:
        out["tools"] = _tool_catalog()
        if include_tool_schemas:
            out["tools"]["schemas"] = research_os_tools()
    except Exception:  # noqa: BLE001
        out["tools"] = None

    # 3. Protocols (counts by category).
    try:
        from research_os.tools.actions.router import route_request  # noqa: F401

        out["protocols"] = _protocol_catalog()
    except Exception:  # noqa: BLE001
        out["protocols"] = None

    # 4. Work state — freshness + recent runs.
    store = getattr(daemon, "runstore", None)
    if store is not None:
        try:
            from . import provenance as _prov
            from . import staleness as _stale

            manifests = store.recent_manifests(limit=200)
            ws: dict[str, Any] = {"recorded_results": len(manifests)}
            if manifests:
                verdict = _stale.assess(manifests, _prov.hash_fn_for_root(root))
                ws["fresh"] = verdict["counts"].get("fresh")
                ws["stale"] = verdict["counts"].get("stale")
            out["work_state"] = ws
        except Exception:  # noqa: BLE001
            out["work_state"] = None
    else:
        out["work_state"] = {"recorded_results": 0}

    # 5. Gateway readiness (no secrets — booleans only).
    if cfg is not None:
        import os as _os

        out["gateway"] = {
            "enabled": bool(getattr(cfg, "enable_gateway", False)),
            "upstream_model": getattr(cfg, "gateway_upstream_model", None),
            "token_set": bool(_os.environ.get(getattr(cfg, "gateway_token_env", ""), "")),
            "api_key_set": bool(
                _os.environ.get(getattr(cfg, "gateway_api_key_env", ""), "")
            ),
        }

    return out


def _protocol_catalog() -> dict[str, Any]:
    """Counts of available reasoning protocols, grouped by category.

    Globs the engine's protocol directory directly (pure, no router calls).
    Skips ``_``-prefixed control files (e.g. ``_router_index.yaml``); the
    category is the protocol's parent directory name. Best-effort.
    """
    from research_os.tools.actions.protocol import PROTOCOLS_DIR

    by_cat: dict[str, int] = {}
    total = 0
    try:
        for yaml_file in PROTOCOLS_DIR.rglob("*.yaml"):
            if yaml_file.name.startswith("_"):
                continue
            rel = yaml_file.relative_to(PROTOCOLS_DIR)
            cat = rel.parts[0] if len(rel.parts) > 1 else "general"
            by_cat[cat] = by_cat.get(cat, 0) + 1
            total += 1
    except Exception:  # noqa: BLE001
        pass
    return {"total": total, "by_category": dict(sorted(by_cat.items()))}


def _extract_text(content_list: Sequence[Any]) -> str:
    """Flatten a list[TextContent] (the dispatch seam's return) to text."""
    parts: list[str] = []
    for item in content_list or []:
        text = getattr(item, "text", None)
        if text is None and isinstance(item, dict):
            text = item.get("text")
        if text is not None:
            parts.append(str(text))
    return "\n".join(parts)


def execute_tool_call(call: dict, root: Any) -> str:
    """Run one OpenAI tool_call through the dispatch seam, return text.

    Never raises: a tool failure is returned as a JSON error string so the
    LLM can see it and recover, rather than crashing the completion.
    """
    fn = (call or {}).get("function") or {}
    name = fn.get("name") or ""
    raw_args = fn.get("arguments")
    try:
        args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
    except (TypeError, ValueError):
        args = {}
    try:
        from research_os.server.dispatch import _handle_tool_call

        result = _handle_tool_call(name, args, root)
        return _extract_text(result)
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": f"tool '{name}' failed: {exc}"})


# ── the completion loop ───────────────────────────────────────────────


def run_completion(
    body: dict,
    daemon: Any,
    forward_fn: ForwardFn,
    *,
    upstream_headers: dict | None = None,
    max_tool_rounds: int = 6,
    expose_tools: bool = True,
) -> dict:
    """Run one OpenAI-compatible chat completion through the gateway.

    Steps:
      1. Pull the latest user message; build the Research-OS context block.
      2. Prepend the context as a system message; advertise RO tools.
      3. Forward to the upstream LLM via ``forward_fn``.
      4. While the model returns tool_calls (up to ``max_tool_rounds``):
         execute each via the dispatch seam, append results, forward again.
      5. Return the final OpenAI response, annotated with
         ``x_research_os`` routing metadata.

    ``forward_fn`` isolates all network I/O so this is fully testable.
    """
    messages = list(body.get("messages") or [])

    # Latest user message drives routing.
    user_prompt = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content")
            user_prompt = content if isinstance(content, str) else json.dumps(content)
            break

    ctx = build_context_block(user_prompt, daemon)

    # Prepend context as a system message (keep any client system message).
    augmented = [{"role": "system", "content": ctx["system"]}, *messages]

    out_body = {k: v for k, v in body.items() if k != "messages"}
    out_body["messages"] = augmented
    if expose_tools and "tools" not in out_body:
        out_body["tools"] = research_os_tools()

    headers = dict(upstream_headers or {})
    response = forward_fn(out_body, headers)

    # Tool-call loop.
    rounds = 0
    root = getattr(daemon, "root", None)
    while rounds < max_tool_rounds:
        choices = response.get("choices") or []
        if not choices:
            break
        message = choices[0].get("message") or {}
        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            break
        rounds += 1
        # Append the assistant's tool-call message, then each tool result.
        augmented.append(message)
        for call in tool_calls:
            result_text = execute_tool_call(call, root)
            augmented.append(
                {
                    "role": "tool",
                    "tool_call_id": call.get("id", ""),
                    "name": (call.get("function") or {}).get("name", ""),
                    "content": result_text,
                }
            )
        out_body["messages"] = augmented
        response = forward_fn(out_body, headers)

    # Annotate with routing metadata (non-standard but harmless extension).
    response.setdefault("x_research_os", {})
    response["x_research_os"].update(
        {
            "domain": ctx.get("domain"),
            "primary_protocol": (ctx.get("route") or {}).get("primary_protocol"),
            "intent_class": (ctx.get("route") or {}).get("intent_class"),
            "freshness": ctx.get("freshness"),
            "tool_rounds": rounds,
        }
    )
    return response


def to_stream_chunks(result: dict) -> Iterator[str]:
    """Render a finished completion as OpenAI-compatible SSE frames.

    The gateway runs a *multi-round tool-call loop*, so it cannot honestly
    stream token-by-token from the upstream mid-loop. Instead, once the loop
    resolves to a final assistant message, this re-emits that result as the
    standard ``chat.completion.chunk`` event stream every OpenAI streaming
    client understands:

      1. a role-priming chunk (``delta={"role": "assistant"}``)
      2. one content chunk carrying the full answer text
      3. a final chunk with ``finish_reason`` + the ``x_research_os`` routing
         metadata mirrored onto the chunk (so streaming clients still see it)
      4. the terminal ``data: [DONE]`` sentinel

    Each frame is a ``data: <json>\\n\\n`` line. Yielding strings keeps this
    pure + fully testable; the server wraps it in a StreamingResponse.
    """
    cid = result.get("id") or f"chatcmpl-ro-{uuid.uuid4().hex[:12]}"
    created = result.get("created") or int(time.time())
    model = result.get("model") or "research-os-gateway"
    choices = result.get("choices") or [{}]
    message = (choices[0].get("message") or {}) if choices else {}
    text = message.get("content") or ""
    finish = choices[0].get("finish_reason") or "stop" if choices else "stop"

    def _frame(delta: dict, *, finish_reason=None, extra: dict | None = None) -> str:
        chunk = {
            "id": cid,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [
                {"index": 0, "delta": delta, "finish_reason": finish_reason}
            ],
        }
        if extra:
            chunk.update(extra)
        return f"data: {json.dumps(chunk)}\n\n"

    # 1. role priming.
    yield _frame({"role": "assistant"})
    # 2. content (single chunk — we have the whole answer already).
    if text:
        yield _frame({"content": text})
    # 3. terminal chunk: finish_reason + mirror routing metadata.
    extra = {}
    if "x_research_os" in result:
        extra["x_research_os"] = result["x_research_os"]
    yield _frame({}, finish_reason=finish, extra=extra)
    # 4. SSE done sentinel.
    yield "data: [DONE]\n\n"


def error_response(message: str, *, code: str = "research_os_error") -> dict:
    """An OpenAI-shaped error completion (so clients parse it normally)."""
    return {
        "id": f"chatcmpl-ro-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": "research-os-gateway",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": f"[Research-OS] {message}"},
                "finish_reason": "stop",
            }
        ],
        "error": {"message": message, "type": code},
    }
