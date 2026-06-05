# Research question

Which genes are differentially expressed between primary breast tumor
tissue and matched adjacent-normal tissue in the TCGA-BRCA cohort
(N=200, paired design where available), and do the top differentially
expressed genes recapitulate the canonical luminal vs basal signatures
from Parker et al. 2009?

## Hypothesis

H1: Estrogen-receptor-pathway genes (ESR1, GATA3, FOXA1) are
upregulated in primary tumor relative to adjacent normal with log2FC
> 1.5 and adjusted p-value < 0.01 in the luminal-A subset.

H2: Proliferation markers (MKI67, TOP2A, BIRC5) are upregulated in
basal-like tumors vs adjacent normal with log2FC > 2.

## Inputs

- inputs/data/Snakefile — six-rule Snakemake workflow
  (download -> trim -> align -> count -> deseq2 -> report)
- inputs/scripts/run_pipeline.sh — sbatch wrapper invoking
  `snakemake --profile slurm` with 7 #SBATCH headers
- inputs/context/research_question.md — this file

## Expected outputs

- workspace/05_deseq2/results.tsv — gene x stats table
- workspace/06_report/report.html — knitr report
