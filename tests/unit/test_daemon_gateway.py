"""Unit tests for the OpenAI-compatible gateway (Phase 2).

Entirely network-free: ``forward_fn`` is injected with a fake upstream so
the routing, context injection, and tool-call loop are exercised without
any API key or HTTP call.
"""
from __future__ import annotations

import json

from research_os.daemon import gateway
from research_os.daemon.core import Daemon


# ── context assembly ──────────────────────────────────────────────────


def test_build_context_no_root():
    """No workspace -> available False, still returns a usable system msg."""
    daemon = Daemon.for_root(None)
    ctx = gateway.build_context_block("analyze my data", daemon)
    assert ctx["available"] is False
    assert "Research-OS" in ctx["system"]
    # No route/domain/freshness without a root, but never crashes.
    assert ctx["route"] is None


def test_build_context_with_root(tmp_path):
    """A resolved root routes the prompt and injects domain awareness."""
    daemon = Daemon.for_root(tmp_path)
    ctx = gateway.build_context_block("plan a new experiment", daemon)
    assert ctx["available"] is True
    # Domain detection runs (GENERIC fallback at minimum).
    assert ctx["domain"] is not None
    assert "RESEARCH FIELD" in ctx["system"]


def test_route_summary_handles_failure():
    assert "general assistance" in gateway._route_summary({"status": "error"})
    assert "general assistance" in gateway._route_summary({})


def test_route_summary_with_protocol():
    summary = gateway._route_summary(
        {
            "status": "success",
            "primary_protocol": "guidance/analysis_plan",
            "intent_class": "execute",
            "sub_intent": "new_experiment",
            "advice": "Load the protocol first.",
            "decomposition": ["sys_boot", "tool_route"],
        }
    )
    assert "guidance/analysis_plan" in summary
    assert "execute/new_experiment" in summary
    assert "Load the protocol first." in summary
    assert "sys_boot" in summary


# ── tool schema bridge ────────────────────────────────────────────────


def test_research_os_tools_shape():
    tools = gateway.research_os_tools(limit=5)
    assert len(tools) == 5
    for t in tools:
        assert t["type"] == "function"
        fn = t["function"]
        assert isinstance(fn["name"], str) and fn["name"]
        assert isinstance(fn["description"], str)
        assert isinstance(fn["parameters"], dict)


def test_to_openai_tool_uses_short_then_description():
    spec = {"short": "Short desc", "description": "Long desc", "inputSchema": {"type": "object"}}
    out = gateway._to_openai_tool("sys_x", spec)
    assert out["function"]["description"] == "Short desc"
    assert out["function"]["parameters"] == {"type": "object"}


def test_to_openai_tool_falls_back_to_name():
    out = gateway._to_openai_tool("sys_y", {})
    assert out["function"]["description"] == "sys_y"
    # Empty schema is still a valid object schema.
    assert out["function"]["parameters"]["type"] == "object"


# ── tool execution ────────────────────────────────────────────────────


def test_execute_tool_call_unknown_tool_returns_error(tmp_path):
    call = {"function": {"name": "definitely_not_a_tool", "arguments": "{}"}}
    out = gateway.execute_tool_call(call, tmp_path)
    # Returns text (the dispatch seam's did-you-mean / error envelope).
    assert isinstance(out, str) and out


def test_execute_tool_call_bad_json_args(tmp_path):
    call = {"function": {"name": "sys_boot", "arguments": "{not json"}}
    # Must not raise even with malformed arguments.
    out = gateway.execute_tool_call(call, tmp_path)
    assert isinstance(out, str)


# ── completion loop ───────────────────────────────────────────────────


def _final_response(text="done"):
    return {
        "id": "chatcmpl-1",
        "object": "chat.completion",
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": text},
             "finish_reason": "stop"}
        ],
    }


def test_run_completion_no_tools(tmp_path):
    """A plain completion: one forward, context injected, metadata stamped."""
    daemon = Daemon.for_root(tmp_path)
    seen = {}

    def fake_forward(body, headers):
        seen["body"] = body
        return _final_response("hello")

    body = {"model": "x", "messages": [{"role": "user", "content": "what is pca"}]}
    resp = gateway.run_completion(body, daemon, fake_forward, max_tool_rounds=6)

    # System context was prepended.
    assert seen["body"]["messages"][0]["role"] == "system"
    assert "Research-OS" in seen["body"]["messages"][0]["content"]
    # Tools were advertised.
    assert "tools" in seen["body"]
    # Routing metadata stamped on the response.
    assert "x_research_os" in resp
    assert resp["x_research_os"]["tool_rounds"] == 0


def test_run_completion_tool_loop(tmp_path):
    """Model requests a tool, gateway executes it, loops to a final answer."""
    daemon = Daemon.for_root(tmp_path)
    calls = {"n": 0}

    def fake_forward(body, headers):
        calls["n"] += 1
        if calls["n"] == 1:
            # First turn: model asks for a tool call.
            return {
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {"name": "sys_boot", "arguments": "{}"},
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ]
            }
        # Second turn: model produces the final answer.
        return _final_response("finished")

    body = {"model": "x", "messages": [{"role": "user", "content": "boot the session"}]}
    resp = gateway.run_completion(body, daemon, fake_forward, max_tool_rounds=6)

    assert calls["n"] == 2  # one tool round + final
    assert resp["x_research_os"]["tool_rounds"] == 1
    assert resp["choices"][0]["message"]["content"] == "finished"


def test_run_completion_respects_max_rounds(tmp_path):
    """An LLM that loops forever is bounded by max_tool_rounds."""
    daemon = Daemon.for_root(tmp_path)
    calls = {"n": 0}

    def always_tool(body, headers):
        calls["n"] += 1
        return {
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {"id": f"c{calls['n']}", "type": "function",
                             "function": {"name": "sys_boot", "arguments": "{}"}}
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ]
        }

    body = {"model": "x", "messages": [{"role": "user", "content": "loop"}]}
    resp = gateway.run_completion(body, daemon, always_tool, max_tool_rounds=3)
    # 3 tool rounds = 1 initial + 3 follow-up forwards = 4 calls.
    assert calls["n"] == 4
    assert resp["x_research_os"]["tool_rounds"] == 3


def test_run_completion_does_not_override_client_tools(tmp_path):
    """If the client already passes tools, the gateway leaves them alone."""
    daemon = Daemon.for_root(tmp_path)
    seen = {}

    def fake_forward(body, headers):
        seen["body"] = body
        return _final_response()

    body = {
        "model": "x",
        "messages": [{"role": "user", "content": "hi"}],
        "tools": [{"type": "function", "function": {"name": "client_tool"}}],
    }
    gateway.run_completion(body, daemon, fake_forward)
    assert seen["body"]["tools"] == body["tools"]


# ── error shaping ─────────────────────────────────────────────────────


def test_error_response_is_openai_shaped():
    err = gateway.error_response("no token configured")
    assert err["object"] == "chat.completion"
    assert err["choices"][0]["message"]["role"] == "assistant"
    assert "no token configured" in err["choices"][0]["message"]["content"]
    assert err["error"]["message"] == "no token configured"


# ── capabilities (agent front door) ──────────────────────────────────


def test_capabilities_no_root():
    """No workspace -> still self-describes (identity + tools + protocols)."""
    daemon = Daemon.for_root(None)
    cap = gateway.build_capabilities(daemon)
    assert cap["service"] == "research-os"
    assert cap["available"] is False
    assert cap["version"]
    # Endpoints + tool/protocol inventory are root-independent.
    assert "chat" in cap["endpoints"]
    assert cap["tools"]["total"] > 0
    assert cap["tools"]["by_category"]
    assert cap["protocols"]["total"] > 0


def test_capabilities_with_root_has_field_and_state(tmp_path):
    """A resolved root adds field detection + work-state freshness."""
    daemon = Daemon.for_root(tmp_path)
    cap = gateway.build_capabilities(daemon)
    assert cap["available"] is True
    assert cap["field"]["id"]  # GENERIC fallback at minimum
    assert "confidence" in cap["field"]
    # Empty project: zero recorded results, never crashes.
    assert cap["work_state"]["recorded_results"] == 0


def test_capabilities_tool_schemas_opt_in():
    """Full OpenAI schemas only ride along when explicitly requested."""
    daemon = Daemon.for_root(None)
    lean = gateway.build_capabilities(daemon)
    full = gateway.build_capabilities(daemon, include_tool_schemas=True)
    assert "schemas" not in lean["tools"]
    assert isinstance(full["tools"]["schemas"], list)
    assert full["tools"]["schemas"][0]["type"] == "function"


def test_capabilities_gateway_readiness_no_secrets():
    """Gateway block reports booleans only — never the token/key value."""
    daemon = Daemon.for_root(None, enable_gateway=True)
    cap = gateway.build_capabilities(daemon)
    gw = cap["gateway"]
    assert gw["enabled"] is True
    assert gw["token_set"] in (True, False)
    assert gw["api_key_set"] in (True, False)
    # No raw secret leaks into the payload.
    blob = json.dumps(cap)
    assert "RESEARCH_OS_GATEWAY_TOKEN" not in blob or "token_set" in blob

