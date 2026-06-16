"""Grounded reasoning + Reflexion lessons tests."""

from pathlib import Path

from research_os.tools.actions.research.grounding import (
    claim_verify,
    ground_from_context,
    grounding_for_decision,
    grounding_register,
    grounding_verify,
    thought_log,
    thought_trace,
)
from research_os.tools.actions.research.lessons import (
    lessons_consult,
    lessons_record,
)


# ── Thought log ──────────────────────────────────────────────────────


def test_thought_log_appends(tmp_path: Path):
    r = thought_log(tmp_path, kind="thought", content="Consider Welch t-test.")
    assert r["status"] == "success"
    assert r["trace_id"]


def test_thought_log_rejects_bad_kind(tmp_path: Path):
    r = thought_log(tmp_path, kind="ponder", content="...")
    assert r["status"] == "error"


def test_thought_trace_filters(tmp_path: Path):
    thought_log(tmp_path, kind="thought", content="A", step_id="01_eda")
    thought_log(tmp_path, kind="action", content="B", step_id="02_fit")
    thought_log(tmp_path, kind="observation", content="C", step_id="02_fit")
    r = thought_trace(tmp_path, step_id="02_fit")
    assert r["n_total"] == 2


# ── Grounding registry ──────────────────────────────────────────────


def test_grounding_register_requires_sources(tmp_path: Path):
    r = grounding_register(tmp_path, claim="X causes Y", sources=[])
    assert r["status"] == "error"


def test_grounding_register_records_prov_o(tmp_path: Path):
    r = grounding_register(
        tmp_path,
        claim="Welch's t-test preferred for unequal variances.",
        sources=[
            {"type": "paper", "citation_key": "welch1947", "doi": "10.1093/biomet/34.1-2.28",
             "cited_text": "When the variances are unequal..."},
        ],
    )
    assert r["status"] == "success"
    rec = grounding_for_decision(tmp_path, r["decision_id"])
    assert rec is not None
    assert rec["prov:used"][0]["citation_key"] == "welch1947"


def test_ground_from_context(tmp_path: Path):
    ctx = tmp_path / "inputs" / "context" / "intake.md"
    ctx.parent.mkdir(parents=True)
    ctx.write_text("Primary outcome is improvement on the MoCA score.\n")
    r = ground_from_context(
        tmp_path,
        claim="Primary outcome is MoCA improvement.",
        context_paths=["inputs/context/intake.md"],
    )
    assert r["status"] == "success"


def test_claim_verify_records_cove(tmp_path: Path):
    # Provenance-bound verification: supports:true is only honoured when
    # the cited source actually contains the token. Write the substrate
    # files first.
    rep = tmp_path / "workspace" / "01_eda" / "outputs" / "reports"
    rep.mkdir(parents=True)
    (rep / "levene.md").write_text("Levene p = 0.003\n")
    (rep / "bartlett.md").write_text("Bartlett p = 0.01\n")
    r = claim_verify(
        tmp_path,
        claim="Variances are unequal across groups.",
        verifications=[
            {"question": "Does Levene reject equality?",
             "answer": "p = 0.003 — yes",
             "supports": True,
             "evidence": {"type": "workspace_artefact",
                          "path": "workspace/01_eda/outputs/reports/levene.md",
                          "cited_text": "Levene p = 0.003"}},
            {"question": "Does Bartlett agree?",
             "answer": "p = 0.01 — yes",
             "supports": True,
             "evidence": {"type": "workspace_artefact",
                          "path": "workspace/01_eda/outputs/reports/bartlett.md",
                          "cited_text": "Bartlett p = 0.01"}},
        ],
    )
    assert r["status"] == "success"
    assert r["verdict"] == "verified"


def test_claim_verify_unverified_without_substrate(tmp_path: Path):
    # supports:true with no cited source can no longer self-grade to
    # 'verified' — it is now 'unverified' (provenance-bound check).
    r = claim_verify(
        tmp_path,
        claim="Variances are unequal across groups.",
        verifications=[
            {"question": "Does Levene reject equality?",
             "answer": "p = 0.003 — yes",
             "supports": True},
        ],
    )
    assert r["status"] == "success"
    assert r["verdict"] == "unverified"


def test_claim_verify_flags_needs_revision(tmp_path: Path):
    r = claim_verify(
        tmp_path,
        claim="Effect is causal.",
        verifications=[
            {"question": "RCT?", "answer": "no", "supports": False},
        ],
    )
    assert r["verdict"] == "needs_revision"


def test_grounding_verify_empty_workspace(tmp_path: Path):
    # No analysis.md → success with n=0.
    r = grounding_verify(tmp_path)
    assert r["status"] == "success"
    assert r["n_decisions"] == 0


# ── Lessons ──────────────────────────────────────────────────────────


def test_lessons_record_basic(tmp_path: Path):
    r = lessons_record(
        tmp_path,
        outcome="failure",
        reflection="Misread the column type; the join silently dropped rows.",
        recommendation="Always validate row count after every join.",
        tags=["pandas", "join", "data"],
    )
    assert r["status"] == "success"


def test_lessons_consult_returns_relevant(tmp_path: Path):
    lessons_record(
        tmp_path, outcome="failure",
        reflection="Pandas join dropped rows due to key type mismatch.",
        tags=["pandas", "join"],
    )
    lessons_record(
        tmp_path, outcome="success",
        reflection="Bootstrap CI worked well for skewed data.",
        tags=["bootstrap", "ci"],
    )
    r = lessons_consult(tmp_path, task="merge two pandas frames", tags=["pandas"])
    assert r["status"] == "success"
    # The pandas-tagged failure should rank highest.
    assert r["lessons"]
    assert "pandas" in r["lessons"][0]["tags"]
