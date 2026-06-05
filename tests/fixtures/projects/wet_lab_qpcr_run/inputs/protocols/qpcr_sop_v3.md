# SOP: SYBR qPCR on ABI QuantStudio 5 — v3

**Owner:** wet_lab core
**Applies to:** 96-well SYBR qPCR runs targeting low- to mid-abundance
transcripts (Cq < 35).

## Changelog

- **v3 (2026-05-30)** — Switched to SsoAdvanced master mix (was
  PowerUp); reduced anneal-extend from 90 s to 60 s based on
  GAPDH/IL6 standard-curve efficiency check. Added mandatory melt
  curve. Edge-well policy: buffer-only blanks (was: edge-effect
  correction in analysis).
- **v2 (2026-03-12)** — Added inter-plate calibrators (3 wells) for
  multi-plate experiments. Reference dye set to ROX explicitly.
- **v1 (2025-11-04)** — Initial release. PowerUp SYBR, 95/15-60/60
  cycling, no melt curve, edge-effect correction in R.

## Cycling parameters (v3)

| Stage         | Temp   | Time  | Cycles |
|---------------|--------|-------|--------|
| Hold          | 95 C   | 10:00 | 1x     |
| Denature      | 95 C   | 0:15  | 40x    |
| Anneal-extend | 60 C   | 1:00  | 40x    |
| Melt ramp     | 65→95C | 0.5 C/step | 1x |

- Reference dye: ROX (passive normalisation, QuantStudio default).
- Baseline method: auto.
- Reaction volume: 10 uL (5 uL master mix, 0.4 uL each primer at
  10 uM, 2 uL cDNA template, 2.2 uL nuclease-free water).
- Plate seal: optical adhesive film, sealed with manual roller.
- Spin plate 1 min at 1000 x g before loading on instrument.

## Mandatory controls per plate

- 3 NTC wells per target (template replaced with H2O).
- 5-point standard curve in triplicate for the housekeeping target
  (10-fold dilutions of a pooled cDNA reference).
- 3 inter-plate calibrator wells (pooled cDNA) for cross-plate
  normalisation when scaled beyond one plate.
- Edge wells (row A, row H, column 1, column 12) = buffer-only blanks.
