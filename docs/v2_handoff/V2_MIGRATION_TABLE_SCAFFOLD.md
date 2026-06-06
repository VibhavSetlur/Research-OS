# V2.0.0 Migration Table — SCAFFOLD

> Phase 9 cluster agents append rows to `docs/V2_MIGRATION_TABLE.md` (the live doc).
> This scaffold establishes the column shape they all agree on.

| Old name (v1.x) | New canonical name (v2.0.0) | Dispatch kwarg | Value | Status |
|-----------------|------------------------------|----------------|-------|--------|
| tool_audit_assumptions | tool_audit | scope+dimension | step+assumptions | aliased v2.0.x, removed v2.1.0 |
| tool_audit_citations | tool_audit | scope+dimension | project+citations | aliased v2.0.x, removed v2.1.0 |
| tool_audit_claims | tool_audit | scope+dimension | project+claims | aliased v2.0.x, removed v2.1.0 |
| tool_audit_cliches | tool_audit | scope+dimension | project+cliches | aliased v2.0.x, removed v2.1.0 |
| tool_audit_code_quality | tool_audit | scope+dimension | step+code_quality | aliased v2.0.x, removed v2.1.0 |
| tool_audit_coherence | tool_audit | scope+dimension | project+coherence | aliased v2.0.x, removed v2.1.0 |
| tool_audit_cross_deliverable_consistency | tool_audit | scope+dimension | project+cross_deliverable | aliased v2.0.x, removed v2.1.0 |
| tool_audit_dashboard_content | tool_audit | scope+dimension | synthesis+dashboard_content | aliased v2.0.x, removed v2.1.0 |
| tool_audit_evalue | tool_audit | scope+dimension | step+evalue | aliased v2.0.x, removed v2.1.0 |
| tool_audit_figure | tool_audit | scope+dimension | step+figure | aliased v2.0.x, removed v2.1.0 |
| tool_audit_figure_coverage | tool_audit | scope+dimension | synthesis+figure_coverage | aliased v2.0.x, removed v2.1.0 |
| tool_audit_figure_full | tool_audit | scope+dimension | step+figure_full | aliased v2.0.x, removed v2.1.0 |
| tool_audit_figure_interactivity | tool_audit | scope+dimension | step+figure_interactivity | aliased v2.0.x, removed v2.1.0 |
| tool_audit_figure_quality | tool_audit | (existing alias of figure_full → chained) | step+figure_full | aliased v1.x, removed v2.1.0 |
| tool_audit_power | tool_audit | scope+dimension | step+power | aliased v2.0.x, removed v2.1.0 |
| tool_audit_prose | tool_audit | scope+dimension | project+prose | aliased v2.0.x, removed v2.1.0 |
| tool_audit_reproducibility | tool_audit | scope+dimension | step+reproducibility | aliased v2.0.x, removed v2.1.0 |
| tool_audit_reviewer_responses | tool_audit | scope+dimension | synthesis+reviewer_responses | aliased v2.0.x, removed v2.1.0 |
| tool_audit_statistical_power | tool_audit | (existing alias of power → chained) | step+power | aliased v1.x, removed v2.1.0 |
| tool_audit_step_completeness | tool_audit | scope+dimension | step+completeness | aliased v2.0.x, removed v2.1.0 |
| tool_audit_step_literature | tool_audit | scope+dimension | step+literature | aliased v2.0.x, removed v2.1.0 |
| tool_audit_synthesis | tool_audit | scope+dimension | synthesis+all | aliased v2.0.x, removed v2.1.0 |
| tool_audit_version_coherence | tool_audit | scope+dimension | project+version_coherence | aliased v2.0.x, removed v2.1.0 |
| tool_audit_findings_query | tool_audit_findings | operation | query | aliased v2.0.x, removed v2.1.0 |
| tool_audit_findings_diff | tool_audit_findings | operation | diff | aliased v2.0.x, removed v2.1.0 |
| | | | | |
| (Phase 9 clusters C2 → C9 will append their rows below) | | | | |
