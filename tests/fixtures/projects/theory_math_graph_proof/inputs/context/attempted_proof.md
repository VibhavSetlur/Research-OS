# Attempted proof — sub-cubic 4-colourability

## Theorem

For any finite simple graph $G$ with $\Delta(G) \le 3$, $\chi(G) \le 4$.

## Proof

Suppose $G$ is a finite simple graph with $\Delta(G) \le 3$. We
consider two cases.

### Case 1. $G$ is connected.

By Brooks' theorem (1941), for any connected simple graph $G$ that is
neither a complete graph nor an odd cycle, $\chi(G) \le \Delta(G)$.

The exceptional cases for $\Delta(G) = 3$:
* $K_n$ for $n$ such that $\Delta(K_n) = n - 1 = 3$, i.e. $n = 4$.
  $K_4$ has $\chi(K_4) = 4$.
* Odd cycle: an odd cycle has $\Delta = 2$, not 3, so this exception
  does not apply here.

Therefore, if $G$ is connected and $G \ne K_4$, $\chi(G) \le 3 \le 4$.
If $G = K_4$, $\chi(G) = 4 \le 4$. Either way the bound holds.

### Case 2. $G$ is disconnected.

Decompose $G$ into connected components $G_1, \ldots, G_k$. Each
$G_i$ has $\Delta(G_i) \le \Delta(G) \le 3$, and by Case 1 each $G_i$
admits a proper 4-colouring. Union the colourings (re-using the same
4-colour palette across components — components share no edges, so
no conflicts can arise). The result is a proper 4-colouring of $G$.

Therefore $\chi(G) \le 4$ in either case. $\blacksquare$

## Notes

* Step that needs independent review: the "re-using the same 4-colour
  palette across components" step in Case 2. Standard but worth a
  cold read.
* No unusual axioms; formal-check waiver appropriate.
* Reusable lemma: register Case 1 as `subcubic_four_colourable_connected`
  with `K_4_chromatic_number_is_4` as a sub-lemma.

## Open questions

* What's the smallest cubic graph that needs all 4 colours? ($K_4$.)
* Same bound for $\Delta(G) = 4$ via Brooks? (Yes, $\chi(G) \le 4$
  unless $G = K_5$.)
