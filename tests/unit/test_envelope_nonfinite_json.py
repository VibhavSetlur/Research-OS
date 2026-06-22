"""C1b: the shared _text serializer must never emit invalid JSON tokens.

json.dumps defaults to allow_nan=True and emits the JS-only literals
NaN / Infinity / -Infinity (invalid per RFC 8259). _text now serialises with
allow_nan=False and recursively sanitises non-finite floats to null on
fallback, so every tool — not just data_profile — is protected.
"""
from __future__ import annotations

import json

from research_os.server.envelopes import _sanitize_nonfinite, _text


def test_text_serialises_nan_and_inf_as_null():
    payload = {
        "status": "success",
        "columns": [
            {"name": "x", "mean": float("inf"), "std": float("nan")},
            {"name": "y", "min": float("-inf"), "max": 3.0},
        ],
        "nested": {"deep": [float("nan"), 1.5]},
    }
    text = _text(payload)[0].text
    # The emitted text must be valid strict JSON (no NaN/Infinity tokens).
    assert "NaN" not in text and "Infinity" not in text
    parsed = json.loads(text)  # parses without parse_constant hacks
    assert parsed["columns"][0]["mean"] is None
    assert parsed["columns"][0]["std"] is None
    assert parsed["columns"][1]["min"] is None
    assert parsed["columns"][1]["max"] == 3.0
    assert parsed["nested"]["deep"] == [None, 1.5]


def test_text_finite_payload_unchanged():
    payload = {"a": 1, "b": 2.5, "c": ["x", {"d": 4.0}]}
    parsed = json.loads(_text(payload)[0].text)
    assert parsed == payload


def test_sanitize_nonfinite_recurses_lists_and_dicts():
    obj = {"a": [float("nan"), {"b": float("inf")}], "c": (1.0, float("-inf"))}
    out = _sanitize_nonfinite(obj)
    assert out == {"a": [None, {"b": None}], "c": [1.0, None]}
