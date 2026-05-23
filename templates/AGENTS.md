# Research OS Agent Guidelines

1. **Immutability**: Do not modify `inputs/raw_data/` or `inputs/literature/`. Write new data to the current experiment step's `data/` directory.
2. **State Logging**: Log significant methodological decisions using `tool.log.decision`.
3. **Methodological Appends**: Append new analysis steps to `workspace/methods.md` using `mem.methods.append`.
4. **Analysis Checkpointing**: Append chronologically to `workspace/analysis.md` using `mem.analysis.log`.
5. **Experiment Paths**: Use `sys.path.create` for new steps. Use `sys.path.abandon` for dead ends (preserves files). The workspace does not contain a pre-built 01_ experiment folder. After understanding the data and research question, you must create the first experiment path using sys.path.create.
6. **Execution Estimation**: Before running heavy scripts, check `data_inventory.json` and use `tool.data.sample` to test logic first.
7. **Approval Gates**: In `supervised` mode, use `sys.checkpoint.pending` for major milestones.
8. **Checkpointing**: Use `sys.checkpoint.create` before massive refactoring.
9. **Model-Size Awareness**: Small models MUST use protocols from `protocols/light/` and `sys.state.minimal_context`.
10. **Fact-Checking**: Cite sources via `tool.search.*` calls.
11. **Autonomy Modes**:
    - **manual**: Propose actions and wait for PI approval.
    - **supervised**: Auto-execute routines; pause at key decisions.
    - **autopilot**: Execute one numbered task per response, end with "Type continue". After 4+ continues, call `sys.session.handoff`.
12. **Output-Driven Workflow**:
    - **exploratory/dashboard**: Build interactive dashboards/summaries.
    - **abstract**: 250-word abstract + key figure.
    - **poster**: Call `tool.poster.create`.
    - **paper**: Full IMRAD (section-by-section for complex work via `tool.synthesize section=...`).

13. Session Management (Task Breaking):
    - When the researcher gives a multi-step task, create a numbered task list
      using mem.analysis.log. Execute ONE task per response.
    - End each response with a clear status: "✅ Done: [task]. Next: [next task].
      Type 'continue' to proceed."
    - After 4+ consecutive "continues", call sys.session.handoff and instruct the
      researcher to start a new chat with the handoff prompt.
    - For writing tasks: NEVER combine methods, citations, conclusions, and
      synthesis into one response. Load `writing_standards` (which is now an index) to discover the right
      protocol.
    - When undertaking any writing task, always load `writing_core` first, then load the specific protocol (e.g., `writing/methods`, `synthesis/paper`).
    - If a writing task is complex, split it across multiple chat sessions using `sys.session.handoff`.
    - After writing any MD file, verify it follows the template from the relevant writing protocol using sys.md.validate.

14. Token Budget: Adjust your model_profile in inputs/researcher_config.yaml
    (small/medium/large). Small models should use protocols/light/ and 
    sys.state.minimal_context. Medium/large models can use full protocols.
