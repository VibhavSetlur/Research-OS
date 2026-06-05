# Figure fixtures with `.caption.md` sidecars

This directory ships sample `<stem>.caption.md` sidecars (with YAML
frontmatter) alongside placeholder PNGs. Used by tests that exercise
the figure-caption pipeline:

* `src/research_os/tools/actions/viz/figures.py::caption_synthesise`
* `src/research_os/tools/actions/synthesis/synthesize.py::_read_caption_sidecar`
* `src/research_os/tools/actions/synthesis/dashboard_v2.py::_figure_companion`
* `src/research_os/tools/actions/synthesis/typst.py` (figure embedding)

## Sidecar schema

Each `.caption.md` opens with a YAML frontmatter block, then the
plain-English caption body:

```markdown
---
figure_id: fig:umap_microglia_braak
title: "UMAP of microglia, coloured by Braak stage"
license: CC-BY-4.0
source: "GSE174367 — Mathys et al. 2019"
software: "Seurat v5.0.1"
generated_by: workspace/01_de/figures/umap_microglia_braak.py
data_provenance: workspace/01_de/inputs/seurat_object.rds
alt_text: "UMAP scatter colored by Braak stage I-VI..."
---

**What it shows.** Two-dimensional UMAP projection of 5,000 microglial
nuclei from entorhinal cortex...
```

Today only the body is consumed by the existing readers; the
frontmatter is forward-looking metadata for `tool_audit_figure_sidecar`
(planned) and for the dashboard cards. Existing readers tolerate the
frontmatter because everything between the `---` markers is stripped
or ignored when the body alone is rendered.

## Files

| Figure | Domain | Notes |
|---|---|---|
| `umap_microglia_braak.png` | biology | UMAP scatter, biology_genomics_mini |
| `volcano_de_tyrobp.png` | biology | DE volcano, biology_genomics_mini |
| `kappa_round_progression.png` | qualitative | Cohen's κ over rounds, qualitative_interviews |
| `manuscript_f23v_thumb.png` | humanities | IIIF thumbnail crop, humanities_ms_review |

## How to use

These are loaded directly from this directory by tests under
`tests/unit/test_v1110_caption_sidecars.py`. Per-project copies live
under each project's `inputs/figures/` or `workspace/<step>/outputs/figures/`
when the manifest stress-runner needs an in-project figure.

The PNGs are 1×1 transparent pixels — large enough to be a valid PNG
for any pillow/typst probe, small enough to keep the test fixture
under 1 KB total.
