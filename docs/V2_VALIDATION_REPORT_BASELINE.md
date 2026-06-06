# Research-OS v2.0.0 — Baseline Validation Report (Phase 15a)

Synthesis of 20 baseline validation reports (5 scenarios x 4 perspectives) produced before Phase 9 consolidation. Source: `docs/v2_handoff/validation_baseline/*.json`.

## 1. Overall averages

| Metric | Value |
| --- | --- |
| Reports | 20 |
| Average final_rating | 6.35 |
| Total HIGH friction items | 124 |
| Total first-5-turn HIGH friction | 66 |
| Deliverable-produced rate | 55% |
| Min rating | 5.8 |
| Max rating | 7.4 |

## 2. Per-perspective averages

| Perspective | N | Avg rating | Total HIGH | Total first-5 HIGH | Deliverable rate |
| --- | --- | --- | --- | --- | --- |
| auditor | 5 | 6.64 | 27 | 12 | 4/5 |
| maintainer | 5 | 6.28 | 29 | 16 | 2/5 |
| naive_ai | 5 | 6.06 | 37 | 20 | 3/5 |
| researcher | 5 | 6.4 | 31 | 18 | 2/5 |

## 3. Per-scenario averages

| Scenario | N | Avg rating | Total HIGH | Total first-5 HIGH | Deliverable rate |
| --- | --- | --- | --- | --- | --- |
| biology_rnaseq | 4 | 6.5 | 27 | 14 | 1/4 |
| engineering_benchmark | 4 | 6.4 | 24 | 13 | 2/4 |
| humanities_close_reading | 4 | 6.5 | 20 | 12 | 3/4 |
| qualitative_interviews | 4 | 6.2 | 28 | 15 | 1/4 |
| theory_math_proof | 4 | 6.12 | 25 | 12 | 4/4 |

## 4. Never-called tools (union across 20 reports)

Total distinct tool names flagged as never-called by at least one perspective: **204**. Full list with frequency below; the JSON candidate file is `docs/v2_handoff/never_called_candidates.json`.

| Tool | # reports flagging |
| --- | --- |
| tool_audit_evalue | 15 |
| tool_dashboard_reviewer_sim | 15 |
| tool_audit_figure_interactivity | 15 |
| tool_dashboard_story_quality_bar | 14 |
| tool_audit_dashboard_content | 14 |
| tool_preregister_diff | 14 |
| tool_humanities_essay_scaffold | 13 |
| tool_figure_interactive_autogen | 13 |
| tool_dashboard_create | 13 |
| tool_poster_create | 12 |
| tool_slurm_submit | 12 |
| tool_dashboard_story_edit | 12 |
| tool_preregister_freeze | 12 |
| tool_sensitivity_run | 12 |
| tool_rmarkdown_render | 12 |
| tool_julia_exec | 11 |
| tool_audit_reviewer_responses | 11 |
| tool_dashboard_story_generate | 11 |
| tool_audit_figure_coverage | 11 |
| tool_sensitivity_define | 11 |
| tool_audit_power | 11 |
| tool_rebuttal_draft | 10 |
| tool_reviewer_response_compile | 10 |
| tool_slides_create | 10 |
| tool_slurm_status | 10 |
| tool_slurm_fetch | 10 |
| tool_paper_figures_autoembed | 10 |
| tool_dashboard_test_generate | 10 |
| tool_dashboard_test_run | 10 |
| tool_notebook_exec | 10 |
| tool_r_exec | 10 |
| tool_audit_figure | 10 |
| tool_audit_figure_full | 10 |
| tool_audit_cliches | 9 |
| tool_response_to_reviewers | 9 |
| tool_paper_compile_typst | 9 |
| tool_slurm_list | 9 |
| tool_audit_reproducibility | 9 |
| tool_latex_compile | 8 |
| tool_synthesis_curate_figures | 8 |
| tool_step_pipeline_define | 8 |
| tool_step_pipeline_run | 8 |
| tool_step_pipeline_status | 8 |
| tool_redteam_review | 7 |
| tool_mistake_replay | 7 |
| tool_figure_palette | 7 |
| tool_reviewer_simulate | 7 |
| tool_step_pipeline_diagram | 7 |
| sys_env_docker_generate | 7 |
| tool_audit_assumptions | 7 |
| tool_search_pubmed | 7 |
| tool_dead_end_lessons | 6 |
| tool_search_arxiv | 6 |
| tool_alternative_path_propose | 6 |
| sys_export_share_archive | 6 |
| tool_audit_code_quality | 6 |
| tool_data_convert | 6 |
| tool_data_profile | 6 |
| tool_data_sample | 6 |
| tool_branch_recommendation | 5 |
| tool_writing_discussion_from_verdicts | 5 |
| tool_audit_version_coherence | 5 |
| tool_audit_cross_deliverable_consistency | 5 |
| tool_audit_findings_diff | 5 |
| tool_failure_record | 5 |
| tool_failure_check | 5 |
| tool_failure_list | 5 |
| tool_reliability_log_event | 5 |
| tool_reliability_report | 5 |
| tool_step_revision_options | 5 |
| tool_step_iterations_list | 5 |
| tool_audit_statistical_power | 5 |
| tool_figure_caption_synthesise | 5 |
| tool_step_env_lock | 5 |
| sys_env_snapshot | 5 |
| tool_self_certify | 4 |
| tool_list_certifications | 4 |
| tool_step_iterate | 4 |
| tool_audit_figure_quality | 4 |
| tool_search_crossref | 4 |
| tool_adapter_extract | 4 |
| tool_adapters_run_all | 4 |
| tool_lessons_consult | 3 |
| tool_lessons_record | 3 |
| tool_progress_digest | 3 |
| tool_section_substantiveness | 3 |
| tool_audit_findings_query | 3 |
| tool_null_findings_report | 3 |
| tool_resolve_gate_strictness | 3 |
| tool_project_tier_strictness | 3 |
| tool_thought_log | 3 |
| tool_thought_trace | 3 |
| tool_discussion_coverage_audit | 3 |
| mem_intake_regenerate | 3 |
| mem_citations_generate | 3 |
| tool_engineering_fmea_render | 3 |
| tool_engineering_fault_tree_render | 3 |
| tool_engineering_requirements_matrix | 3 |
| tool_audit_coherence | 3 |
| tool_audit_step_literature | 3 |
| tool_workflow_dag | 3 |
| tool_search_semantic_scholar | 3 |
| tool_nextflow_run | 3 |
| tool_snakemake_run | 3 |
| tool_dry_run | 2 |
| tool_promote_to_step | 2 |
| sys_session_handoff | 2 |
| tool_theory_math_proof_outline | 2 |
| tool_literature_download | 2 |
| mem_hypothesis_add | 2 |
| mem_hypothesis_list | 2 |
| tool_audit_claims | 2 |
| tool_adapters_list | 2 |
| sys_adapters_installed | 2 |
| tool_python_exec | 2 |
| tool_synapse_pull | 2 |
| tool_workspace_repair | 2 |
| tool_figure_create | 2 |
| tool_redcap_export | 2 |
| tool_animation_design helpers | 1 |
| tool_quick_review | 1 |
| tool_cache_clear | 1 |
| tool_synthesis_grant | 1 |
| synthesis_lay_summary | 1 |
| synthesis_handout | 1 |
| synthesis_progress_update | 1 |
| synthesis_null_findings | 1 |
| synthesis_title_workshop | 1 |
| tool_data_ethics_review-related | 1 |
| tool_wet_lab_plate_map_render | 1 |
| tool_wet_lab_reagent_query | 1 |
| tool_wet_lab_sample_lineage_export | 1 |
| tool_humanities_* | 1 |
| tool_qualitative_* | 1 |
| tool_theory_math_* | 1 |
| tool_engineering_* | 1 |
| tool_synapse_* | 1 |
| tool_cytoscape_* | 1 |
| tool_redcap_* | 1 |
| tool_nextflow_* | 1 |
| tool_snakemake_* | 1 |
| sys_checkpoint_rollback | 1 |
| tool_synthesis_preview | 1 |
| tool_qualitative_pii_redaction | 1 |
| tool_audit_synthesis | 1 |
| edit | 1 |
| quality_bar | 1 |
| tool_humanities_argumentation_audit | 1 |
| tool_qualitative_codebook_render | 1 |
| tool_qualitative_kappa | 1 |
| tool_qualitative_member_check | 1 |
| tool_wet_lab_consumables_estimate | 1 |
| tool_wet_lab_qc_panel | 1 |
| tool_wet_lab_reagent_log | 1 |
| tool_theory_lean_compile | 1 |
| tool_theory_math_theorem_render | 1 |
| tool_audit_citations | 1 |
| tool_path_finalize is invoked once at the end but the 6 fmea/fta/reqs tools are unused for this scenario | 1 |
| tool_search_web | 1 |
| tool_slurm_log | 1 |
| tool_slurm_array_plan | 1 |
| tool_notebook_render | 1 |
| tool_external_tool_setup | 1 |
| tool_branch_compare | 1 |
| tool_branch_promote | 1 |
| tool_sensitivity_analysis | 1 |
| tool_sensitivity_check | 1 |
| tool_redteam | 1 |
| tool_failure_analysis | 1 |
| tool_failure_modes | 1 |
| mem_decision_log | 1 |
| mem_hypothesis_* | 1 |
| tool_package_install | 1 |
| tool_script_exec | 1 |
| tool_alternatives_consider | 1 |
| tool_state_promote | 1 |
| tool_cytoscape_load | 1 |
| tool_cytoscape_layout | 1 |
| tool_cytoscape_export | 1 |
| tool_nextflow_resume | 1 |
| tool_snakemake_dag | 1 |
| tool_redcap_pull | 1 |
| tool_redcap_metadata | 1 |
| tool_engineering_benchmark | 1 |
| tool_wet_lab_protocol_compose | 1 |
| tool_adapter_extract, tool_adapters_list, tool_adapters_run_all | 1 |
| tool_audit_figure_full, tool_figure_palette | 1 |
| tool_workflow_dag, tool_step_env_lock | 1 |
| tool_env_snapshot, tool_env_docker_generate | 1 |
| tool_literature_search_and_save | 1 |
| tool_step_literature_list | 1 |
| tool_sys_env_docker_generate | 1 |
| tool_deprecations_summary | 1 |
| all 6 adapter packs | 1 |
| tool_audit_step_literature variants that presume empirical verdicts | 1 |
| tool_redcap_import | 1 |
| tool_synapse_push | 1 |
| tool_cytoscape_session | 1 |
| tool_dashboard_render | 1 |
| tool_dashboard_build | 1 |
| tool_dashboard_assemble | 1 |
| tool_synapse_sync | 1 |
| tool_cytoscape_render | 1 |
| mem_hypothesis_update | 1 |

## 5. Top 20 friction categories (frequency)

| Rank | Category | Frequency | Example perspectives |
| --- | --- | --- | --- |
| 1 | tool_surface_bloat | 11 | auditor@engineering_benchmark, auditor@humanities_close_reading, maintainer@biology_rnaseq |
| 2 | protocol_jargon | 4 | auditor@biology_rnaseq, maintainer@biology_rnaseq, maintainer@engineering_benchmark, maint |
| 3 | tool_sprawl | 3 | maintainer@engineering_benchmark, maintainer@humanities_close_reading, maintainer@qualitat |
| 4 | domain_coverage_gap | 2 | maintainer@biology_rnaseq, researcher@biology_rnaseq |
| 5 | literature_gate_mismatch | 2 | auditor@humanities_close_reading, naive_ai@engineering_benchmark |
| 6 | jargon_density | 2 | researcher@humanities_close_reading, researcher@qualitative_interviews |
| 7 | naming_inconsistency | 2 | researcher@qualitative_interviews, researcher@theory_math_proof |
| 8 | surface_area_bloat | 1 | auditor@biology_rnaseq |
| 9 | fragmented_ledger | 1 | auditor@biology_rnaseq |
| 10 | provenance_gap_for_R | 1 | auditor@biology_rnaseq |
| 11 | scenario_specific_coverage_missing | 1 | auditor@biology_rnaseq |
| 12 | opaque_blocker_messages | 1 | auditor@biology_rnaseq |
| 13 | ambiguous_gate_routing | 1 | auditor@biology_rnaseq |
| 14 | rng_seed_loophole | 1 | auditor@biology_rnaseq |
| 15 | no_dataset_provenance | 1 | auditor@biology_rnaseq |
| 16 | wet_lab_pack_discoverability | 1 | auditor@biology_rnaseq |
| 17 | version_coherence_warning_too_quiet | 1 | auditor@biology_rnaseq |
| 18 | audit_telemetry | 1 | maintainer@biology_rnaseq |
| 19 | protocol_routing_clarity | 1 | maintainer@biology_rnaseq |
| 20 | synthesis_tool_overload | 1 | maintainer@biology_rnaseq |

## 6. Top 10 convoluted tools (frequency)

| Rank | Tool | # reports flagging |
| --- | --- | --- |
| 1 | tool_audit_step_completeness | 16 |
| 2 | tool_audit_quality_full | 13 |
| 3 | tool_audit_synthesis | 11 |
| 4 | tool_audit_step_literature | 10 |
| 5 | tool_route | 10 |
| 6 | tool_semantic_route | 10 |
| 7 | tool_audit_findings_query | 8 |
| 8 | sys_semantic_tool_search | 8 |
| 9 | tool_audit_figure | 7 |
| 10 | tool_audit_figure_full | 7 |

## 7. Top 10 confusing protocols (frequency)

| Rank | Protocol | # reports flagging |
| --- | --- | --- |
| 1 | guidance/dead_end_routing | 3 |
| 2 | engineering/test/build_test_fix_loop | 3 |
| 3 | methodology/method_comparison | 3 |
| 4 | audit_and_validation | 2 |
| 5 | provenance_completeness | 2 |
| 6 | guidance/analysis_plan | 2 |
| 7 | methodology/methodology_selection | 2 |
| 8 | methodology/methodological_consultation | 2 |
| 9 | methodology/pick_tool_stack | 2 |
| 10 | methodology/mixed_language_orchestration | 2 |

## 8. Headline findings

- Average rating across all 20 baseline runs: **6.35 / 10**.
- Total HIGH-severity friction items reported: **124** (of which **66** hit in the first 5 turns).
- Distinct never-called tool candidates: **204** (Phase 9 should cross-reference these against actual production callers).
- Deliverable-produced rate: **55%** — i.e. every requested artifact landed in only ~55% of runs.
