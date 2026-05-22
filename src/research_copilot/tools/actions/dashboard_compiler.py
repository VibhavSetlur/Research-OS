import json
from pathlib import Path
from typing import Any, Dict, Optional


class DashboardCompiler:
    """Ephemeral UI Visualization Artifacts.
    
    Compiles self-contained JSON payloads or static HTML from Plotly/Altair.
    Allows IDE-native rendering via MCP resources/read protocol without
    the need for persistent background web servers.
    """

    def __init__(self, root: Optional[Path] = None):
        from research_copilot.utils.common import find_project_root
        self.root = root or find_project_root()
        
    def export_ephemeral_dashboard(self, dashboard_id: str, components: Dict[str, Any]) -> Path:
        """Export a dashboard to a self-contained JSON artifact.
        
        Args:
            dashboard_id: Unique identifier for this dashboard instance.
            components: Dictionary of plot definitions or JSON specifications.
            
        Returns:
            Path to the saved JSON artifact.
        """
        out_dir = self.root / "03_synthesis" / "ephemeral_dashboards"
        out_dir.mkdir(parents=True, exist_ok=True)
        
        out_path = out_dir / f"{dashboard_id}.json"
        
        payload = {
            "dashboard_id": dashboard_id,
            "type": "ephemeral_dashboard",
            "components": components,
        }
        
        with open(out_path, "w") as f:
            json.dump(payload, f, indent=2)
            
        return out_path
