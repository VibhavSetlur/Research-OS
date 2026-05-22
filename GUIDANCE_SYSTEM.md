# The Guidance System

Research OS enforces methodological rigor through its Guidance System. This system is driven by versioned YAML protocols that dictate step-by-step methodologies.

## Available Protocols
Agents can fetch the full specifications using `sys.guidance.get {"protocol_name": "<name>"}`.

- **domain_analysis.yaml**: Standardizes how a research domain is surveyed.
- **literature_search.yaml**: Guides boolean query construction and screening criteria.
- **methodology_selection.yaml**: Helps agents choose between experimental and observational designs.
- **research_design.yaml**: Specifies variable identification and power analyses.
- **analysis_plan.yaml**: Structures the data processing and statistical modeling steps.
- **evidence_synthesis.yaml**: Standardizes meta-analysis and narrative combination of findings.
- **figure_guidelines.yaml**: Enforces 300 DPI, colorblind-friendly palettes.
- **writing_standards.yaml**: Imposes the IMRAD structure and academic tone.
- **reproducibility.yaml**: Mandates environment freezing and fixed random seeds.
- **audit_and_validation.yaml**: Guides simulated peer-review and data integrity checks.

## Protocol Versioning & Caching
Protocols include a `schema_version` and a `version` string. They are cached in memory during an active MCP session to minimize disk I/O when referenced repeatedly by LLMs.
