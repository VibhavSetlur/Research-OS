# Token Budget Manager

## Purpose
Monitors context window usage and automatically compresses/summarizes earlier context when approaching limits. Never let token overflow silently corrupt outputs.

## Protocol

### Token Tracking
1. Track tokens used per agent invocation
2. Update the global ledger (`state.json`) with current usage via `ResearchLedger.track_tokens()`
3. Default context window: 200,000 tokens (adjustable per model)

### Compression Thresholds

| Usage | Action |
|-------|--------|
| 0-60% | Normal operation, full context available |
| 60-80% | Summarize completed phases into 3-sentence abstracts. Keep only essential skill docs. |
| 80-90% | Flush non-essential skill docs from context. Keep only the active skill being executed. Compress literature review to key findings only. |
| 90-100% | Force checkpoint save. Split into new conversation with state transfer prompt. Include: current phase, state.json summary, last results, next steps. |

### State Transfer Prompt Template
When splitting at 90%+:
```
CONTEXT TRANSFER — Research Copilot Session Continuation

Previous session state:
- Run ID: {run_id}
- Phase: {phase} (step {step})
- Completed checkpoints: {checkpoints}
- Active hypotheses: {hypotheses}
- Last result: {last_result_summary}
- Next step: {next_action}

Continue from here. Do NOT repeat completed work.
```

### Token Estimation
- 1 token ≈ 4 characters for English text
- 1 token ≈ 0.75 words
- Code: 1 token ≈ 2-3 characters
- JSON: count braces, brackets, quotes as overhead

### Implementation for Agents
Before each major output:
1. Estimate tokens in accumulated context
2. Compare against `token_budget.limit` in state.json
3. If threshold exceeded: apply compression rules above
4. Log compression action in state.json errors array with type "token_compression"

### CLI Reference
```bash
research budget          # Show token budget usage by phase
research state           # Shows token budget in ledger summary
```
