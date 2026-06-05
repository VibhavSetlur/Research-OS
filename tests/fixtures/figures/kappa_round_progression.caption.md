---
figure_id: fig:kappa_round_progression
title: "Per-code Cohen's kappa across coding rounds"
license: CC-BY-4.0
source: "qualitative_interviews fixture — N=8 transcripts, 28 codes"
software: "irrCAC v1.0, Python 3.10"
generated_by: workspace/coding/figures/kappa_round_progression.py
data_provenance: workspace/coding/round_*/kappa.csv
ir_metric: cohens_kappa
rater_count: 2
seed: 20240412
alt_text: "Line plot. X-axis: round number (1 through 4). Y-axis: Cohen's kappa, ranging 0.4 to 1.0. 28 lines, one per code; most rise from approximately 0.55 in round 1 to above 0.75 in round 4. Three lines stay below 0.6 throughout (the rewritten codes that triggered triage)."
---

**What it shows.** Per-code Cohen's kappa across four rounds of
double-coding. Each line is one of 28 codes; the x-axis is round
number; the y-axis is the per-code kappa between the two coders for
that round.

**How to read it.** Lines that rise from round 1 to round 4 indicate
codes whose inter-rater agreement improved as the codebook was
iterated. Lines that stay flat below 0.6 are the codes flagged for
triage in round 2 (rewritten with explicit inclusion / exclusion
criteria) — the gain from round 2 to round 3 is the post-triage
recovery.

**Why it matters.** Demonstrates the per-round-kappa-floor gate
firing as intended: round-1 codes below floor were rewritten, and
round-3 measurements confirm recovery. No code was retired below
floor.
