"""Provenance-bound verification: tool_verify checks the cited substrate.

Previously claim_verify recorded supports:true exactly as the model
asserted. Now each supporting verification's cited file must resolve AND
contain the claimed token, else the entry is downgraded / flagged
unverifiable.
"""

from pathlib import Path

from research_os.tools.actions.research.grounding import claim_verify


def _evidence_file(root: Path, rel: str, body: str) -> str:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body)
    return rel


# ── confirmed: cited file exists AND contains the token ──────────────


def test_verify_confirmed_when_token_present(tmp_path: Path):
    rel = _evidence_file(
        tmp_path, "workspace/01/outputs/stats.md", "Levene p = 0.003\n"
    )
    res = claim_verify(
        tmp_path,
        claim="Variances are unequal across the two groups.",
        verifications=[{
            "question": "Is Levene significant?",
            "answer": "p = 0.003",
            "supports": True,
            "evidence": {"type": "workspace_artefact", "path": rel,
                         "cited_text": "Levene p = 0.003"},
        }],
    )
    assert res["status"] == "success"
    assert res["verdict"] == "verified"
    assert res["n_confirmed"] == 1
    sub = res["verifications"][0]["substrate_check"]
    assert sub["substrate"] == "confirmed"


def test_verify_numeric_tolerant_match(tmp_path: Path):
    rel = _evidence_file(
        tmp_path, "workspace/01/outputs/r.md", "accuracy: 0.8401\n"
    )
    res = claim_verify(
        tmp_path,
        claim="Accuracy is 0.84.",
        verifications=[{
            "supports": True,
            "evidence": {"path": rel, "cited_text": "0.84"},
        }],
    )
    assert res["verdict"] == "verified"


# ── needs_revision: asserted support but token NOT in the file ───────


def test_verify_downgrades_when_token_absent(tmp_path: Path):
    rel = _evidence_file(
        tmp_path, "workspace/01/outputs/stats.md", "Levene p = 0.42\n"
    )
    res = claim_verify(
        tmp_path,
        claim="Variances are unequal.",
        verifications=[{
            "supports": True,
            "evidence": {"path": rel, "cited_text": "Levene p = 0.003"},
        }],
    )
    # Source contradicts the asserted support → not verified.
    assert res["verdict"] == "needs_revision"
    assert res["n_supports"] == 0
    assert res["n_contradicted"] == 1
    sub = res["verifications"][0]["substrate_check"]
    assert sub["substrate"] == "missing_token"


def test_verify_downgrades_when_file_missing(tmp_path: Path):
    res = claim_verify(
        tmp_path,
        claim="X holds.",
        verifications=[{
            "supports": True,
            "evidence": {"path": "workspace/does_not_exist.csv",
                         "cited_text": "X"},
        }],
    )
    assert res["verdict"] == "needs_revision"
    sub = res["verifications"][0]["substrate_check"]
    assert sub["substrate"] == "missing_file"


def test_verify_rejects_path_traversal(tmp_path: Path):
    res = claim_verify(
        tmp_path,
        claim="escape attempt",
        verifications=[{
            "supports": True,
            "evidence": {"path": "../../etc/passwd", "cited_text": "root"},
        }],
    )
    sub = res["verifications"][0]["substrate_check"]
    assert sub["substrate"] == "missing_file"
    assert res["verdict"] == "needs_revision"


# ── unverified: asserted support, file exists, but no locator given ──


def test_verify_unverified_when_no_locator(tmp_path: Path):
    rel = _evidence_file(tmp_path, "workspace/01/r.md", "some content\n")
    res = claim_verify(
        tmp_path,
        claim="Y is true.",
        verifications=[{
            "supports": True,
            "evidence": {"path": rel},  # no cited_text/locator
        }],
    )
    # File exists but nothing to substantiate against → unverified.
    assert res["verdict"] == "unverified"
    assert res["n_unverifiable"] == 1
    sub = res["verifications"][0]["substrate_check"]
    assert sub["substrate"] == "no_locator"


def test_verify_unverified_when_no_path(tmp_path: Path):
    res = claim_verify(
        tmp_path,
        claim="Z follows from reasoning.",
        verifications=[{
            "supports": True,
            "answer": "by transitivity",
            # no evidence at all
        }],
    )
    assert res["verdict"] == "unverified"
    sub = res["verifications"][0]["substrate_check"]
    assert sub["substrate"] == "no_path"


# ── model-said-no still propagates ───────────────────────────────────


def test_verify_needs_revision_when_model_says_unsupported(tmp_path: Path):
    rel = _evidence_file(tmp_path, "workspace/01/r.md", "anything\n")
    res = claim_verify(
        tmp_path,
        claim="W is true.",
        verifications=[{
            "supports": False,
            "evidence": {"path": rel, "cited_text": "anything"},
        }],
    )
    assert res["verdict"] == "needs_revision"
    assert res["n_supports"] == 0
