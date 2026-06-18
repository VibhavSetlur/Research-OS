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


# Harder, real-world PARAPHRASE / jargon prompts — the queries that don't
# contain a protocol's exact trigger phrase (the misfires users actually hit).
# 3.2.3 lifted top-1 here from 52% → 88% via targeted trigger coverage. This
# fixture is the permanent guard: routing quality on paraphrases must not
# regress below the budget. A handful of genuinely-ambiguous near-synonym
# pairs (dashboard deliverable vs viz design, casual vs formal exploration,
# reviewer-response deliverable vs the peer-review-response protocol) are
# expected to sometimes land on the sibling — hence the top-3 floor.
HARD_FIXTURE: list[tuple[str, str]] = [
    ("lock in my hypotheses and analysis before I peek at the data", "methodology/preregistration"),
    ("the reviewer says I tested too many things so my p-values are inflated", "methodology/multiple_comparisons"),
    ("my two annotators keep disagreeing on the labels", "methodology/inter_rater_reliability"),
    ("make sure someone else can rerun my whole pipeline and get the same numbers", "reproducibility/reproducibility"),
    ("wrapping up for the day, I'll continue tomorrow", "guidance/chat_handoff"),
    ("what journal should I aim for", "synthesis/journal_selection"),
    ("knit everything into a manuscript draft", "synthesis/synthesis_paper"),
    ("how many participants do I need to detect the effect", "methodology/power_analysis"),
    ("my dataset has a lot of empty cells and gaps", "methodology/missing_data_strategy"),
    ("draft the part about what my study cannot conclude", "writing/writing_limitations"),
    ("the colours in my plot are not colourblind safe", "visualization/color_accessibility_audit"),
    ("set up a new project, I have some data and a question", "guidance/project_startup"),
    ("add a definition for a domain term to the glossary", "guidance/glossary_update"),
    ("this approach isn't working, abandon it and move on", "guidance/dead_end_routing"),
    ("summarize my findings for a general audience", "synthesis/synthesis_lay_summary"),
    ("check my code for bugs and style", "guidance/code_review"),
    ("is this relationship causal or just correlation", "methodology/causal_inference_deep"),
    ("the data has timestamps, predict future values", "methodology/timeseries_analysis"),
    ("register where my data lives for the funder", "methodology/data_management_plan"),
    ("does the original paper's result hold on my data", "methodology/replication_study"),
    ("tune the model honestly without overfitting", "methodology/hyperparameter_search_design"),
    ("fit a survival model and check its assumptions", "methodology/cox_ph_diagnostics"),
    ("how well calibrated are my model's probabilities", "methodology/uncertainty_quantification"),
    ("respond to the reviewers point by point", "guidance/peer_review_response"),
    ("forecast next quarter from the historical series", "methodology/timeseries_analysis"),
]


def test_hard_paraphrase_top1_budget():
    """Paraphrase / jargon prompts (no exact trigger) must route top-1 at
    >= 80%. This is the 3.2.3 accuracy guard — the queries users actually
    misfire on. Regressions here mean trigger coverage or doc composition
    drifted."""
    if not semantic.semantic_available():
        import pytest
        pytest.skip("semantic routing unavailable")
    semantic.reset_caches()
    ok = 0
    misses: list[tuple[str, str, list[str]]] = []
    for prompt, expected in HARD_FIXTURE:
        ids = [m.id for m in semantic.top_k_protocols(prompt, k=3)]
        if ids and ids[0] == expected:
            ok += 1
        else:
            misses.append((prompt, expected, ids))
    threshold = int(len(HARD_FIXTURE) * 0.80)
    assert ok >= threshold, (
        f"hard-paraphrase top-1 {ok}/{len(HARD_FIXTURE)} below {threshold}. "
        f"Misses: {misses}"
    )


def test_hard_paraphrase_top3_budget():
    """On the hard set the expected protocol must appear in the top-3 for
    >= 90% of prompts (the soft floor — near-synonym siblings allowed)."""
    if not semantic.semantic_available():
        import pytest
        pytest.skip("semantic routing unavailable")
    semantic.reset_caches()
    in_top3 = 0
    for prompt, expected in HARD_FIXTURE:
        ids = [m.id for m in semantic.top_k_protocols(prompt, k=3)]
        if expected in ids:
            in_top3 += 1
    threshold = int(len(HARD_FIXTURE) * 0.90)
    assert in_top3 >= threshold, (
        f"hard-paraphrase top-3 {in_top3}/{len(HARD_FIXTURE)} below {threshold}."
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
    """Bizarre prompts must not crash route_request and must not return HIGH confidence.

    Per the same contract as test_nothing_floor_works above: BGE-small +
    cosine without a calibrated abstention head will occasionally produce
    ~0.55–0.60 cosines on random tokens. We don't promise to return
    primary=None on those (a "medium" guess plus visible candidates is
    fine — the AI will confirm); we DO promise to never return HIGH.
    """
    from research_os.tools.actions.router import route_request

    resp = route_request("zzzz random nonsense xyz", tmp_path, persist_plan=False)
    assert resp.get("status") == "success"
    assert resp.get("confidence") != "high"


def test_trigger_router_still_works_when_semantic_disabled(tmp_path: Path, monkeypatch):
    """Force semantic unavailable and confirm the trigger router still serves."""
    monkeypatch.setattr(semantic, "semantic_available", lambda: False)
    from research_os.tools.actions.router import route_request

    resp = route_request("preregister my analysis plan", tmp_path, persist_plan=False)
    assert resp.get("status") == "success"
    assert resp.get("primary_protocol") == "methodology/preregistration"
    assert resp.get("method") == "trigger"
