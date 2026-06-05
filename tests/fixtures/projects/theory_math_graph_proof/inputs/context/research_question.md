# Research question

In a finite simple graph $G$ with maximum degree $\Delta(G) = 3$, is the
chromatic number $\chi(G) \le 4$?

## Why this project

A graph-theory variant of the short-proof fixture. The question is a
restricted case of Brooks' theorem (which gives $\chi(G) \le \Delta(G)$
for connected graphs other than $K_n$ or odd cycles), specialised to
cubic graphs. Small enough to finish in an afternoon, big enough to
exercise the theory_math pack's routing for theorem-proving prompts.

The SMOKE GAPS dossier flags this exact prompt — "prove that every
planar graph with maximum degree 3 is 4-colorable" — as one that
currently mis-routes to `guidance/analysis_plan` via a false-positive
`DEG` trigger. This fixture exists to assert the routing fix
(theory_math triggers must outrank biology `DEG` for proof-shaped
prompts) and to give the pack a non-sqrt(2) project to flex on.

## Scope

* Focus: cubic graphs (every vertex has degree exactly 3) and
  sub-cubic graphs (maximum degree at most 3). Both are covered by
  the conjecture.
* Out of scope: the full four-colour theorem for planar graphs of
  arbitrary degree (Appel & Haken 1976) — that's a separate machinery.

## Dependencies

* Lemma (Brooks 1941). For any connected simple graph $G$ that is
  neither a complete graph nor an odd cycle, $\chi(G) \le \Delta(G)$.
* Lemma (greedy-colouring upper bound). For any graph $G$,
  $\chi(G) \le \Delta(G) + 1$.

## Strategy

Two-track:
1. Cite Brooks' theorem directly for $G$ connected, non-complete,
   not an odd cycle — gives $\chi(G) \le 3 \le 4$.
2. Handle the exceptional cases ($K_4$, odd cycles of degree 3 = none,
   disconnected graphs) by case-analysis.

## Inputs

- inputs/context/research_question.md (this file)
- inputs/context/conjecture.md — formal statement
- inputs/context/attempted_proof.md — draft proof outline
