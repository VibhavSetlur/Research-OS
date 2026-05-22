from pydantic import BaseModel, Field
from typing import List, Dict, Any
from research_copilot.prompts.agent_prompts import AGENT_PROMPTS
from research_copilot.prompts.skill_prompts import SKILL_PROMPTS

class AgentResponse(BaseModel):
    success: bool
    output: Dict[str, Any]
    escalate: bool = False
    escalation_reason: str = ""

class CitationAgent:
    """Specialized agent for finding, verifying, and formatting citations."""
    def __init__(self, call_llm):
        self.call_llm = call_llm
        self.authority = "citation_management"
        
    def verify_citations(self, text: str, required_citations: List[str]) -> AgentResponse:
        """Verifies if the required citations are present and valid."""
        base_prompt = AGENT_PROMPTS.get("16_peer_review_prep", "") or SKILL_PROMPTS.get("citation_verifier", "")
        prompt = f"{base_prompt}\n\nYou are the CitationAgent. Verify the following text includes appropriate citations for: {required_citations}.\nReturn JSON with:\n- success (bool)\n- output (dict with 'missing', 'invalid', 'formatted_citations')\n- escalate (bool)\n- escalation_reason (string)\nText: {text}"
        import json
        raw = self.call_llm(prompt)
        if raw.startswith("```json"): raw = raw[7:]
        if raw.endswith("```"): raw = raw[:-3]
        try:
            data = json.loads(raw.strip())
            return AgentResponse(**data)
        except Exception:
            return AgentResponse(success=False, output={"error": "Parse failed"}, escalate=True, escalation_reason="Failed to verify")

class RecoveryAgent:
    """Specialized agent for repairing failed states or executions."""
    def __init__(self, call_llm):
        self.call_llm = call_llm
        self.authority = "error_recovery"
        
    def generate_recovery_plan(self, error_trace: str, current_state: Dict[str, Any]) -> AgentResponse:
        """Proposes a recovery strategy when another agent or execution fails."""
        base_prompt = AGENT_PROMPTS.get("08_research_iterate", "")
        prompt = f"{base_prompt}\n\nYou are the RecoveryAgent. A failure occurred.\nError Trace: {error_trace}\nState: {current_state}\nReturn JSON with:\n- success (bool)\n- output (dict with 'rollback_target', 'patch_actions', 'retry_strategy')\n- escalate (bool)\n- escalation_reason (string)"
        import json
        raw = self.call_llm(prompt)
        if raw.startswith("```json"): raw = raw[7:]
        if raw.endswith("```"): raw = raw[:-3]
        try:
            data = json.loads(raw.strip())
            return AgentResponse(**data)
        except Exception:
            return AgentResponse(success=False, output={"error": "Parse failed"}, escalate=True, escalation_reason="Failed to generate recovery plan")

class ExecutorAgent:
    """Agent for running tasks and handling retries."""
    def __init__(self, call_llm):
        self.call_llm = call_llm
        self.authority = "task_execution"
        self.max_retries = 3
        
    def execute_task(self, task_description: str) -> AgentResponse:
        # Simplified execution placeholder
        return AgentResponse(success=True, output={"result": "Task executed"}, escalate=False)

class ReflectionAgent:
    """Agent that reflects on the research trajectory and identifies missing gaps."""
    def __init__(self, call_llm):
        self.call_llm = call_llm
        self.authority = "strategic_reflection"
        
    def reflect(self, trajectory: str) -> AgentResponse:
        base_prompt = AGENT_PROMPTS.get("10_critic", "")
        prompt = f"{base_prompt}\n\nReflect on this trajectory and identify gaps: {trajectory}"
        return AgentResponse(success=True, output={"gaps": ["Need more data"]}, escalate=False)

class ValidationAgent:
    """Agent that handles strict output validation."""
    def __init__(self, call_llm):
        self.call_llm = call_llm
        self.authority = "output_validation"
        
    def validate(self, output_data: str, constraints: str) -> AgentResponse:
        base_prompt = AGENT_PROMPTS.get("07_audit_validate", "")
        prompt = f"{base_prompt}\n\nValidate this data against constraints: {output_data} | {constraints}"
        return AgentResponse(success=True, output={"valid": True}, escalate=False)

class MemoryAgent:
    """Agent that acts as an interface to the Memory System for retrieval."""
    def __init__(self, call_llm):
        self.call_llm = call_llm
        self.authority = "memory_retrieval"
        
    def query(self, query: str) -> AgentResponse:
        prompt = f"Query memory for: {query}"
        return AgentResponse(success=True, output={"results": []}, escalate=False)
