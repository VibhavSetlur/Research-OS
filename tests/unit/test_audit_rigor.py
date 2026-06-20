"""3.2.9 — scientific-rigor fixes to the statistical audit gates.

Locks the methodology corrections: claim-grounding integer-exact + CI/p-value
exclusion (A1/A2), power test-family awareness + numeric coercion (A3/C1),
E-value scale conversion (A5).
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from research_os.tools.actions.audit.claim_grounding import (
    _claim_grounded,
    extract_claims,
)


def _root():
    return Path(tempfile.mkdtemp())


# -- A1: integer claims match EXACTLY (no relative tolerance) -----------------


def test_integer_claim_requires_exact_match():
    # A hallucinated N=2456 must NOT "ground" to a real 2469 (0.5% off).
    assert _claim_grounded(2456.0, {2469.0}, 0.01, is_int=True) is False
    assert _claim_grounded(2456.0, {2456.0}, 0.01, is_int=True) is True


def test_float_claim_keeps_relative_tolerance():
    # Genuine floats still match within 1%.
    assert _claim_grounded(0.84, {0.838}, 0.01) is True


# -- A2: CI levels + p-value thresholds are not extracted as claims -----------


def test_ci_level_and_pvalue_threshold_excluded():
    p = _root() / "paper.md"
    p.write_text("AUROC 0.84 (95% CI 0.79-0.89), p<0.001, on N=2456 patients.\n")
    toks = {c["token"] for c in extract_claims(p)}
    assert "95%" not in toks          # CI confidence level excluded
    assert "0.001" not in toks        # p-value threshold excluded
    assert {"0.84", "0.79", "0.89", "2456"} <= toks  # real estimates kept


def test_pvalue_guard_does_not_eat_unrelated_numbers():
    p = _root() / "paper.md"
    p.write_text("The pipeline ran step < 5 phases and 3 groups.\n")
    toks = {c["token"] for c in extract_claims(p)}
    assert "5" in toks and "3" in toks  # 'step <' must NOT match the p-value guard


def test_integer_claims_flagged_is_int():
    p = _root() / "paper.md"
    p.write_text("We enrolled 2456 patients with AUROC 0.84.\n")
    by_tok = {c["token"]: c for c in extract_claims(p)}
    assert by_tok["2456"]["is_int"] is True
    assert by_tok["0.84"]["is_int"] is False


# -- A3 / A4: power is test-family aware ------------------------------------


def test_power_differs_by_test_family():
    pytest.importorskip("statsmodels")
    from research_os.tools.actions.audit.audit import audit_power
    r = _root()
    two = audit_power("f.py", 0.5, 0.05, 30, r, test="two_sample_t")["report"]["power"]
    paired = audit_power("f.py", 0.5, 0.05, 30, r, test="paired_t")["report"]["power"]
    assert abs(two - paired) > 0.05  # a paired design is NOT the two-sample figure


def test_power_anova_requires_k_groups():
    pytest.importorskip("statsmodels")
    from research_os.tools.actions.audit.audit import audit_power
    r = _root()
    assert audit_power("f.py", 0.4, 0.05, 20, r, test="anova")["status"] == "error"
    ok = audit_power("f.py", 0.4, 0.05, 20, r, test="anova", k_groups=3)
    assert ok["status"] in ("success", "warning")
    assert ok["report"]["assumed_test"] == "anova"


def test_power_report_stamps_assumed_test():
    pytest.importorskip("statsmodels")
    from research_os.tools.actions.audit.audit import audit_power
    r = _root()
    res = audit_power("f.py", 0.5, 0.05, 30, r)
    assert res["report"]["assumed_test"] == "two_sample_t"


# -- C1: power handler coerces stringified numeric args ----------------------


def test_power_handler_coerces_string_args():
    pytest.importorskip("statsmodels")
    import json

    import research_os.server as srv
    out = srv._handle_tool_call(
        "tool_audit",
        {"scope": "step", "dimension": "power", "filepath": "f.py",
         "effect_size": "0.5", "alpha": "0.05", "n": "30"},
        _root(),
    )
    env = json.loads(out[0].text)
    assert env["status"] in ("success", "warning")  # not a TypeError crash


# -- A5: E-value scale conversion -------------------------------------------


def test_evalue_converts_common_outcome_or_to_rr():
    from research_os.tools.actions.audit.audit import audit_evalue
    r = _root()
    res = audit_evalue(4.0, r, effect_measure="or")  # RR ≈ sqrt(4) = 2.0
    assert abs(res["risk_ratio"] - 2.0) < 0.01
    assert res["scale_note"]


def test_evalue_rr_default_unchanged():
    from research_os.tools.actions.audit.audit import audit_evalue
    r = _root()
    res = audit_evalue(2.0, r)
    assert abs(res["risk_ratio"] - 2.0) < 0.01
    assert res["effect_measure"] == "rr"


def test_evalue_rare_outcome_uses_value_directly():
    from research_os.tools.actions.audit.audit import audit_evalue
    r = _root()
    res = audit_evalue(3.0, r, effect_measure="or", rare_outcome=True)
    assert abs(res["risk_ratio"] - 3.0) < 0.01  # OR≈RR for rare outcomes
