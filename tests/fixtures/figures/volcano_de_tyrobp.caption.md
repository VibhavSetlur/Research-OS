---
figure_id: fig:volcano_de_tyrobp
title: "Volcano plot — microglial DE markers, Alzheimer's vs control"
license: CC-BY-4.0
source: "GSE174367 — Mathys et al. 2019"
software: "Seurat v5.0.1, Wilcoxon rank-sum, BH-adjusted"
generated_by: workspace/01_de/figures/volcano_de_tyrobp.py
data_provenance: workspace/01_de/results.csv
de_method: wilcoxon
multiple_testing_correction: benjamini_hochberg
fdr_threshold: 0.05
log2fc_threshold: 1.0
seed: 20240315
alt_text: "Volcano plot with log2 fold change on the x-axis (range -3 to 3) and -log10 adjusted p-value on the y-axis. TYROBP, TREM2, and CD74 sit in the upper right (high positive fold change, low p-value). Horizontal dashed line marks FDR=0.05; vertical dashed lines mark log2FC=+/-1."
---

**What it shows.** Volcano plot of differential expression for 12,847
genes tested in microglia between Alzheimer's (Braak VI) and control
samples. The x-axis is log2 fold change (Alzheimer's vs control); the
y-axis is -log10 of the BH-adjusted p-value.

**How to read it.** Genes in the upper-right quadrant (log2FC > 1,
FDR < 0.05) are significantly upregulated in Alzheimer's microglia.
TYROBP, TREM2, and CD74 — the three markers we pre-registered — all
land in this quadrant.

**Why it matters.** Confirms H1: the canonical microglial activation
trio is upregulated in disease microglia at the threshold we
pre-committed to (log2FC > 1, FDR < 0.05). Effect sizes are
biologically meaningful (TYROBP log2FC = 1.74; TREM2 = 1.41;
CD74 = 1.93).
