from typing import List, Dict, Any
from pydantic import BaseModel, Field

class ToolMetadata(BaseModel):
    tool_name: str = Field(..., description="The exact name of the script or tool")
    capabilities: List[str] = Field(..., description="Semantic capabilities (e.g. claim_validation, literature_search)")
    cost: str = Field(..., description="low, medium, high")
    risk: str = Field(..., description="low, medium, high")
    failure_modes: List[str] = Field(default_factory=list, description="Known ways this tool can fail")
    preferred_when: List[str] = Field(default_factory=list, description="Conditions under which this tool is preferred")
    inputSchema: Dict[str, Any] = Field(default_factory=lambda: {"type": "object", "properties": {}}, description="JSON Schema for MCP")

class ToolRegistry:
    """Registry that maps semantic capabilities to specific tools."""
    
    def __init__(self):
        self._tools: Dict[str, ToolMetadata] = {}
        self._register_defaults()
        
    def _register_defaults(self):
        # Core Action Tools
        self.register(ToolMetadata(
            tool_name="claim_tracer",
            capabilities=["claim_validation", "evidence_strengthening"],
            cost="medium",
            risk="low",
            failure_modes=["Ambiguous claim"],
            preferred_when=["verifying explicit factual claims"],
            inputSchema={
                "type": "object",
                "properties": {"claim": {"type": "string"}},
                "required": ["claim"]
            }
        ))
        self.register(ToolMetadata(
            tool_name="citation_verifier",
            capabilities=["citation_check", "bibliography_validation"],
            cost="low",
            risk="low",
            failure_modes=["PDF not found", "Paywall"],
            preferred_when=["checking specific citation formats"],
            inputSchema={
                "type": "object",
                "properties": {"citation_text": {"type": "string"}},
                "required": ["citation_text"]
            }
        ))
        self.register(ToolMetadata(
            tool_name="manuscript_compiler",
            capabilities=["document_generation", "formatting"],
            cost="high",
            risk="low",
            failure_modes=["Missing sections"],
            preferred_when=["compiling final outputs"],
            inputSchema={
                "type": "object",
                "properties": {"sections": {"type": "array", "items": {"type": "string"}}},
                "required": ["sections"]
            }
        ))
        self.register(ToolMetadata(
            tool_name="dashboard_compiler",
            capabilities=["visualization", "dashboarding"],
            cost="medium",
            risk="low",
            failure_modes=["Data missing"],
            preferred_when=["generating interactive plots"],
            inputSchema={
                "type": "object",
                "properties": {"data_path": {"type": "string"}},
                "required": ["data_path"]
            }
        ))
        # Live Web Connectivity
        self.register(ToolMetadata(
            tool_name="literature_retrieval",
            capabilities=["literature_search", "live_web", "evidence_gathering"],
            cost="low",
            risk="low",
            failure_modes=["Rate limits", "Empty results", "Network error"],
            preferred_when=["searching live literature databases like Arxiv, PubMed, Crossref"],
            inputSchema={
                "type": "object",
                "properties": {"query": {"type": "string"}, "source": {"type": "string", "enum": ["crossref", "arxiv", "pubmed"]}},
                "required": ["query"]
            }
        ))

    def register(self, tool: ToolMetadata):
        self._tools[tool.tool_name] = tool
        
    def get_tool(self, tool_name: str) -> ToolMetadata:
        return self._tools.get(tool_name)
        
    def get_all(self) -> List[ToolMetadata]:
        return list(self._tools.values())
        
    def find_tools_by_capability(self, capability: str) -> List[ToolMetadata]:
        """Finds all tools that provide a specific capability."""
        matches = []
        for tool in self._tools.values():
            if capability in tool.capabilities:
                matches.append(tool)
        return matches
