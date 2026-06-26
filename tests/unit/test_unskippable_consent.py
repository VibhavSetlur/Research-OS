"""Daemon-enforced un-skippable consent layer.

server/autopilot_gate.py historically let the agent clear a floor gate by
passing its own ``confirmed=true``. That flag is written by the very actor
the gate constrains, so under pressure the agent can self-confirm past it.

When a daemon is running for the project it becomes the consent AUTHORITY:
the gate then requires a daemon-minted ``consent_token`` bound to the exact
(gate_key, argument-fingerprint), and the agent's confirmed=true no longer
suffices. With no daemon, behaviour degrades to the historical self-confirm
path so stdio-only users are unaffected.

These tests drive server/consent.py and the gate directly with a
hand-written ledger + a fake daemon descriptor (current PID = guaranteed
alive). No running daemon required.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

from research_os.server import consent
from research_os.server.autopilot_gate import enforce_autopilot_gate
from research_os.server.errors import RoError

# A representative floor gate used across these tests.
_TOOL = "tool_audit"
_ARGS = {"scope": "step", "dimension": "reproducibility"}
_GATE_KEY = "tool_audit:reproducibility"


def _set_autonomy(root: Path, level: str = "autopilot") -> None:
    cfg_dir = root / "inputs"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "researcher_config.yaml").write_text(
        yaml.safe_dump({"interaction": {"autonomy_level": level}})
    )


def _write_daemon_descriptor(root: Path, *, pid: int | None = None) -> None:
    """Advertise a 'running' daemon. Default pid = this process (alive)."""
    state = root / ".os_state"
    state.mkdir(parents=True, exist_ok=True)
    (state / "daemon.json").write_text(
        json.dumps({"pid": os.getpid() if pid is None else pid, "port": 8787})
    )


def _write_ledger(root: Path, grants: list[dict]) -> None:
    cdir = root / ".os_state" / "consent"
    cdir.mkdir(parents=True, exist_ok=True)
    (cdir / "granted.json").write_text(json.dumps({"grants": grants}))


def _grant(root: Path, *, token: str, gate_key: str = _GATE_KEY,
           tool: str = _TOOL, args: dict | None = None,
           expires_in_s: int = 300, consumed: bool = False) -> dict:
    fp = consent.arg_fingerprint(tool, args if args is not None else _ARGS)
    exp = (datetime.now(timezone.utc) + timedelta(seconds=expires_in_s))
    return {
        "token": token,
        "gate_key": gate_key,
        "tool": tool,
        "arg_fingerprint": fp,
        "granted_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": exp.isoformat().replace("+00:00", "Z"),
        "consumed": consumed,
        "granted_by": "researcher",
    }


# --- fingerprint -----------------------------------------------------------

def test_fingerprint_is_order_independent():
    a = consent.arg_fingerprint("t", {"x": 1, "y": 2})
    b = consent.arg_fingerprint("t", {"y": 2, "x": 1})
    assert a == b


def test_fingerprint_ignores_control_fields():
    base = consent.arg_fingerprint(_TOOL, _ARGS)
    with_token = consent.arg_fingerprint(
        _TOOL, {**_ARGS, "consent_token": "abc", "confirmed": True}
    )
    assert base == with_token


def test_fingerprint_differs_on_real_args():
    a = consent.arg_fingerprint(_TOOL, {"scope": "step"})
    b = consent.arg_fingerprint(_TOOL, {"scope": "project"})
    assert a != b


# --- daemon_present --------------------------------------------------------

def test_daemon_absent_when_no_descriptor(tmp_path):
    assert consent.daemon_present(tmp_path) is False


def test_daemon_present_with_live_pid(tmp_path):
    _write_daemon_descriptor(tmp_path)
    assert consent.daemon_present(tmp_path) is True


def test_daemon_absent_with_dead_pid(tmp_path):
    # PID 2^31-1 is effectively never a live process.
    _write_daemon_descriptor(tmp_path, pid=2_147_483_646)
    assert consent.daemon_present(tmp_path) is False


def test_daemon_absent_with_garbage_descriptor(tmp_path):
    state = tmp_path / ".os_state"
    state.mkdir(parents=True)
    (state / "daemon.json").write_text("{ not json")
    assert consent.daemon_present(tmp_path) is False


# --- DEGRADE path (no daemon) ---------------------------------------------

def test_no_daemon_confirmed_true_still_clears_gate(tmp_path):
    _set_autonomy(tmp_path, "autopilot")
    # No daemon descriptor → historical behaviour.
    enforce_autopilot_gate(_TOOL, {**_ARGS, "confirmed": True}, tmp_path)


def test_no_daemon_without_confirmed_blocks(tmp_path):
    _set_autonomy(tmp_path, "autopilot")
    with pytest.raises(RoError) as exc:
        enforce_autopilot_gate(_TOOL, dict(_ARGS), tmp_path)
    assert exc.value.what == "autopilot_gate_blocked"


# --- HARD path (daemon present) -------------------------------------------

def test_daemon_present_confirmed_true_no_longer_suffices(tmp_path):
    """The whole point: with a daemon, agent self-confirm is rejected."""
    _set_autonomy(tmp_path, "autopilot")
    _write_daemon_descriptor(tmp_path)
    with pytest.raises(RoError) as exc:
        enforce_autopilot_gate(_TOOL, {**_ARGS, "confirmed": True}, tmp_path)
    assert exc.value.what == "consent_required"


def test_daemon_present_valid_token_clears_gate(tmp_path):
    _set_autonomy(tmp_path, "autopilot")
    _write_daemon_descriptor(tmp_path)
    _write_ledger(tmp_path, [_grant(tmp_path, token="good-token")])
    enforce_autopilot_gate(
        _TOOL, {**_ARGS, "consent_token": "good-token"}, tmp_path
    )


def test_token_for_wrong_gate_key_rejected(tmp_path):
    _set_autonomy(tmp_path, "autopilot")
    _write_daemon_descriptor(tmp_path)
    _write_ledger(
        tmp_path,
        [_grant(tmp_path, token="t", gate_key="tool_package_install")],
    )
    with pytest.raises(RoError) as exc:
        enforce_autopilot_gate(
            _TOOL, {**_ARGS, "consent_token": "t"}, tmp_path
        )
    assert exc.value.what == "consent_required"


def test_token_for_different_args_rejected(tmp_path):
    """A token granted for action A cannot be replayed on action B."""
    _set_autonomy(tmp_path, "autopilot")
    _write_daemon_descriptor(tmp_path)
    # Grant bound to scope=project, but the call is scope=step.
    other = {"scope": "project", "dimension": "reproducibility"}
    _write_ledger(tmp_path, [_grant(tmp_path, token="t", args=other)])
    with pytest.raises(RoError) as exc:
        enforce_autopilot_gate(
            _TOOL, {**_ARGS, "consent_token": "t"}, tmp_path
        )
    assert exc.value.what == "consent_required"


def test_expired_token_rejected(tmp_path):
    _set_autonomy(tmp_path, "autopilot")
    _write_daemon_descriptor(tmp_path)
    _write_ledger(
        tmp_path, [_grant(tmp_path, token="t", expires_in_s=-10)]
    )
    with pytest.raises(RoError) as exc:
        enforce_autopilot_gate(
            _TOOL, {**_ARGS, "consent_token": "t"}, tmp_path
        )
    assert exc.value.what == "consent_required"


def test_consumed_token_rejected(tmp_path):
    _set_autonomy(tmp_path, "autopilot")
    _write_daemon_descriptor(tmp_path)
    _write_ledger(
        tmp_path, [_grant(tmp_path, token="t", consumed=True)]
    )
    with pytest.raises(RoError) as exc:
        enforce_autopilot_gate(
            _TOOL, {**_ARGS, "consent_token": "t"}, tmp_path
        )
    assert exc.value.what == "consent_required"


def test_valid_token_is_one_shot(tmp_path):
    """A valid token clears the gate exactly ONCE, then is burned.

    Regression for the defect live-verification caught: the reader only
    checked the daemon's ``consumed`` flag, which the agent could never
    trigger, so a single approval cleared unlimited gated calls. The gate
    now burns the token (server/consent.consume_grant) the instant it
    clears an action, so a replay of the same token is refused.
    """
    _set_autonomy(tmp_path, "autopilot")
    _write_daemon_descriptor(tmp_path)
    _write_ledger(tmp_path, [_grant(tmp_path, token="one-shot-tok")])

    # First use: clears the gate (no raise).
    enforce_autopilot_gate(
        _TOOL, {**_ARGS, "consent_token": "one-shot-tok"}, tmp_path
    )
    # Second use of the SAME token: must be refused — it was burned.
    with pytest.raises(RoError) as exc:
        enforce_autopilot_gate(
            _TOOL, {**_ARGS, "consent_token": "one-shot-tok"}, tmp_path
        )
    assert exc.value.what == "consent_required"


def test_spent_token_rejected_by_reader(tmp_path):
    """find_valid_grant returns None for a token already in the spent log."""
    _write_ledger(tmp_path, [_grant(tmp_path, token="t")])
    fp = consent.arg_fingerprint(_TOOL, _ARGS)
    # Valid before burning.
    assert consent.find_valid_grant(tmp_path, _GATE_KEY, fp, "t") is not None
    consent.consume_grant(tmp_path, "t")
    # None after burning.
    assert consent.find_valid_grant(tmp_path, _GATE_KEY, fp, "t") is None


def test_missing_token_with_daemon_rejected(tmp_path):
    _set_autonomy(tmp_path, "autopilot")
    _write_daemon_descriptor(tmp_path)
    _write_ledger(tmp_path, [_grant(tmp_path, token="t")])
    with pytest.raises(RoError) as exc:
        enforce_autopilot_gate(_TOOL, dict(_ARGS), tmp_path)
    assert exc.value.what == "consent_required"


def test_garbage_ledger_fails_closed(tmp_path):
    _set_autonomy(tmp_path, "autopilot")
    _write_daemon_descriptor(tmp_path)
    cdir = tmp_path / ".os_state" / "consent"
    cdir.mkdir(parents=True)
    (cdir / "granted.json").write_text("{ not valid json")
    with pytest.raises(RoError) as exc:
        enforce_autopilot_gate(
            _TOOL, {**_ARGS, "consent_token": "anything"}, tmp_path
        )
    assert exc.value.what == "consent_required"


def test_below_floor_adaptive_gate_still_flows_with_daemon(tmp_path, monkeypatch):
    """A daemon must not turn a below-floor adaptive gate into a hard stop.

    tool_audit:reproducibility floor is 'normal'. If a project resolves to
    'light' strictness in adaptive mode, the gate does not fire at all —
    consent enforcement should never even be reached.

    NB: resolve the gate fn from the live module object and patch THAT same
    object. Sibling tests (e.g. test_router_no_deg_false_positive) wipe
    research_os.* from sys.modules and re-import, so the module-level
    ``enforce_autopilot_gate`` imported at the top of this file can point at
    a stale module whose globals differ from the one we patch. Binding both
    the function and the patch to the current sys.modules entry keeps them
    sharing one globals namespace and makes this test pollution-proof.
    """
    _set_autonomy(tmp_path, "adaptive")
    _write_daemon_descriptor(tmp_path)

    import importlib

    ag = importlib.import_module("research_os.server.autopilot_gate")
    # Precondition: the project really is adaptive. If a polluting test left
    # global state that flips this to autopilot, fail loud and specific
    # instead of mysteriously hitting the consent gate below.
    assert ag._read_autonomy_level(tmp_path) == "adaptive"

    # Force light strictness on the SAME module the gate fn closes over.
    monkeypatch.setattr(ag, "_resolved_strictness", lambda root: "light")
    # No token, no confirmed — must NOT raise, because gate is below floor.
    ag.enforce_autopilot_gate(_TOOL, dict(_ARGS), tmp_path)
