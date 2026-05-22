from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Literal

InterruptionClass = Literal["informational", "corrective", "branching", "speculative", "destructive", "replanning"]

class SideTask(BaseModel):
    task_id: str = Field(..., description="Unique ID for the side task")
    description: str = Field(..., description="Description of the side task")
    interruption_class: InterruptionClass = Field(..., description="Type of interruption")
    return_to_main_thread: bool = Field(True, description="Whether to resume the main task after this completes")

class ExecutionIntent(BaseModel):
    user_goal: str = Field(..., description="The user's inferred goal")
    intent_type: str = Field(..., description="The inferred primary intent type")
    task_action: Literal[
        "continue",
        "modify",
        "branch",
        "pause",
        "spawn_side_task",
        "replan",
        "answer_directly",
        "repair_state"
    ] = Field(..., description="The nature of the action to take")
    confidence: float = Field(..., description="Confidence in this intent mapping (0.0 to 1.0)")
    requires_human_input: bool = Field(..., description="Whether the action requires user input/approval")
    affected_research_objects: List[str] = Field(default_factory=list, description="IDs of research objects affected")
    planning_depth: str = Field(..., description="How deep the planner should go (e.g., shallow, deep, exhaustive)")
    next_action_description: str = Field(..., description="Description of the next action to take")
    state_patch: Dict[str, Any] = Field(default_factory=dict, description="Key-value pairs to update in the state ledger")

class GraphMutation(BaseModel):
    action: Literal["insert", "remove", "rewire"] = Field(..., description="The type of mutation")
    node_id: str = Field(..., description="The target node ID")
    script_path: Optional[str] = Field(None, description="Script path (for insert)")
    depends_on: Optional[List[str]] = Field(None, description="Dependencies (for insert or rewire)")

class PlannerDecision(BaseModel):
    workflow_name: str = Field(..., description="The inferred workflow name")
    workflow_steps: List[str] = Field(..., description="The sequence of steps to execute")
    mutations: List[GraphMutation] = Field(default_factory=list, description="Graph mutations to apply to the execution DAG (if replanning)")
    gating_points: List[str] = Field(default_factory=list, description="Steps that require human approval")
    expected_artifacts: List[str] = Field(default_factory=list, description="List of artifacts that should be produced")
    fallback_plan: str = Field(..., description="What to do if the workflow fails")
    stop_conditions: List[str] = Field(default_factory=list, description="Conditions under which execution should halt")

class SkillPlannerOutput(BaseModel):
    relevant_skills: List[str] = Field(..., description="Skills to be loaded into context")
    excluded_skills: List[str] = Field(default_factory=list, description="Skills explicitly excluded from this workflow")
    required_agents: List[str] = Field(..., description="Agents required to complete the steps")
    workflow_steps: List[str] = Field(..., description="The steps to execute")
    expected_outputs: List[str] = Field(default_factory=list, description="Expected outputs from the workflow")
    confidence_score: float = Field(..., description="Confidence in this skill selection (0.0 to 1.0)")
