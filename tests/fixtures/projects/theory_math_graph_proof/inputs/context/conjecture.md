# Conjecture

**Conjecture (cubic-graph 4-colourability).** Let $G = (V, E)$ be a
finite simple graph with maximum degree $\Delta(G) \le 3$. Then $G$
admits a proper vertex colouring with at most 4 colours, i.e.
$\chi(G) \le 4$.

## Equivalent formulations

1. Every sub-cubic graph is 4-colourable.
2. The chromatic number of any cubic graph is bounded above by 4.
3. (Stronger, via Brooks) Every connected sub-cubic graph other than
   $K_4$ satisfies $\chi(G) \le 3$.

## Status

Resolved (this is a corollary of Brooks' theorem, 1941, plus a
trivial inspection of the exceptional case $K_4$). The conjecture is
written here in conjecture-form rather than theorem-form because the
project's purpose is to drive the proof-verification workflow on a
result the runner can independently double-check from textbook
materials.

## Dependents

This result is used downstream as a building block for:
- Vizing-class arguments on edge chromatic number of cubic graphs.
- Greedy-colouring case analyses in pedagogy materials.

When promoted to the lemma library, register at slug
`subcubic_four_colourable` with dependents = [].
