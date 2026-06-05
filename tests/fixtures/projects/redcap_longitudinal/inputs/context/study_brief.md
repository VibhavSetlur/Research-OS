# Study brief — post-stroke recovery cohort

Twelve-month observational cohort study (N=60) of adult patients
discharged from inpatient rehab after first ischemic stroke. Interest:
how functional recovery (Barthel Index, NIH Stroke Scale) evolves from
discharge through one year, and which baseline characteristics predict
plateau vs continued gain.

## Design

Three REDCap study events per patient:

- `baseline_arm_1` — discharge from inpatient rehab
- `6_month_arm_1`  — 6-month follow-up visit
- `12_month_arm_1` — 12-month follow-up visit

Data captured in a single REDCap project (longitudinal mode enabled,
arm 1 only) at a single academic medical center, 2024-09 to ongoing.

## Inputs

- inputs/raw_data/study_DataDictionary.csv — REDCap data dictionary
  export (variable definitions, validation, branching, PHI flags)
- inputs/raw_data/study_DATA.csv — REDCap data export, one row per
  (record_id, redcap_event_name)
- inputs/context/study_brief.md (this file)

## PHI note

The data dictionary marks SSN as `Identifier? = y`. Raw export must
not leave the secured environment without an executed DUA.
