# Claim

**Theorem.** $\sqrt{2}$ is irrational. That is, there exist no integers
$p, q$ with $q \neq 0$ such that $\left(\frac{p}{q}\right)^2 = 2$.

## Why this project

A 2-page proof used to exercise the `theory_math` pack end-to-end:
proof-verification workflow, lemma library, and the non-IMRAD
theory-paper structure. Small enough to finish in an afternoon, big
enough to touch every gate the pack cares about.

## Dependencies

This theorem depends on one small algebraic lemma:

- **Lemma (coprime-parity).** If $p, q$ are coprime integers and
  $p^2 = 2 q^2$, then $p$ is even. Consequently $q$ is also even, which
  contradicts coprimality.

The lemma is registered in `workspace/lemmas/coprime_parity_lemma.md`
once the project is run; it earns library status because the same parity
argument is reused for the open question on $\sqrt{3}$ irrationality.

## Strategy

Proof by contradiction. Assume $\sqrt{2} = p/q$ in lowest terms, apply
the coprime-parity lemma, derive that both $p$ and $q$ are even, and
contradict the lowest-terms assumption.

## Notes

This is a frozen fixture for stress-testing. Real proofs in this style
should still go through `theory_math/proof/proof_verification_workflow`
including independent review, even when the result is classical.
