# Research question

Are microglial activation markers (TYROBP, CD74, TREM2) differentially
expressed in Alzheimer's-affected entorhinal cortex (Braak stage VI)
vs cognitively-normal controls in single-nucleus RNA-seq from the
Mathys et al. 2019 cohort?

## Hypothesis

H1: TYROBP and TREM2 are upregulated > 2x (log2FC > 1) in microglia
from Alzheimer's samples vs control, with FDR < 0.05.

## Inputs

- inputs/data/seurat_object.rds — Seurat v5 object, ~5000 nuclei
  (subset of GSE174367)
- inputs/context/cohort_metadata.csv — per-sample diagnosis + Braak stage
