# Study brief — IL6 induction qPCR (single run)

**Project:** Quantify IL6 transcript induction in LPS-stimulated vs
unstimulated THP-1 macrophages, normalised to GAPDH (housekeeping).

**Scope of this run:** ONE qPCR plate, one readout (amplification + melt
curve), single biological time-point (4 h post-stimulation). This is a
frozen reference project used by the stress-test runner — not a real
ongoing study.

## Design

- Conditions: 2 (LPS 100 ng/mL, vehicle control)
- Biological replicates: N = 3 independent THP-1 differentiations
- Technical replicates: 3 wells per biological replicate
- Reactions per target: 2 conditions x 3 bio x 3 tech = 18
- Targets: 2 (GAPDH housekeeping, IL6 target)
- Total sample wells: 36
- Plus: 3 NTCs per target, 5-point GAPDH standard curve (triplicate),
  3 inter-plate calibrators, edge wells = buffer-only blanks.
- Plate format: 96-well, randomised layout with recorded seed.

## Primers

- GAPDH-F: IDT cat# 51-01-15-09, lot 0009123456, HPLC-purified
- GAPDH-R: IDT cat# 51-01-15-10, lot 0009123457, HPLC-purified
- IL6-F:   IDT cat# 51-01-19-21, lot 0009124003, HPLC-purified
- IL6-R:   IDT cat# 51-01-19-22, lot 0009124004, HPLC-purified

## Antibodies / cell line provenance

- Cell line: THP-1, ATCC TIB-202, passage 14 used, mycoplasma-negative
  (last test 2026-05-28), STR-authenticated.
- (No antibodies in this run — qPCR only.)

## Reagents

- SYBR master mix: Bio-Rad SsoAdvanced 1725271, lot 64308201
- MMLV-RT (cDNA prep, upstream): Promega M1701, lot 0000523189
- RNase inhibitor: Promega N2615, lot 0000528012

## Instrument

- ABI QuantStudio 5 (QS5_A), method file GAPDH_IL6_v3.edt.
- Cycling: 95 C / 10 min, then 40x [95 C / 15 s, 60 C / 60 s], melt 65 → 95 C.
