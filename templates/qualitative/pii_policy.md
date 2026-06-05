# PII / De-Identification Policy

Read by `methodology/qualitative_pii_redaction`. Lives at
`inputs/policy/pii_policy.md`. Copy this template, fill in the rows
for your corpus, get IRB / DPO sign-off, then commit to your
project repo (the policy itself contains NO identifying data —
only rules).

The policy MUST address every one of the 18 HIPAA Safe Harbor
identifier classes (45 CFR §164.514(b)(2)). For GDPR projects, also
address special-category personal data (Article 9). For IRB protocols,
mirror the de-identification clauses from your approved protocol.

---

## Project + governance

- Project: <project name>
- Governing standard: HIPAA Safe Harbor | GDPR Art. 4(5) | IRB-only | Other
- IRB protocol number: <e.g. IRB-2026-001234>  (or N/A)
- DPO / privacy officer of record: <name, email>
- Date approved: YYYY-MM-DD
- Re-review due: YYYY-MM-DD  (default annual)
- Pseudonym map location: `inputs/private/pseudonym_map.csv` (gitignored)
- Redacted corpus location: `inputs/raw_data_redacted/`
- Original transcripts: `inputs/raw_data/` (NEVER edited in place)

---

## Per-class rules (HIPAA Safe Harbor — 18 classes)

For each class, set the action to ONE of:

  REMOVE          → replace with `[redacted: <class>]`
  GENERALISE      → replace with a less-specific descriptor
  PSEUDONYMISE    → replace with a stable token from the pseudonym map
  NOT_APPLICABLE  → class is absent from this corpus

| # | Class | Action | Notes (generalisation rule / token prefix / etc.) |
|---|---|---|---|
| 1 | Names | PSEUDONYMISE | Participant → `P##`. Third-party people mentioned → `Person<A,B,…>`. |
| 2 | Geographic subdivisions smaller than a state | GENERALISE | City/county → region (e.g. "Houston" → "a metropolitan area in the U.S. Gulf Coast"). |
| 3 | Dates (except year) related to the individual | GENERALISE | Specific dates → quarter or season (e.g. "March 14, 2024" → "Q1 2024"). |
| 4 | Telephone numbers | REMOVE | |
| 5 | Fax numbers | REMOVE | |
| 6 | Email addresses | REMOVE | |
| 7 | Social security numbers | REMOVE | |
| 8 | Medical record numbers | REMOVE | |
| 9 | Health plan beneficiary numbers | REMOVE | |
| 10 | Account numbers | REMOVE | |
| 11 | Certificate / license numbers | REMOVE | |
| 12 | Vehicle identifiers + serial numbers (incl. plates) | REMOVE | |
| 13 | Device identifiers + serial numbers | REMOVE | |
| 14 | URLs | REMOVE | Public-org URLs (employer website cited as a fact) → GENERALISE to "the organisation's website". |
| 15 | IP addresses | REMOVE | |
| 16 | Biometric identifiers | REMOVE | |
| 17 | Full-face photographs + comparable images | NOT_APPLICABLE | Transcript corpus — no images. |
| 18 | Other unique identifying number / characteristic / code | GENERALISE | Rare conditions, unique employment titles, distinctive life events. Document each generalisation in the redaction ledger. |

---

## Additional rules (GDPR / IRB add-ons)

For GDPR Art. 9 special-category data + IRB-specific protections:

| Class | Action | Notes |
|---|---|---|
| Racial / ethnic origin | KEEP | Analytic relevance; quote per IRB approval. |
| Political opinions | KEEP | |
| Religious / philosophical beliefs | KEEP | |
| Trade union membership | GENERALISE | Specific union → "a national trade union". |
| Genetic / biometric data | REMOVE | |
| Health data (specific diagnoses) | GENERALISE | Specific diagnosis → diagnostic category (e.g. "stage IIIB melanoma" → "advanced cancer"). |
| Sex life / sexual orientation | KEEP | If analytically relevant; otherwise GENERALISE. |
| Employer name | PSEUDONYMISE | `OrgA`, `OrgB`, … |
| Distinctive job title | GENERALISE | "Chief Medical Officer at <small clinic>" → "senior clinician at a small clinic". |

---

## Redaction ledger schema

`workspace/<step>/outputs/reports/redaction_ledger_<file>.csv`:

```
line,start,end,original_hash,class,replacement,score,requires_review,resolved
```

- `original_hash`: sha256 of the original span (NEVER the plaintext).
- `score`: detector confidence (0-1). Spans below 0.85 get
  `requires_review: true` and a `[REVIEW: …]` marker in the
  redacted transcript.
- `resolved`: set true after manual review confirms the redaction
  (or chooses to leave the span as plain text — a false positive).

---

## Audit cadence

- Held-out sample for each redaction pass: ≥ 5% of transcript lines
  (≥ 50 lines minimum). Target NER recall ≥ 0.95, false negatives 0.
- Re-audit when: (a) corpus grows by ≥ 20%, (b) policy changes,
  (c) a false negative is found in any downstream artefact.
- Policy review: annual or on regulatory change (whichever first).
