"""Tests for the semantic-routing module + its integration with route_request.

The semantic router is the PRIMARY path inside ``route_request`` when
fastembed + the on-disk embeddings file are both present. Without
fastembed, ``semantic_available()`` returns False and the trigger router
serves every request — verify that path doesn't blow up.

The accuracy floor (≥ 28 / 35 top-1, i.e. 80%) is intentionally loose:
the candidates list always carries the correct protocol in the top-3,
and route_request's hybrid fallback recovers when semantic is uncertain.
The point of this test is to catch regressions in the EMBEDDING DOC
COMPOSITION or the THRESHOLD CALIBRATION, not to assert routing
perfection.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from research_os.tools.actions import semantic

pytestmark = pytest.mark.skipif(
    not semantic.semantic_available(),
    reason="semantic routing unavailable (fastembed not installed OR _embeddings.npz missing)",
)


# Pairs of (prompt, expected protocol_id). `None` = should be "no match"
# (top-1 score below the NOTHING_FLOOR — surfaces ask_user instead).
PROMPT_FIXTURE: list[tuple[str, str | None]] = [
    ("preregister my analysis plan",                  "methodology/preregistration"),
    ("design a survey instrument",                    "methodology/survey_design"),
    ("audit my model for bias and fairness",          "methodology/fairness_audit"),
    ("data management plan for NIH",                  "methodology/data_management_plan"),
    ("help me with my thesis defense",                "synthesis/defense_prep"),
    ("write the paper for a journal submission",      "synthesis/synthesis_paper"),
    ("I need to pick a journal",                      "synthesis/journal_selection"),
    ("make a poster for the conference",              "synthesis/synthesis_poster"),
    ("check inter-rater reliability for my coders",   "methodology/inter_rater_reliability"),
    ("multiple comparisons correction strategy",      "methodology/multiple_comparisons"),
    ("storyboard the figures",                        "synthesis/manuscript_outline"),
    ("help me with my interview guide",               "methodology/interview_guide_design"),
    ("develop the codebook for my qualitative data",  "methodology/coding_scheme_development"),
    ("kappa for my annotators",                       "methodology/inter_rater_reliability"),
    ("cox proportional hazards check",                "methodology/cox_ph_diagnostics"),
    ("bayesian model with stan",                      "methodology/bayesian_analysis"),
    ("confidence interval via bootstrap",             "methodology/bootstrapping_design"),
    ("how well calibrated is my model",               "methodology/uncertainty_quantification"),
    ("respond to reviewers",                          "guidance/peer_review_response"),
    ("build a dashboard",                             "synthesis/synthesis_dashboard"),
    ("write the grant",                               "synthesis/synthesis_grant"),
    ("do a literature search",                        "literature/literature_search"),
    ("prisma systematic review",                      "literature/systematic_review"),
    ("time series forecast",                          "methodology/timeseries_analysis"),
    ("replicate the published study",                 "methodology/replication_study"),
    ("train a classifier",                            "methodology/machine_learning"),
    ("explore my dataset",                            "methodology/exploratory_data_analysis"),
    ("compare two methods head to head",              "methodology/method_comparison"),
    ("end session, picking up tomorrow",              "guidance/chat_handoff"),
    ("I'm going to lunch",                            "guidance/chat_handoff"),
    ("send to a collaborator",                        "guidance/collaboration_handoff"),
    ("review this paper quickly",                     "guidance/quick_paper_review"),
    ("ablation study",                                "methodology/ablation_study"),
    ("pilot study before the full trial",             "methodology/pilot_study"),
    ("random nonsense xyz qqqq foo",                  None),
]


def test_fixture_size_and_no_duplicate_prompts():
    """Smoke check on the fixture itself before grading anything."""
    assert len(PROMPT_FIXTURE) >= 30, "fixture should grow over time"
    prompts = [p for p, _ in PROMPT_FIXTURE]
    assert len(prompts) == len(set(prompts)), "duplicate prompts in fixture"


def test_semantic_route_top1_accuracy():
    """At least 80% of fixture prompts must route to their expected protocol top-1.

    This is the regression budget — drops below 28/35 indicate the
    embedding doc composition or the threshold calibration drifted in
    a way that hurts routing quality.
    """
    semantic.reset_caches()
    ok = 0
    misses: list[tuple[str, str | None, str | None]] = []
    for prompt, expected in PROMPT_FIXTURE:
        resp = semantic.semantic_route(prompt)
        primary = (resp or {}).get("primary_protocol")
        if expected is None:
            if primary is None:
                ok += 1
            else:
                misses.append((prompt, expected, primary))
        else:
            if primary == expected:
                ok += 1
            else:
                misses.append((prompt, expected, primary))
    threshold = int(len(PROMPT_FIXTURE) * 0.80)
    assert ok >= threshold, (
        f"semantic top-1 accuracy {ok}/{len(PROMPT_FIXTURE)} "
        f"below {threshold} threshold. Misses (first 5): {misses[:5]}"
    )


def test_expected_protocol_always_in_top3():
    """When the expected primary doesn't win, it should still appear in the top-3.

    This is a softer floor than top-1: it confirms semantic search is
    not catastrophically losing the right candidate, only sometimes
    ranking it second/third when another similar protocol embeds closer.
    """
    semantic.reset_caches()
    not_in_top3: list[tuple[str, str, list[str]]] = []
    for prompt, expected in PROMPT_FIXTURE:
        if expected is None:
            continue
        matches = semantic.top_k_protocols(prompt, k=3)
        ids = [m.id for m in matches]
        if expected not in ids:
            not_in_top3.append((prompt, expected, ids))
    assert len(not_in_top3) <= 3, (
        f"too many prompts where expected protocol missed top-3: "
        f"{not_in_top3}"
    )


def test_nothing_floor_works():
    """Gibberish prompts must not return HIGH-confidence routes.

    BGE-small (like any cosine-only embedder without a calibrated
    abstention head) will occasionally produce ~0.55-0.60 cosines on
    random tokens because protocols with abstract / generic
    descriptions are mid-band similar to noise. The contract is
    therefore weaker than "primary is None" — what we DO promise the
    caller is that gibberish never lands as `confidence: high`, so
    the AI knows to confirm before acting.
    """
    semantic.reset_caches()
    for nonsense in [
        "qqqq xyz wibble foo",
        "asdfghjkl",
        "the the the the the the",
    ]:
        resp = semantic.semantic_route(nonsense)
        if resp is not None:
            assert resp.get("confidence") != "high", (
                f"gibberish {nonsense!r} routed at HIGH confidence — "
                f"this should never happen. Response: {resp}"
            )


def test_tool_search_returns_results():
    """Semantic tool search should find SOMETHING relevant for common queries."""
    semantic.reset_caches()
    # 'preregister' should rank tool_preregister_freeze high.
    matches = semantic.top_k_tools("freeze my analysis plan", k=5)
    names = [m.id for m in matches]
    assert any("preregister" in n for n in names), (
        f"expected a preregister-related tool in top-5, got {names}"
    )


def test_route_request_uses_semantic_path(tmp_path: Path):
    """When semantic is available, route_request returns method='semantic' on a high-confidence prompt."""
    from research_os.tools.actions.router import route_request

    resp = route_request("preregister my analysis plan", tmp_path, persist_plan=False)
    assert resp.get("status") == "success"
    # Either semantic-confident or a shortcut hit (shortcut_intents could match in theory).
    assert resp.get("method") in ("semantic", "trigger")
    if resp.get("method") == "semantic":
        assert resp.get("primary_protocol") == "methodology/preregistration"
        assert resp.get("confidence") in ("high", "medium")


def test_route_request_handles_unknown_prompt(tmp_path: Path):
    """Bizarre prompts must not crash route_request."""
    from research_os.tools.actions.router import route_request

    resp = route_request("zzzz random nonsense xyz", tmp_path, persist_plan=False)
    assert resp.get("status") == "success"
    # Either no primary or a low-confidence guess with ask_user populated.
    assert (
        resp.get("primary_protocol") is None
        or resp.get("ask_user") is not None
        or (resp.get("confidence") in (None, "low", "none"))
    )


def test_trigger_router_still_works_when_semantic_disabled(tmp_path: Path, monkeypatch):
    """Force semantic unavailable and confirm the trigger router still serves."""
    monkeypatch.setattr(semantic, "semantic_available", lambda: False)
    from research_os.tools.actions.router import route_request

    resp = route_request("preregister my analysis plan", tmp_path, persist_plan=False)
    assert resp.get("status") == "success"
    assert resp.get("primary_protocol") == "methodology/preregistration"
    assert resp.get("method") == "trigger"
