---
figure_id: fig:umap_microglia_braak
title: "UMAP of microglia, coloured by Braak stage"
license: CC-BY-4.0
source: "GSE174367 — Mathys et al. 2019, Nature 570:332-337"
software: "Seurat v5.0.1, SCTransform normalisation"
generated_by: workspace/01_de/figures/umap_microglia_braak.py
data_provenance: workspace/01_de/inputs/seurat_object.rds
seed: 20240315
alt_text: "Two-dimensional UMAP scatter of approximately 5000 microglial nuclei from entorhinal cortex. Points are coloured along a six-step gradient corresponding to Braak stages I through VI. A clear gradient is visible from lower-left (Braak I, control) to upper-right (Braak VI, severe Alzheimer's), indicating progressive transcriptional shift."
---

**What it shows.** Two-dimensional UMAP projection of 5,000 microglial
nuclei from entorhinal cortex, coloured by Braak neuropathological
stage (I–VI). Each point is a single nucleus.

**How to read it.** Position along the first UMAP component
approximately tracks Braak stage; points cluster by donor diagnosis
status (control versus Alzheimer's) more than by sequencing batch,
consistent with biology dominating technical variance after
SCTransform normalisation.

**Why it matters.** The progressive shift along UMAP-1 sets up the
differential-expression analysis in Figure 2: microglia in
Braak VI samples occupy a distinct UMAP neighbourhood that we then
interrogate for activation markers.
