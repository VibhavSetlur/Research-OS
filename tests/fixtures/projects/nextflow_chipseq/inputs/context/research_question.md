# Research question

Do estrogen receptor alpha (ERα) binding sites differ in genomic
distribution and motif composition between MCF-7 and T47D ER-positive
breast cancer cell lines under 100 nM estradiol stimulation at 45 min?

## Hypothesis

H1: T47D exhibits a distinct subset of ERα peaks (> 20% of consensus
peaks) enriched for FOXA1 co-motifs at promoter-distal enhancers,
relative to MCF-7, despite both being luminal-A ER+ models.

H2: Shared MCF-7/T47D peaks are enriched for the canonical ERE motif
(MA0112) and lie within 5 kb of estradiol-responsive genes
(PGR, GREB1, TFF1).

## Inputs

- inputs/pipeline/main.nf — Nextflow DSL2 workflow
  (FASTQC -> BWA -> MACS2_PEAKCALL -> MOTIF_ENRICH)
- inputs/pipeline/nextflow.config — executor + profile config
  (test profile for CI; full profile for SLURM on the cluster)
- ChIP-seq FASTQs (not bundled): GSE32465 (MCF-7) + GSE38985 (T47D),
  2 replicates per cell line + matched input controls

## Out-of-scope

- RNA-seq integration (covered in a separate downstream project).
- Hi-C / 3D-genome context (no compatible data in either GEO series).
